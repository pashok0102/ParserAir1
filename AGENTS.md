## Summary

### Done
- Fixed price regex to support `\u2009` (thin space) in prices like `15 ⁠796`
- Fixed mobile search button: added `width: 100%` to `.search-button`
- Added `STATICFILES_DIRS` → `project/dist/`
- Added `spa_serve` catch-all view + URL pattern for SPA
- Fixed catch-all regex: `^(?!/api/|/admin/|/static/).*`
- **Range + 'both' sources**: removed Aviasales-cloning for date range 'both' — now falls through to per-day parallel search (real prices from each source) (views.py)
- **Tutu link fix**: removed slug-based `route[0]` parameter — now only adds IDs if both from/to IDs are known; skips route[0] entirely for unknown-city pairs to avoid "выберите направление" error
- Kupibilet sales filtering: returns only timed offers (`hot_expires_at`), removed Aviasales fallback when `hot_offer=True`
- Deployed to VPS (kgswlznbth)

### Key decisions
- 'both' + date range now runs 3 parsers per day via generic fallback (was: clone Aviasales prices to all 3 sources)
- Tutu link without known IDs → no `route[0]` param (shows direction page, user picks date manually) instead of broken slug-based route
- Kupibilet hot-offer mode returns empty when no timed offers found (no fallback to Aviasales)

### Known issues
- Tutu link works only for cities with known IDs (MOW=491, AER=78, REN=64) — other cities show selecting-date page
- Kupibilet sales page shows "Выгодно" label instead of "−30% · 12:34:56" timer for most cards → hot offer mode finds few/no results
- `parser_metrics` might fail on VPS with KeyError for keys not inserted yet
- `build_fast_reference_range` still clones Aviasales data for 'tutu' and 'kupibilet' date ranges (views.py ~595-607)
