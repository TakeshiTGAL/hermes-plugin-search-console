"""Tool schemas: what the model reads to decide when and how to call each tool."""

_SITE = {
    "type": "string",
    "description": (
        "Search Console property, e.g. 'sc-domain:example.com' or 'https://www.example.com/'. A bare domain "
        "like 'example.com' is matched to the property automatically. Omit to use the plugin's default_site, "
        "or the only property the key can read."
    ),
}
_LANG = {
    "type": "string",
    "enum": ["auto", "en", "ja"],
    "description": "Language of the 'message' text. auto = Japanese when most searches are in Japanese.",
}

GSC_WEEKLY_REPORT = {
    "name": "gsc_weekly_report",
    "description": (
        "Weekly Google Search Console check for the user's own site: the last 7 finalised days vs the 7 before "
        "(Google's unfinished last 2-3 days are left out and named). Returns the 3 most worthwhile fixes ranked "
        "by clicks at stake, queries whose position dropped, queries with more impressions but no more clicks "
        "(title rewrite candidates), pages that vanished from search with URL Inspection results, sitemap errors "
        "and top queries, plus a ready-to-send 'message'. Use for 'how is my site doing this week', 'what should "
        "I fix in SEO', or a scheduled weekly report. When the user wants the report, reply with 'message' as is."
    ),
    "parameters": {"type": "object", "properties": {"site_url": _SITE, "language": _LANG}},
}

GSC_AUDIT = {
    "name": "gsc_audit",
    "description": (
        "Deeper SEO audit from the site's real Search Console data over 28 days (or 'days') vs the period "
        "before: CTR anomalies judged against the site's own CTR by position, striking-distance queries "
        "(positions 8-20), cannibalisation (several pages splitting one query), decaying pages, rank drops and "
        "winners, indexing checks on the worst pages, sitemap errors, and the 3 fixes worth doing first. "
        "Use for 'audit my site', 'SEO health check', 'why is organic traffic down'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "site_url": _SITE,
            "days": {"type": "integer", "minimum": 7, "maximum": 90, "default": 28,
                     "description": "Length of each compared period in days."},
            "language": _LANG,
        },
    },
}

GSC_RANK_CHANGES = {
    "name": "gsc_rank_changes",
    "description": (
        "Rank tracking from Search Console's real positions: winners, losers (sorted by clicks lost), new and "
        "lost queries or pages between two periods. Default: last 28 finalised days vs the 28 before. Give "
        "current_start/current_end (and optionally previous_start/previous_end) to split around an event such "
        "as a site change or a Google update."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "site_url": _SITE,
            "dimension": {"type": "string", "enum": ["query", "page"], "default": "query"},
            "days": {"type": "integer", "minimum": 1, "maximum": 90, "default": 28},
            "current_start": {"type": "string", "description": "YYYY-MM-DD"},
            "current_end": {"type": "string", "description": "YYYY-MM-DD"},
            "previous_start": {"type": "string", "description": "YYYY-MM-DD (default: same length right before)"},
            "previous_end": {"type": "string", "description": "YYYY-MM-DD"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
    },
}

GSC_QUERY = {
    "name": "gsc_query",
    "description": (
        "Raw Search Console performance rows (clicks, impressions, CTR, position) for any dimensions and dates, "
        "for questions the other tools do not answer, e.g. 'clicks by device last month' or 'which pages rank "
        "for queries containing pricing'. Defaults to the last 28 finalised days by query. Search Console keeps "
        "16 months of data; rows with the query dimension leave out anonymised queries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "site_url": _SITE,
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            "days": {"type": "integer", "minimum": 1, "maximum": 480, "default": 28,
                     "description": "Used when start_date/end_date are not given."},
            "dimensions": {"type": "array", "items": {"type": "string", "enum": [
                "query", "page", "date", "country", "device", "searchAppearance"]}, "default": ["query"]},
            "filters": {
                "type": "array",
                "description": "All must match. Example: [{'dimension': 'page', 'operator': 'contains', "
                               "'expression': '/blog/'}]",
                "items": {"type": "object", "properties": {
                    "dimension": {"type": "string", "enum": ["query", "page", "country", "device", "searchAppearance"]},
                    "operator": {"type": "string", "enum": ["equals", "notEquals", "contains", "notContains",
                                                            "includingRegex", "excludingRegex"]},
                    "expression": {"type": "string"}}, "required": ["dimension", "expression"]},
            },
            "row_limit": {"type": "integer", "minimum": 1, "maximum": 100000, "default": 100},
            "data_state": {"type": "string", "enum": ["final", "all"], "default": "final",
                           "description": "final = only finished days (default). all = include the last 2-3 "
                                          "days, whose numbers are still rising."},
            "search_type": {"type": "string", "enum": ["web", "image", "video", "news", "discover", "googleNews"],
                            "default": "web"},
        },
    },
}

GSC_INSPECT_URL = {
    "name": "gsc_inspect_url",
    "description": (
        "Ask Search Console's URL Inspection whether one page is in Google's index and why not: verdict, "
        "coverage state, robots.txt, noindex, fetch result, last crawl, Google-chosen vs declared canonical. "
        "Use for 'is this page indexed' or 'why is this page not on Google'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full page URL, e.g. https://example.com/pricing/"},
            "site_url": _SITE,
            "language": _LANG,
        },
        "required": ["url"],
    },
}

GSC_SITES = {
    "name": "gsc_sites",
    "description": (
        "List the Search Console properties this plugin's key can read, with permission levels, and which "
        "Google identity it uses. Use first when unsure of the exact property name, or to diagnose access."
    ),
    "parameters": {"type": "object", "properties": {}},
}

ALL = [GSC_WEEKLY_REPORT, GSC_AUDIT, GSC_RANK_CHANGES, GSC_QUERY, GSC_INSPECT_URL, GSC_SITES]
