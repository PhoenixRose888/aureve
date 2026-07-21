# Aureve — Your AI Personal Stylist

## Fixed (2026-07-21i) — blank wardrobe photos
- 🐞 **Blank item images fixed.** Root cause: some stored photos (esp. AI background-removed images ~460KB base64, and large uploads) were too big/uncompressed and rendered blank on device. Fix: backend `compress_b64` (Pillow) normalises every image to a bounded JPEG (≤1024px, q72) on `POST/PUT /items` and on `/capture` clean_image; ran a one-time migration that repaired 10 existing oversized photos. Verified iteration 11 (7/7): ~11× size reduction, all photos valid JPEG, 0 oversized remain.



## Implemented (2026-07-21h) — Exceptional wardrobe capture
- ✅ **One-shot capture with AI background removal** — new `POST /api/capture` runs auto-tagging (GPT vision) + background removal (Gemini `gemini-3.1-flash-image-preview`) in parallel, returning `{analysis, clean_image}`. Add-item now calls it: pieces are auto-filled AND get a clean, catalogue-style photo on a neutral background (with a one-tap "Original" revert). `/analyze-item` kept for compat. Free (capture is core). Verified iteration 10 (11/11).



## Implemented (2026-07-21g) — Google Calendar integration
- ✅ **Calendar-aware Dress Me** — custom Google OAuth (read-only `calendar.readonly`, own client). Endpoints: `/calendar/status`, `/calendar/authorize`, `/api/calendar/callback` (public, state-keyed), `/calendar/events`, `/calendar/disconnect`; tokens per-account in `calendar_tokens` (auto-refresh). `POST /api/dressme` now pulls today's events and styles for the real schedule (returns `calendar_events`). UI: connect/schedule on the Dress Me screen + a Google Calendar row in Profile. Creds in backend/.env (GOOGLE_CALENDAR_*). Redirect URI is the preview URL — must add the production URL to the same OAuth client after deploy.



## Implemented (2026-07-21f) — Share your look
- ✅ **Share/download Try-On looks** — new `src/utils/shareImage.ts` (expo-sharing on native, direct download on web). "Share" button on the Try-On result and a "Share this look" pill on saved Try-On looks in the Looks gallery. Added dep `expo-sharing` (+ expo-file-system/legacy). Bundle compiles clean.



## Implemented (2026-07-21e) — Try-On stickiness
- ✅ **Remembered body photo** — the try-on photo is saved per profile (`GET/PUT/DELETE /api/tryon/photo`, `body_photos` collection) and auto-loads, so users don't re-upload each session.
- ✅ **Save Try-On to Looks** — try-on results save as an outfit (`source:'tryon'`, `preview_image` base64) via the existing `/outfits`; the Looks "Saved" tab shows the generated image as a full cover with a TRY-ON badge. Verified via curl; frontend lint-clean.



## Implemented (2026-07-21d) — Virtual Try-On (Nano Banana)
- ✅ **Virtual Try-On** (Premium) — `POST /api/tryon {person_image, item_ids[], outfit_id?}` sends your photo + garment photos to Gemini `gemini-3.1-flash-image-preview` and returns a photorealistic image of you wearing the outfit. New `app/tryon.tsx` (pick your photo → select wardrobe pieces → generate). Entry points: Home CTA + "See it on me" from a Dress Me result (prefills the items). Premium-gated; validates photo/items. Verified iteration 9 (7/7, real generation ~8s).



## Implemented (2026-07-21c) — 7-day free trial + conversion ribbon
- ✅ **App-managed 7-day free trial** (no card, once per account). `POST /api/membership/trial` grants 7 days Premium instantly (premium_source='trial', trial_used=true). `/membership/plans` + `/auth/me` expose trial_used / trial_eligible / trial_days / premium_source; paid grants tagged premium_source='paid'. Paywall shows a "Start 7 days free" hero when eligible; Home shows a "Try Premium free for 7 days" ribbon (gift icon) that swaps to "Unlock your AI stylist" after the trial. Verified iteration 8 (9/9): grant, no-reuse, expiry lapse → 402, regression.
- 🔜 Next: Virtual Try-On (Gemini Nano Banana) → then Calendar integration.



## Implemented (2026-07-21b) — Dress Me + calm brand identity
- ✅ **Flagship "Dress Me"** (Premium) — one-tap daily outfit. `POST /api/dressme` infers today's occasion from the planner (else "a normal day"), uses live weather + the ready wardrobe via the shared `_build_outfit` engine, returns confidence score + reasoning. New `app/dressme.tsx` (charcoal, auto-runs on open) and it's now the **primary Home CTA**; custom-occasion Stylist demoted to secondary. Verified iteration 7 (6/6).
- ✅ **Brand identity refresh** to the "calm, timeless, inclusive" direction: palette → soft ivory `#FAF9F6` + deep charcoal `#232323`, muted-emerald accent `#3F6B5B`, sage success `#7A9E7E`, terracotta error `#C46A5C`, sapphire info `#4B6587`. Typography switched from ornate serif (Cormorant) to **Plus Jakarta Sans** (local static TTFs) — modern, readable, timeless. Voice stays never-judgemental ("Wear everything you own").



## Implemented (2026-07-21) — Rebrand + Premium membership
- ✅ **Rebrand to "Aureve — Your AI Personal Stylist."** across app UI + AI persona (backend prompts). Storage keys unchanged.
- ✅ **Premium membership (per-account / whole household)** via Stripe Checkout (emergentintegrations one-time payment → time-boxed `users.premium_until`; $9.99/30d monthly, $79.99/365d annual). Endpoints: `GET /api/membership/plans`, `POST /api/payments/checkout`, `GET /api/payments/status/{id}` (idempotent grant, owner-scoped). Paywall `app/premium.tsx` + `app/premium-success.tsx` (polls status).
- ✅ **Gating philosophy — wardrobe always free, AI gated.** Free: unlimited wardrobe/insights + 5 AI stylist outfits/day + 1 colour analysis/month + 1 profile. Premium-only (HTTP 402 on free): packing, capsule, shop-check, missing-piece, health-report, item compatibility, and extra household profiles (up to 6). `enforce_limit` + `usage` collection meter free calls. FE routes 402 → paywall and shows lock badges + upsell banners.
- ✅ Verified: testing agent iteration 6 — 37/37 backend passing (gating, metering, payments, household cap, regression). FE lint clean.
- 🔮 Deferred (future premium): flagship **Dress Me** one-tap daily outfit, Virtual Try-On, Calendar integration, AI style-evolution tracking, 7-day Premium trial.


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

## Implemented (2026-07-20h) — Beauty + instant pairing badges
- ✅ **Hair & Makeup recommendations** — new `POST /api/beauty/suggest` (AI colour analysis from the active profile's skin tone + undertone; optional occasion). New `app/beauty.tsx` screen reached from a CTA in the Profile tab: returns a flattering colour palette, makeup (base/blush/lip/eye/tip), hair (colour/style/tip), what to avoid, and an occasion note. Gracefully prompts to add skin tone/undertone if the profile is empty. Verified iteration 5.
- ✅ **Instant "pairs with" badges** — `GET /api/items` now returns a rule-based `pairs_count` per item (no AI, instant), and wardrobe cards show a link-icon badge with the count. Pairing respects category logic (no same-category, Dresses don't pair with Tops/Bottoms) and one-step formality adjacency for main garments; laundry items are excluded. Scoped per profile. Verified iteration 5 (9/9).


- ✅ **Household / Multi-Profile architecture VERIFIED** — one account, many wardrobe profiles. Backend `get_scope` resolves the active profile from the `X-Profile-Id` header and scopes ALL data per profile. Testing agent iteration 4: 20/20 passing; strict per-profile isolation confirmed (Aura vs David see only their own items/outfits/plans/wear/laundry; cross-profile GET/PUT → 404). Profile switcher lives in the Profile tab.
- ✅ **Worn-photo AI isolation (Msg 371)** — POST /api/analyze-item now takes an optional `category_hint`. Adding a piece pops a "Which piece is this?" step (category chips + "Just detect it for me") so the vision AI focuses on one garment when several are worn. Verified: hint='Tops' → category='Tops'; no hint still works.
- ✅ **Laundry discoverability (Msg 463)** — always-visible laundry (droplet) button in the Wardrobe header with a live count badge, plus a friendly "Laundry basket is empty" state when nothing is in the wash.
- ✅ **Crop trap (Msg 371)** — confirmed already resolved (`allowsEditing:false`); photos go straight through.


- ✅ **Personal Style Profile** — new Style Profile screen (from Insights tab): height, weight, bust, waist, hips, inseam, arm, shoulder, shoe size + body shape, skin tone, undertone, notes (all optional). `PUT /api/profile` (merges). Fed into the Stylist, Capsule and Packing AI prompts to flatter body shape + skin tone.
- ✅ **BUGFIX packing 500** — future travel dates (`start_offset_days`) crashed on Open-Meteo null temps; now filtered. Packing has a "When's the trip?" selector (Today / 3 days / a week / 2 weeks) and forecasts the actual travel window.
- ✅ **BUGFIX image-picker crop trap** — `allowsEditing:false` so photos go straight through (no forced crop).
- ✅ **BUGFIX weather hang / frozen pages** — 8s timeout on location so it never spins forever; Home/Stylist degrade gracefully to "styling without live weather".
- ✅ **BUGFIX session drop cascade** — API client no longer clears the token on a transient 401 (was causing "nothing works" / request-failed cascades).
- ✅ **Capsule occasion** — capsule builder now takes an optional purpose/occasion (e.g. business+pleasure trip).
- ✅ Verified: testing agent 17/17.

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
  - Makeup & hair recommendations that use skin tone / undertone from the Style Profile.
  - Worn-photo analysis with a "which piece is this?" confirmation step (figure-aware learning).
  - Push reminder the night before a planned day ("tomorrow you're wearing X") — Emergent push (real device only).
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
