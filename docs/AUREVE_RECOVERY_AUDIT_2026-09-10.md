# Aureve Recovery Audit — 10 Sep 2026

## Purpose
This file records the recovered Sep 7 direct GitHub work and the mismatch between that preserved branch and the currently tested app. It is documentation only. Do not treat this branch as the production source or merge the historical Sep 7 work wholesale.

## Canonical historical references
- Emergent snapshot: `aureve-current-2026-09-07`
- Direct-fix branch: `charlie-launch-fixes-2026-09-07`
- Historical PR: #1 `Launch-critical Aureve fixes`
- Recovery audit branch: `recovery-audit-2026-09-10`

The Charlie branch is 36 commits ahead of the Sep 7 Emergent snapshot and 0 behind.

## Critical recovered fact 1 — Dress Me single-item swap already existed
The preserved `frontend/app/(tabs)/dressme.tsx` contains:
- `Tap any item to change`
- a modal picker opened by tapping a rendered outfit item
- category-matched wardrobe options
- search within the wardrobe
- replacement of only the selected item via `swapItem`
- demo pieces filtered out of the swap wardrobe

Current real-device QA reported that the user could not replace one unavailable/unwanted item without regenerating the whole outfit. Treat this as a regression/reconciliation issue.

## Critical recovered fact 2 — same-session anti-repeat logic already existed
The Sep 7 direct-fix work changed Dress Me so `Create Another Look` sends the current outfit item IDs as `avoid_item_ids` back through `/dressme`.

Backend `DressMeRequest` was extended to accept `avoid_item_ids`, and `/dressme` forwards them into `_build_outfit`.

Current QA still shows the same black dress + brown cardigan + boots + bag combination repeated multiple times in one session. Therefore one of the following is true in the currently tested build:
1. the Sep 7 logic never reached the build,
2. it was overwritten later,
3. it is bypassed in a newer flow, or
4. the backend receives the exclusion list but does not enforce it strongly enough.

## Critical recovered fact 3 — cross-day Week Ahead rotation had already been built before Sep 7
Neo commit `4cf2d269011d6fbbf0b14e680831b22bfc03605c` added cross-day variety support:
- `/stylist/suggest` accepts `avoid_item_ids`
- `_build_outfit` gets a list of items already used elsewhere in the week
- the prompt explicitly asks for different silhouette, colour, footwear and accessories and discourages reusing hero pieces
- `planner.tsx` gathers item IDs from other planned days and passes them as `avoid_item_ids`

The Sep 7 Charlie branch still contains this Week Ahead logic.

Current QA shows the same core outfit returning again on separate days in Dress Me. This proves the remaining P0 is broader than Week Ahead. Dress Me needs persistent rolling-history awareness across days, not only current-screen avoidance and not only planner-week avoidance.

## P0 launch blocker — styling repetition
Aureve's core value proposition is intelligent outfit styling from a user's existing wardrobe. The currently tested build repeatedly selects the same core outfit despite a large wardrobe.

Required recovery target:
- current-screen exclusions must actually be enforced
- recently suggested full outfits must be strongly excluded across a rolling history window
- recently suggested hero items must be strongly deprioritised across days
- wear count, last worn, underused items, occasion, weather and user preferences should all participate in ranking
- repeats should occur only for a clear contextual reason or explicit user request
- diagnostics should record candidate selection, recent-history penalties and final item choice

## Important superseded Sep 7 decisions
Do not restore all historical changes blindly.

Examples:
- Sep 7 removed the wardrobe-grid `Pairs with X` badge; later product review approved the clearer `Pairs with 80 / 82` treatment.
- Sep 7 hid Calendar for launch; later OAuth work continued, so current launch strategy must decide whether Calendar stays hidden or is fixed.
- Reviewer/demo handling evolved later. Preserve intentional reviewer samples while preventing real-user leakage.

## Safe reconciliation workflow
1. Preserve `charlie-launch-fixes-2026-09-07` unchanged as evidence.
2. Obtain/export the exact current Emergent source snapshot into GitHub.
3. Compare current source against the Sep 7 branch file-by-file.
4. For each current P0/P1 issue, selectively re-implement or cherry-pick only still-valid fixes.
5. Use a fresh implementation branch for recovery work.
6. Keep PR #1 draft and never merge it wholesale.
7. Real-device acceptance tests are mandatory before merging any restored styling logic.
