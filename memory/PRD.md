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
- A static bearer session is seeded in the PREVIEW database only for automated backend testing (account user_testaura01); the token itself lives in /app/memory/test_credentials.md, which is not tracked in git. It is not created by any application code, so production has no such session. Real users get their own user_id via Google.
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
- Shopping Intelligence Premium live; Missing Pieces=subsection; Packing refs removed(dormant); Sign in with Apple added; store-reviewer account premium_until=2099 (credentials in /app/memory/test_credentials.md, not tracked in git).
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

## RETEST ROUND 2 (iteration 30) — 4 scoped items, IMPLEMENTED & VERIFIED
**1. Missing ~54 real pieces** — user's audit showed only the reviewer account (device signed in as review@aureve.app). Added `GET /api/diag/wardrobe-scan` (auth required, STRICTLY read-only, no-write verified): accounts for a given email with masked addresses + per-wardrobe real/demo counts, and the 10 largest wardrobes in the DB holding REAL pieces incl. guest-owned ones (finds an unmigrated guest wardrobe, which has no email). Surfaced in `app/audit.tsx` ("Find pieces that aren't showing" → `scan-email-input` + `run-scan`). NOTHING deleted/migrated/relinked — awaiting the user's production scan output before any recovery plan.
**2. Premium entitlement scoping** — BEFORE: `premium` came from the account, so every family profile inherited ALL Premium features (household-wide unlock). NOW: `get_scope` returns `is_primary`, `account_premium` and `premium = account_premium AND is_primary`. Premium AI features run on the primary (first) wardrobe only; secondary wardrobes keep full item CRUD and the free monthly AI allowances; the 100-item cap uses `account_premium` so a premium household keeps unlimited storage everywhere; creating extra wardrobes still needs account premium. `enforce_limit` returns a specific 402 ("Premium features run on your main wardrobe…"). `GET /profiles` returns `is_primary`; new `src/hooks/usePremiumAccess.ts` used by wardrobe/shop/profile/outfit-builder; WardrobeSwitcher copy no longer promises household-wide Premium and tags the primary wardrobe MAIN.
**3. Bulk Add "Choose photos" dead button** — RCA: the screen auto-launched the picker on mount; on iOS presenting a picker while the modal is still animating silently fails, leaving `busy.current === true` forever so the button no-op'd, and the queued picker later presented after navigating back (processing then ran with the screen unmounted — which also caused #4's "idle wardrobe screen"). Auto-launch removed, picker wrapped in try/finally with an `opening` spinner, stage logs `bulk.picker.open/picked/cancelled/failed`.
**4. Bulk progress** — "Uploading and analysing X of Y — N done" + progress bar + note that larger batches can take up to a minute and to stay on the screen.
Testing: iteration_30.json — backend 19/19 (incl. scan no-write proof and masked emails), frontend all pass.
Deploy: backend items need a redeploy; the frontend fixes need ONE new iOS build for TestFlight.

## WORKSPACE SWITCHED TO GITHUB BRANCH (10 Sep 2026)
Pulled `recovery-implementation-2026-09-10` from `PhoenixRose888/aureve` directly via git fetch (repo reachable read-only from the workspace). It was a strict FAST-FORWARD of the previous workspace HEAD (`ab00445`) → `c1c81bc`, so nothing was overwritten or merged: 8 files changed (backend/server.py, dressme.tsx, stylist.tsx, wardrobe.tsx, item/[id].tsx, looks.tsx + 2 new docs). No `.env` files exist in the branch, so all protected environment values are untouched. Nothing was pushed; the GitHub branch and main are unmodified. Local checkout is now on branch `recovery-implementation-2026-09-10` (previous state remains reachable at `main` / `ab00445`).
Branch adds: persistent `style_suggestions` history + hard candidate-pool exclusion for Dress Me rotation, `STYLE_ROTATION` diagnostics, dynamic reviewer demo visibility (real uploads stop demo resurrection), demo outfits/plans/wear-logs excluded server-side, removal of wardrobe money metrics, AI Stylist context question, frontend TS cleanup. See `docs/RECOVERY_IMPLEMENTATION_STATUS.md`.
Verified after switch: backend syntax OK, backend boots (reviewer reconcile 16 canonical, pruned 0), API responds, Expo boots and the app renders. Two consecutive `/dressme` calls produced different looks with STYLE_ROTATION logging (`recent=0` then `recent=1`). NOTE: a single probe of `/stylist/chat` with "What should I wear tonight?" answered directly instead of asking for context — needs checking before that item can be called done.

## ON BRANCH recovery-implementation-2026-09-10 — targeted changes (10 Sep 2026)
1. AI Stylist vague-context: now BOTH layers. Frontend `needsOccasionContext(text, history)` widened (no longer requires a time word; covers "what do i wear/what to wear/style me/dress me/pick an outfit"), only asks once per conversation, question names the time word. Backend `needs_occasion_context()` + `occasion_question()` short-circuit `/stylist/chat` BEFORE `enforce_limit` (returns `needs_context: true`, no AI call, no allowance used); STYLIST_CHAT_SYSTEM also told to ask one question instead of guessing.
2. Dress Me rotation: inspected, already correct on this branch — hard candidate-pool exclusion for `avoid_item_ids`, `recent_suggestions(source='dressme')` feeding the prompt, `record_style_suggestion` writing only to `style_suggestions` (never wear_count/last_worn), dressme.tsx sends the current look's ids on Create Another Look. No changes made.
3. Photo cleanup on every ingestion path: new `POST /api/items/{id}/clean` (cleans the stored photo, keeps the pre-clean image in `orig_photo`, returns `cleaned:false` on failure, 404 for another scope). Bulk Add now runs a second "Preparing and cleaning your wardrobe photos…" phase (per-photo progress + bar, failures skipped, batch never fails); `ItemCreate.orig_photo` added and single Add sends it. Worn photos untouched everywhere.
4-7. Hair & Makeup → **Hair**: `BEAUTY_SYSTEM` replaced by `HAIR_SYSTEM` (hairstyles only; explicitly forbids hair colour, makeup, skincare and clothing palettes), endpoint renamed internally to `hair_suggest` (route kept `/api/beauty/suggest`), now accepts occasion + neckline + hair_length + hair_type + weather and no longer requires a skin-tone profile. Response: summary / styles[{name,why,how}] / tip / occasion_note. `app/beauty.tsx` rebuilt as the Hair screen with those chip groups. Copy updated in profile.tsx, profile-edit.tsx, premium.tsx, legal.tsx and the premium message. No "makeup" string remains in the frontend or backend prompts.
Verified: backend syntax + boot, vague/answered/specific stylist probes, hair suggestion output, `/items/{id}/clean` (photo replaced, orig retained, 404 guard), Expo boots, Hair screen renders. Nothing pushed, merged, published or deployed; still on branch `recovery-implementation-2026-09-10`.

## LAUNCH POLISH BATCH (branch recovery-implementation-2026-09-10, 10 Sep 2026)
1. Wardrobe scroll/filter memory: module-level `lastFilter/lastSub/lastOffset` in wardrobe.tsx + FlatList ref; returning from an item restores category, subfilter and offset.
2. Duplicate detection rewritten (`find_similar_items`): same category + same colour family (containment/first-word) + >=2 matching descriptors (style/fabric/pattern) + >=2 shared name words, and returns a human `reason`. Verified: same garment re-shot IS flagged, unrelated garment is NOT.
3. Create Outfit: real `loadingItems` state — picker shows a spinner instead of a false "no items" message.
4. "Get AI Inspiration" → "Check My Outfit": new `POST /api/outfit/feedback` (verdict + feedback + at most ONE validated optional swap, ids checked against the wardrobe). The user's selection is never replaced; the swap is applied only if they tap "Try the swap".
5. Compatibility: local pre-scoring shortlists to 12 for wardrobes >14 items, returns `total_compatible`/`shortlisted`; item detail header reads "TOP MATCHES FROM N COMPATIBLE PIECES".
6. Dress Me: new `GET /api/dressme/context`; with no plan/calendar context the screen asks "What are you doing today?" with 9 quick options instead of guessing.
7. Wardrobe Health: money tiles replaced with unworn/total piece counts; backend stats now include worn_count + category counts; nudges phrased as invitations; Profile teaser uses the real `unworn_count` from /insights instead of the 5-item sample.
8. Google Calendar: audited, no code bug found beyond the https redirect fix that is IN THIS BRANCH BUT NEVER DEPLOYED. Remaining "access blocked" is a Google Cloud consent-screen state (Testing mode without the tester added, or unverified app with the sensitive calendar scope) — not fixable in code.
9. Wear confirmation: `GET /api/wear/pending?date=LOCAL_YESTERDAY` + `POST /api/wear/confirm`; Home shows a one-tap check-in. Yes increments wear_count/last_worn dated to that local day; No records nothing; `wear_prompts` stops repeat asks. Suggestions still never touch wear history.
10. Photo-quality warning: recognition returns `photo_quality`/`photo_quality_note`; single Add shows a soft card (Retake / Keep this one / Photo tips), Bulk Add shows a per-row note. Never blocks an upload.
11. Category subfilters: Tops/Outerwear/Bottoms subfilter chips derived from existing name/style/fabric metadata (no schema change); Shoes untouched.
12. Bulk Add copy now says processing continues in the background (true — the async loop keeps running after navigation).
Verified: backend syntax + boot, duplicate strictness both ways, outfit feedback (incl. 400 guard), photo_quality output, wear pending/confirm (incl. bad-date guard and no-repeat), dressme context probe, Expo boot, wardrobe subfilters rendering. Still on branch recovery-implementation-2026-09-10; nothing pushed, merged, published or deployed.

## Iteration 33 (branch recovery-implementation-2026-09-10)
- Dress Me now uses the device LOCAL date: GET /api/dressme/context?date=YYYY-MM-DD and POST /api/dressme { local_date }. Yesterday/deleted plans no longer leak into the next local day; with no context the screen asks "What are you doing today?" (chips + Other free text).
- Wardrobe displayCategory(): obvious tops (bodysuit, leotard, bustier, corset, bralette, halter, cami, singlet, tank, tube/crop, tee, blouse, button-up) can never be re-mapped to Outerwear, so knit bodysuits stay in Tops and show under the Bodysuits chip.
- New Tops subfilter rules: "Halter / Crop tops", broader Blouses/Shirts and T-shirts, so halters no longer fall into Other. subOptions is de-duped (no duplicate T-shirts chip).
- Check My Outfit (/api/outfit/feedback) prompt rewritten to be candid (names clashing colour / formality / season / weak pieces) while never criticising the user. Same-slot swap guard unchanged.
- Internal planner moved from My Outfits ("View Calendar") to Home as "Plan Your Week" (testID home-plan-week) -> /planner. Google Calendar untouched.
- Verified by testing agent iteration 33: 5/5 backend pytest (/app/backend/tests/test_iteration33_local_date_and_feedback.py) + frontend flows. No push/merge/publish/deploy.

## Iteration 34 (branch recovery-implementation-2026-09-10)
- Tops subfilters: labels/order now T-Shirts, Shirts, Blouses, Singlets, Camis, Crops, Halter, Long Sleeve, Bodysuits, Corsets, Other (SUB_ORDER for display, SUB_RULES most-specific-first for matching; one chip per item, empty chips hidden).
- Classification text now reads name+style+fabric+pattern+description+fit_notes+normalised sleeve_length.
- Bodysuit root cause: bodysuits were often STORED under Dresses/Outerwear, so they never reached the Tops chips. BODYSUIT_RE now hoists them to Tops for display (swimsuits excluded).
- ANALYZE_SYSTEM tells the AI bodysuits/corsets/camis/singlets/halters/crops are Tops and to name the garment type.
- Dress Me local midnight: _gcal_events(tz_offset) windows the users LOCAL day; /dressme/context?tz_offset= and POST /dressme {tz_offset}; screen drops yesterdays look/activity and re-probes when the device date changes.
- OUTFIT_FEEDBACK_SYSTEM assesses colour, formality, proportion/silhouette, season/weather, footwear, texture/pattern competition, cohesion. Swap guard unchanged.
- Verified by testing agent iteration 34 (8/8 backend + 5/5 frontend). No push/merge/publish/deploy.

## Iteration 35 (branch recovery-implementation-2026-09-10)
- Removed the top-level "All" wardrobe view; FILTERS = the 8 main categories, default Tops. Opening a category lists all of its pieces; subfilters are optional narrowing chips.
- No user-facing "Other" chip anywhere (unplaced items keep an internal label and still show in the category view).
- Final subfilter sets: Tops [T-Shirts, Shirts, Blouses, Polos, Singlets, Camis, Crops, Halter, Long Sleeve, Vests, Bodysuits, Corsets]; Bottoms [Jeans, Pants, Shorts, Skirts, Leggings]; Dresses none; Outerwear [Blazers, Jackets, Coats, Cardigans, Jumpers]; Shoes [Sneakers, Boots, Heels, Flats, Sandals, Dress Shoes]; Bags [Handbags, Backpacks, Clutches, Briefcases, Crossbody]; Accessories [Hats, Sunglasses, Scarves, Ties, Belts, Gloves]; Jewellery [Necklaces, Bracelets, Earrings, Rings, Watches].
- Vests/waistcoats now live under Tops (removed from Outerwear); hoodies/sweatshirts -> Jumpers; bodysuits still hoisted to Tops.
- ANALYZE_SYSTEM now asks for the specific garment word per category so NEW uploads land in the right subfilter.
- Verified by testing agent iteration 35 (6/6 backend, 32/32 frontend assertions). No push/merge/publish/deploy.
- Google Calendar prod failure (unchanged code): production backend runs a STALE GOOGLE_CALENDAR_CLIENT_ID (529785392979-9jdd...) while the workspace/intended client is 538895898254-0ns95m6...; redirect URI is correct. Fix = update production env var + redeploy.

## Iteration 36 (branch recovery-implementation-2026-09-10)
- Guest/demo flow removed: backend POST /api/auth/guest + seed_demo_wardrobe() deleted; AuthContext.guestLogin removed; "Explore as guest" button and Profile guest card/badges removed. New accounts start completely empty. Reviewer seeding/Premium untouched.
- /welcome is now the account screen shown whenever there is no valid session: Welcome to Aureve + tagline + [Start Free] -> onboarding slides -> /login?mode=signup, and [Log In] -> /login. app/index.tsx: session -> /(tabs), else /welcome.
- Registration sets storage flag aureve_tour_pending; Home pushes /tour once. /tour = 5-step first-run tour (Home, Add/Bulk Add, Wardrobe, Dress Me, Profile) with Next/Skip, clears the flag. Profile row "How Aureve Works" replays it.
- Wardrobe empty state: "Your wardrobe is ready when you are" + Add Item / Bulk Add.
- Sign out / switch account / delete account now return to /welcome or /login as appropriate.
- Verified by testing agent iteration 36 (12/12 backend + frontend flows); two minor findings fixed afterwards (Profile switch-account login ref, onboarding pointerEvents deprecation).

## Iteration 37 (branch recovery-implementation-2026-09-10)
- Taxonomy moved to /app/frontend/src/utils/taxonomy.ts and shared by Wardrobe + item editor. Items now carry a user-chosen `subcategory` (backend ItemCreate/ItemUpdate; "" = back to automatic). primarySub honours it; displayCategory trusts the stored category when an override exists.
- Add/Edit Item has a SUBCATEGORY chip row (testID sub-<Label>); changing category clears it; editing pre-selects the current one. Root cause of the stuck jumpsuit: subcategory was purely derived from text with no editable stored value.
- Classification: specific type beats appearance. jumpsuit/playsuit/romper/dungaree -> Tops>Bodysuits; Sneakers matched before Boots (high-tops); Sandals before Heels (wedges); sweatshirt/hoodie -> Outerwear>Jumpers (fixed "swea-TSHIRT" substring bug); bags rebuilt on carry style (backpack/crossbody/handbag/clutch/briefcase). Regexes are Hermes-safe (no lookbehind).
- Photo cleanup: prompt now removes hangers/hooks/clips/rails/mannequins/hands and forbids recolouring; ONE retry only if a pass errors/returns empty; single Add runs cleanup even when recognition fails (was skipped).
- Wardrobe back nav: silent refresh (no spinner over a populated grid) + restore flag reset on focus, so category+subfilter+scroll survive opening an item. Card meta now shows the display category.
- Premium copy: "Capsule wardrobes & occasion planning" -> "Occasion planning".
- Calendar: no logic/redirect change. Callback now shows Googles error code, /api/calendar/config exposes last_callback_error + client_secret_fingerprint, env values stripped. Production failure is an env pairing issue (stale client id/secret) to fix in the deployed env vars.
- Verified by testing agent iteration 37 (11/11 backend + 13/13 classification + editor flow). No push/merge/publish/deploy.

## Iteration 38-39 (branch recovery-implementation-2026-09-10)
- Bottoms subfilters: Jeans, Trousers, Lounge Pants, Shorts, Skirts, Leggings ("Pants" removed). Soft/pull-on/drawstring/track/jogger/sweat -> Lounge Pants; tailored/chino/dress/work/cargo -> Trousers.
- Long Sleeve vs Jumper tightened: Jumpers now needs warmth-layer construction (sweatshirt/hoodie/fleece/pullover/cable or knitted jumper); lightweight long-sleeve tops stay in Tops>Long Sleeve.
- Bags simplified to Handbags + Clutches (crossbody/backpack/briefcase now fall under Handbags). Shoes simplified to Sneakers, Boots, Heels, Flats, Dress Shoes (heeled sandals/wedges -> Heels; flat sandals/slides/thongs -> Flats).
- Dress Me core vs extras: STYLIST_SYSTEM builds the core outfit first and tags every piece necessity=core|recommended|optional; may return no bag/jewellery/accessory; never styles a backpack/briefcase/work bag. UI groups rows under core / RECOMMENDED / OPTIONAL.
- Performance: items store a ~320px `thumb`; GET /api/items drops orig_photo and serves the thumb as `photo` (bounded backfill of 20 legacy items per call) - measured ~94% smaller per item; GET /api/items/{id} still full size. New src/utils/wardrobeCache.ts paints from cache, skips refetch when <60s old and nothing changed, marks dirty on add/edit/delete/bulk/wear and clears on a real profile switch. load() has an inFlight guard; Home reuses the cache for its count.
- Verified: iteration 38 (4/4 backend + taxonomy fixtures) and iteration 39 (request counts: wardrobe entry 1 GET, back-nav 0, after edit 1, Home refocus 0). No push/merge/publish/deploy.

## Iteration 40 (branch recovery-implementation-2026-09-10)
- Dress Me core vs extras now DETERMINISTIC in the backend (necessity_for): Tops/Bottoms/Dresses/Shoes always core; Outerwear core only when temp <= 15C or rain/snow/wind, else recommended/optional; Bags/Jewellery/Accessories can never be core. Prompt also states most everyday looks need no bag and no jewellery. UI splits the core flatlay (dressme-core) from a smaller extras row (dressme-extras) and groups the list under CORE OUTFIT / RECOMMENDED / OPTIONAL. Single-piece swap still maps back to the original resolved_items index.
- Calendar invalid_client root cause: PRODUCTION client_id is correct (538895898254-0ns95m6...) but its GOOGLE_CALENDAR_CLIENT_SECRET is only 8 chars (truncated/placeholder); Google returned "The provided client secret is invalid." Preview holds the correct 35-char secret (fingerprint e325431300). Code fix: /calendar/authorize now fails fast with a clear message when the configured secret is < 20 chars. Real fix = set the full 35-char secret in the production env and redeploy.
- Verified by testing agent iteration 40 (6/6 backend + frontend split/swap checks).

## Iteration 41 (branch recovery-implementation-2026-09-10)
- LAUNCH BLOCKER fixed: My Outfits previews showed placeholders. Cause (a) /api/outfits (plus plans, looks, collections-with-outfits) embedded FULL item docs - 1024px photo + orig_photo + worn_photo as base64 - so a real wardrobe shipped tens of MB and the device dropped image decodes; cause (b) GarmentImage used the same recyclingKey ("0-0") for every instance, so recycled collage/grid cells reused a neighbours slot and rendered blank, and one dropped decode fell through to the placeholder even with no fallback source.
- Fix: new slim_items_by_id() serves the ~320px thumb as `photo`, drops orig_photo/worn_photo and lazily backfills up to 20 legacy thumbs per call; used by /outfits, collections-with-outfits, plans and looks. GET /items/{id} still full resolution. GarmentImage derives a unique recyclingKey from the source, retries a dropped decode twice and only advances to a fallback when one exists.
- Measured: /api/outfits 160KB -> 28.8KB; embedded photo 3.6KB vs 18.3KB full. Verified by testing agent iteration 41 (6/6 backend + My Outfits/detail/new-outfit/Home/Wardrobe/Dress Me checks).

## Iteration 42 — PHASE 1 (branch recovery-implementation-2026-09-10)
- HOME is a one-screen dashboard: date + compact weather row, greeting, 2x2 grid (Wardrobe / Create Outfit / Dress Me / AI Stylist), wider My Collections card with Saved + Worn. Removed Plan Your Week, bell, growing banner, Dress Me hero, Recent Outfits/See All and old Quick Actions. Home fetches NO items/outfits (0 requests). Yesterday wear check-in kept. /planner route still exists (deferred, just unlinked from Home).
- WARDROBE progressive nav: Wardrobe -> category -> subcategory (where one exists) -> garments. Browse levels render NO thumbnails and use the new photo-free GET /api/items?summary=1 (3.1KB vs 176KB). In-screen back steps one level; select/add only at the garment level; scroll+level restoration preserved.
- SIX top-level categories: Tops, Bottoms, Dresses, Outerwear, Shoes, Accessories. Stored Bags/Jewellery records are folded into Accessories by displayCategory (data untouched). Accessories subs: Bags (not subdivided), Belts, Hats, Sunglasses, Scarves, Gloves, Jewellery; Jewellery has a third level (Earrings/Necklaces/Bracelets/Rings/Watches). Dresses goes straight to items.
- Classification refinements for NEW uploads/manual edits only: suit jacket -> Blazers, jumpsuit/playsuit -> Tops>Bodysuits, skort -> Skirts, cami vs singlet by fabric not strap width, heeled/wedge sandals -> Heels, flat sandals/slides -> Flats. 45/45 fixture cases correct. No bulk reclassification or cleanup re-run.
- MATCHING SETS: items accept set_name (ItemCreate/ItemUpdate); Add/Edit has "Part of a matching set?" No/Yes + Set name. No new navigation category.
- Item editor shows the six main categories and maps Accessories>Bags / Accessories>Jewellery back to their stored categories on save.
- CLEANED-IMAGE BUG: POST /items/{id}/clean updated photo but not the grid thumb, so grids showed the raw upload while detail showed the cleaned image. It now regenerates the thumbnail.
- Verified by testing agent iteration 42 (9/9 backend + full frontend Phase 1 checks). Preview /api/weather 502 is pre-existing. Phases 2-5 NOT started.

## Iteration 43 — Phase 1 polish (branch recovery-implementation-2026-09-10)
- HOME visual refinement only (structure unchanged): differentiated Aureve card tones, icon pucks, tighter type hierarchy, soft shadow + pressed state; My Collections is now a charcoal card with a gold-soft bookmark puck and two outlined chips.
- WARDROBE browse levels polished: top-level categories are tinted cards with a restrained icon puck and count; subcategory/leaf rows are compact with a sage dot and count pill. Still no garment photos before the final level.
- Shopping Intelligence entry REMOVED from the whole Wardrobe tab (service/route untouched; moves to Profile in a later phase).
- Photo Tips restored as a visible bordered pill on BOTH Add Item and Bulk Add, expanded to the 8 requested tips, never mandatory.
- Verified by testing agent iteration 43 (Home testIDs + 0 item/outfit requests, wardrobe levels + back, 0 garment images on browse levels, shopping-intelligence-entry absent everywhere, Photo Tips on both screens).

## Iteration 44 — Phase 1 final visual polish (branch recovery-implementation-2026-09-10)
- HOME: responsive card height (clamped 136-196, derived from window height, insets and whether the wear check-in is showing) so the dashboard fills the space with no dead area or clipping; one warm muted family (Wardrobe taupe, Create Outfit champagne, Dress Me pale eucalyptus, AI Stylist dusty plum) with ink text, white icon pucks and soft shadow. My Collections is now light cream with a warm gold hairline, gold bookmark puck and outlined Saved/Worn pills (dark card removed). New theme tokens: champagne, eucalyptus, taupe, plum.
- BRAND MARK: src/components/BrandMark.tsx is the single reusable treatment (centred, 38x28, opacity 0.95, consistent spacing) used identically on Home, Wardrobe, My Outfits, Dress Me (balanced in its top bar) and Profile. AI Stylist chat header keeps its own controls.
- WARDROBE: shared visual alignment only - same warm tones, radius and shadow language as Home. Structure/counts/navigation/thumbnail behaviour untouched.
- PHOTO TIPS: bags/jewellery tip reworded as requested (still 8 tips).
- Verified by testing agent iteration 44 at 390x844 and 390x700 (no clipping, 39-63px clearance above the tab bar, all Home nav intact, brand mark centred once per screen, wardrobe drill/back/no-early-images intact, Photo Tips expand/collapse + verbatim copy).

## Iteration 45 — Phase 2: Dress Me + My Collections (Suggested / Saved / Worn)
- DRESS ME now opens with "What am I dressing you for?" and a free-text box as the primary interaction; shortcut chips only populate that box. If a Google Calendar event / planned look exists for today it first asks "I see you have [event] scheduled today. Would you like me to dress you for it?" (Yes styles for it, No falls through to the question). A single short follow-up question is asked only when the request is too broad (Work, Date, Event...), with Skip.
- Generated look now offers four actions: Wear this today (POST /api/wear = Worn), Save for later (POST /api/outfits = Saved), Create another look (regenerates with avoid_item_ids, commits nothing), Discard (clears the suggestion, records nothing). Multiple requests per day are allowed. A suggestion is never auto-saved or auto-worn.
- MY COLLECTIONS (/collections) is now two destinations only: Saved (/saved, from /api/outfits — includes manually created outfits) and Worn (/worn, from /api/wear, grouped by date, several per day). Saved outfit detail primary action is "Wear this today" (records a wear, the outfit stays saved). Worn detail (/worn/[id]) offers "Wear it again" and "Mix it up".
- BACKEND: WearLog gained `name`; new GET /api/wear/{log_id} (registered after /wear/pending so it is not shadowed); new POST /api/outfits/mix (item_ids | wear_log_id | outfit_id) which calls _build_outfit with the new `base_item_ids` REFRESH instruction so the stylist keeps what works and changes only 1-2 pieces (source="mix", so the do-not-repeat history line does not fight the refresh).
- Verified by testing agent iteration 45: backend 12/12 pytest (incl. suggestion creates no Saved/Worn records, mix keeps the majority of base pieces, /wear/pending not shadowed) and the full frontend Phase 2 flow at 390x844. No issues.

## Iteration 46 — Phase 3: AI Stylist + Profile
- AI STYLIST is now a collaborative conversation about the user own clothes rather than a second outfit generator. STYLIST_CHAT_SYSTEM rewritten (discuss named pieces, give an honest opinion, say what to change, name real wardrobe gaps) and the prompt now carries profile context, learned prefs, underused pieces, recently worn combinations and saved outfits. StylistChatRequest gained `item_ids` so the user can ATTACH wardrobe pieces (+ button next to the chat input, picker sheet, removable chips) and talk about those garments. Chat screen also uses the shared brand mark header and four conversational starters. The existing vague-request short circuit (needs_context, no AI spend) is untouched.
- PROFILE reorganised: removed the Pieces/Looks/Profiles metric row, the top-card sign-out icon and the duplicate Switch account row (and the /insights fetch that only fed the counts). One Active Wardrobe selector near the top, Style Profile and Google Calendar rows unchanged, new PREMIUM FEATURES section (Monthly Wardrobe Health + Shopping Intelligence, padlocked on Free) and a new YOUR SUBSCRIPTION card (plan, renews/expires from premium_until, Manage Subscription -> App Store / Play Store subscription page via Linking, /premium fallback on web; Go Premium for Free). Lower ACCOUNT and PRIVACY & DATA groups keep How Aureve Works, Sign out, Wardrobe audit, Privacy, Terms and Delete my account.
- MONTHLY WARDROBE HEALTH rebuilt on the warm light palette with real imagery: tiles for outfits worn / pieces in rotation / never worn, horizontal strips for most-worn-this-month (with wear counts) and still-unworn pieces, rotation nudges, wins and the Smartest Next Buy card (links into Shopping Intelligence). GET /api/insights now returns slim thumbnails and a `month` block computed ONLY from wear_logs in the current month, so every wear statistic comes from explicit Worn activity.
- Shopping Intelligence screen gained a back control + brand mark since it is now entered from Profile.
- Verified by testing agent iteration 46: backend 7/7 pytest (attached pieces referenced by name, unknown ids ignored, needs_context still free, month block moves on /wear and not on /dressme) and the full Phase 3 UI at 390x844. No issues.

## Iteration 47 — Device-test fix pass (Phases 1-3 refinements)
1. Shopping Intelligence: removed the dead "Re-analyse wardrobe" button (UI only; POST /api/insights/shopping-intelligence untouched).
2. Shop-check now tells ONE story: SHOP_SYSTEM redefines outfits_added as GENUINELY new outfits, and /shop-check forces outfits_added=0 for duplicates/Skip and returns `already_covered` ("You can already create similar looks with the <owned piece> you own."). The UI hides the new-outfits metric in that case and shows the sentence instead.
3. Monthly Wardrobe Health: dropped the three big numeric tiles (kept a one-line subtitle), kept the garment strips / insight / nudges / wins / smartest next buy, and HEALTH_SYSTEM now forbids quoting wardrobe totals or category counts and asks for human phrasing ("bring a few of your unworn dresses into rotation"). Wear data still comes only from explicit wear logs.
4. AI Stylist conversations persist: new db.stylist_threads; /stylist/chat takes and returns `thread_id` and appends both turns (including the needs_context short circuit); GET /stylist/threads (journal), GET /stylist/threads/{id} (full messages), POST /stylist/threads/{id}/archive (keeps the conversation, generates title/summary/recommendations). The screen restores the live thread on focus, the pen icon archives then starts a fresh chat, and a clock icon opens "Your styling journal" where past conversations can be reopened and continued. Archived summaries are passed as context via earlier_threads_line. Thread docs are removed with profile/account deletion.
5. Stylist intent: _UNRESTRICTED bypasses the occasion gate and the system prompt now names the four intents, so "a completely different look, it doesn't have to be from my wardrobe" is answered freely instead of being forced into wardrobe styling or gap analysis.
6. Stylist brevity: recommendation first, short reason, pieces, one optional note, ~120 words, no repeating the question back.
7. Profile: the large Your Subscription card is gone; subscription management is a compact ACCOUNT row (Manage Subscription + "Aureve Premium · Renews <date>", or Go Premium on Free).
8. Profile: removed the How Aureve Works row.
9. Saved outfit detail: Duplicate replaced by "Mix it up" -> /dressme?mix_outfit=<id>, which generates a variation while the saved original stays untouched and nothing is marked worn.
10. Outfit state semantics unchanged (Suggested / Saved / Worn; viewing never changes wear stats).
- Verified by testing agent iteration 47: backend 11/11 pytest and the full frontend fix list at 390x844. No issues.

## Iteration 48 — Live RevenueCat premium unlock fix
- Symptom: live App Store build showed the Aureve entitlement Active with unlimited duration while the app still treated the account as non-premium.
- Cause 1: the client gated on a configured entitlement identifier (frontend/.env EXPO_PUBLIC_REVENUECAT_ENTITLEMENT=premium) while the live entitlement is named "Aureve", so entitlements.active["premium"] was undefined.
- Cause 2: backend premium is server-side from users.premium_until, written ONLY by the RevenueCat webhook. CustomerInfo was never reported by the client, and an entitlement with no expiry (lifetime/promotional/unlimited) or a missed/mismatched webhook left premium_until null forever.
- Fix: purchases.native.ts now treats ANY active entitlement in CustomerInfo as Premium (never a product or subscription type) and exposes entitlementState(), refreshCustomerInfo() (invalidateCustomerInfoCache + getCustomerInfo) and addCustomerInfoListener(); initPurchases re-binds identity with logIn when already configured. AuthContext refreshes CustomerInfo on launch, on app foreground and via the customer-info listener, then POSTs the entitlement to the new POST /api/membership/entitlement, which grants/extends premium_until (about 50 years for a non-expiring entitlement), sets premium_source "revenuecat" and NEVER downgrades on an inactive/offline report. premium.tsx syncs after paywall and restore. The webhook now stores a far-future premium_until for active events with no expiration_at_ms (TEMPORARY_ENTITLEMENT_GRANT still 31 days).
- Verified by testing agent iteration 48: backend 15/15 pytest (unlimited entitlement unlocks, explicit/past expiry handled honestly, no downgrade, auth-scoped, gated AI unlocked, webhook non-expiring + dedup) and a clean frontend web smoke. Native purchase/launch refresh needs a device build to confirm.

## Iteration 49 — Complimentary 7-day Premium for new accounts
- grant_welcome_premium(user_id) runs on every brand-new account creation path (/auth/register, /auth/session Google, /auth/apple) and sets complimentary_started_at, complimentary_expires_at = now+7d, complimentary_used, trial_used, premium_until = expiry, premium_source = "complimentary". It is a no-op when complimentary_used / trial_used / premium_until already exist, so it cannot restart or re-grant (reinstall, logout/login, new device) and never touches existing paid accounts.
- complimentary_state() adds complimentary_active / complimentary_days_left / complimentary_expires_at to /auth/me and /membership/plans. Premium entitlement is still the SINGLE existing is_premium() check (premium_until > now), so paid RevenueCat entitlement OR an unexpired complimentary period = Premium, otherwise Free. No second premium system.
- A purchase during the period wins: POST /api/membership/entitlement grants/extends premium_until and flips premium_source to "revenuecat", so complimentary_active goes false while access continues. The complimentary period never creates a subscription, never charges and never auto-renews; the old opt-in /membership/trial path is closed for these accounts (trial_used already true).
- On expiry the account simply returns to Free (no data touched); Free-tier limits resume through the existing enforce_limit gates.
- UI: users land in the app already Premium (no opt-in screen). Home shows a subtle `complimentary-pill` ("Premium Access · N days remaining"), Profile shows `complimentary-row` with "Complimentary — no charge, and it won't auto-renew", and /premium shows `premium-complimentary` welcome-gift copy instead of the Start Trial CTA.
- EXISTING USERS: not back-filled. Only accounts created after this ships receive the grant (the grant happens at creation, never on login).
- Verified by testing agent iteration 49: backend 12/12 pytest (grant, no restart across sessions, once-only, expiry to Free with data intact, full access during period, purchase precedence, reviewer + existing free untouched, trial path closed) and a frontend web smoke of signup -> pill -> profile row -> premium copy, plus reviewer regression.

## Iteration 50 — Bulk upload honesty + subscription management (live fix pass)
1. BULK UPLOAD ROOT CAUSE: reproduced in preview — for a NON-PREMIUM account at/over the 100-piece free cap, POST /api/capture succeeds but EVERY POST /api/items returns 402 (free wardrobe cap), so every tile failed, 0 were added, and the old screen still printed "All set — they are in your wardrobe now." The live account read as non-premium because of the RevenueCat entitlement bug fixed in iteration 48 while holding a 100+ piece wardrobe.
   - bulk-add.tsx now captures the real reason per photo (402 gate message, expired session, timeout, too large, 400 detail), shows it under the failed tile, and reports honestly: all-success "X pieces added / All set…", partial "X of Y pieces added" with per-item reasons, zero "0 pieces added / We couldn't add these items. Please try again."
   - "Retry failed items" re-runs ONLY the failed photos from the images already picked (no re-picking), and a "See Premium" button appears when the failure was a Premium/cap gate.
   - An item is only counted as added when the wardrobe record returns an id, and the background cleaning pass now maps cleaned photos by row index (previously a cleaned photo could land on the wrong tile when a batch contained failures). 402s create no partial, duplicate or orphan records.
2. MANAGE / CANCEL SUBSCRIPTION: Profile opens Apple's native StoreKit sheet via Purchases.showManageSubscriptions(), falling back to the store subscription page (web falls back to /premium). No custom cancellation logic; RevenueCat products and entitlements untouched.
3. MEMBERSHIP DISPLAY: new Profile MEMBERSHIP section with exactly one state — Premium Membership (plan Monthly/Annual from the RevenueCat product via the new premium_plan field, renews/expires, Manage / Cancel Subscription), Complimentary Premium Access (Ends date, days remaining, "No subscription has been started and you will not be charged automatically.", See Premium plans, and NO cancel button), or Free Membership + Go Premium.
4. DELETE ACCOUNT: paid members now see "Deleting your Aureve account does not automatically cancel your App Store subscription." plus a Manage / Cancel Subscription button in the confirm dialog; complimentary members do not (there is no subscription). Deletion and cancellation stay separate actions.
- The iteration 49 complimentary 7-day Premium system is unchanged and was re-verified.
- Verified by testing agent iteration 50: backend 24/24 pytest and the three bulk-result states, retry-without-re-picking, all three membership states and the delete warning in the UI. Tightened premium_plan_label afterwards so ids like "promo" are no longer read as Monthly.

## Iteration 51 — Free wardrobe limit UX + slot-aware batch upload (final pre-relaunch)
- New GET /api/items/capacity returns {count, cap, remaining, full, premium}; POST /api/items still enforces FREE_ITEM_CAP=100 server-side, so hiding the button is never the only protection. Premium AND complimentary-active accounts report cap null and are never limited.
- WARDROBE at 100 free pieces: the Add button is replaced by a "Wardrobe full" pill and the root shows a card — "Your Free wardrobe is full / You have reached the 100-piece limit on your Free account. Upgrade to Premium for unlimited wardrobe uploads." with an Upgrade to Premium button. Capacity comes from the server (the root level only loads the lightweight summary), and deleting a piece refreshes it so Add returns immediately. /add-item also guards with the same card, so no photo or AI analysis is wasted.
- BULK ADD is slot-aware: it reads /items/capacity first and only uploads/analyses as many photos as there are free slots; the rest are marked "Free wardrobe limit reached" with the upgrade copy and NEVER sent for analysis. If the wardrobe fills mid-run (402) the remaining photos are marked the same way and the loop stops. Copy: partial = "3 of 5 pieces added" + limit explanation; zero slots = "Your Free wardrobe is full" (never the generic technical failure text). Retry failed items only offers genuinely retryable failures, and Add more is hidden once full.
- Verified: backend 10/10 pytest in iteration 51 (capacity values, route not shadowed, server cap intact with no orphan writes, premium/complimentary exempt, delete frees a slot) plus a main-agent Playwright pass on a seeded 97-piece free account: 5 photos picked -> exactly 3 /api/capture calls, "3 of 5 pieces added", Upgrade to Premium shown, no Retry/Add more; at 100 pieces -> full card + pill, no Add button, add-item guard, zero /api/capture calls on bulk add; after deleting one piece the Add button returned. Test account and filler items deleted; reviewer and user_testaura01 verified untouched.

## Iteration 52 — Memory diagnostic + orig_photo projection (approved, read-only diagnosis first)
- DIAGNOSIS (read-only, nothing deployed/restarted in prod): production backend limit is 512Mi (request 128Mi), 2 replicas x 1 uvicorn worker, MongoDB is managed Atlas (NOT in the pod, so no in-pod WiredTiger cache). Pod up ~15 days with restart_count 0, zero OOMKilled/exit-137, and the last 24h logs show health probes only — so "100% memory" is a flat baseline + reclaimable page cache filling the cgroup, NOT a leak.
- Measured baseline: ~206MB RSS before any request, of which `import emergentintegrations.llm.chat` alone adds ~131MB. Sequential traffic does not grow RSS (50+ calls moved it 36KB); 12 concurrent full-wardrobe loads added ~14MB that glibc then retained.
- IMPLEMENTED (user-approved): added `{"orig_photo": 0}` to the 14 db.items.find projections that previously pulled the internal original-upload field: /laundry, /capture duplicates, /stylist/chat, _build_outfit, /tryon, /items/{id}/compatibility, /outfit/feedback, /shop-check, pending_wear_check, /insights/missing-piece, /insights/shopping-intelligence, /packing/plan, /capsule/build, /insights/health-report. `orig_photo` is read in exactly ONE place — POST /api/items/{item_id}/clean (find_one) — which was deliberately left untouched. No logic, response-shape or UI change.
- HONEST CAVEAT: measured saving in the current data is near zero because only 3 of 1333 items actually have orig_photo populated (~0MB vs 51MB of `photo`). The change is correct and permanently prevents the field from being loaded, but it is NOT the fix for the memory ceiling.
- THE REAL HOTSPOT (identified, NOT implemented, awaiting approval): 10 of those endpoints load every item's base64 `photo` (avg 37KB, 51MB across 1333 items) purely to build a text summary for the AI, then only need photos for the handful of resolved items they return. Proposed fix: fetch the pool with photo/thumb/worn_photo excluded and hydrate photos for just the resolved ids — identical responses and appearance, ~25-35MB less transient allocation per AI request on a 300-piece wardrobe. /tryon and /capture duplicates genuinely need photos and would keep them.
- Verified by testing agent iteration 52 (report written to /app/test_reports/iteration_51.json, tests in backend/tests/test_iteration52_orig_photo_projection.py): 21/21 new backend tests pass with live AI and nothing mocked, plus the 10 iteration-51 capacity tests. The agent seeded an item with a real orig_photo so every changed endpoint actually loaded the heavy field. Photos still present everywhere they were before (items/summary/category, item detail, laundry, capture duplicates, dressme, wear/pending, stylist outfits, compatibility, shop-check, packing, capsule, outfit/feedback); /items/{id}/clean still rebuilds from orig_photo; add/edit still store it; free 100-item cap and /items/capacity unchanged.

## Iteration 53 — Wardrobe pool: stop loading photos the AI never looks at (user-approved)
- ROOT ISSUE: ten AI endpoints loaded EVERY item's base64 imagery purely to build a TEXT prompt (summarize_items_for_ai), then only returned a handful of pieces. On a 512Mi pod with a ~206MB import baseline, that transient allocation is what pins memory.
- NEW HELPERS (server.py, after available_items): `wardrobe_pool(user, limit)` loads items with AI_POOL_PROJECTION {_id:0, orig_photo:0, photo:0, thumb:0, worn_photo:0} (metadata only); `hydrate_photos(user, items, keys=("photo","thumb","worn_photo"))` re-queries just the needed ids and mutates those dicts in place (only sets a key the DB doc actually has, so absent keys stay absent; shared dicts across several response keys are covered once).
- CONVERTED TO wardrobe_pool: /capture duplicates, /stylist/chat, _build_outfit (Dress Me + stylist suggest + Mix It Up), /items/{id}/compatibility, /outfit/feedback, /shop-check, /insights/missing-piece, /insights/shopping-intelligence, /packing/plan, /capsule/build, /insights/health-report. hydrate_photos is called in 8 of them right before the response is built; /capture passes keys=("photo",) so the duplicates payload keeps its original shape. Compatibility's `focus` find_one also got orig_photo:0. The {"id": {"$ne": item_id}} Mongo filter became an equivalent in-Python filter (verified the focus item never appears in its own matches).
- DELIBERATELY UNCHANGED (genuinely need imagery): GET /api/items, /api/laundry, /api/tryon, /api/wear/pending, outfits/collections/plans/wear-log endpoints, /api/items/{id}/clean.
- MEASURED (backend/scripts/mem_compare_rss.py — real documents, process RSS, not tracemalloc, run twice): 300 real pieces cost 38.5MB before vs 5.7MB after per AI request — ~33MB and ~85% less. A 100-piece seeded wardrobe (small photos) went 1.8MB -> 1.0MB. NOT measured: the effect on the production dashboard figure, which needs a redeploy.
- Verified by testing agent iteration 53 (report /app/test_reports/iteration_52.json, tests backend/tests/test_iteration53_wardrobe_pool_hydration.py + test_iteration53_guest_scope.py): 41/41 with live AI, every returned photo/thumb/worn_photo compared byte-for-byte against the DB, no cross-user photo leakage, demo/reviewer scope intact, and the 21 iteration-52 tests re-run green. Main agent then restored the /capture duplicates shape (photo only, as before the change), fixed the focus projection and re-ran the suites.
- KNOWN PRE-EXISTING FLAKE (not caused by this work, NOT fixed): POST /api/packing/plan returns 500 when the open-meteo forecast call times out, even though the code has an "Weather forecast unavailable — pack versatile layers" fallback for weather=None — the httpx ConnectTimeout propagates instead. Reproduced only under back-to-back test load; open-meteo itself answered 200 in 0.1-0.5s when checked directly. A try/except around forecast_summary would make the intended fallback work.

## Iteration 54 — Pre-Play-release stabilisation: weather fixes + regression (user-approved, nothing deployed)
WEATHER — root causes found and fixed:
1. `useWeather.ts` created PER SCREEN state with no cache: Home, Dress Me, AI Stylist, Hair and the outfit builder each re-ran location + fetch on mount, so the dash (`—`, shown whenever status !== "done") reappeared on every navigation and a stylist message sent in the first seconds carried NO weather — which is exactly why the AI said it had no live weather and asked for the user's city. Rewritten with a MODULE-level cache (30 min fresh, usable for 3 h), a single de-duplicated in-flight request, persistence via storage key `aureve.weather.v1`, session-cached coordinates, time-boxed permission calls, and up to 2 automatic retries (5s, 10s) when there is nothing cached. London stays the last-resort default and is deliberately not cached as the session coordinates.
2. The ipapi.co IP fallback was silently DEAD — the free tier now answers HTTP 429 and the old code JSON-parsed the error body. It now checks res.ok and falls through.
3. `GET /api/weather` had no error handling at all (provider exception = HTTP 500) and no coordinate validation. Now: 400 for out-of-range coordinates, two attempts (6s then 4s, so ≤10s total), and a per-0.1°-cell cache of the last good reading served for up to 60 min when the provider stalls. Verified directly: live read OK; provider forced to fail in the same cell returns the last good reading; an uncached cell returns an honest 502 (no invented weather); bad coordinates return 400.
4. `stylist_chat` now adds an explicit instruction when no temperature is supplied: style for the season, NEVER ask for the city/location, never state the weather. Verified — the stylist no longer asks for a city and does not invent conditions.
5. `geocode_place` / `forecast_summary` catch network errors and return None, so the pre-existing Packing 500 on a slow open-meteo call is gone and the intended "Weather forecast unavailable — pack versatile layers" fallback actually runs.
OTHER CONFIRMED FIXES: the AI Stylist send button sat 21px off-screen at 375px (RN-web flex needs `minWidth: 0` on the TextInput) — fixed; the Android tab bar used a FIXED height so a gesture-navigation bar clipped the labels — now adds `useSafeAreaInsets().bottom` (no change on iOS or on phones without an inset); removed 91 leftover `TEST_*` items from earlier automated runs that were polluting the seeded wardrobes and appearing as Shop Check "similar items" (scripts/clean_test_items.py).
NOT CHANGED, reported instead: wrong-password login returns 400 rather than 401 (auth change, cosmetic); the Packing "forecast unavailable" sentence is AI-rewritten each time so the exact wording is not guaranteed; `READ_MEDIA_IMAGES` is declared although expo-image-picker uses the Android Photo Picker (Play's Photo and Video Permissions policy) — removing it needs device testing on Android 12 and below.
TESTING: testing agent iteration 54 (report /app/test_reports/iteration_53.json, tests backend/tests/test_iteration54_weather_regression.py) covered weather plus a full regression of accounts, wardrobe CRUD + bulk, Dress Me, AI Stylist, Saved/Worn, Shopping Intelligence, membership/capacity and navigation — all passed except the weather provider stall, which the server-side cache above now absorbs. After the fixes: 60/60 backend tests green across iterations 52, 53 and 54; TypeScript clean; weather verified end-to-end in the web preview (Home, Dress Me and a return to Home all instant, no dash).

## Iteration 55 — Final pre-Play changes: photo permission, unreleased-feature gate (user-approved, nothing deployed)
ANDROID PHOTO PERMISSION (user approved removal):
- `app.json`: `READ_MEDIA_IMAGES` removed from `android.permissions`; `READ_MEDIA_IMAGES` + `READ_MEDIA_VIDEO` added to `android.blockedPermissions` so no dependency can reintroduce them. CAMERA and both location permissions untouched. READ_EXTERNAL_STORAGE deliberately NOT blocked — expo-image-picker still needs it on Android 12 and below.
- `src/utils/image.ts`: `ensureLibraryPermission()` returns "granted" immediately on Android — the system photo picker hands over only the chosen images and needs no permission (expo-image-picker dropped these permissions in v16 precisely for Play compliance). iOS and web paths unchanged, so the web preview still exercises the old code; the Android branch can only be proven on a device.
UNRELEASED FEATURES (user said KEEP the code, just make it unreachable):
- Frontend: new `src/config/features.ts` with `FEATURES = {packing, capsule, tryon, planner, looks}` all false. Each of those five screens now starts with `if (!FEATURES.x) return <Redirect href="/" />;` and its original body moved verbatim into a second component. Redirect target is `/` (not `/(tabs)`) so a signed-out deep link lands on Welcome rather than an empty Home.
- Backend: new `UNRELEASED_FEATURES = {"packing","capsule","tryon","planner"}` + `unreleased()` dependency, attached to 10 routes: POST /tryon, GET|PUT|DELETE /tryon/photo, POST|GET /plans, DELETE /plans/{id}, POST /packing/plan, POST /capsule/build, POST /stylist/suggest. They answer 404 like an unknown path, with and without auth. To ship a feature: flip its flag in features.ts AND remove its name from the backend set.
- Copy that advertised the hidden Planner was reworded for Play's misleading-claims policy: onboarding slide 3 ("Plan Your Week with Confidence / Create outfits in advance") is now "Keep Track of What You Wear" about Saved looks and Worn history (icon calendar -> bookmark), and the paywall bullet "Occasion planning" is now "Monthly Wardrobe Health report" (a real Premium feature).
OTHER FIXES THIS ROUND: `usePremiumAccess` now also returns `ready` (= !auth loading) and Profile's two Premium cards ignore taps until it is true — previously a Premium member tapping Wardrobe Health or Shopping Intelligence in the first seconds after launch was sent to the paywall. Expo patch versions aligned with `yarn expo install --fix` (expo 54.0.35->54.0.37, expo-constants 18.0.13->18.0.14, expo-file-system 19.0.23->19.0.24) ahead of the release build.
TESTS UPDATED because their endpoints are now gated: iterations 52/53/54 assert 404 for packing/capsule/tryon/stylist-suggest, and /plans was dropped from the released-endpoint sweep. New `tests/test_iteration55_unreleased_gate.py` (10 gated -> 404, 9 released -> 200) and the testing agent's `tests/test_iteration56_release_gate_regression.py`. Current state: 65 passed + 1 xfail on the two gate suites; 21 + 18 + 21 green on iterations 52/53/54.
ACCEPTED, NOT FIXED (reported to the user): a malformed body gets 422 and a wrong method 405 on gated routes, so a prober can tell the routes exist (no data or stack trace leaks); /dressme still falls back to `db.plans` for today's occasion, harmless while no new plans can be created (2 historical plans, none future); "Wear this today" still has no undo endpoint; the reviewer demo wardrobe disappears once that account adds a real piece.
