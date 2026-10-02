"""The checks themselves: weekly check, audit, rank changes, raw query, URL inspection, sites."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from . import analysis as an
from . import render
from .api import Client
from .errors import GscError
from .periods import Periods, Window, explicit_periods, find_last_final, make_periods
from .textnorm import detect_language

DIMENSIONS = {"query", "page", "date", "country", "device", "searchAppearance"}
OPERATORS = {"equals", "notEquals", "contains", "notContains", "includingRegex", "excludingRegex"}
SEARCH_TYPES = {"web", "image", "video", "news", "discover", "googleNews"}
MAX_ROWS = 100_000


@dataclass
class WindowData:
    window: Window
    totals: dict
    queries: dict
    pages: dict
    query_page: dict
    truncated: bool


def _fetch(client: Client, site: str, window: Window, max_rows: int = MAX_ROWS) -> WindowData:
    base = dict(window.body(), dataState="final", type="web")
    totals = an.totals_dict(client.search_analytics(site, base).get("rows") or [])
    q_rows, _, t1 = client.search_analytics_all(site, dict(base, dimensions=["query"]), max_rows)
    p_rows, _, t2 = client.search_analytics_all(site, dict(base, dimensions=["page"]), max_rows)
    qp_rows, _, t3 = client.search_analytics_all(site, dict(base, dimensions=["query", "page"]), max_rows)
    return WindowData(window, totals, an.aggregate(q_rows), an.aggregate(p_rows, kind="page"),
                      an.top_page_for_query(qp_rows), t1 or t2 or t3)


def _language(requested: str | None, settings: dict, data: WindowData | None) -> str:
    lang = (requested or settings.get("language") or "auto").lower()
    if lang in ("en", "ja"):
        return lang
    if data is None:
        return "en"
    return detect_language((m.display, m.impressions) for m in data.queries.values())


def _delta(cur: dict, prev: dict) -> dict:
    out = {}
    for k in ("clicks", "impressions"):
        diff = cur[k] - prev[k]
        out[k] = {"change": diff, "pct": round(diff / prev[k], 3) if prev[k] else None}
    out["ctr"] = {"change": round(cur["ctr"] - prev["ctr"], 4)}
    out["position"] = {"change": round(cur["position"] - prev["position"], 1)}
    return out


def classify_inspection(url: str, status: dict, cur_pages: dict) -> tuple[str, str]:
    """('ok' | 'moved' | 'problem', short machine reason) from structured fields, never from the
    localised coverage text."""
    verdict = status.get("verdict", "")
    canonical = status.get("googleCanonical", "")
    if verdict == "PASS":
        return "ok", "indexed"
    if canonical and canonical != url and an.page_key(canonical) == an.page_key(url):
        return "ok", "same_page_other_spelling"
    if canonical and an.page_key(canonical) != an.page_key(url):
        target = cur_pages.get(an.page_key(canonical))
        if target and target.impressions > 0:
            return "moved", "google_uses_other_url"
        return "problem", "canonical_elsewhere_without_impressions"
    if status.get("robotsTxtState") == "DISALLOWED":
        return "problem", "blocked_by_robots_txt"
    if str(status.get("indexingState", "")).startswith("BLOCKED"):
        return "problem", "noindex"
    fetch = status.get("pageFetchState", "")
    if fetch and fetch != "SUCCESSFUL":
        return "problem", fetch.lower()
    return "problem", "not_indexed"


def _inspect_pages(client: Client, site: str, pages: list[tuple[str, an.Metric, str]], cur_pages: dict,
                   lang: str) -> dict:
    """URL Inspection for the pages worth checking. A refusal or quota stop leaves the rest as 'unchecked'
    (still reported), so a missing permission never hides a page that dropped out of search."""
    out = {"problems": [], "moved": [], "checked": [], "unchecked": [], "notes": []}
    for i, (url, before, why) in enumerate(pages):
        try:
            res = client.inspect(site, url, lang)
        except GscError as exc:
            # 403/404 = permission; 429 = daily quota; anything else (a 400 for a URL outside the
            # property, a 5xx, a network error) is a failed check, not a reason to change permissions.
            # A 400 is not necessarily temporary, so the report words it separately.
            code = {"no_access": "inspection_refused",
                    "quota_exceeded": "inspection_quota"}.get(exc.code, "inspection_failed")
            out["notes"].append({"code": code, "error": exc.code, "detail": exc.message})
            out["unchecked"] = [{"url": u, "why": w, "clicks_before": int(m.clicks),
                                 "impressions_before": int(m.impressions)} for u, m, w in pages[i:]]
            break
        status = res.get("indexStatusResult") or {}
        state, reason = classify_inspection(url, status, cur_pages)
        item = {
            "url": url,
            "why_checked": why,
            "state": state,
            "problem": reason if state == "problem" else "",
            "verdict": status.get("verdict", ""),
            "coverage": status.get("coverageState", ""),
            "indexing_state": status.get("indexingState", ""),
            "robots_txt": status.get("robotsTxtState", ""),
            "page_fetch": status.get("pageFetchState", ""),
            "last_crawl": status.get("lastCrawlTime", ""),
            "google_canonical": status.get("googleCanonical", ""),
            "user_canonical": status.get("userCanonical", ""),
            "clicks_before": int(before.clicks),
            "impressions_before": int(before.impressions),
        }
        out["checked"].append(item)
        if state == "problem":
            out["problems"].append(item)
        elif state == "moved":
            out["moved"].append(item)
    return out


def _sitemaps(client: Client, site: str) -> dict:
    try:
        maps = client.sitemaps(site)
    except GscError as exc:
        return {"checked": False, "note": exc.message}
    issues = []
    for m in maps:
        errors, warnings = int(m.get("errors", 0) or 0), int(m.get("warnings", 0) or 0)
        if errors or warnings:
            issues.append({"path": m.get("path", ""), "errors": errors, "warnings": warnings,
                           "last_downloaded": m.get("lastDownloaded", "")})
    return {"checked": True, "submitted": len(maps), "with_issues": issues}


def _vanished_pages(cur_pages: dict, prev_pages: dict, floor: int, limit: int) -> list[tuple[str, an.Metric]]:
    """Pages (URL spellings merged) that had real impressions before and none now."""
    gone = [(k, m) for k, m in prev_pages.items() if m.impressions >= floor and k not in cur_pages]
    gone.sort(key=lambda t: (t[1].clicks, t[1].impressions), reverse=True)
    return gone[:limit]


def _top_items(metrics: dict, prev: dict, limit: int, label: str) -> list[dict]:
    items = sorted(metrics.items(), key=lambda kv: (kv[1].clicks, kv[1].impressions), reverse=True)[:limit]
    out = []
    for key, m in items:
        p = prev.get(key)
        d = {label: m.display, **m.to_dict()}
        if p:
            d["previous"] = p.to_dict()
        out.append(d)
    return out


def _periods_for(client: Client, site: str, days: int, today: dt.date | None) -> Periods:
    last_final, excluded, source = find_last_final(client, site, today)
    return make_periods(last_final, days, excluded, source)


def _check(client: Client, site: str | None, days: int, settings: dict, language: str | None,
           today: dt.date | None, deep: bool) -> dict:
    site = client.resolve_site(site, settings.get("default_site"))
    periods = _periods_for(client, site, days, today)
    cur = _fetch(client, site, periods.current)
    prev = _fetch(client, site, periods.previous)
    lang = _language(language, settings, cur if cur.queries else prev)
    floor = an.min_impressions(cur.totals["impressions"], days)
    curve = an.CtrCurve([cur.queries, prev.queries])

    vanished = [(m.display, m, "vanished") for _, m in _vanished_pages(cur.pages, prev.pages, floor, 5 if deep else 3)]
    if deep:  # also look at the pages losing the most clicks
        decaying = sorted(((k, m) for k, m in prev.pages.items() if k in cur.pages
                           and cur.pages[k].clicks <= 0.7 * m.clicks and m.clicks >= 5),
                          key=lambda t: t[1].clicks - cur.pages[t[0]].clicks, reverse=True)
        vanished += [(cur.pages[k].display, m, "decaying") for k, m in decaying][: max(0, 5 - len(vanished))]
    inspected = _inspect_pages(client, site, vanished, cur.pages, lang)
    problems, moved, checked, notes = (inspected["problems"], inspected["moved"], inspected["checked"],
                                       inspected["notes"])
    sitemaps = _sitemaps(client, site)

    page_curve = an.CtrCurve([cur.pages, prev.pages])
    cands = an.find_candidates(cur.queries, prev.queries, cur.pages, prev.pages, cur.query_page, curve, floor,
                               problems, include_page_decay=deep, page_curve=page_curve,
                               unchecked=[u for u in inspected["unchecked"] if u["why"] == "vanished"])
    fixes = an.pick_top(cands, 3)
    changes = an.rank_changes(cur.queries, prev.queries, floor, limit=10 if deep else 5)
    page_changes = an.rank_changes(cur.pages, prev.pages, floor, limit=10 if deep else 5, kind="page")

    result = {
        "site_url": site,
        "language": lang,
        "periods": periods.to_dict(),
        "totals": {"current": cur.totals, "previous": prev.totals, "change": _delta(cur.totals, prev.totals)},
        "anonymized_share": an.anonymized_share(cur.totals, cur.queries, cur.truncated),
        "noise_floor_impressions": floor,
        "next_fixes": [c.to_dict() for c in fixes],
        "top_queries": _top_items(cur.queries, prev.queries, 10 if deep else 5, "query"),
        "top_pages": _top_items(cur.pages, prev.pages, 10 if deep else 5, "page"),
        "rank_drops": changes["losers"],
        "rank_drops_pages": page_changes["losers"],
        "impressions_up_clicks_flat": an.impressions_up_clicks_flat(cur.queries, prev.queries, floor)[: 10 if deep else 5],
        "impressions_up_clicks_flat_pages":
            an.impressions_up_clicks_flat(cur.pages, prev.pages, floor)[: 10 if deep else 5],
        "index": {"pages_checked": checked, "problems": problems, "moved": moved,
                  "unchecked": inspected["unchecked"], "sitemaps": sitemaps,
                  "vanished_pages": len(_vanished_pages(cur.pages, prev.pages, floor, 10_000))},
        "notes": notes,
        "data_truncated": cur.truncated or prev.truncated,
        "requests_used": client.calls,
    }
    if deep:
        by_kind = lambda k: [c.to_dict() for c in sorted(cands, key=lambda c: -c.gain) if c.kind == k][:10]
        result.update({
            "ctr_anomalies": by_kind("title_snippet"),
            "striking_distance": by_kind("striking_distance"),
            "cannibalization": by_kind("cannibalization"),
            "decaying_pages": by_kind("decaying_page"),
            "winners": changes["winners"],
            "ctr_curve": curve.to_dict(),
            "ctr_curve_pages": page_curve.to_dict(),
        })
    result["message"] = render.report(result, lang, deep=deep)
    return result


def weekly(client: Client, site: str | None = None, settings: dict | None = None, language: str | None = None,
           today: dt.date | None = None) -> dict:
    """Last finished 7 days vs the 7 before: totals, rank drops, title candidates, index problems, 3 fixes."""
    return _check(client, site, 7, settings or {}, language, today, deep=False)


def audit(client: Client, site: str | None = None, settings: dict | None = None, language: str | None = None,
          days: int = 28, today: dt.date | None = None) -> dict:
    """Deeper audit over 28 days (or ``days``): adds striking distance, cannibalisation, decaying pages."""
    days = max(7, min(int(days or 28), 90))
    return _check(client, site, days, settings or {}, language, today, deep=True)


def rank_changes(client: Client, site: str | None = None, settings: dict | None = None, days: int = 28,
                 dimension: str = "query", current_start: str | None = None, current_end: str | None = None,
                 previous_start: str | None = None, previous_end: str | None = None, limit: int = 10,
                 today: dt.date | None = None) -> dict:
    settings = settings or {}
    if dimension not in ("query", "page"):
        raise GscError("bad_argument", "dimension must be 'query' or 'page'.", "Use dimension='query' or 'page'.")
    site = client.resolve_site(site, settings.get("default_site"))
    last_final, excluded, source = find_last_final(client, site, today)
    notes = []
    if current_start and current_end:
        try:
            periods = explicit_periods(current_start, current_end, previous_start, previous_end, last_final, excluded,
                                       source)
        except ValueError as exc:
            raise GscError("bad_argument", f"Bad date: {exc}", "Use YYYY-MM-DD dates.") from None
        if periods.current.end > last_final:
            notes.append(f"Days after {last_final.isoformat()} are not final yet and return no data in this "
                         "comparison; the current window is effectively shorter.")
    else:
        periods = make_periods(last_final, max(1, min(int(days or 28), 90)), excluded, source)
    cur = _fetch(client, site, periods.current)
    prev = _fetch(client, site, periods.previous)
    floor = an.min_impressions(cur.totals["impressions"], periods.current.days)
    cur_m = cur.queries if dimension == "query" else cur.pages
    prev_m = prev.queries if dimension == "query" else prev.pages
    changes = an.rank_changes(cur_m, prev_m, floor, limit=max(1, min(int(limit or 10), 50)), kind=dimension)
    return {"site_url": site, "dimension": dimension, "periods": periods.to_dict(),
            "totals": {"current": cur.totals, "previous": prev.totals}, "noise_floor_impressions": floor,
            **changes, "notes": notes, "requests_used": client.calls}


def query(client: Client, site: str | None = None, settings: dict | None = None, start_date: str | None = None,
          end_date: str | None = None, days: int = 28, dimensions: list | None = None, filters: list | None = None,
          row_limit: int = 100, data_state: str = "final", search_type: str = "web",
          today: dt.date | None = None) -> dict:
    settings = settings or {}
    dims = [d for d in (dimensions or ["query"])]
    bad = [d for d in dims if d not in DIMENSIONS]
    if bad:
        raise GscError("bad_argument", f"Unknown dimension(s): {', '.join(bad)}.",
                       "Use any of: " + ", ".join(sorted(DIMENSIONS)))
    if search_type not in SEARCH_TYPES:
        raise GscError("bad_argument", f"Unknown search_type {search_type!r}.", "Use one of: " + ", ".join(sorted(SEARCH_TYPES)))
    if data_state not in ("final", "all"):
        raise GscError("bad_argument", "data_state must be 'final' or 'all'.", "Use 'final' (default) or 'all'.")
    site = client.resolve_site(site, settings.get("default_site"))
    last_final, excluded, _ = find_last_final(client, site, today)
    notes = []
    if not (start_date and end_date):
        window = Window(last_final - dt.timedelta(days=max(1, min(int(days or 28), 480)) - 1), last_final)
    else:
        try:
            window = Window(dt.date.fromisoformat(start_date), dt.date.fromisoformat(end_date))
        except ValueError:
            raise GscError("bad_argument", "Dates must be YYYY-MM-DD.", "Example: 2026-09-01") from None
        if window.end > last_final:
            notes.append(f"{(last_final + dt.timedelta(days=1)).isoformat()} onward is not final yet"
                         + (" and is left out (data_state=final)." if data_state == "final"
                            else "; those numbers will still rise."))
    body = dict(window.body(), dimensions=dims, dataState=data_state, type=search_type)
    group = []
    for f in filters or []:
        if not isinstance(f, dict) or f.get("dimension") not in DIMENSIONS - {"date"} \
                or f.get("operator", "contains") not in OPERATORS or not f.get("expression"):
            raise GscError("bad_argument", f"Bad filter {f!r}.",
                           "Filters look like {'dimension': 'page', 'operator': 'contains', 'expression': '/blog/'}.")
        group.append({"dimension": f["dimension"], "operator": f.get("operator", "contains"),
                      "expression": str(f["expression"])})
    if group:
        body["dimensionFilterGroups"] = [{"groupType": "and", "filters": group}]
    limit = max(1, min(int(row_limit or 100), MAX_ROWS))
    rows, metadata, truncated = client.search_analytics_all(site, body, limit)
    out_rows = [dict(zip(dims, r.get("keys") or []), clicks=int(r.get("clicks", 0)),
                     impressions=int(r.get("impressions", 0)), ctr=round(float(r.get("ctr", 0)), 4),
                     position=round(float(r.get("position", 0)), 1)) for r in rows[:limit]]
    if "query" in dims:
        notes.append("Rows with the query dimension leave out anonymised queries, so they add up to less than "
                     "the site total.")
    return {"site_url": site, "window": window.to_dict(), "dimensions": dims, "data_state": data_state,
            "search_type": search_type, "rows": out_rows, "row_count": len(out_rows),
            "more_rows_available": truncated, "first_incomplete_date": (metadata or {}).get("firstIncompleteDate"),
            "notes": notes, "requests_used": client.calls}


def inspect_url(client: Client, url: str, site: str | None = None, settings: dict | None = None,
                language: str | None = None) -> dict:
    if not url or not url.startswith(("http://", "https://")):
        raise GscError("bad_argument", "url must be a full page address starting with https://.",
                       "Example: https://example.com/pricing/")
    settings = settings or {}
    site = client.resolve_site(site or url, settings.get("default_site") if not site else None)
    lang = (language or settings.get("language") or "en").lower()
    res = client.inspect(site, url, "ja" if lang == "ja" else "en")
    status = res.get("indexStatusResult") or {}
    return {"site_url": site, "url": url, "verdict": status.get("verdict", ""),
            "coverage": status.get("coverageState", ""), "indexing_state": status.get("indexingState", ""),
            "robots_txt": status.get("robotsTxtState", ""), "page_fetch": status.get("pageFetchState", ""),
            "last_crawl": status.get("lastCrawlTime", ""), "crawled_as": status.get("crawledAs", ""),
            "google_canonical": status.get("googleCanonical", ""), "user_canonical": status.get("userCanonical", ""),
            "sitemaps": status.get("sitemap", []), "referring_urls": (status.get("referringUrls") or [])[:5],
            "inspection_link": res.get("inspectionResultLink", ""), "requests_used": client.calls}


def sites(client: Client) -> dict:
    entries = client.sites()
    readable = [{"site_url": s["siteUrl"], "permission": s.get("permissionLevel", "")}
                for s in entries if s.get("permissionLevel") != "siteUnverifiedUser"]
    out = {"credential": client.identity.describe(), "properties": readable}
    if not readable:
        who = client.identity.email or "the authorized Google account"
        out["fix"] = ("No property is shared with this key yet. In Search Console open the property → Settings → "
                      f"Users and permissions → Add user → {who} → permission Restricted or Full.")
    return out
