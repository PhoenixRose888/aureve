# P0 Dress Me Recovery Spec — 10 Sep 2026

Branch: `recovery-implementation-2026-09-10`
Base: `aureve-current-2026-09-10`

## Confirmed regressions

### 1. Same-session anti-repeat was lost
Current Sep 10 frontend `Dress Me` clears the result and calls `/dressme` with weather only.
Current Sep 10 backend `DressMeRequest` has no `avoid_item_ids` field and `/dressme` does not forward exclusions into `_build_outfit`.

Historical Sep 7 Charlie branch did both.

### 2. Cross-day Dress Me suggestion history does not exist
`recent_looks_line()` reads only `wear_logs`, so it remembers outfits the user actually logged as worn, not outfits Aureve merely suggested.

This allows the same high-ranked outfit to return on another day even when the wardrobe is large.

### 3. Vague AI Stylist context guard was lost
Current Sep 10 `stylist.tsx` immediately styles `What should I wear tonight?`.
Historical Sep 7 branch first asked for the user's plans/occasion.

## Recovery implementation requirements

### Frontend Dress Me
- Preserve the current result while generating another look long enough to collect its item IDs.
- On `Create Another Look`, send current `resolved_items[].item.id` as `avoid_item_ids` to `/dressme`.
- Reuse `occasion_used` when available.
- Keep Dress Me quota on the `/dressme` endpoint.
- Do not remove the existing single-item swap UI.
- Filter demo pieces from swap options defensively.

### Backend Dress Me
- Add `avoid_item_ids` to `DressMeRequest`.
- Forward `avoid_item_ids` to `_build_outfit`.
- Persist each successful Dress Me suggestion separately from wear history in a new collection such as `suggestion_history`.
- Store at minimum: profile/user scope, source=`dressme`, item_ids, occasion, created_at.
- Never increment `wear_count` or set `last_worn` merely because an outfit was suggested.

### Styling prompt / ranking context
- Read recent Dress Me suggestion history independently from `wear_logs`.
- Strongly avoid exact recent full combinations.
- Strongly deprioritise recently over-suggested hero pieces when the wardrobe provides alternatives.
- Keep occasion, weather, wear count, last worn, underused pieces and learned preferences as inputs.
- Allow justified reuse where constraints genuinely require it.

### AI Stylist vague requests
Restore the context guard for time-only prompts such as:
- `What should I wear tonight?`
- `Help me dress for today`
when no useful occasion/plans are present.

## Acceptance test
1. Generate Dress Me look A.
2. Press Create Another Look at least five times. No repeated core combination.
3. Close/relaunch and generate again. Recent suggestions still influence selection.
4. Test again on another day without logging earlier looks as worn.
5. Confirm wear counts remain unchanged by suggestions.
6. Confirm existing item-swap UI still works.
7. Confirm Week Ahead cross-day avoidance still works.
8. Confirm vague time-only AI Stylist prompt asks for context.
9. Add diagnostics proving exclusions/history penalties were applied.

## Non-goals for this P0 patch
- Do not change RevenueCat, authentication, subscription entitlement, Google Calendar OAuth, deployment config or store settings.
- Do not restore every Sep 7 Charlie change wholesale.
- Do not alter historical branches.
