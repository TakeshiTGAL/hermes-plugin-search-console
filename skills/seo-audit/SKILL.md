---
name: seo-audit
description: SEO audit of the user's own site from its real Search Console data — indexing, CTR anomalies, decaying pages, striking-distance queries, cannibalisation, and the 3 fixes to do first. Use when asked to "audit my site", "SEO health check", or "why is my organic traffic down".
---

# SEO audit (Search Console)

Adapted from the `seo-audit` skill in Ryze AI's open-seo-mcp-skills (MIT, see NOTICE), rewritten for
this plugin's tools, which read Google Search Console directly with the user's own key.

Everything comes from the site's own Search Console data. Never fill gaps with third-party estimates.

## Workflow

1. **Property.** If the user did not name one and `gsc_audit` answers `site_required`, call `gsc_sites`
   and pick the property matching their domain; ask only when it is truly ambiguous.
2. **Run `gsc_audit`** (default 28 days vs the 28 before). It already leaves out Google's unfinished
   last 2-3 days, so do not "fix" the dates by hand.
3. **Read the result in this order:** `next_fixes` (already ranked: blocking index problems first, then
   by clicks at stake), then `index`, `rank_drops`, `ctr_anomalies`, `striking_distance`,
   `cannibalization`, `decaying_pages`.
4. **Dig only where it changes the advice.** For a page in `next_fixes`, `gsc_inspect_url` shows why it
   is not indexed; `gsc_query` with a `page` filter shows which queries it earns.
5. **Traffic quality (optional).** This plugin does not read GA4. If another GA4 tool is available,
   cross-check organic sessions and conversions for the pages in `next_fixes`.

## Output

Start with the verdict (is the site healthy, and the single most worthwhile fix), then the three fixes
with the page, the evidence numbers and the concrete change. Then short supporting lists. If the user
just wants the report, send the `message` field as is. Do not pad to three fixes when the result has
fewer — say the data is thin instead.

## If it fails

Each error carries `fix`: relay it in plain words (it names the exact Search Console or Google Cloud
screen). `no_access` means the key's e-mail address has to be added in Search Console → Settings →
Users and permissions.
