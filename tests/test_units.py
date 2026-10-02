"""Small pure functions: periods, text, URL merging, CTR curve, candidate guards, site matching."""

import datetime as dt

from search_console_plugin.gsc_core import analysis as an
from search_console_plugin.gsc_core.api import _candidates
from search_console_plugin.gsc_core.periods import find_last_final, make_periods
from search_console_plugin.gsc_core.textnorm import detect_language, normalize_query


class Probe:
    def __init__(self, payload):
        self.payload = payload

    def search_analytics(self, site, body):
        assert body["dataState"] == "all" and body["dimensions"] == ["date"]
        return self.payload


TODAY = dt.date(2026, 10, 2)


def test_last_final_from_metadata():
    last, excluded, source = find_last_final(Probe({"metadata": {"firstIncompleteDate": "2026-09-30"}}), "s", TODAY)
    assert last == dt.date(2026, 9, 29) and excluded.start == dt.date(2026, 9, 30) and source == "metadata"


def test_last_final_without_marker_uses_rows_then_assumes_lag():
    last, excluded, source = find_last_final(Probe({"rows": [{"keys": ["2026-09-27"]}, {"keys": ["2026-09-28"]}]}),
                                             "s", TODAY)
    assert (last, excluded, source) == (dt.date(2026, 9, 28), None, "rows")
    last, excluded, source = find_last_final(Probe({}), "s", TODAY)
    assert last == dt.date(2026, 9, 29) and source == "assumed"


def test_periods_have_same_weekdays():
    p = make_periods(dt.date(2026, 9, 29), 7, None, "metadata")
    assert p.current.start.weekday() == p.previous.start.weekday()
    assert p.previous.end + dt.timedelta(days=1) == p.current.start


def test_japanese_normalisation():
    assert normalize_query("食パン　レシピ") == normalize_query("食パン レシピ") == normalize_query("食パン ﾚｼﾋﾟ")
    assert normalize_query("ﾊﾟﾝ  作り方") == "パン 作り方"
    assert detect_language([("食パン", 80), ("template", 20)]) == "ja"
    assert detect_language([("食パン", 10), ("template", 90)]) == "en"


def test_page_key_merges_spellings_only():
    assert an.page_key("https://www.example.jp/guide.html") == an.page_key("http://example.jp/guide/")
    assert an.page_key("https://example.jp/a/index.html") == an.page_key("https://example.jp/a/")
    assert an.page_key("https://example.jp/a") != an.page_key("https://example.jp/b")


def test_site_candidates():
    assert list(_candidates("example.com"))[0] == "sc-domain:example.com"
    assert list(_candidates("https://www.example.com"))[0] == "https://www.example.com/"
    assert "sc-domain:example.com" in list(_candidates("https://www.example.com/blog/post"))


def _m(clicks, impr, pos, name="x"):
    m = an.Metric()
    m.add({"clicks": clicks, "impressions": impr, "position": pos}, name)
    return m


def test_ctr_curve_needs_enough_data():
    thin = an.CtrCurve([{"a": _m(1, 10, 3.0)}])
    assert not thin.usable and thin.expected(3.0) is None
    curve = an.CtrCurve([{f"q{i}": _m(10, 100, 3.5) for i in range(3)}])
    assert abs(curve.expected(3.5) - 0.1) < 1e-9
    assert curve.expected(9.0) == curve.expected(3.5)  # nearest band with data


def test_zero_clicks_on_few_impressions_is_not_a_finding():
    curve = an.CtrCurve([{f"q{i}": _m(8, 100, 5.0) for i in range(3)}])  # 8% at position 4-5
    few = {"rare": _m(0, 20, 5.0)}  # expected 1.6 clicks: zero is ordinary chance
    many = {"real": _m(0, 80, 5.0)}  # expected 6.4 clicks: zero is a signal
    assert not an.find_candidates(few, {}, {}, {}, {}, curve, 10)
    assert [c.kind for c in an.find_candidates(many, {}, {}, {}, {}, curve, 10)] == ["title_snippet"]


def test_page_average_position_falling_from_growth_is_not_a_drop():
    prev = {"p": _m(3, 100, 3.0)}
    grew = {"p": _m(4, 400, 7.0)}  # shows for many new lower searches: growth, not a drop
    assert an.rank_changes(grew, prev, 10, kind="page")["losers"] == []
    assert an.rank_changes(grew, prev, 10, kind="query")["losers"]  # for one query it is a real drop


def test_pick_top_dedups_and_skips_tiny_gains():
    cands = [an.Candidate("title_snippet", 5, "q", "https://e.jp/a"),
             an.Candidate("rank_drop", 4, "q2", "https://e.jp/a.html"),  # same page, other spelling
             an.Candidate("striking_distance", 1, "q3", "https://e.jp/c"),  # below MIN_GAIN
             an.Candidate("index_issue", 0, page="https://e.jp/d", blocking=True)]
    top = an.pick_top(cands)
    assert [c.kind for c in top] == ["index_issue", "title_snippet"]


def test_anonymised_share():
    share = an.anonymized_share({"clicks": 100, "impressions": 1000}, {"a": _m(40, 600, 3)}, False)
    assert share == {"clicks": 0.6, "impressions": 0.4}
    assert an.anonymized_share({"clicks": 100, "impressions": 1000}, {}, True) is None
