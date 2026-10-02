"""Branches the main scenarios do not reach: inspection outcomes, paging, CLI, rendering limits."""

import json
import os
import types
import urllib.parse

import pytest

from helpers import SA, TODAY, FakeSession, Resp
from search_console_plugin import cli, tools
from search_console_plugin.gsc_core import api, auth, render, schedule, service
from search_console_plugin.gsc_core.analysis import Metric
from search_console_plugin.gsc_core.api import Client
from search_console_plugin.gsc_core.errors import GscError, message_language


def _cur(**pages):
    out = {}
    for key, impr in pages.items():
        m = Metric()
        m.add({"clicks": 1, "impressions": impr, "position": 3}, key)
        out[key] = m
    return out


@pytest.mark.parametrize("status, cur, expected", [
    ({"verdict": "PASS"}, {}, ("ok", "indexed")),
    ({"verdict": "NEUTRAL", "robotsTxtState": "DISALLOWED"}, {}, ("problem", "blocked_by_robots_txt")),
    ({"verdict": "FAIL", "pageFetchState": "NOT_FOUND"}, {}, ("problem", "not_found")),
    ({"verdict": "NEUTRAL", "googleCanonical": "https://e.jp/b/"}, {}, ("problem", "canonical_elsewhere_without_impressions")),
    ({"verdict": "NEUTRAL", "googleCanonical": "https://e.jp/b/"}, {"e.jp/b": 50}, ("moved", "google_uses_other_url")),
    ({"verdict": "NEUTRAL", "googleCanonical": "https://e.jp/a.html"}, {}, ("ok", "same_page_other_spelling")),
    ({"verdict": "NEUTRAL", "pageFetchState": "SUCCESSFUL"}, {}, ("problem", "not_indexed")),
])
def test_inspection_is_classified_from_structured_fields(status, cur, expected):
    assert service.classify_inspection("https://e.jp/a", status, _cur(**cur)) == expected


def test_problem_phrases_are_localised():
    item = {"problem": "blocked_by_robots_txt"}
    assert render.problem_text(item, "ja") == "robots.txt でブロックされている"
    assert render.problem_text({"problem": "soft_404", "page_fetch": "SOFT_404"}, "en") == \
        "Google could not fetch it (soft 404)"
    # Google's enum values never reach a Japanese report as they are.
    assert render.problem_text({"problem": "not_found"}, "ja") == "Google がページを取得できない（ページが見つからない（404））"
    assert render.problem_text({"problem": "not_indexed", "verdict": "NEUTRAL"}, "ja") == \
        "インデックスに登録されていない（除外）"
    assert render.problem_text({"problem": "not_indexed"}, "ja") == "インデックスに登録されていない"


def test_paging_past_the_page_size(monkeypatch, client):
    monkeypatch.setattr(api, "MAX_ROWS_PER_PAGE", 4)
    body = {"startDate": "2026-09-23", "endDate": "2026-09-29", "dimensions": ["query"], "dataState": "final"}
    rows, _, truncated = client.search_analytics_all("sc-domain:example.jp", body)
    assert len(rows) == 27 and not truncated  # 6 named + 21 filler queries, read 4 at a time
    starts = [b["startRow"] for m, u, b in client.session.log if "searchAnalytics" in u]
    assert starts == [0, 4, 8, 12, 16, 20, 24]
    rows, _, truncated = client.search_analytics_all("sc-domain:example.jp", body, max_rows=8)
    assert len(rows) == 8 and truncated


def test_inspection_refused_keeps_the_vanished_pages_visible(make_client):
    c = make_client(urlInspection=[(403, {"error": {"code": 403, "message": "Forbidden"}})])
    r = service.weekly(c, "example.jp", today=TODAY)
    unchecked = [u["url"] for u in r["index"]["unchecked"]]
    assert "https://example.jp/old-campaign/" in unchecked
    assert any(f["kind"] == "index_unchecked" for f in r["next_fixes"])
    assert "https://example.jp/old-campaign/: 前の期間は表示 80 回、今の期間は0回（理由は未確認）" in r["message"]
    assert "「フル」" in r["message"] and "Forbidden" not in r["message"]


def test_inspection_quota_is_not_reported_as_a_permission_problem(make_client):
    c = make_client(urlInspection=[(429, {})] * 3)
    r = service.weekly(c, "example.jp", today=TODAY)
    assert r["notes"][0]["code"] == "inspection_quota"
    assert "1日の上限" in r["message"] and "「フル」" not in r["message"]


def test_index_problem_without_lost_clicks_does_not_take_first_place():
    from search_console_plugin.gsc_core import analysis as an

    cands = an.find_candidates({}, {}, {}, {}, {}, an.CtrCurve([]), 10,
                               index_findings=[{"url": "https://e.jp/x", "clicks_before": 0, "problem": "noindex"}])
    assert cands[0].kind == "index_issue" and not cands[0].blocking


def test_anonymised_share_is_shown(client):
    r = service.weekly(client, "example.jp", today=TODAY)
    assert r["anonymized_share"]["clicks"] > 0.05
    assert "匿名化された語から" in r["message"]


def test_long_reports_drop_low_sections_first(monkeypatch, client):
    monkeypatch.setattr(render, "MAX_CHARS", 900)
    r = service.weekly(client, "example.jp", today=TODAY)
    assert len(r["message"]) <= 900 or r["message"].count("■") == 1
    assert "■ 次に直す3件" in r["message"] and "■ 上位の語" not in r["message"]


def test_japanese_slugs_are_shown_decoded():
    assert render.show_url("https://e.jp/%E3%83%91%E3%83%B3") == "https://e.jp/パン"
    assert render._path("https://e.jp/%E3%83%91%E3%83%B3/") == "/パン/"


def test_inspect_url_success(client):
    r = service.inspect_url(client, "https://example.jp/old-campaign/")
    assert r["site_url"] == "sc-domain:example.jp"
    assert r["indexing_state"] == "BLOCKED_BY_META_TAG" and r["inspection_link"]


def test_tool_errors_follow_the_site_language(monkeypatch):
    monkeypatch.delenv("GSC_CREDENTIALS_FILE", raising=False)
    auth.reset_cache()
    monkeypatch.setattr(tools, "client_factory", tools.Client)
    out = json.loads(tools.gsc_weekly_report({"site_url": "sc-domain:example.jp"}))
    assert out["error"] == "not_configured" and "設定されていない" in out["message"]
    out = json.loads(tools.gsc_weekly_report({"site_url": "example.com", "language": "en"}))
    assert out["message"].startswith("GSC_CREDENTIALS_FILE is not set")


@pytest.mark.parametrize("client_id", [
    "764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com",  # application-default login
    "32555940559.apps.googleusercontent.com",  # gcloud auth login (adc.json)
])
def test_gcloud_builtin_client_is_refused(monkeypatch, tmp_path, client_id):
    assert client_id in auth.GCLOUD_DEFAULT_CLIENT_IDS
    auth.reset_cache()
    f = tmp_path / "adc.json"
    f.write_text(json.dumps({"type": "authorized_user", "client_id": client_id,
                             "client_secret": "x", "refresh_token": "y"}))
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", str(f))
    with pytest.raises(GscError) as e:
        auth.load_identity()
    assert e.value.code == "oauth_shared_client"


def test_damaged_private_key_is_explained(monkeypatch, tmp_path):
    auth.reset_cache()
    f = tmp_path / "sa.json"
    f.write_text(json.dumps({"type": "service_account", "client_email": "a@b.iam.gserviceaccount.com",
                             "private_key": "-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n",
                             "token_uri": "https://oauth2.googleapis.com/token"}))
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", str(f))
    with pytest.raises(GscError) as e:
        auth.load_identity()
    assert e.value.code == "key_file_unreadable" and "damaged" in e.value.message


def _patch_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "Client", lambda *a: Client(SA, FakeSession(), sleep=lambda s: None))
    monkeypatch.setattr(cli, "load_identity", lambda: SA)
    key = tmp_path / "key.json"
    key.write_text("{}")
    monkeypatch.setenv("GSC_CREDENTIALS_FILE", str(key))
    monkeypatch.setattr(cli, "_hermes_home", lambda: tmp_path)


def test_doctor_cli(monkeypatch, tmp_path, capsys):
    _patch_cli(monkeypatch, tmp_path)
    rc = cli.handle(types.SimpleNamespace(gsc_command="doctor", site="example.jp", lang="ja"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "✓ 鍵ファイルを読めました: サービスアカウント gsc-reader@demo-project.iam.gserviceaccount.com" in out
    assert "sc-domain:example.jp: データを読めました。確定している最新の日は 2026-09-29（2026-09-30 以降は Google が集計中）" in out


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_doctor_warns_when_others_can_read_the_key(monkeypatch, tmp_path, capsys):
    _patch_cli(monkeypatch, tmp_path)
    key = tmp_path / "key.json"
    for mode, warned in ((0o644, True), (0o640, True), (0o600, False)):
        key.chmod(mode)
        assert cli.handle(types.SimpleNamespace(gsc_command="doctor", site="example.jp", lang="ja")) == 0
        out = capsys.readouterr().out
        assert ("ほかのユーザーも鍵ファイルを読めます" in out) is warned
        if warned:
            assert f"（権限 {mode:04o}）" in out and f"chmod 600 {key}" in out
    key.chmod(0o604)
    cli.handle(types.SimpleNamespace(gsc_command="doctor", site="example.jp", lang="en"))
    assert "Other users on this machine can read the key file (permissions 0604)" in capsys.readouterr().out


def test_schedule_cli_writes_script_and_prints_the_cron_line(monkeypatch, tmp_path, capsys):
    _patch_cli(monkeypatch, tmp_path)
    rc = cli.handle(types.SimpleNamespace(gsc_command="schedule", site="example.jp", deliver="telegram",
                                          when="0 9 * * 1", lang="auto"))
    out = capsys.readouterr().out
    assert rc == 0 and (tmp_path / "scripts" / "search-console-weekly-domain-example-jp.py").is_file()
    assert "hermes cron create '0 9 * * 1' --no-agent --script search-console-weekly-domain-example-jp.py " \
           "--deliver telegram" in out
    assert "gateway" in out


def test_cli_error_exit_code_and_text(monkeypatch, capsys):
    monkeypatch.delenv("GSC_CREDENTIALS_FILE", raising=False)
    auth.reset_cache()
    rc = cli.handle(types.SimpleNamespace(gsc_command="weekly", site="example.com", lang="en", json=False))
    assert rc == 1 and "What to do:" in capsys.readouterr().out


def test_slash_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(cli, "Client", boom)
    assert "doctor" in cli.slash("weekly example.com")


def test_inspection_400_is_a_failed_check_not_a_permission_problem(make_client):
    c = make_client(urlInspection=[(400, {"error": {"code": 400, "message": "URL not in property"}})])
    r = service.weekly(c, "example.jp", today=TODAY)
    assert r["notes"][0]["code"] == "inspection_failed" and r["notes"][0]["error"] == "bad_request"
    assert "範囲外の URL など" in r["message"] and "一時的とは限りません" in r["message"]
    assert "「フル」" not in r["message"]


def test_inspection_5xx_is_worded_as_an_error_not_a_rejection(make_client):
    c = make_client(urlInspection=[(503, {})] * 3)
    r = service.weekly(c, "example.jp", today=TODAY)
    assert r["notes"][0]["code"] == "inspection_failed" and r["notes"][0]["error"] == "google_unavailable"
    assert "URL 検査でエラーが返ったため" in r["message"] and "範囲外" not in r["message"]


def test_bad_request_reads_as_japanese_and_keeps_googles_words_in_details(client):
    exc = client._http_error(400, {"error": {"code": 400, "message": "Invalid dimension"}}, None)
    message, fix = exc.parts("ja")
    assert message == "Search Console がこの問い合わせを受け付けませんでした（HTTP 400）。"
    assert "Invalid dimension" not in message + fix
    assert exc.to_dict("ja")["details"]["google_message"] == "Invalid dimension"
    assert "Invalid dimension" in exc.text("en")


def test_schedule_fixes_the_alert_language_in_the_script(monkeypatch, tmp_path, capsys):
    _patch_cli(monkeypatch, tmp_path)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    cli.handle(types.SimpleNamespace(gsc_command="schedule", site="example.jp", deliver="local",
                                     when="0 9 * * 1", lang="auto"))
    text = (tmp_path / "scripts" / "search-console-weekly-domain-example-jp.py").read_text(encoding="utf-8")
    assert "main('sc-domain:example.jp', 'auto', alert_language='ja')" in text  # fixed now, not at failure time
    cli.handle(types.SimpleNamespace(gsc_command="schedule", site="example.jp", deliver="local",
                                     when="0 9 * * 1", lang="en"))
    text = (tmp_path / "scripts" / "search-console-weekly-domain-example-jp.py").read_text(encoding="utf-8")
    assert "main('sc-domain:example.jp', 'en', alert_language='en')" in text


class _SearchesSession(FakeSession):
    """Two properties whose searches disagree with their domain: a .com site searched in Japanese and
    a .jp site searched in English. Search Analytics answers with the property's query rows for any window."""

    ROWS = {
        "sc-domain:example.com": [("パン 作り方", 70, 900), ("食パン レシピ", 40, 500), ("bread recipe", 5, 100)],
        "sc-domain:example.jp": [("tokyo bakery guide", 50, 800), ("sourdough starter", 20, 300), ("パン", 1, 40)],
    }

    def request(self, method, url, json=None, timeout=None):
        assert timeout
        self.log.append((method, url, json))
        if url.endswith("/sites"):
            return Resp(200, {"siteEntry": [{"siteUrl": s, "permissionLevel": "siteFullUser"} for s in self.ROWS]})
        if "searchAnalytics" in url:
            if json.get("dataState") == "all" and json.get("dimensions") == ["date"]:
                return Resp(200, self.f["date_probe"])
            site = next(s for s in self.ROWS if urllib.parse.quote(s, safe="") in url)
            rows = [{"keys": [q], "clicks": c, "impressions": i, "ctr": c / i, "position": 4.0}
                    for q, c, i in self.ROWS[site]]
            return Resp(200, {"rows": rows[json.get("startRow", 0):]})
        return Resp(404, {"error": {"code": 404, "message": "not found"}})


def test_schedule_alert_language_follows_the_searches_not_the_tld(monkeypatch, tmp_path):
    _patch_cli(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "Client", lambda *a: Client(SA, _SearchesSession(), sleep=lambda s: None))
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    for site, expected in (("sc-domain:example.com", "ja"), ("sc-domain:example.jp", "en")):
        # The top-level domain alone would say the opposite in both cases.
        assert message_language("auto", site) != expected
        cli.handle(types.SimpleNamespace(gsc_command="schedule", site=site, deliver="local",
                                         when="0 9 * * 1", lang="auto"))
        script = tmp_path / "scripts" / schedule.script_name(site)
        assert f"main({site!r}, 'auto', alert_language={expected!r})" in script.read_text(encoding="utf-8")
