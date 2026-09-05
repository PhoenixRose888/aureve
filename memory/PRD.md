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

## Deployment Fix — iOS EAS Build (2026-06)
- BLOCKER (resolved): iOS EAS build failed at CocoaPods INSTALL_PODS — `PurchasesHybridCommon` version conflict.
  - Cause: `react-native-purchases@10.4.4` (needs PurchasesHybridCommon 18.22.2) vs `react-native-purchases-ui@10.6.0` (needs 18.28.0).
  - Fix: bumped `react-native-purchases` -> 10.6.0 via `yarn expo install`. Both packages now aligned at 10.6.0; both require PurchasesHybridCommon 18.28.0. Verified in package.json, node_modules, yarn.lock.
- NOTE: react-native-purchases has NO Expo config plugin (autolinked). Do NOT add it to app.json plugins — it breaks the Expo build.
- User action required: re-trigger the iOS build via Publish; agent cannot start EAS builds directly.

## App Store Readiness Fixes (2026-06)
- Sign in with Apple added (Apple 5.1.1(v)): backend POST /api/auth/apple verifies identity token vs Apple JWKS (RS256, iss/aud/exp), upserts by apple_sub, mints 7-day session, migrates guest data. Env APPLE_AUDIENCES=<bundleid>,host.exp.Exponent. Frontend: AuthContext.loginApple() + native AppleAuthenticationButton on login.tsx (iOS only, gated by isAvailableAsync). app.json: ios.usesAppleSignIn=true + "expo-apple-authentication" plugin. Installed expo-apple-authentication.
- app.json ios.infoPlist.ITSAppUsesNonExemptEncryption=false (app uses only HTTPS/TLS = exempt).
- legal.tsx: support email houseoffmr@gmail.com now tappable via mailto:.
- premium.tsx: iOS no longer falls back to Stripe — if RevenueCat/StoreKit unavailable it shows a purchases-unavailable state; Stripe kept for web only (Apple 3.1.1).
- PrivacyInfo.xcprivacy: NOT missing — required-reason SDKs ship their own signed manifests, merged by Expo at prebuild. No change made.
- OPEN (user/production): confirm live iOS RevenueCat key (appl_...) is set in Emergent Custom Keys so the production build doesn't ship a test key.
- Requires: redeploy backend + generate a NEW iOS build (app.json entitlement + new native dep + backend changes).

## Shopping Intelligence + Packing removal (2026-06)
- NEW Premium feature "Shopping Intelligence" (built on wardrobe-gap analysis, reuses existing 'premium' entitlement — no new purchase system).
  - Backend: POST /api/insights/shopping-intelligence, gated by enforce_limit(user,'shop') → 402 for free. Returns {summary, recommendations[{piece,category,priority,why,pairs_with[owned item names],outfits_added}], avoid}.
  - Frontend: repurposed hidden /(tabs)/shop.tsx into "Shopping Intelligence" (gap analysis section on top + existing photo shop-check below). Entry banner added on Wardrobe tab (testID shopping-intelligence-entry): premium → /shop, free → /premium (lock icon).
  - Existing /insights/missing-piece (Profile card, health-report) left intact.
- Packing Assistant references removed from user-facing copy: premium.tsx feature list + looks.tsx empty state. Dormant code kept (app/packing.tsx, _layout Stack.Screen, backend /packing/plan) for a future version.
- Tested iteration 25: backend 4/4, frontend 6/6, 100%. No new build needed for backend; frontend needs redeploy + new iOS build to reach devices.
- OPEN: memory/ASO_store_listing.md store copy STILL mentions "packing/packing lists/packing capsules" — must be updated in App Store Connect before listing, since Packing is now deferred.

## Reviewer Premium fix + Shopping Intelligence naming (2026-06)
- BUG (reviewer not premium in-app): login flows set user from raw /auth/login response, which lacks the COMPUTED `premium` flag (only /auth/me derives it from premium_until). So reviewer (premium_until=2099) appeared non-premium → paywall. FIX: AuthContext now hydrates user from /auth/me right after token set in email, Google-session, and Apple login. Backend unchanged (grant was already correct).
- Naming: Profile "THE MISSING PIECE" card rebranded to "SHOPPING INTELLIGENCE" entry that routes to /shop (premium) or /premium (free); removed inline duplicate missing-piece analysis + unused state. Inside /shop the gap section labelled "MISSING PIECES · WARDROBE GAP ANALYSIS". /insights/missing-piece endpoint retained.
- Verified iteration 26: reviewer premium recognised immediately, Shopping Intelligence opens without paywall, guest still gated. FRONTEND-ONLY changes → requires a NEW iOS build to reach devices; redeploy backend only needed to ensure reviewer account+premium exists in production.

## CRITICAL WARDROBE BUG — diagnosis in progress (2026-06)
- P1 data loss (40->18->23) + P2 generic names ("New tops/shoes/bottoms") + wrong category (sunglasses->Tops).
- Evidence: add-item.tsx L93-94 apply AI name/category ONLY if (!name)/(CATEGORIES.includes); L134 fallback "New {category}". CATEGORIES already has Accessories/Bags/Jewellery so category-drop is NOT a missing-enum issue.
- Prime suspect: BULK-ADD path ("Several" button in screenshot) not carrying AI name/category into save payload -> defaults Tops + "New tops"; and likely partial/non-persist or wrong profile scoping on reload causing count drop.
- NEXT (do NOT wipe data): inspect app/bulk-add.tsx save payload; backend POST/GET /items (id gen, profile scoping via get_scope, any limit/truncation); confirm images persist in object storage; verify persistence across reload with testing_agent. Then P3 Dress Me week variety (add cross-day used-item awareness).

## WARDROBE PERSISTENCE RCA — FIXED & VERIFIED (iteration 27)
- ROOT CAUSE: items scope per profile via X-Profile-Id header. ProfileContext.load() set the header only AFTER /profiles fetched, so first /items (and early uploads) on relaunch had NO header -> get_scope fell back to DEFAULT/earliest profile. Multi-profile (premium/household) accounts thus saw a DIFFERENT profile (old/generic "New tops" items) and their real named items were hidden -> looked like data loss + wrong names. Backend persists name/category faithfully (verified).
- FIX (frontend only): ProfileContext.load() restores persisted active profile into API client BEFORE any request; Wardrobe waits for profileLoading=false before GET /items.
- Verified: relaunch sends correct X-Profile-Id on first /profiles+/items; names/categories persist; no leakage; counts stable.
- Deliverable: backend/scripts/diagnose_wardrobe.py (READ-ONLY prod diagnostic).
- Optional hardening (not done): get_scope could 400/404 on foreign X-Profile-Id instead of silent default fallback.
- P3 (Dress Me / Week Ahead styling repetition) NOT yet done — deferred to next pass per user order. Needs cross-day used-item awareness + occasion weighting in the weekly plan generator.
- Requires NEW iOS BUILD (frontend fix); backend unchanged so no redeploy strictly needed for the fix (redeploy still needed if reviewer account not yet in prod).

## Real-world photo recognition robustness (2026-06)
- ANALYZE_SYSTEM prompt rewritten: told these are REAL phone photos (imperfect lighting, cluttered/household backgrounds, angled/worn items); must identify the obvious main item anyway, ALWAYS pick closest category (sunglasses/belts/scarves->Accessories; rings/watches->Jewellery), and return an honest confidence 0-100. _analyze_core no-hint prompt strengthened similarly.
- add-item.tsx: captures r.confidence; when <60 shows a non-blocking "please confirm name/category" banner (testID low-confidence-banner) above the editable category chips. Best AI guess is always preserved and easy to correct; nothing is silently trusted.
- NOTE: real-photo recognition ACCURACY can only be validated on-device with real garment photos; cannot be meaningfully curl/browser tested. Low-confidence UX + editability are in place.
- Part of the combined redeploy + new iOS build (backend prompt + frontend UX).

## Week Ahead styling diversity — FIXED (P3, 2026-06)
- ROOT CAUSE: planner styled each day via an INDEPENDENT /stylist/suggest call with only occasion -> AI kept picking the same top-ranked "safe" hero items every day (no cross-day awareness).
- FIX: SuggestRequest.avoid_item_ids added; _build_outfit injects an "ALREADY WORN this week" instruction telling the stylist to vary silhouette/colour/footwear/accessories and not reuse hero pieces (tops/bottoms/dresses/outerwear/shoes/bags) without reason (basics may be reused if styled differently). Frontend planner.autoStyle now collects item_ids from all OTHER days in the week (resolving outfit_id via /outfits) and passes them as avoid_item_ids. Not randomized.
- VERIFIED (reviewer wardrobe): Day1 work=Black blouse/black trousers/tan boots/black tote/brown belt; Day2 date-night avoiding those = Floral wrap dress/camel overcoat/white sneakers -> 0 overlap, occasion-appropriate.
- Combined redeploy + new iOS build covers P1 persistence, P2 recognition robustness, P3 weekly variety.

## CHECKPOINT (handoff)
Aureve (Expo+FastAPI+Mongo), prod live, prepping App Store iOS+Play.
DONE in PREVIEW, pending ONE combined redeploy+new iOS build:
- iOS RevenueCat: frontend/.env now LIVE appl_(iOS)+goog_(Android), entitlement=premium (verified masked). TestFlight still has old test_ key -> rebuild needed.
- P1 wardrobe data-loss FIXED (profile-scope header timing: ProfileContext.load + wardrobe.tsx gate). backend/scripts/diagnose_wardrobe.py READ-ONLY diag (user not run yet; find scattered items under another profile before safe re-scope, NO deletes).
- P2 recognition FIXED (ANALYZE_SYSTEM real-photo prompt+confidence 0-100; add-item.tsx confirm banner <60). needs on-device check.
- P3 Week Ahead variety FIXED (SuggestRequest.avoid_item_ids + cross-day prompt; planner passes other-day ids).
- Shopping Intelligence Premium live; Missing Pieces=subsection; Packing refs removed(dormant); Sign in with Apple added; reviewer review@aureve.app/AureveTest2026 premium_until=2099.
NEXT: user runs diag -> re-scope; combined redeploy+build; on-device verify.
CONSTRAINTS: dont change RevenueCat config/prices/ids, entitlement premium, bundle com.emergent.wardrobeai.l0r5ay, auth, reviewer creds, legal; never expose full keys; no data wipes.

## LAUNCH-CRITICAL BATCH (Priority 1, iteration 28) — IMPLEMENTED & VERIFIED
Approved 24-item product brief; only Priority-1 items built. Multi-photo per item DEFERRED. Priority 2/3 NOT started.

**B1 — Recognition reliability (frontend+backend, needs redeploy + NEW iOS build)**
- RCA: backend AI was fine (1.3s, 96-98% confidence on real photos). Failures were transport: raw ~2-4MB iPhone base64 + recognition and Gemini background-removal in ONE /capture request (10-30s) with no timeout/retry, plus a blocking "Which piece is this?" category modal.
- `src/utils/image.ts`: on-device downscale to 1280px longest edge, JPEG q0.7 (expo-image-manipulator) → ~100-300KB uploads.
- `src/utils/diag.ts` + `POST /api/diag/log`: stage logs (capture.picked, compress.done/failed, analyze.start/done/error, clean.start/done/failed, bulk.*) shipped to backend log so TestFlight failures are isolatable.
- add-item: photo → auto-analyse immediately (no modal), `/capture {clean:false}` 60s timeout + 1 retry + "Try again" button; background removal moved to new `POST /api/clean-photo` (90s) fired AFTER details are filled, non-blocking ("Tidying photo…" pill). Low-confidence (<60) confirm banner kept.
- bulk-add: clean=false (fast/reliable), per-photo stage logs.
- Size + Fabric inputs REMOVED from add/edit form; backend fields + AI fabric detection preserved and still fed to the stylist.
- New `PhotoTips` collapsible (collapsed by default) on Add Item + Bulk Add.

**B2 — Wardrobe (backend redeploy + new build)**
- Demo isolation: `items_scope(user)` excludes `demo:true` for every account except guest sessions and REVIEWER_EMAIL; applied to all 20 db.items queries (items, laundry, insights, health, shopping intelligence, compatibility, stylist). NOTHING deleted.
- `POST /api/items/bulk-delete` + Wardrobe Select mode (long-press or select button, count, Select all on filtered set, Cancel, confirm sheet, refresh).

**B3 — Intelligence + tone + tiers (backend redeploy + new build)**
- Stylist: `summarize_items_for_ai` now includes worn count + last_worn; new `underused_line()` (pieces worn <=1) and `recent_looks_line()` (last 6 worn combos) injected into `_build_outfit`; prompt tells it to rotate the wardrobe and favour suitable forgotten pieces but never at the cost of relevance. Cross-day `avoid_item_ids` diversity preserved.
- Health report: `wasted_summary` → `underused_summary`; neutral prompt/UI copy ("Pieces worth revisiting", "Underused pieces + your smartest next buy").
- Shopping Intelligence labels: "SHOULD I BUY THIS?" (photo/item evaluation) + "WHAT SHOULD I ADD?" (gap analysis). "Missing Pieces" removed as a user-facing name.
- Free tier per brief: stylist 5/MONTH, dressme 5/MONTH, `FREE_ITEM_CAP=100` active items (402 on POST /items; deleting frees slots). Premium unlimited.

**B4 — Google Calendar (backend redeploy only)**
- RCA: `GCAL_REDIRECT_URI` env was hard-coded to the PREVIEW host → `redirect_uri_mismatch` in production.
- `_gcal_redirect_uri(request)` derives `{x-forwarded-proto}://{x-forwarded-host|host}/api/calendar/callback`; stored on the oauth state doc and reused in the token exchange. Env var is now only a fallback.
- USER ACTION: add `https://wardrobe-ai-311.emergent.host/api/calendar/callback` (and keep the preview one) to the Google Cloud OAuth client's Authorised redirect URIs.

Testing: iteration_28.json — 16/18 backend pass (1 skip, 1 preview ingress artifact), all frontend checks pass.
Still required from user: (a) Google redirect URI registration, (b) one combined redeploy, (c) ONE new iOS build, (d) real-device photo recognition validation across tops/bottoms/dresses/outerwear/shoes/bags/sunglasses/jewellery.

## REAL-DEVICE FIX BATCH (iteration 29) — P1 + UI cleanups, IMPLEMENTED & VERIFIED
**1. Worn photo (P1)** — `create_item` accepts an item with only `worn_photo`; `CaptureRequest.worn` adds a worn-photo instruction (person wearing it → catalogue the most prominent garment) WITHOUT touching ANALYZE_SYSTEM; add-item runs recognition on the worn shot when there's no hanging photo, validation accepts either photo, background-clean skipped for worn shots. Hanging vs worn stay separate fields.
**2. Session + persistence (P1)** — TWO root causes fixed:
  - `reconcile_reviewer_wardrobe` was deleting EVERY non-canonical item on the reviewer profile on each backend start → any real uploads made while signed in as the reviewer account were destroyed on redeploy (demo items survived, matching the report exactly). Now prunes ONLY stale `demo:true` non-canonical rows; user-added items are never touched; demo wear_count/last_worn moved to `$setOnInsert` so history isn't reset.
  - `AuthContext.checkExisting` cleared the token on ANY `/auth/me` failure → a cold-start timeout signed returning users out (app then opened at login/Guest). Now clears only on 401/403, caches the last user (`aureve_cached_user`) to open signed-in, and revalidates in the background.
  - `diagnose_wardrobe.py` now also reports demo-flagged / reviewer-seeded / real counts per profile.
**3. Family wardrobes (P1)** — new shared `src/components/WardrobeSwitcher.tsx` (list, switch, add with inline validation + busy state + 402→paywall, delete behind confirmation, copy: Premium belongs to the account, family wardrobes are profiles). Reachable from a chip in the Wardrobe header (`wardrobe-switcher-chip`) and from Profile (inline sheet deleted). New profiles verified to start EMPTY; premium stays account-level.
**4. Google Calendar (P1)** — added read-only `GET /api/calendar/config` returning the exact `redirect_uri_sent_to_google`, `client_id_tail`, `client_secret_present`, host/forwarded headers. Secret never returned. User must compare production output against the Google Cloud OAuth client.
**Cleanups** — Brand + Price removed from add/edit and no longer AI-inferred (schema kept, manual-only); item detail lost cost/wear, bought-for, Size, flatter badge, laundry availability controls and post-wear laundry prompt; laundry UI removed from Wardrobe (toggle, banner, badges) with backend fields untouched; total "X PIECES" counter removed; link-icon count → readable "Pairs with N"; compatibility result auto-scrolls to Wardrobe Intelligence; "Several" → "Bulk Add" (bordered button) and Bulk Add gained an explicit "Choose photos" button and no longer bounces back on cancel.
Testing: iteration_29.json — backend 14/14 (incl. reviewer reconciliation across a real restart), frontend checks pass.
Still needs one redeploy + ONE new iOS build. Untouched: RevenueCat, auth providers, reviewer credentials, recognition prompt for normal category ambiguity.

## AUDIT + CALENDAR HARDENING (post-iteration 29)
- `GET /api/diag/my-wardrobe-audit` (auth, own account only, strictly read-only): per-wardrobe counts split real vs demo-seeded, items missing a photo, first/last added dates, items stranded on the raw account_id, OTHER accounts using the same email (different sign-in provider) with their wardrobe counts, and the 60 most recent pieces with scope + date. 401 without a session.
- New in-app screen `app/audit.tsx`, reachable from Profile → Privacy & Data → "Wardrobe audit" (registered in `_layout.tsx`). Read-only; no writes anywhere.
- `_gcal_redirect_uri` hardened: scheme FORCED to https for real hosts (ingress terminates TLS so the app only sees http, which produced an http:// redirect_uri and a guaranteed mismatch), default :443/:80 ports stripped, localhost still http. `/api/calendar/config` now also returns client_id_prefix/length and secret length (never the secret) plus `register_this_exact_uri_in_google_console`.
- Confirmed with user: OAuth client `538895898254-0ns95m6…` IS the new client and is of type "Web application" → remaining cause was the scheme/port derivation, now fixed. Needs redeploy.
- Startup writes audited: only index creation + reviewer seed/reconcile (reviewer profile demo rows only). A redeploy cannot reset or reseed any normal user's wardrobe.
