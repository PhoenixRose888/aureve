# Aura — Smart AI Wardrobe & Personal Stylist

## Original Problem Statement
A digital wardrobe app that solves three problems: (1) cataloguing what you own (photo + tags: category, colour, fabric, season, fit, brand, size, wear frequency, flatter), (2) building outfits using ONLY items you own based on weather + occasion + what suits you, and (3) shopping restraint — checking a potential purchase against what you already have. The killer feature is a feedback loop where users rate worn outfits (flattering/comfort/confidence) so the AI learns their real style. Also framed as reducing decision overload (helpful for ADHD users).

## Architecture
- **Frontend:** Expo (SDK 54) + expo-router file-based routing, react-native-reanimated, @gorhom/bottom-sheet, react-native-keyboard-controller, expo-image, expo-image-picker, expo-location.
- **Backend:** FastAPI + Motor (MongoDB). All routes under `/api`.
- **AI:** OpenAI `gpt-5.4` (vision + text) via `emergentintegrations` (EMERGENT_LLM_KEY).
- **Auth:** Emergent-managed Google OAuth; Bearer session tokens (7-day TTL) in `user_sessions`.
- **Weather:** Open-Meteo (no key); reverse geocode on device via expo-location.
- **Design:** "Editorial Mobile LIGHT" — Cormorant Garamond display + Geist body, paper-white surfaces, charcoal primary, muted rust accent.

## User Personas
- **The overwhelmed dresser** — owns lots, wears little, wants "just tell me what to wear".
- **The mindful shopper** — wants to stop buying duplicates and track cost-per-wear.
- **The style learner** — wants recommendations that flatter *them*, not generic fashion.

## Core Requirements (static)
- Wardrobe catalogue with photos + AI-detected attributes.
- AI outfit builder constrained to owned items, weather/occasion aware.
- Worn-outfit rating feedback loop feeding future suggestions.
- Shopping checker (buy/skip verdict + duplicates + gap).
- Insights: cost-per-wear, most/least worn, confidence scores, wardrobe health, "Missing Piece".

## Implemented (2026-07-20e)
- ✅ **Seasonal / Purpose Capsule Builder** (`app/capsule.tsx`) — pick a theme (Autumn/Winter/Spring/Summer/Work/Weekend/Travel/Evening); AI curates a lean mix-and-match capsule from owned items with outfit combos, a tip, gaps to complete it, and a "save to looks". New `POST /api/capsule/build`. Reached from Home.
- ✅ **Full backend regression: 46/46 passing** (30 core + 16 new endpoints) via testing agent — laundry exclusion, confidence score, compatibility, plans, packing, capsule, health report all verified.

## Implemented (2026-07-20d)
- ✅ **Outfit Planner / Calendar** (`app/planner.tsx`) — a 7-day agenda; tap any day to plan an outfit by picking a saved look or auto-styling with AI. Reached from Home. New `plans` CRUD: `POST/GET/DELETE /api/plans` (range query + hydrated items; snapshots item_ids from linked outfits).

## Implemented (2026-07-20c)
- ✅ **"Looks" gallery** (`app/looks.tsx`) — Saved looks (AI-styled / manual / capsule, with delete) + wear History (date, occasion, ratings, item thumbnails). Reached from Home. New `DELETE /api/outfits/{id}` and hydrated `GET /api/wear`.
- ✅ **Save packing capsules** — capsules can be saved to Looks (source "capsule").
- ✅ **Auto-laundry loop** — `mark_dirty` on `/api/wear`; Stylist rate card has a "move pieces to laundry" toggle, and item detail prompts to add to laundry right after "I wore this today" (Zero-Friction).

## Implemented (2026-07-20b)
- ✅ **Laundry-aware availability** — every item has a status (Ready / Dirty / Washing / Drying), set from item detail. Anything not "Ready" is automatically excluded from Stylist, Packing and Compatibility suggestions. Wardrobe shows laundry badges + a "N in the laundry" filter banner; new `GET /api/laundry` endpoint. Verified end-to-end.

## Implemented (2026-07-20)
- ✅ **Outfit Confidence Score** — Stylist now returns a 0-100 score (colour harmony, style cohesion, occasion + weather fit, proportion, wardrobe use) with 3-5 justifying reasons, shown as a prominent dark score card.
- ✅ **Wardrobe Intelligence / Compatibility Engine** — per-item versatility score (0-100) + star-rated (1-5) "pairs best with" list and stylist explanations, on-demand from item detail.
- ✅ Richer AI capture: formality, warm/cool tone, style, sleeve length added to recognition + item detail.
- ✅ Zero-Friction: item name is now optional (AI/attributes fill it); no forced fields.

## Implemented (2026-07-19)
- ✅ Google OAuth login (Emergent), session handling, logout.
- ✅ Wardrobe CRUD with hanging + worn photos (base64), filter chips, editorial grid.
- ✅ AI photo cataloguing (`/api/analyze-item`) auto-fills name/category/colour/fabric/pattern/season/condition/estimated value.
- ✅ AI Stylist (`/api/stylist/suggest`) — outfit from owned items only, weather+occasion aware, with hair/makeup/confidence tips; learns from wear feedback.
- ✅ Rating feedback loop (`/api/wear`) + wear-count/cost-per-wear tracking.
- ✅ Shop Check (`/api/shop-check`) — verdict, similar owned items, outfits added, gap.
- ✅ Insights dashboard + AI "Missing Piece" gap analyzer (`/api/insights/missing-piece`).
- ✅ Live weather (Open-Meteo) on Home + Stylist.
- ✅ Backend tested: 30/30 endpoints passing.

## Prioritized Backlog
- **P1**
  - Push reminder the night before a planned day ("tomorrow you're wearing X") — Emergent push notifications (real device only).
  - Precompute compatibility for instant per-item "matches" counts on cards.
- **P2**
  - Premium tier + paywall (free: 100 items / 3 outfits-a-day; premium: unlimited + advanced styling) via Stripe/RevenueCat.
  - Virtual try-on (AI-generated preview of you in the outfit).
  - Social mode (compare wardrobes / borrow from friends).
  - Deeper figure-aware learning from worn photos (cuts/waist heights/lengths).
  - Split server.py into routers; add timeout wrapper on LlmChat calls; trim base64 from insights list payloads.

## Next Tasks
1. Build the "Looks" gallery screen to browse saved outfits + outfit history.
2. Packing capsule generator (high subscription-driver per user feedback).
3. Deepen figure-aware learning using worn photos.

## Notes / Mocks
- No mocked APIs. All AI + weather + auth are live.
- Test session seeded for automated backend testing: `Authorization: Bearer test-session-token-aura-123` (user_testaura01). Real users get their own user_id via Google.
- Features needing a native build to fully test: none blocking; camera/photos/location handled via expo APIs and work in Expo Go (Google OAuth login works in Expo Go too).
