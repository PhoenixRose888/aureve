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
  - Packing / capsule assistant ("4 days in Melbourne → carry-on capsule").
  - Calendar integration (prep outfits before events).
  - Outfit history + "don't repeat around the same people".
  - Save & browse a gallery of built looks (outfits screen UI).
- **P2**
  - Virtual try-on (AI-generated you wearing the outfit).
  - Social mode (compare wardrobes / borrow from friends).
  - Wardrobe health reminders (sell/donate/upcycle prompts every 6 months).
  - Richer figure-aware learning from worn photos (cuts/waist heights/lengths).
  - Laundry status, resale/donation pile, condition-based repair prompts.

## Next Tasks
1. Build the "Looks" gallery screen to browse saved outfits + outfit history.
2. Packing capsule generator (high subscription-driver per user feedback).
3. Deepen figure-aware learning using worn photos.

## Notes / Mocks
- No mocked APIs. All AI + weather + auth are live.
- Test session seeded for automated backend testing: `Authorization: Bearer test-session-token-aura-123` (user_testaura01). Real users get their own user_id via Google.
- Features needing a native build to fully test: none blocking; camera/photos/location handled via expo APIs and work in Expo Go (Google OAuth login works in Expo Go too).
