# Aureve Recovery Audit — 10 Sep 2026

## Purpose
This file records the recovered Sep 7 direct GitHub work and the mismatch between that preserved branch and the currently tested app. It is documentation only. Do not treat this branch as the production source or merge the historical Sep 7 work wholesale.

## Canonical references
- Sep 7 Emergent snapshot: `aureve-current-2026-09-07`
- Direct-fix branch: `charlie-launch-fixes-2026-09-07`
- Current Emergent export: `aureve-current-2026-09-10`
- Historical PR: #1 `Launch-critical Aureve fixes`
- Recovery audit branch: `recovery-audit-2026-09-10`

The Charlie branch is 36 commits ahead of the Sep 7 snapshot and 0 behind. The new Sep 10 Emergent export has now been pushed and inspected.

## Confirmed current-source finding 1 — single-item swap is actually present
The current Sep 10 Emergent source still contains the Dress Me single-item swap UI:
- `Tap any item to change`
- tapping a rendered item opens the swap modal
- category-matched wardrobe options
- search
- replacement of only the selected item via `swapItem`

So this feature was not lost from source. The earlier QA complaint is now reclassified as a discoverability / device-behaviour check, not a proven code regression. The current branch does not defensively filter demo pieces out of the swap wardrobe, though the historical Charlie branch did.

## Confirmed current-source finding 2 — same-session anti-repeat logic WAS lost
The current Sep 10 frontend `Dress Me` implementation resets the result and calls `/dressme` with weather only. It does not send the current outfit's item IDs back as `avoid_item_ids` when `Create Another Look` is pressed.

The current Sep 10 backend `DressMeRequest` also does not define `avoid_item_ids`, and `/dressme` calls `_build_outfit(...)` without any exclusion list.

This is a confirmed regression relative to the Sep 7 Charlie branch, not a theory. It directly explains why repeated requests in the same Dress Me session can return the same core outfit.

## Confirmed current-source finding 3 — cross-day Week Ahead rotation survived
The current Sep 10 `planner.tsx` still gathers item IDs from other planned days and passes them to `/stylist/suggest` as `avoid_item_ids`.

So the Week Ahead cross-day mechanism itself survived. The remaining launch blocker is specifically broader Dress Me rotation, not the planner implementation alone.

## Confirmed current-source finding 4 — Dress Me history only knows what was actually worn
The current Sep 10 backend includes `underused_line()` and `recent_looks_line()`.

However, `recent_looks_line()` reads only from `db.wear_logs` and returns `RECENTLY WORN combinations`. It does not record or retrieve outfits that Aureve merely suggested in Dress Me but the user did not log as worn.

Concrete failure mode:
- Aureve suggests outfit A on Monday.
- The user does not mark outfit A as worn.
- Tuesday's Dress Me history contains no record that outfit A was suggested.
- The model may select outfit A again.

Therefore a correct P0 fix needs persistent **suggestion history** separate from wear history. Suggested looks should be recorded without incrementing `wear_count` or changing `last_worn`.

## Confirmed current-source finding 5 — vague AI Stylist context guard WAS lost
The current Sep 10 `stylist.tsx` immediately sends vague prompts such as `What should I wear tonight?` to `/stylist/chat`.

The Sep 7 Charlie branch had a frontend guard that asked what the user was doing before styling vague time-only requests. Current QA screenshots match the Sep 10 source: the guard is absent.

This is another confirmed regression relative to the Charlie branch.

## Confirmed current-source finding 6 — reviewer/demo isolation hardening WAS lost
The current Sep 10 backend sets `show_demo` true for the reviewer account regardless of whether that reviewer wardrobe contains real uploaded pieces.

The Sep 7 Charlie branch had stronger logic: once real reviewer uploads existed, seeded demo pieces were no longer shown/reseeded into the real working wardrobe. This hardening is absent from the current source and should be selectively reconsidered because current QA has shown sample/demo language leaking into user-facing intelligence.

## P0 launch blocker — styling repetition
Aureve's core value proposition is intelligent outfit styling from a user's existing wardrobe. The current source plus real-device QA now establish two separate rotation defects:

1. **Same-session regression:** `Create Another Look` no longer passes current-item exclusions.
2. **Cross-day design gap:** Dress Me has no persisted suggestion history, only wear history.

Required recovery target:
- restore current-screen `avoid_item_ids` support through frontend + `/dressme` backend
- persist Dress Me / stylist suggestion-history records separate from wear logs
- strongly exclude recent full combinations across a rolling history window
- strongly deprioritise recently over-suggested hero pieces across days
- retain wear count, last worn, underused items, occasion, weather and user preferences as inputs
- do not increment wear counts unless the user explicitly logs a wear
- add diagnostics for recent-history penalties and final item choice

## Minimum P0 acceptance test
Do not call styling fixed until all pass on a populated real wardrobe:
1. Generate Dress Me look A.
2. Press `Create Another Look` at least five times. No subsequent look may reuse the same core combination; hero overlap must materially reduce unless constraints require reuse.
3. Close/relaunch and generate again. Recent suggestions must still influence selection.
4. Repeat on a later calendar day without marking earlier looks worn. Suggestion history must still influence selection.
5. Verify suggestion history does not alter `wear_count` or `last_worn`.
6. Verify Week Ahead still produces occasion-appropriate looks with meaningful cross-day variety.
7. Verify tapping one Dress Me item replaces only that item on-device.
8. Verify vague `What should I wear tonight?` asks for context unless occasion is already known.
9. Capture diagnostics proving exclusions/penalties were applied.

## Important superseded Sep 7 decisions
Do not restore all historical changes blindly.

Examples:
- Sep 7 removed the wardrobe-grid `Pairs with X` badge; later product review approved the clearer `Pairs with 80 / 82` treatment.
- Sep 7 hid Calendar for launch; later OAuth work continued, so current launch strategy must decide whether Calendar stays hidden or is fixed.
- Reviewer/demo handling evolved later. Preserve intentional reviewer samples while preventing real-user leakage.

## Safe reconciliation workflow
1. Preserve `charlie-launch-fixes-2026-09-07` unchanged as evidence.
2. Preserve `aureve-current-2026-09-10` unchanged as the current Emergent snapshot.
3. Use a new implementation branch for selective recovery.
4. Restore only still-valid fixes, starting with P0 Dress Me rotation.
5. Keep PR #1 draft and never merge it wholesale.
6. Real-device acceptance tests are mandatory before merging restored styling logic.

## Recovery audit status
Source reconciliation is now materially complete enough to begin selective implementation. The most important regression is no longer speculative: same-session Dress Me exclusion support is absent from the Sep 10 source, while the single-item swap and Week Ahead cross-day logic are still present.
