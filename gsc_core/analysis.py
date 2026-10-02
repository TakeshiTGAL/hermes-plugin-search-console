"""Turning two windows of Search Console rows into a short list of things worth fixing.

The audit lenses (CTR anomalies, striking distance 8-20, decaying pages, cannibalisation, winners /
losers / new / lost, losers ranked by clicks lost) follow Ryze AI's open-seo-mcp-skills (MIT); see
NOTICE. What is added here: an expected-CTR curve learned from the site's own data instead of a
fixed threshold, a rough "clicks at stake" estimate so candidates of different kinds can be ranked
against each other, and merging of query spellings that differ only in width or spacing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .textnorm import normalize_query

# Position buckets for the site's own CTR curve.
_BUCKETS = [(1, 2), (2, 3), (3, 4), (4, 6), (6, 8), (8, 11), (11, 16), (16, 21), (21, 1e9)]
_MIN_BUCKET_IMPRESSIONS = 50
_MIN_BUCKET_QUERIES = 3
# A CTR shortfall only counts when the typical CTR would have produced at least this many clicks;
# below that, zero clicks is ordinary chance (P(0 | mean 3) is about 5%).
MIN_EXPECTED_CLICKS = 3.0
# A fix has to be worth at least this many clicks per period to take one of the three slots.
MIN_GAIN = 2.0


@dataclass
class Metric:
    clicks: float = 0.0
    impressions: float = 0.0
    pos_sum: float = 0.0  # impressions-weighted position sum
    display: str = ""
    _display_impr: float = -1.0
    variants: int = 0

    def add(self, row: dict, display: str) -> None:
        impr = float(row.get("impressions", 0))
        self.clicks += float(row.get("clicks", 0))
        self.impressions += impr
        self.pos_sum += float(row.get("position", 0)) * impr
        self.variants += 1
        if impr > self._display_impr:
            self.display, self._display_impr = display, impr

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0

    @property
    def position(self) -> float:
        return self.pos_sum / self.impressions if self.impressions else 0.0

    def to_dict(self) -> dict:
        return {
            "clicks": int(round(self.clicks)),
            "impressions": int(round(self.impressions)),
            "ctr": round(self.ctr, 4),
            "position": round(self.position, 1),
        }


def page_key(url: str) -> str:
    """One key for the spellings of one page, so a move from /guide to /guide.html (or http→https,
    www→bare, adding a trailing slash) is compared as the same page instead of 'lost' + 'new'."""
    u = (url or "").strip()
    low = u.lower()
    for prefix in ("https://", "http://"):
        if low.startswith(prefix):
            u, low = u[len(prefix):], low[len(prefix):]
            break
    host, _, rest = u.partition("/")
    host = host.lower()
    host = host[4:] if host.startswith("www.") else host
    path = rest.split("#", 1)[0]
    for suffix in ("index.html", "index.htm", ".html", ".htm"):
        if path.lower().endswith(suffix):
            path = path[: -len(suffix)]
            break
    return f"{host}/{path.rstrip('/')}"


def aggregate(rows: list[dict], index: int = 0, kind: str = "query") -> dict[str, Metric]:
    keyfn = normalize_query if kind == "query" else page_key
    out: dict[str, Metric] = {}
    for row in rows:
        keys = row.get("keys") or []
        if len(keys) <= index:
            continue
        raw = keys[index]
        out.setdefault(keyfn(raw), Metric()).add(row, raw)
    return out


def top_page_for_query(query_page_rows: list[dict]) -> dict[str, tuple[str, dict[str, float]]]:
    """normalised query -> (page URL with most impressions, {page URL: impressions}), URL spellings merged."""
    per: dict[str, dict[str, Metric]] = {}
    for row in query_page_rows:
        keys = row.get("keys") or []
        if len(keys) < 2:
            continue
        per.setdefault(normalize_query(keys[0]), {}).setdefault(page_key(keys[1]), Metric()).add(row, keys[1])
    out = {}
    for q, pages in per.items():
        flat = {m.display: m.impressions for m in pages.values()}
        out[q] = (max(flat, key=flat.get), flat)
    return out


class CtrCurve:
    """Expected CTR by position, learned from this site's own queries."""

    def __init__(self, metrics: list[dict[str, Metric]]):
        clicks = [0.0] * len(_BUCKETS)
        impr = [0.0] * len(_BUCKETS)
        count = [0] * len(_BUCKETS)
        for group in metrics:
            for m in group.values():
                if m.impressions <= 0:
                    continue
                i = _bucket(m.position)
                clicks[i] += m.clicks
                impr[i] += m.impressions
                count[i] += 1
        self.values: list[float | None] = [
            (clicks[i] / impr[i]) if impr[i] >= _MIN_BUCKET_IMPRESSIONS and count[i] >= _MIN_BUCKET_QUERIES else None
            for i in range(len(_BUCKETS))
        ]

    @property
    def usable(self) -> bool:
        return any(v is not None for v in self.values[:6])

    def expected(self, position: float) -> float | None:
        i = _bucket(position)
        if self.values[i] is not None:
            return self.values[i]
        # Nearest bucket with data, preferring the worse-ranked side (a conservative estimate).
        for step in range(1, len(_BUCKETS)):
            for j in (i + step, i - step):
                if 0 <= j < len(_BUCKETS) and self.values[j] is not None:
                    return self.values[j]
        return None

    def to_dict(self) -> list[dict]:
        out = []
        for (lo, hi), v in zip(_BUCKETS, self.values):
            label = f"{lo}-{hi - 1 if hi < 1e8 else '+'}" if hi - lo > 1 else f"{lo}"
            out.append({"positions": label, "ctr": None if v is None else round(v, 4)})
        return out


def _bucket(position: float) -> int:
    for i, (lo, hi) in enumerate(_BUCKETS):
        if lo <= position < hi:
            return i
    return 0 if position < 1 else len(_BUCKETS) - 1


def min_impressions(total_impressions: float, days: int) -> int:
    """Noise floor for 'this query matters': scales with the site, never below 10 a week."""
    base = 10 if days <= 7 else 30
    return max(base, int(math.ceil(total_impressions * 0.002)))


@dataclass
class Candidate:
    kind: str  # index_issue | title_snippet | rank_drop | striking_distance | cannibalization | decaying_page
    gain: float  # rough extra clicks per window if fixed
    query: str = ""
    page: str = ""
    cur: dict = field(default_factory=dict)
    prev: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)
    blocking: bool = False

    def to_dict(self) -> dict:
        out = {"kind": self.kind, "estimated_extra_clicks": round(self.gain, 1)}
        for key in ("query", "page"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.cur:
            out["current"] = self.cur
        if self.prev:
            out["previous"] = self.prev
        if self.facts:
            out.update(self.facts)
        return out


def _page_avg_artifact(c: Metric, p: Metric) -> bool:
    """A page's average position falls when it starts showing for many new, lower-ranked searches.
    That is growth, not a drop: impressions up by half or more while clicks did not fall."""
    return c.impressions >= 1.5 * p.impressions and c.clicks >= p.clicks


def rank_changes(cur: dict[str, Metric], prev: dict[str, Metric], floor: int, limit: int = 10,
                 kind: str = "query") -> dict:
    """Winners / losers / new / lost, as in the precursor's rank-tracking skill."""
    winners, losers, new, lost = [], [], [], []
    for key in set(cur) | set(prev):
        c, p = cur.get(key), prev.get(key)
        if c and p:
            if max(c.impressions, p.impressions) < floor:
                continue
            delta = c.position - p.position
            item = {"key": c.display or p.display, "position_before": round(p.position, 1),
                    "position_after": round(c.position, 1), "clicks_before": int(p.clicks),
                    "clicks_after": int(c.clicks), "impressions_before": int(p.impressions),
                    "impressions_after": int(c.impressions)}
            if _dropped(p.position, c.position):
                if kind == "page" and _page_avg_artifact(c, p):
                    continue
                losers.append(item)
            elif delta <= -2 or (p.position <= 10 and delta <= -1 and c.position <= 3):
                winners.append(item)
        elif c and c.impressions >= floor:
            new.append({"key": c.display, "position_after": round(c.position, 1), "clicks_after": int(c.clicks),
                        "impressions_after": int(c.impressions)})
        elif p and p.impressions >= floor:
            lost.append({"key": p.display, "position_before": round(p.position, 1), "clicks_before": int(p.clicks),
                         "impressions_before": int(p.impressions)})
    # Losers by clicks lost first (a 4→7 drop on a money query beats a 40→80 crash on a nothing query).
    losers.sort(key=lambda x: (x["clicks_before"] - x["clicks_after"], x["impressions_before"]), reverse=True)
    winners.sort(key=lambda x: (x["clicks_after"] - x["clicks_before"], x["impressions_after"]), reverse=True)
    new.sort(key=lambda x: x["impressions_after"], reverse=True)
    lost.sort(key=lambda x: (x["clicks_before"], x["impressions_before"]), reverse=True)
    return {"winners": winners[:limit], "losers": losers[:limit], "new": new[:limit], "lost": lost[:limit],
            "counts": {"winners": len(winners), "losers": len(losers), "new": len(new), "lost": len(lost)}}


def _dropped(before: float, after: float) -> bool:
    if before > 20:
        return False
    delta = after - before
    return delta >= 2 or (before <= 3 and delta >= 1)


def impressions_up_clicks_flat(cur: dict[str, Metric], prev: dict[str, Metric], floor: int) -> list[dict]:
    out = []
    for key, c in cur.items():
        p = prev.get(key)
        if not p or c.impressions < floor or c.position > 20:
            continue
        grew = c.impressions - p.impressions
        if grew >= floor and c.impressions >= p.impressions * 1.3 and c.clicks <= p.clicks:
            out.append((key, c, p))
    out.sort(key=lambda t: t[1].impressions - t[2].impressions, reverse=True)
    return [{"key": c.display, "impressions_before": int(p.impressions), "impressions_after": int(c.impressions),
             "clicks_before": int(p.clicks), "clicks_after": int(c.clicks), "position_after": round(c.position, 1)}
            for key, c, p in out]


def _metric_candidates(cur: dict[str, Metric], prev: dict[str, Metric], curve: CtrCurve, floor: int,
                       scope: str, page_for) -> list[Candidate]:
    """Title / rank-drop / striking-distance candidates for one level (queries or pages)."""
    out: list[Candidate] = []

    def make(kind, gain, key, c, p, facts=None):
        facts = dict(facts or {}, scope=scope)
        if scope == "query":
            return Candidate(kind, gain, c.display if c else p.display, page_for(key),
                             c.to_dict() if c else {}, p.to_dict() if p else {}, facts)
        return Candidate(kind, gain, "", (c or p).display, c.to_dict() if c else {}, p.to_dict() if p else {}, facts)

    for key, c in cur.items():
        p = prev.get(key)
        exp = curve.expected(c.position)
        # A. good position, CTR far below what this site usually gets there → title/description.
        if c.impressions >= floor and c.position <= 10:
            if exp is not None and c.ctr < 0.5 * exp and c.impressions * exp >= MIN_EXPECTED_CLICKS:
                out.append(make("title_snippet", c.impressions * (exp - c.ctr), key, c, p, {"typical_ctr": round(exp, 4)}))
                continue
            if exp is None and c.position <= 5 and c.ctr < 0.02 and c.impressions * 0.02 >= MIN_EXPECTED_CLICKS:
                # precursor's fixed rule (position <= 5, CTR < 2%) when the site has too little data for a curve
                out.append(make("title_snippet", c.impressions * (0.02 - c.ctr), key, c, p, {"typical_ctr": 0.02}))
                continue
        # A'. impressions grew a lot but clicks did not → the snippet is not winning the new searches.
        if p and c.impressions >= floor and c.position <= 20 and c.impressions - p.impressions >= floor \
                and c.impressions >= p.impressions * 1.3 and c.clicks <= p.clicks:
            base_ctr = p.ctr if p.ctr > 0 else (exp or 0.0)
            gain = c.impressions * base_ctr - c.clicks
            if gain > 0 and c.impressions * base_ctr >= MIN_EXPECTED_CLICKS:
                out.append(make("title_snippet", gain, key, c, p,
                                {"typical_ctr": round(base_ctr, 4), "reason": "impressions_up_clicks_flat"}))
                continue
        # B. rank drop on something that mattered.
        if p and p.impressions >= floor and _dropped(p.position, c.position) \
                and not (scope == "page" and _page_avg_artifact(c, p)):
            e_before, e_after = curve.expected(p.position), curve.expected(c.position)
            modelled = p.impressions * (e_before - e_after) if e_before is not None and e_after is not None else 0
            gain = max(p.clicks - c.clicks, modelled, 0.0)
            if gain > 0:
                out.append(make("rank_drop", gain, key, c, p))
                continue
        # C. striking distance: 8-20, one push from the top of page 1.
        if 8 <= c.position <= 20 and c.impressions >= 2 * floor:
            target = curve.expected(4.5)
            if target is not None and target > c.ctr:
                gain = 0.25 * c.impressions * (target - c.ctr)  # discounted: moving up takes work and may fail
                out.append(make("striking_distance", gain, key, c, p, {"typical_ctr_top5": round(target, 4)}))

    if scope == "query":  # queries that vanished entirely after ranking on page 1-2
        for key, p in prev.items():
            if key not in cur and p.impressions >= floor and p.position <= 20 and p.clicks > 0:
                out.append(make("rank_drop", p.clicks, key, None, p, {"reason": "disappeared"}))
    return out


def find_candidates(cur_q: dict[str, Metric], prev_q: dict[str, Metric], cur_pages: dict[str, Metric],
                    prev_pages: dict[str, Metric], query_page: dict, curve: CtrCurve, floor: int,
                    index_findings: list[dict] | None = None, include_page_decay: bool = False,
                    page_curve: CtrCurve | None = None, unchecked: list[dict] | None = None) -> list[Candidate]:
    """Query-level and page-level candidates. Page level matters on small sites, where most clicks
    come from anonymised queries that never appear as query rows, but every page row is complete."""
    cands: list[Candidate] = []

    def page_for(key: str) -> str:
        hit = query_page.get(key)
        return hit[0] if hit else ""

    for f in index_findings or []:
        lost = float(f.get("clicks_before", 0))
        # First place only when it actually cost clicks; a page excluded on purpose with no clicks
        # stays in the Indexing list without pushing real fixes out of the top three.
        cands.append(Candidate("index_issue", gain=lost, page=f["url"],
                               facts={"coverage": f.get("coverage", ""), "verdict": f.get("verdict", ""),
                                      "problem": f.get("problem", ""),
                                      "google_canonical": f.get("google_canonical", ""),
                                      "impressions_before": f.get("impressions_before", 0)},
                               blocking=lost >= MIN_GAIN))
    for u in unchecked or []:  # URL Inspection unavailable: still worth a look, ranked by clicks lost
        cands.append(Candidate("index_unchecked", gain=float(u.get("clicks_before", 0)), page=u["url"],
                               facts={"impressions_before": u.get("impressions_before", 0)}))

    cands += _metric_candidates(cur_q, prev_q, curve, floor, "query", page_for)
    cands += _metric_candidates(cur_pages, prev_pages, page_curve or CtrCurve([cur_pages, prev_pages]), floor,
                                "page", page_for)

    # E. cannibalisation: two or more pages split the same query.
    for key, (_, pages) in query_page.items():
        c = cur_q.get(key)
        if not c or c.impressions < 2 * floor or c.position <= 3:
            continue
        total = sum(pages.values())
        split = sorted((u for u, v in pages.items() if total and v / total >= 0.2), key=lambda u: -pages[u])
        if len(split) >= 2:
            target = curve.expected(max(1.0, c.position - 2)) or c.ctr
            gain = 0.3 * c.impressions * max(target - c.ctr, 0)
            cands.append(Candidate("cannibalization", gain, c.display, split[0], c.to_dict(), {},
                                   {"competing_pages": split[:3], "scope": "query"}))

    if include_page_decay:
        for key, p in prev_pages.items():
            c = cur_pages.get(key)
            now = c.clicks if c else 0.0
            if p.clicks >= max(5, floor / 10) and now <= 0.7 * p.clicks:
                cands.append(Candidate("decaying_page", p.clicks - now, page=(c or p).display,
                                       cur=c.to_dict() if c else {}, prev=p.to_dict(), facts={"scope": "page"}))
    return cands


def pick_top(cands: list[Candidate], n: int = 3) -> list[Candidate]:
    """Blocking problems first, then by clicks at stake; one entry per page and per query."""
    ordered = sorted(cands, key=lambda c: (not c.blocking, -c.gain))
    out, pages, queries = [], set(), set()
    for c in ordered:
        if c.gain < MIN_GAIN and not c.blocking:
            continue
        nq = normalize_query(c.query) if c.query else ""
        pk = page_key(c.page) if c.page else ""
        if (pk and pk in pages) or (nq and nq in queries):
            continue
        out.append(c)
        if pk:
            pages.add(pk)
        if nq:
            queries.add(nq)
        if len(out) == n:
            break
    return out


def totals_dict(rows: list[dict]) -> dict:
    r = rows[0] if rows else {}
    return {"clicks": int(r.get("clicks", 0)), "impressions": int(r.get("impressions", 0)),
            "ctr": round(float(r.get("ctr", 0.0)), 4), "position": round(float(r.get("position", 0.0)), 1)}


def anonymized_share(totals: dict, queries: dict[str, Metric], truncated: bool) -> dict | None:
    """Share of clicks/impressions that Search Console hides as anonymised queries."""
    if truncated or not totals.get("impressions"):
        return None
    qc = sum(m.clicks for m in queries.values())
    qi = sum(m.impressions for m in queries.values())
    clicks = totals["clicks"]
    return {
        "clicks": round(max(0.0, 1 - qc / clicks), 3) if clicks else 0.0,
        "impressions": round(max(0.0, 1 - qi / totals["impressions"]), 3),
    }
