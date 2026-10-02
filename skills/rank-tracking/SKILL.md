---
name: rank-tracking
description: Rank tracking without a tracker subscription — what moved between two periods from Search Console's real positions. Use when asked "how are my rankings", "what moved this week/month", "did the Google update hit me", or to set up a weekly ranking report.
---

# Rank tracking (Search Console)

Adapted from the `rank-tracking` skill in Ryze AI's open-seo-mcp-skills (MIT, see NOTICE), rewritten
for this plugin's tools.

Rank trackers estimate positions by scraping results. Search Console records the position Google
actually showed the site at. Use that number.

## Workflow

1. **Windows.** Default `gsc_rank_changes` compares the last 28 finalised days with the 28 before. For
   "this week" use `days: 7`. If the user names an event ("since we moved the site", "since the March
   core update"), pass `current_start`/`current_end` around that date.
2. **Queries and pages.** Run with `dimension: "query"`, then `dimension: "page"` when page-level
   movement matters.
3. **Classes.** winners, losers (sorted by clicks lost — a 4→7 drop on a query that brings customers beats
   a 40→80 crash on one nobody clicks), new, lost.
4. **Answer the question asked.** For an update question, say plainly whether the before/after numbers
   show an effect.

## Output

Verdict first (net direction and the single biggest move), then winners, losers, new, lost with
positions before → after and the click change.

## Every week

`gsc_weekly_report` is the scheduled version. Script-only (no LLM cost):
`hermes search-console-checkup schedule <site> --deliver telegram`, then run the `hermes cron create` line it
prints. Or ask in chat: "Every Monday at 9, run gsc_weekly_report for <site> and send me its message."
