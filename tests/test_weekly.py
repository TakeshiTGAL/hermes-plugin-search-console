"""End-to-end checks on recorded responses: the weekly check, the audit, rank changes and raw queries."""

import json

from helpers import FakeSession, SA, TODAY
from search_console_plugin.gsc_core import service
from search_console_plugin.gsc_core.api import Client


def run_weekly(client, **kw):
    return service.weekly(client, "example.jp", today=TODAY, **kw)


def test_unfinished_days_are_left_out_and_named(client):
    r = run_weekly(client)
    p = r["periods"]
    assert p["current"] == {"start": "2026-09-23", "end": "2026-09-29", "days": 7}
    assert p["previous"] == {"start": "2026-09-16", "end": "2026-09-22", "days": 7}
    assert p["excluded_unfinished"]["start"] == "2026-09-30"
    assert "9/30〜10/2 は Google がまだ集計中のため、比較から外しました" in r["message"]
    # every performance request for the comparison asked for finalised data only
    analytics = [b for m, u, b in client.session.log if "searchAnalytics" in u and b.get("dataState") != "all"]
    assert analytics and all(b["dataState"] == "final" and b["endDate"] <= "2026-09-29" for b in analytics)


def test_three_fixes_blocking_first_then_by_clicks(client):
    r = run_weekly(client)
    kinds = [f["kind"] for f in r["next_fixes"]]
    assert kinds == ["index_issue", "title_snippet", "rank_drop"]
    first = r["next_fixes"][0]
    assert first["page"] == "https://example.jp/old-campaign/" and first["problem"] == "noindex"
    assert r["next_fixes"][1]["query"] == "パン 作り方 初心者"
    assert r["next_fixes"][1]["page"] == "https://example.jp/guide/hajimete/"
    assert "■ 次に直す3件" in r["message"] and "1. インデックスから外れたページを戻す" in r["message"]


def test_moved_pages_are_not_reported_as_lost(client):
    r = run_weekly(client)
    # /recipes/shokupan -> .html is merged, not 'vanished'
    assert not any("shokupan" in x["url"] for x in r["index"]["pages_checked"])
    top = {x["page"]: x for x in r["top_pages"]}
    assert top["https://example.jp/recipes/shokupan.html"]["previous"]["clicks"] == 38
    # /about -> /company/ is a different URL; inspection shows Google moved it, so it is fine
    assert [m["url"] for m in r["index"]["moved"]] == ["https://example.jp/about"]
    assert all(f.get("page") != "https://example.jp/about" for f in r["next_fixes"])


def test_japanese_spelling_variants_are_merged(client):
    r = run_weekly(client)
    top = r["top_queries"][0]
    assert top["query"] == "食パン レシピ"
    assert top["clicks"] == 32 and top["impressions"] == 640  # half-width + full-width space rows


def test_language_auto_and_forced_english(client, make_client):
    assert run_weekly(client)["language"] == "ja"
    en = run_weekly(make_client(), language="en")
    assert en["message"].startswith("Search Console weekly check: sc-domain:example.jp")
    assert "Next 3 fixes" in en["message"] and "still being processed by Google" in en["message"]


def test_rank_drops_and_title_candidates_lists(client):
    r = run_weekly(client)
    assert r["rank_drops"][0]["key"] == "天然酵母 起こし方"
    assert r["impressions_up_clicks_flat"][0]["key"] == "パン 発酵 時間"


def test_message_fits_one_chat_message_and_request_budget(client):
    r = run_weekly(client)
    assert len(r["message"]) < 4096
    assert r["requests_used"] <= 15


def test_no_data_says_so_instead_of_inventing_fixes():
    empty = {"sites": {"siteEntry": [{"siteUrl": "sc-domain:new.example", "permissionLevel": "siteOwner"}]},
             "date_probe": {"rows": []}, "windows": {}, "sitemaps": {}, "inspections": {}}
    c = Client(SA, FakeSession(fixture=empty), sleep=lambda s: None)
    r = service.weekly(c, None, today=TODAY)
    assert r["next_fixes"] == []
    assert r["periods"]["how_last_final_was_found"] == "assumed"
    assert "Nothing to compare yet" in r["message"]


def test_audit_adds_deeper_lenses(client):
    r = service.audit(client, "sc-domain:example.jp", today=TODAY, days=7)
    for key in ("striking_distance", "cannibalization", "decaying_pages", "winners", "ctr_curve"):
        assert key in r
    assert any(c["query"] == "ホームベーカリー おすすめ 機種" for c in r["striking_distance"])
    assert r["message"].startswith("Search Console 点検（7日間）")


def test_rank_changes_explicit_window_past_final_is_noted(client):
    r = service.rank_changes(client, "example.jp", current_start="2026-09-23", current_end="2026-10-01",
                             previous_start="2026-09-16", previous_end="2026-09-22", today=TODAY)
    assert r["notes"] and "not final yet" in r["notes"][0]
    assert r["losers"][0]["key"] == "天然酵母 起こし方"


def test_query_tool_rows_and_anonymised_note(client):
    r = service.query(client, "example.jp", dimensions=["query"], row_limit=5, days=7, today=TODAY)
    assert r["row_count"] == 5 and set(r["rows"][0]) >= {"query", "clicks", "impressions", "ctr", "position"}
    assert any("anonymised" in n for n in r["notes"])
    json.dumps(r, ensure_ascii=False)
