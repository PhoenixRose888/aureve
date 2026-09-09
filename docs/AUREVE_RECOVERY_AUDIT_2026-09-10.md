# Aureve Recovery Audit — 10 Sep 2026

## Purpose
This file records the recovered Sep 7 direct GitHub work, the exact Sep 10 Emergent export, and the selective recovery work built from that comparison. Historical branches remain preserved. Do not merge the Sep 7 branch wholesale.

## Canonical references
- Sep 7 Emergent snapshot: `aureve-current-2026-09-07`
- Sep 7 direct-fix branch: `charlie-launch-fixes-2026-09-07`
- Sep 10 exact Emergent export: `aureve-current-2026-09-10`
- Recovery audit branch: `recovery-audit-2026-09-10`
- Selective implementation branch: `recovery-implementation-2026-09-10`
- Historical recovery PR: #1 `Launch-critical Aureve fixes`
- Current selective recovery PR: #3 `P0 Dress Me recovery implementation`

## Source reconciliation findings

### Dress Me same-session rotation was genuinely lost
The Sep 10 export reset the current result before regeneration and sent no `avoid_item_ids` to `/dressme`. Its backend `DressMeRequest` also no longer accepted or forwarded `avoid_item_ids`.

The Sep 7 Charlie branch had both pieces. This is a confirmed regression, not an inference.

### Dress Me single-item swap survived in source
The Sep 10 export still contains:
- `Tap any item to change`
- a modal swap picker
- category-matched wardrobe choices
- search
- replacement of only the selected item

Therefore the user's report that item swapping was unavailable is now treated as a discoverability/device-behaviour issue rather than missing source code.

### Week Ahead variety survived
`planner.tsx` in the Sep 10 export still collects item IDs from other planned days and passes them as `avoid_item_ids` to `/stylist/suggest`.

### Cross-day Dress Me had a deeper design gap
The backend's existing `recent_looks_line()` reads only `wear_logs`, meaning it remembers outfits actually logged as worn but not outfits merely suggested by Dress Me.

That allows a Monday suggestion to return Tuesday if the user never logged Monday's outfit as worn.

### AI Stylist vague-context guard was lost
The Sep 7 branch asked for plans/occasion before styling materially vague prompts such as `What should I wear tonight?`. That guard was absent in the Sep 10 export.

### Reviewer/demo hardening was lost
The Sep 10 backend broadly enabled demo visibility for the reviewer account even after real uploads, and server-side outfit/plan/wear endpoints lacked the stronger demo filters from the Sep 7 branch.

## Selective recovery implemented on `recovery-implementation-2026-09-10`

### P0 commit `99e6f4e610695025fc80f8d6a4f0096eb9f9886f`
`fix: restore Dress Me rotation and suggestion history`

Implemented:
- restored frontend `avoid_item_ids` on Create Another Look
- restored backend `DressMeRequest.avoid_item_ids`
- `/dressme` now forwards exclusions through `_build_outfit`
- current on-screen outfit items are removed from the candidate pool when enough alternatives exist, making same-session avoidance a hard constraint rather than only prompt wording
- introduced `style_suggestions` persistence separate from `wear_logs`
- Dress Me records AI-suggested item combinations without incrementing wear counts
- recent suggested combinations and repeatedly suggested item IDs feed back into the styling prompt
- bounded suggestion-history storage per wardrobe/source
- added `STYLE_ROTATION` diagnostics containing exclusions, recent-history count and selected IDs
- restored the AI Stylist vague-occasion context question
- backend syntax verification passed in GitHub Actions

GitHub Actions run: `34408068785` — SUCCESS.

### P1 commit `e8b86cc0b760fcd3bde75f7b3f8325e13a780acd`
`fix: restore reviewer demo isolation`

Implemented:
- reviewer demo visibility is now dynamic per active profile
- seeded demo pieces remain only while the reviewer wardrobe has no real pieces
- once real reviewer uploads exist, old demo items/outfits/wear logs/plans are removed instead of being reseeded on restart
- `/outfits`, `/plans`, and `/wear` exclude demo rows server-side whenever demo visibility is off
- backend syntax verification passed in GitHub Actions

The first P1 workflow attempt failed safely before commit because a separate monetary-insights replacement did not match the current source exactly. No partial source changes were committed. The patch was narrowed to demo isolation and rerun successfully.

GitHub Actions run: `34408301427` — SUCCESS.

## Still intentionally not merged
PR #3 remains draft. No recovery code has been merged into the Sep 10 Emergent snapshot or production.

## Remaining work before merge
1. Static/frontend QA on the implementation branch.
2. Reconcile monetary wardrobe-value / cost-per-wear code separately against the exact current source rather than forcing an old patch.
3. Real-device acceptance test for Dress Me:
   - generate look A
   - Create Another Look at least five times
   - verify meaningful hero-piece/core-look rotation
   - close/relaunch and regenerate
   - repeat on a later day without marking prior looks worn
   - verify suggestion history still influences selection
   - confirm wear_count/last_worn are unchanged until explicit wear logging
4. Confirm item swap is visible and functional on-device.
5. Confirm vague `What should I wear tonight?` asks for context.
6. Verify reviewer with real uploads no longer mixes seeded demo data into intelligence.
7. Review `STYLE_ROTATION` diagnostics from device testing.

## Recovery conclusion
The missing continuity has now been reconstructed into three separate facts:
- some Sep 7 fixes survived into Sep 10,
- some were overwritten/lost,
- and at least one core issue, cross-day Dress Me repetition, required a new design fix beyond the old Sep 7 work.

The project now has a preserved history branch, an exact current snapshot, an audit branch, and a selective implementation branch. No historical evidence has been overwritten.
