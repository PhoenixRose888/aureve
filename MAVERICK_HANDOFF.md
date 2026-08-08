# Aureve — Back-of-House Handoff ("Maverick" brief)

App: **Aureve** — AI wardrobe & styling app
Stack: **Expo React Native (expo-router)** frontend · **FastAPI + MongoDB** backend
Developer/brand: **House of FMR** · Contact: **houseoffmr@gmail.com**

---

## 1. App identifiers (DO NOT CHANGE)
- iOS bundle identifier: `com.emergent.wardrobeai.l0r5ay`
- Android package name: `com.emergent.wardrobeai.l0r5ay`
- Android versionCode: `103` (bump +1 for each new build — set in `frontend/app.json` → `expo.android.versionCode`)
- App version: see `frontend/app.json` → `expo.version`

## 2. Compliance URLs (live, public, no login)
- Privacy Policy: `https://<DEPLOYED_DOMAIN>/api/privacy`
- Account deletion: `https://<DEPLOYED_DOMAIN>/api/account-deletion`
- Delete data URL: same as account deletion (`/api/account-deletion` covers full + partial deletion)
- Current preview domain: `https://wardrobe-ai-311.preview.emergentagent.com`
- Source: `backend/server.py` → `privacy_policy_page()` and `account_deletion_page()` (HTML served verbatim)

## 3. RevenueCat integration (in-app purchases)
SDKs used (React Native, NOT SwiftUI): `react-native-purchases` + `react-native-purchases-ui`
Code (platform-isolated so it never enters the web bundle):
- `frontend/src/services/purchases.ts` (web/Expo-Go stub)
- `frontend/src/services/purchases.native.ts` (real impl: configure, offerings, purchase, restore, `presentPaywall()`, `presentCustomerCenter()`, entitlement check)
- Wired in `frontend/app/premium.tsx` (Start Premium → RevenueCat Paywall; Manage subscription → Customer Center; Restore purchases)
- Configured on auth in `frontend/src/context/AuthContext.tsx` via `initPurchases(user_id)` (appUserID = our user_id)

Entitlement: **`premium`** (pinned via env). Keep `premium` as the single entitlement; remove the auto-created "Aureve Pro" Test Store entitlement once its test products are detached.

Backend webhook receiver: `POST /api/webhooks/revenuecat` in `backend/server.py`
- Verifies the `Authorization` header against `REVENUECAT_WEBHOOK_AUTH` (+ optional HMAC via `REVENUECAT_WEBHOOK_SECRET`)
- Idempotent (dedupes on event id in `revenuecat_events`)
- Sets `users.premium_until` / `premium_source` in MongoDB
- Point RevenueCat webhook to: `https://<DEPLOYED_DOMAIN>/api/webhooks/revenuecat`

### Env vars for RevenueCat
Frontend (`frontend/.env`):
- `EXPO_PUBLIC_REVENUECAT_IOS_KEY` — currently the RC **Test Store** key `test_duioYdxNNsMzzaQXzFYpXolUnwp`. Replace with production **`appl_…`** key.
- `EXPO_PUBLIC_REVENUECAT_ANDROID_KEY` — currently the same test key. Replace with production **`goog_…`** key.
- `EXPO_PUBLIC_REVENUECAT_ENTITLEMENT=premium`

Backend (`backend/.env`):
- `REVENUECAT_WEBHOOK_AUTH` — the Authorization header value you set in the RC dashboard (currently empty; set both sides to the same secret string)
- `REVENUECAT_WEBHOOK_SECRET` — optional HMAC signing secret (empty = skipped)
- `REVENUECAT_SECRET_KEY` — reserved for server-side REST calls if needed (empty for now)

### Store product setup (do in App Store Connect / Play Console + RevenueCat)
- App Store Connect: auto-renewable subs `premium_monthly`, `premium_annual` (+ `lifetime` non-consumable if offering lifetime)
- Play Console: subscription `premium` with monthly + annual base plans (+ one-time product for lifetime if used)
- RevenueCat: Entitlement `premium`; Offering `default` with monthly/yearly/lifetime packages attached; connect App Store + Play Store apps
- Play Billing verification: Google Cloud project + service account with Google Play Android Developer API access, JSON key uploaded to RevenueCat (see §6)

## 4. Payments (web fallback)
- Stripe hosted checkout on web only: `POST /api/payments/checkout` (test key already in pod env). Native uses RevenueCat.

## 5. Feature flags (backend `backend/.env`)
- `TRIAL_UNLOCK_ALL` — `true` = everyone gets full Premium (for testers/judging). **Set `false` for paid launch.** (read in `is_premium()`)
- `FREE_TRIAL_ENABLED` — `false` = the in-app 7-day free trial is hidden + endpoint returns 403. (read via `free_trial_enabled()`)

## 6. Google Cloud / Play service account (TODO — user side)
Needed so RevenueCat can verify Google Play purchases:
1. Create Google Cloud project "Aureve"
2. Enable Google Play Android Developer API
3. Create service account → JSON key
4. Play Console → Users & permissions → grant the service account
5. Upload JSON key to RevenueCat (Android app)

## 7. Auth (already built)
- Guest sessions: `POST /api/auth/guest` (auto-seeds 16-item demo wardrobe)
- Email/password: `POST /api/auth/register`, `POST /api/auth/login` (bcrypt, bearer sessions in `user_sessions`, 7-day TTL)
- Google OAuth (Emergent-managed): `POST /api/auth/session` — deferred / guest-first
- Account deletion: `DELETE /api/auth/account` (wipes all user data)
- Bearer token pattern (NOT JWT); `get_current_user` / `get_scope` in `backend/server.py`

## 8. Test / review account
- Email: `review@aureve.app` · Password: `AureveTest2026` (seeded with 16-item wardrobe; use for Play/Apple "App access")

## 9. Store listing copy (ASO)
- See `memory/ASO_store_listing.md` (title, subtitle, keywords, descriptions, screenshot captions)

## 10. Outstanding back-of-house tasks for Maverick
- [ ] Create store subscription products + RevenueCat offering/entitlement (`premium`)
- [ ] Google Cloud project + Play service account → upload JSON to RevenueCat
- [ ] Swap test RC keys → production `appl_…` / `goog_…`
- [ ] Set `REVENUECAT_WEBHOOK_AUTH` on both RC dashboard and backend `.env`
- [ ] Set `TRIAL_UNLOCK_ALL=false` and (optionally) `FREE_TRIAL_ENABLED` for launch
- [ ] Fill Play Data Safety + Apple App Privacy using the URLs in §2
- [ ] Generate builds via Emergent Publish; test IAP in TestFlight / Play internal testing
- [ ] Apple: App Store Connect API key / shared secret into RevenueCat (iOS purchase verification)

## Notes
- IAP (paywall/customer center/purchases) only work in a real build — NOT Expo Go or web.
- Protected env vars: `EXPO_PACKAGER_PROXY_URL`, `EXPO_PACKAGER_HOSTNAME`, `MONGO_URL` — do not modify.
- After any backend/frontend change, redeploy + regenerate builds to push to testers.
