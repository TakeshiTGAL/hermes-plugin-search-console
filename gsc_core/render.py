"""Plain-text report for chat and messaging delivery (English or Japanese).

Verdict first, then the three things to fix, then short supporting lists. No wide tables: the
weekly message is read on a phone in Telegram, Slack, LINE WORKS or e-mail. Kept under
Telegram's 4,096-character limit by dropping the lowest sections first.
"""

from __future__ import annotations

import datetime as dt
import urllib.parse

from .textnorm import shorten

MAX_CHARS = 3800

T = {
    "en": {
        "title_weekly": "Search Console weekly check: {site}",
        "title_audit": "Search Console audit ({days} days): {site}",
        "windows": "Compared {cur} with {prev} (Search Console days, US Pacific time).",
        "excluded": "{excl} still being processed by Google, so left out of the comparison.",
        "assumed": "Google did not say which days are final; the last {n} days were left out to be safe.",
        "no_data": "No Google Search data for this property in either period. Nothing to compare yet.",
        "verdict_up": "Overall: clicks {pct} vs the previous period.",
        "verdict_flat": "Overall: clicks about the same as the previous period.",
        "verdict_main": " Most worth doing: {what}.",
        "verdict_none": " No clear problem stood out.",
        "totals": "Clicks {c} ({dc}) · Impressions {i} ({di}) · CTR {ctr} · Avg position {pos} (was {ppos}; lower is better)",
        "anon": "{p} of clicks came from anonymised queries (Search Console does not show them one by one).",
        "fixes_head": "Next 3 fixes",
        "fixes_few": "Only {n} fix(es) met the bar this time (at least 3 expected clicks behind the evidence and 2 clicks at stake).",
        "fixes_zero": "No fix met the bar this time (at least 3 expected clicks behind the evidence and 2 clicks at stake).",
        "gain": "Rough upside: +{n} clicks per {per}.",
        "per_week": "week", "per_days": "{d} days",
        "drops_head": "Queries and pages that dropped",
        "upflat_head": "More impressions, no more clicks (title candidates)",
        "index_head": "Indexing",
        "index_ok_checked": "No problem found: URL Inspection checked {n} page(s) ({what}); all are indexed.",
        "what_vanished": "{n} that lost all impressions", "what_decaying": "{n} losing clicks",
        "index_ok_none": "No page lost all its impressions.",
        "inspection_refused": "URL Inspection is not allowed for this key. Give it Full permission in Search Console (Settings → Users and permissions) to see why pages left the index; the plugin still only reads.",
        "inspection_quota": "URL Inspection's daily quota was reached, so the remaining pages were not checked.",
        "inspection_failed": "URL Inspection returned an error (Google or the network), so the remaining pages were not checked.",
        "inspection_rejected": "Search Console did not accept a URL Inspection request (for example, a URL outside this property). This is not necessarily temporary. The remaining pages were not checked.",
        "unchecked_line": "- {url}: {impr} impressions in the earlier period, none now (reason not checked)",
        "index_problem": "- {url}: {coverage} ({impr} impressions in the earlier period)",
        "sitemap_issue": "- Sitemap {path}: {e} error(s), {w} warning(s)",
        "sitemap_none": "No sitemap is submitted for this property.",
        "top_head": "Top queries by clicks",
        "top_pages_head": "Top pages by clicks",
        "page_line": "- {u} {c} clicks ({dc}), position {pos}",
        "page_drop_line": "- {u} position {pp} → {cp} (clicks {pc} → {cc})",
        "moved_line": "- Moved, fine: {url} → {canonical} (the new URL keeps getting impressions)",
        "problems": {
            "canonical_elsewhere_without_impressions": "Google treats {canonical} as the main URL, and that URL gets no impressions either",
            "blocked_by_robots_txt": "blocked by robots.txt",
            "noindex": "excluded by a noindex tag or header",
            "not_indexed": "not indexed ({coverage})",
            "fetch": "Google could not fetch it ({state})",
        },
        "striking_head": "Striking distance (positions 8-20)",
        "cannibal_head": "Pages competing for the same query",
        "decay_head": "Pages losing clicks",
        "winners_head": "Queries that improved",
        "q_line": "- \"{q}\" {c} clicks ({dc}), position {pos}",
        "drop_line": "- \"{q}\" position {pp} → {cp} (clicks {pc} → {cc})",
        "lost_line": "- \"{q}\" no longer shows (was position {pp}, {pc} clicks)",
        "upflat_line": "- \"{q}\" impressions {pi} → {ci}, clicks {pc} → {cc}",
        "upflat_page_line": "- {u} impressions {pi} → {ci}, clicks {pc} → {cc}",
        "win_line": "- \"{q}\" position {pp} → {cp} (clicks {pc} → {cc})",
        "none": "- none",
        "truncated": "Note: this property has more rows than were read; small queries may be missing.",
        "kinds": {
            "index_issue": "Get a page back into Google's index",
            "title_snippet": "Rewrite a title and description",
            "rank_drop": "Recover a query that dropped",
            "striking_distance": "Push a nearly-there query onto page 1",
            "cannibalization": "Merge pages competing for one query",
            "decaying_page": "Revisit a page losing clicks",
            "index_unchecked": "Check why a page left Google's results",
        },
    },
    "ja": {
        "title_weekly": "Search Console 週次点検: {site}",
        "title_audit": "Search Console 点検（{days}日間）: {site}",
        "windows": "{cur} を {prev} と比べました（日付は米国太平洋時間）。",
        "excluded": "{excl} は Google がまだ集計中のため、比較から外しました。",
        "assumed": "確定済みの日を Google が返さなかったため、念のため直近{n}日を外しました。",
        "no_data": "どちらの期間にも Google 検索のデータがありません。比べられるものがまだありません。",
        "verdict_up": "全体: クリックは前の期間より {pct}。",
        "verdict_flat": "全体: クリックは前の期間とほぼ同じ。",
        "verdict_main": "いちばん効く手は「{what}」です。",
        "verdict_none": "目立った問題は見つかりませんでした。",
        "totals": "クリック {c}（前比 {dc}）・表示 {i}（{di}）・クリック率 {ctr}・平均順位 {pos}（前 {ppos}。小さいほど上位）",
        "anon": "クリックの {p} は匿名化された語から（Search Console は個別に表示しません）。",
        "fixes_head": "次に直す3件",
        "fixes_few": "今回、基準を満たした候補は {n} 件でした（根拠に期待クリック3回以上、見込み2クリック以上のものだけを挙げています）。",
        "fixes_zero": "今回、基準を満たす直す候補はありませんでした（根拠に期待クリック3回以上、見込み2クリック以上が条件）。",
        "gain": "見込み: {per}あたり +{n} クリック程度（目安）。",
        "per_week": "1週間", "per_days": "{d}日",
        "drops_head": "順位が落ちた語・ページ",
        "upflat_head": "表示は増えたのにクリックが増えない語・ページ（タイトル改善の候補）",
        "index_head": "インデックス",
        "index_ok_checked": "異常なし: URL 検査した {n} 件（{what}）はすべて登録済みでした。",
        "what_vanished": "表示が消えたページ {n} 件", "what_decaying": "クリックが減ったページ {n} 件",
        "index_ok_none": "表示がすべて消えたページはありません。",
        "inspection_refused": "この鍵では URL 検査が許可されていません。Search Console の「設定」→「ユーザーと権限」でこの鍵を「フル」にすると、消えたページの理由まで調べられます（プラグインは読み取りしかしません）。",
        "inspection_quota": "URL 検査の1日の上限に達したため、残りのページは調べていません。",
        "inspection_failed": "URL 検査でエラーが返ったため（Google 側か通信の問題）、残りのページは調べていません。",
        "inspection_rejected": "Search Console が URL 検査の依頼を受け付けませんでした（このプロパティの範囲外の URL など）。一時的とは限りません。残りのページは調べていません。",
        "unchecked_line": "- {url}: 前の期間は表示 {impr} 回、今の期間は0回（理由は未確認）",
        "index_problem": "- {url}: {coverage}（前の期間は表示 {impr} 回）",
        "sitemap_issue": "- サイトマップ {path}: エラー {e} 件・警告 {w} 件",
        "sitemap_none": "サイトマップが送信されていません。",
        "top_head": "上位の語（クリック順）",
        "top_pages_head": "上位のページ（クリック順）",
        "page_line": "- {u} クリック {c}（{dc}）・{pos}位",
        "page_drop_line": "- {u} {pp}位 → {cp}位（クリック {pc} → {cc}）",
        "moved_line": "- 移転を確認（問題なし）: {url} → {canonical}（新しい URL で表示が続いています）",
        "problems": {
            "canonical_elsewhere_without_impressions": "Google は {canonical} を正規の URL として扱っているが、その URL も表示されていない",
            "blocked_by_robots_txt": "robots.txt でブロックされている",
            "noindex": "noindex（タグかヘッダー）で除外されている",
            "not_indexed": "インデックスに登録されていない（{coverage}）",
            "fetch": "Google がページを取得できない（{state}）",
        },
        "striking_head": "あと一歩の語（8〜20位）",
        "cannibal_head": "同じ語を取り合っているページ",
        "decay_head": "クリックが減ったページ",
        "winners_head": "順位が上がった語",
        "q_line": "- 「{q}」クリック {c}（{dc}）・{pos}位",
        "drop_line": "- 「{q}」{pp}位 → {cp}位（クリック {pc} → {cc}）",
        "lost_line": "- 「{q}」検索結果に出なくなった（前の期間は {pp}位・クリック {pc}）",
        "upflat_line": "- 「{q}」表示 {pi} → {ci}・クリック {pc} → {cc}",
        "upflat_page_line": "- {u} 表示 {pi} → {ci}・クリック {pc} → {cc}",
        "win_line": "- 「{q}」{pp}位 → {cp}位（クリック {pc} → {cc}）",
        "none": "- なし",
        "truncated": "注: このプロパティは行数が多く、読み切れなかった小さな語があります。",
        "kinds": {
            "index_issue": "インデックスから外れたページを戻す",
            "title_snippet": "タイトルと説明文を書き直す",
            "rank_drop": "順位が落ちた語を立て直す",
            "striking_distance": "あと一歩の語を1ページ目へ押し上げる",
            "cannibalization": "同じ語を取り合うページをまとめる",
            "decaying_page": "クリックが減ったページを見直す",
            "index_unchecked": "検索結果から消えたページの理由を確かめる",
        },
    },
}


def _n(x) -> str:
    return f"{int(round(x)):,}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _signed(change: int, pct: float | None, lang: str) -> str:
    sign = "+" if change > 0 else ("±" if change == 0 else "−")
    base = f"{sign}{_n(abs(change))}"
    if pct is None:
        return base
    p = f"{'+' if pct > 0 else ('±' if pct == 0 else '−')}{abs(pct) * 100:.0f}%"
    return f"{base}・{p}" if lang == "ja" else f"{base}, {p}"


def _date(d: str, lang: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"{x.month}/{x.day}" if lang == "ja" else f"{x.strftime('%b')} {x.day}"


def _range(w: dict, lang: str) -> str:
    sep = "〜" if lang == "ja" else "–"
    return f"{_date(w['start'], lang)}{sep}{_date(w['end'], lang)}"


def show_url(url: str) -> str:
    """Readable URL: Japanese slugs are shown decoded (%E3%83%91%E3%83%B3 → パン)."""
    try:
        return urllib.parse.unquote(url or "")
    except Exception:
        return url or ""


def _path(url: str) -> str:
    """Short form for lists: the path, or the host for a home page."""
    rest = show_url(url).split("://", 1)[-1]
    host, _, path = rest.partition("/")
    return shorten("/" + path if path else host, 50)


# URL Inspection's enum values (pageFetchState, verdict), worded for the report. coverageState needs no
# table: Google already returns it in the requested language.
FETCH_STATES = {
    "en": {"SOFT_404": "soft 404", "BLOCKED_ROBOTS_TXT": "blocked by robots.txt", "NOT_FOUND": "not found (404)",
           "ACCESS_DENIED": "access denied (401)", "ACCESS_FORBIDDEN": "access forbidden (403)",
           "SERVER_ERROR": "server error (5xx)", "REDIRECT_ERROR": "redirect error", "BLOCKED_4XX": "other 4xx error",
           "INTERNAL_CRAWL_ERROR": "internal crawl error at Google", "INVALID_URL": "invalid URL"},
    "ja": {"SOFT_404": "ソフト 404（中身のないページと判断された）", "BLOCKED_ROBOTS_TXT": "robots.txt でブロック",
           "NOT_FOUND": "ページが見つからない（404）", "ACCESS_DENIED": "アクセスが拒否された（401）",
           "ACCESS_FORBIDDEN": "アクセスが禁止された（403）", "SERVER_ERROR": "サーバーのエラー（5xx）",
           "REDIRECT_ERROR": "リダイレクトのエラー", "BLOCKED_4XX": "そのほかの 4xx エラー",
           "INTERNAL_CRAWL_ERROR": "Google 側のクロールの内部エラー", "INVALID_URL": "URL の形が正しくない"},
}
VERDICTS = {
    "en": {"PASS": "indexed", "PARTIAL": "partly indexed", "FAIL": "error", "NEUTRAL": "excluded"},
    "ja": {"PASS": "登録済み", "PARTIAL": "一部に問題", "FAIL": "エラー", "NEUTRAL": "除外"},
}


def problem_text(item: dict, lang: str) -> str:
    probs = T[lang]["problems"]
    reason = item.get("problem") or "not_indexed"
    if reason in probs:
        verdict = str(item.get("verdict") or "")
        coverage = item.get("coverage") or VERDICTS[lang].get(verdict.upper(), verdict)
        text = probs[reason].format(canonical=item.get("google_canonical", ""), coverage=coverage)
        return text.replace("（）", "").replace(" ()", "")
    state = str(item.get("page_fetch") or reason)
    return probs["fetch"].format(state=FETCH_STATES[lang].get(state.upper(), state))


def _page_fix(kind: str, fix: dict, lang: str) -> list[str]:
    page, cur, prev = show_url(fix.get("page", "")), fix.get("current", {}), fix.get("previous", {})
    ja = lang == "ja"
    where = ("どの語で表示されているかは、Search Console の「検索パフォーマンス」で「ページ」をこの URL に絞ると分かります。" if ja
             else "Search Console → Performance, filtered to this page, shows which searches it appears for.")
    if kind == "title_snippet":
        typical = _pct(fix.get("typical_ctr", 0))
        if fix.get("reason") == "impressions_up_clicks_flat":
            fact = (f"{page} の表示が {_n(prev.get('impressions', 0))} → {_n(cur.get('impressions', 0))} 回に増えたのに、"
                    f"クリックは {_n(prev.get('clicks', 0))} → {_n(cur.get('clicks', 0))} 回。" if ja else
                    f"{page}: impressions {_n(prev.get('impressions', 0))} → {_n(cur.get('impressions', 0))}, "
                    f"clicks {_n(prev.get('clicks', 0))} → {_n(cur.get('clicks', 0))}.")
        else:
            fact = (f"{page} はページ全体で平均 {cur.get('position')} 位・表示 {_n(cur.get('impressions', 0))} 回なのに、"
                    f"クリック率 {_pct(cur.get('ctr', 0))}（このサイトのページの同じ順位帯は {typical}）。" if ja else
                    f"{page} averages position {cur.get('position')} with {_n(cur.get('impressions', 0))} impressions "
                    f"but a {_pct(cur.get('ctr', 0))} CTR (this site's pages usually get {typical} there).")
        act = ("タイトルと説明文を、このページに来る検索の目的に合わせて書き直す。" + where if ja else
               "Rewrite the title and description for what those searchers want. " + where)
        return [fact, act]
    if kind == "rank_drop":
        fact = (f"{page} の平均順位が {prev.get('position')} 位 → {cur.get('position')} 位（クリック "
                f"{_n(prev.get('clicks', 0))} → {_n(cur.get('clicks', 0))}）。" if ja else
                f"{page} went from position {prev.get('position')} to {cur.get('position')} "
                f"(clicks {_n(prev.get('clicks', 0))} → {_n(cur.get('clicks', 0))}).")
        act = ("最近このページを変えていないか確かめ、落ちた語でいま上位のページと比べて足りない情報を足す。" + where if ja else
               "Check whether the page changed recently and compare it with what now outranks it. " + where)
        return [fact, act]
    fact = (f"{page} はページ全体で平均 {cur.get('position')} 位（1ページ目の下か2ページ目）・表示 "
            f"{_n(cur.get('impressions', 0))} 回。" if ja else
            f"{page} averages position {cur.get('position')} with {_n(cur.get('impressions', 0))} impressions, "
            "just short of the top.")
    act = ("表示されている語への答えを見出しつきで足し、よく読まれている自サイトのページからリンクを張る。" + where if ja else
           "Answer the searches it shows for under clear headings and link to it from your strongest pages. " + where)
    return [fact, act]


def fix_text(fix: dict, lang: str, per: str) -> list[str]:
    t = T[lang]
    kind = fix["kind"]
    q = shorten(fix.get("query", ""), 40)
    page = show_url(fix.get("page", ""))
    cur, prev = fix.get("current", {}), fix.get("previous", {})
    ja = lang == "ja"
    lines = [t["kinds"][kind]]
    if kind == "index_issue":
        why = problem_text({"problem": fix.get("problem"), "google_canonical": fix.get("google_canonical", ""),
                            "coverage": fix.get("coverage"), "verdict": fix.get("verdict")}, lang)
        lines.append(f"{page} は前の期間に表示 {fix.get('impressions_before', 0)} 回あったのに、今の期間は0回。URL 検査: {why}。"
                     if ja else f"{page} had {fix.get('impressions_before', 0)} impressions in the earlier period and "
                                f"none now. URL Inspection: {why}.")
        lines.append("意図して外したページでなければ、Search Console の「URL 検査」でこのページを開き、理由（noindex・canonical・"
                     "robots.txt・404 など）を直してから「インデックス登録をリクエスト」を押す。" if ja else
                     "Unless you removed it on purpose, open the page in Search Console's URL Inspection, fix the reason "
                     "it gives (noindex, canonical, robots.txt, 404…), then press Request indexing.")
    elif kind == "index_unchecked":
        lines.append(f"{page} は前の期間に表示 {fix.get('impressions_before', 0)} 回あったのに、今の期間は0回。理由は未確認。"
                     if ja else f"{page} had {fix.get('impressions_before', 0)} impressions in the earlier period and "
                                "none now; the reason was not checked.")
        lines.append("Search Console の「URL 検査」でこのページを開き、登録されていない理由を確かめる（意図して消したなら対応不要）。"
                     if ja else "Open it in Search Console's URL Inspection to see why (nothing to do if you removed it "
                                "on purpose).")
    elif kind in ("title_snippet", "rank_drop", "striking_distance") and fix.get("scope") == "page":
        lines += _page_fix(kind, fix, lang)
    elif kind == "title_snippet":
        typical = _pct(fix.get("typical_ctr", 0))
        if fix.get("reason") == "impressions_up_clicks_flat":
            lines.append(f"「{q}」の表示が {_n(prev.get('impressions', 0))} → {_n(cur.get('impressions', 0))} 回に増えたのに、"
                         f"クリックは {_n(prev.get('clicks', 0))} → {_n(cur.get('clicks', 0))} 回。" if ja else
                         f"\"{q}\" impressions grew {_n(prev.get('impressions', 0))} → {_n(cur.get('impressions', 0))} "
                         f"but clicks went {_n(prev.get('clicks', 0))} → {_n(cur.get('clicks', 0))}.")
        else:
            lines.append(f"「{q}」で平均 {cur.get('position')} 位・表示 {_n(cur.get('impressions', 0))} 回なのに、"
                         f"クリック率 {_pct(cur.get('ctr', 0))}（このサイトの同じ順位帯は {typical}）。" if ja else
                         f"\"{q}\" sits at position {cur.get('position')} with {_n(cur.get('impressions', 0))} impressions "
                         f"but a {_pct(cur.get('ctr', 0))} CTR (this site usually gets {typical} there).")
        target = page or ("このページ" if ja else "the page")
        lines.append(f"{target} のタイトルの前半に「{q}」で探す人が求める言葉を入れ、説明文で中身を具体的に示す。" if ja else
                     f"Put what people searching \"{q}\" want near the start of the title of {target}, "
                     "and make the description say concretely what the page gives them.")
    elif kind == "rank_drop":
        if fix.get("reason") == "disappeared":
            lines.append(f"「{q}」が検索結果に出なくなった（前は {prev.get('position')} 位・クリック {_n(prev.get('clicks', 0))}）。"
                         if ja else f"\"{q}\" no longer shows (was position {prev.get('position')}, "
                                    f"{_n(prev.get('clicks', 0))} clicks).")
        else:
            lines.append(f"「{q}」が {prev.get('position')} 位 → {cur.get('position')} 位（クリック {_n(prev.get('clicks', 0))}"
                         f" → {_n(cur.get('clicks', 0))}）。" if ja else
                         f"\"{q}\" went from position {prev.get('position')} to {cur.get('position')} "
                         f"(clicks {_n(prev.get('clicks', 0))} → {_n(cur.get('clicks', 0))}).")
        target = page or ("このページ" if ja else "the page")
        lines.append(f"{target} を最近変えていないか確かめ、いまこの語で上位のページと比べて足りない情報を足す。" if ja else
                     f"Check whether {target} changed recently, then compare it with what now ranks above it and "
                     "add what is missing.")
    elif kind == "striking_distance":
        lines.append(f"「{q}」が平均 {cur.get('position')} 位（1ページ目の下か2ページ目）で表示 {_n(cur.get('impressions', 0))} 回。"
                     if ja else f"\"{q}\" averages position {cur.get('position')} with "
                                f"{_n(cur.get('impressions', 0))} impressions, just short of the top.")
        target = page or ("このページ" if ja else "the page")
        lines.append(f"{target} にこの語への答えを見出しつきで足し、よく読まれている自サイトのページからリンクを張る。" if ja else
                     f"Add a section to {target} that answers \"{q}\" under its own heading, and link to it from "
                     "your strongest pages.")
    elif kind == "cannibalization":
        pages = fix.get("competing_pages", [])
        lines.append(f"「{q}」で {len(pages)} ページが表示を分け合っている（平均 {cur.get('position')} 位）: " + "、".join(pages)
                     if ja else f"\"{q}\" is split across {len(pages)} pages (position {cur.get('position')}): "
                                + ", ".join(pages))
        lines.append("主にしたいページを1つ決め、他のページは内容をそこへ寄せるか、そのページへリンクする。" if ja else
                     "Pick one page to rank, merge the others into it or link them to it.")
    elif kind == "decaying_page":
        lines.append(f"{page} のクリックが {_n(prev.get('clicks', 0))} → {_n(cur.get('clicks', 0))} 回。" if ja else
                     f"{page} went from {_n(prev.get('clicks', 0))} to {_n(cur.get('clicks', 0))} clicks.")
        lines.append("このページで落ちた語を確かめ、内容が古くなっていないか見直す。" if ja else
                     "See which queries it lost and check whether the content went stale.")
    gain = fix.get("estimated_extra_clicks", 0)
    if gain >= 1:
        lines.append(t["gain"].format(n=_n(gain), per=per))
    return lines


def report(r: dict, lang: str, deep: bool) -> str:
    t = T[lang]
    per_days = r["periods"]["current"]["days"]
    per = t["per_week"] if per_days == 7 else t["per_days"].format(d=per_days)
    head = [t["title_audit"].format(days=per_days, site=r["site_url"]) if deep
            else t["title_weekly"].format(site=r["site_url"])]
    p = r["periods"]
    head.append(t["windows"].format(cur=_range(p["current"], lang), prev=_range(p["previous"], lang)))
    if p.get("excluded_unfinished"):
        head.append(t["excluded"].format(excl=_range(p["excluded_unfinished"], lang)))
    if p.get("how_last_final_was_found") == "assumed":
        head.append(t["assumed"].format(n=3))
    cur, prev = r["totals"]["current"], r["totals"]["previous"]
    if not cur["impressions"] and not prev["impressions"]:
        return "\n".join(head + ["", t["no_data"]])

    ch = r["totals"]["change"]["clicks"]
    pct = ch["pct"]
    verdict = (t["verdict_flat"] if pct is None or abs(pct) < 0.05
               else t["verdict_up"].format(pct=(f"+{pct * 100:.0f}%" if pct > 0 else f"−{abs(pct) * 100:.0f}%")))
    fixes = r.get("next_fixes", [])
    verdict += t["verdict_main"].format(what=t["kinds"][fixes[0]["kind"]]) if fixes else t["verdict_none"]
    head += ["", verdict, t["totals"].format(
        c=_n(cur["clicks"]), dc=_signed(ch["change"], pct, lang), i=_n(cur["impressions"]),
        di=_signed(r["totals"]["change"]["impressions"]["change"], r["totals"]["change"]["impressions"]["pct"], lang),
        ctr=_pct(cur["ctr"]), pos=cur["position"], ppos=prev["position"])]
    anon = r.get("anonymized_share")
    if anon and anon.get("clicks", 0) >= 0.05:
        head.append(t["anon"].format(p=_pct(anon["clicks"])))

    fx = ["", f"■ {t['fixes_head']}"]
    if not fixes:
        fx.append(t["fixes_zero"])
    for i, f in enumerate(fixes, 1):
        lines = fix_text(f, lang, per)
        fx.append(f"{i}. {lines[0]}")
        fx += [f"   {x}" for x in lines[1:]]
    if 0 < len(fixes) < 3:
        fx.append(t["fixes_few"].format(n=len(fixes)))

    sections = [head + fx]

    drops = [t["drop_line"].format(q=shorten(d["key"]), pp=d["position_before"], cp=d["position_after"],
                                   pc=d["clicks_before"], cc=d["clicks_after"]) for d in r.get("rank_drops", [])[:5]]
    drops += [t["page_drop_line"].format(u=_path(d["key"]), pp=d["position_before"], cp=d["position_after"],
                                         pc=d["clicks_before"], cc=d["clicks_after"])
              for d in r.get("rank_drops_pages", [])[:3]]
    sections.append(["", f"■ {t['drops_head']}"] + (drops or [t["none"]]))
    upf = [t["upflat_line"].format(q=shorten(d["key"]), pi=_n(d["impressions_before"]), ci=_n(d["impressions_after"]),
                                   pc=d["clicks_before"], cc=d["clicks_after"])
           for d in r.get("impressions_up_clicks_flat", [])[:5]]
    upf += [t["upflat_page_line"].format(u=_path(d["key"]), pi=_n(d["impressions_before"]),
                                         ci=_n(d["impressions_after"]), pc=d["clicks_before"], cc=d["clicks_after"])
            for d in r.get("impressions_up_clicks_flat_pages", [])[:3]]
    sections.append(["", f"■ {t['upflat_head']}"] + (upf or [t["none"]]))

    idx = r.get("index", {})
    il = ["", f"■ {t['index_head']}"]
    for prob in idx.get("problems", []):
        il.append(t["index_problem"].format(url=show_url(prob["url"]), coverage=problem_text(prob, lang),
                                            impr=prob.get("impressions_before", 0)))
    for mv in idx.get("moved", []):
        il.append(t["moved_line"].format(url=show_url(mv["url"]), canonical=show_url(mv.get("google_canonical", ""))))
    for un in [u for u in idx.get("unchecked", []) if u.get("why") == "vanished"]:
        il.append(t["unchecked_line"].format(url=show_url(un["url"]), impr=un.get("impressions_before", 0)))
    stops = [("inspection_rejected" if n.get("error") == "bad_request" else n["code"])
             for n in r.get("notes", []) if n.get("code") in ("inspection_refused", "inspection_quota",
                                                               "inspection_failed")]
    if stops:
        il.append(t[stops[0]])
    elif not idx.get("problems") and not idx.get("moved"):
        checked = idx.get("pages_checked", [])
        if checked:
            whats = []
            for why in ("vanished", "decaying"):
                n = sum(1 for c in checked if c.get("why_checked") == why)
                if n:
                    whats.append(t[f"what_{why}"].format(n=n))
            il.append(t["index_ok_checked"].format(n=len(checked), what="、".join(whats) if lang == "ja"
                                                   else ", ".join(whats)))
        else:
            il.append(t["index_ok_none"])
    sm = idx.get("sitemaps", {})
    for sm_issue in sm.get("with_issues", []):
        il.append(t["sitemap_issue"].format(path=sm_issue["path"], e=sm_issue["errors"], w=sm_issue["warnings"]))
    if sm.get("checked") and sm.get("submitted") == 0:
        il.append(t["sitemap_none"])
    sections.append(il)

    pages = []
    for pg in r.get("top_pages", [])[:5]:
        pv = pg.get("previous", {})
        pages.append(t["page_line"].format(u=_path(pg["page"]), c=_n(pg["clicks"]),
                                           dc=_signed(pg["clicks"] - pv.get("clicks", 0), None, lang), pos=pg["position"]))
    sections.append(["", f"■ {t['top_pages_head']}"] + (pages or [t["none"]]))
    tops = []
    for q in r.get("top_queries", [])[:5]:
        pv = q.get("previous", {})
        tops.append(t["q_line"].format(q=shorten(q["query"]), c=_n(q["clicks"]),
                                       dc=_signed(q["clicks"] - pv.get("clicks", 0), None, lang), pos=q["position"]))
    sections.append(["", f"■ {t['top_head']}"] + (tops or [t["none"]]))

    if deep:
        def block(key, head_key):
            rows = []
            for c in r.get(key, [])[:5]:
                rows.append("- " + " ".join(fix_text(c, lang, per)[1:2]))
            return ["", f"■ {t[head_key]}"] + (rows or [t["none"]])
        sections.append(block("striking_distance", "striking_head"))
        sections.append(block("cannibalization", "cannibal_head"))
        sections.append(block("decaying_pages", "decay_head"))
        wins = [t["win_line"].format(q=shorten(d["key"]), pp=d["position_before"], cp=d["position_after"],
                                     pc=d["clicks_before"], cc=d["clicks_after"]) for d in r.get("winners", [])[:5]]
        sections.append(["", f"■ {t['winners_head']}"] + (wins or [t["none"]]))
    if r.get("data_truncated"):
        sections.append(["", t["truncated"]])

    while len(sections) > 1 and len("\n".join(sum(sections, []))) > MAX_CHARS:
        sections.pop()
    return "\n".join(sum(sections, []))
