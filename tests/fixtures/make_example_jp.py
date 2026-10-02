"""Builds example_jp.json: Search Console API responses for a made-up Japanese home-baking site.

The response *shapes* (siteEntry, rows/keys, metadata.firstIncompleteDate, sitemap, inspectionResult
with localised coverageState) were recorded from the live API on 2026-10-02. Every value here is
synthetic — no real property's numbers are stored in this repository. Run this file to regenerate.
"""

import json
from pathlib import Path

SITE = "sc-domain:example.jp"
CUR = ("2026-09-23", "2026-09-29")
PREV = ("2026-09-16", "2026-09-22")

# query: (cur clicks, impr, pos), (prev clicks, impr, pos), page
QUERIES = {
    "食パン レシピ": ((30, 600, 3.2), (28, 560, 3.0), "https://example.jp/recipes/shokupan.html"),
    "食パン　レシピ": ((2, 40, 3.4), (2, 40, 3.3), "https://example.jp/recipes/shokupan.html"),
    "パン 作り方 初心者": ((1, 300, 4.1), (6, 280, 4.0), "https://example.jp/guide/hajimete/"),
    "天然酵母 起こし方": ((4, 120, 9.5), (12, 130, 5.2), "https://example.jp/guide/tennen-kobo/"),
    "ホームベーカリー おすすめ 機種": ((3, 250, 12.5), (3, 200, 13.0), "https://example.jp/home-bakery/"),
    "パン 発酵 時間": ((2, 150, 6.5), (2, 60, 7.0), "https://example.jp/blog/hakko/"),
}
# Filler queries so the site's own CTR curve has data in each position band.
FILLER = [(1.5, 0.30), (2.5, 0.20), (3.5, 0.12), (5.0, 0.07), (7.0, 0.04), (9.5, 0.025), (13.0, 0.01)]
for i, (pos, ctr) in enumerate(FILLER):
    for j in range(3):
        impr = 60 + 10 * j
        QUERIES[f"パン 用語 {i}-{j}"] = ((round(impr * ctr), impr, pos), (round(impr * ctr), impr, pos),
                                     "https://example.jp/glossary/")

# page: (cur clicks, impr, pos) or None, (prev ...) or None
PAGES = {
    "https://example.jp/recipes/shokupan.html": ((40, 900, 3.3), None),
    "https://example.jp/recipes/shokupan": (None, (38, 850, 3.2)),  # moved to .html
    "https://example.jp/guide/hajimete/": ((1, 300, 4.1), (6, 280, 4.0)),
    "https://example.jp/guide/tennen-kobo/": ((4, 120, 9.5), (12, 130, 5.2)),
    "https://example.jp/home-bakery/": ((3, 250, 12.5), (3, 200, 13.0)),
    "https://example.jp/blog/hakko/": ((2, 150, 6.5), (2, 60, 7.0)),
    "https://example.jp/glossary/": ((40, 1500, 5.0), (40, 1500, 5.0)),
    "https://example.jp/company/": ((3, 90, 4.0), None),
    "https://example.jp/about": (None, (3, 85, 4.2)),  # renamed to /company/
    "https://example.jp/old-campaign/": (None, (5, 80, 6.0)),  # now noindex
}

INSPECTIONS = {
    "https://example.jp/old-campaign/": {
        "verdict": "NEUTRAL", "coverageState": "noindex タグによって除外されました",
        "robotsTxtState": "ALLOWED", "indexingState": "BLOCKED_BY_META_TAG", "pageFetchState": "SUCCESSFUL",
        "lastCrawlTime": "2026-09-20T03:11:00Z", "googleCanonical": "", "userCanonical": ""},
    "https://example.jp/about": {
        "verdict": "NEUTRAL", "coverageState": "ページにリダイレクトがあります", "robotsTxtState": "ALLOWED",
        "indexingState": "INDEXING_ALLOWED", "pageFetchState": "SUCCESSFUL",
        "lastCrawlTime": "2026-09-18T01:00:00Z", "googleCanonical": "https://example.jp/company/",
        "userCanonical": "https://example.jp/company/"},
}


def row(keys, c, i, p):
    return {"keys": keys, "clicks": c, "impressions": i, "ctr": c / i if i else 0, "position": p}


def window(idx):
    q_rows, qp_rows, p_rows = [], [], []
    for q, (cur, prev, page) in QUERIES.items():
        c, i, p = (cur, prev)[idx]
        q_rows.append(row([q], c, i, p))
        qp_rows.append(row([q, page], c, i, p))
    for url, vals in PAGES.items():
        if vals[idx]:
            p_rows.append(row([url], *vals[idx]))
    q_rows.sort(key=lambda r: -r["clicks"])
    # Site totals include anonymised queries, so they exceed the sum of query rows (here by 40% / 25%).
    clicks = max(sum(r["clicks"] for r in p_rows), sum(r["clicks"] for r in q_rows))
    impr = max(sum(r["impressions"] for r in p_rows), sum(r["impressions"] for r in q_rows))
    total = row([], int(clicks * 1.4), int(impr * 1.25), 6.1 if idx == 0 else 5.8)
    del total["keys"]
    return {"totals": {"rows": [total], "responseAggregationType": "byProperty"},
            "query": {"rows": q_rows, "responseAggregationType": "byProperty"},
            "page": {"rows": p_rows, "responseAggregationType": "byPage"},
            "query,page": {"rows": qp_rows, "responseAggregationType": "byPage"}}


data = {
    "site": SITE,
    "today": "2026-10-02",
    "sites": {"siteEntry": [{"siteUrl": SITE, "permissionLevel": "siteRestrictedUser"},
                            {"siteUrl": "https://other.example/", "permissionLevel": "siteUnverifiedUser"}]},
    "date_probe": {"rows": [row([d], 5, 100, 6.0) for d in
                            ("2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28", "2026-09-29", "2026-09-30",
                             "2026-10-01")],
                   "responseAggregationType": "byProperty", "metadata": {"firstIncompleteDate": "2026-09-30"}},
    "windows": {CUR[0]: window(0), PREV[0]: window(1)},
    "sitemaps": {"sitemap": [{"path": "https://example.jp/sitemap.xml", "lastSubmitted": "2026-09-01T00:00:00Z",
                              "isPending": False, "isSitemapsIndex": False, "lastDownloaded": "2026-09-28T00:00:00Z",
                              "warnings": "0", "errors": "0",
                              "contents": [{"type": "web", "submitted": "42", "indexed": "0"}]}]},
    "inspections": {u: {"inspectionResult": {"inspectionResultLink": "https://search.google.com/search-console/inspect",
                                             "indexStatusResult": v}} for u, v in INSPECTIONS.items()},
}

if __name__ == "__main__":
    out = Path(__file__).with_name("example_jp.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}")
