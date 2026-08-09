# Aureve — App Store & Play Store Submission Checklist

## Before Building

- [ ] **Set `TRIAL_UNLOCK_ALL=false`** in `backend/.env` — disables the free-everything flag
- [ ] **Decide on `FREE_TRIAL_ENABLED`** — set `true` if offering 7-day free trial at launch
- [ ] **Create App Store Connect subscription products:**
  - `premium_monthly` (auto-renewable)
  - `premium_annual` (auto-renewable)
  - Optional: `lifetime` (non-consumable)
  - Set pricing in all territories
- [ ] **Create Play Console subscription products:**
  - Subscription ID: `premium`
  - Base plans: monthly + annual
  - Optional: one-time product for lifetime
- [ ] **RevenueCat setup:**
  - Create iOS app in RevenueCat → get production `appl_…` API key
  - Create Android app in RevenueCat → get production `goog_…` API key
  - Create Entitlement: `premium`
  - Create Offering: `default` → attach monthly/yearly/lifetime packages
  - Connect App Store app (shared secret from ASC)
  - Connect Play Store app (service account JSON — see below)
- [ ] **Replace RevenueCat keys in `frontend/.env`:**
  - `EXPO_PUBLIC_REVENUECAT_IOS_KEY=appl_…` (replace test key)
  - `EXPO_PUBLIC_REVENUECAT_ANDROID_KEY=goog_…` (replace test key)
  - Keep `EXPO_PUBLIC_REVENUECAT_ENTITLEMENT=premium`
- [ ] **Set RevenueCat webhook auth** — choose a secret string, set in:
  - `backend/.env` → `REVENUECAT_WEBHOOK_AUTH=<your-secret>`
  - RevenueCat Dashboard → Webhook → Authorization header value
- [ ] **Google Cloud service account (Play billing verification):**
  1. Create GCP project, enable Google Play Android Developer API
  2. Create service account → download JSON key
  3. Play Console → grant service account access
  4. Upload JSON key to RevenueCat
  5. Save as `frontend/google-play-service-account.json`
- [ ] **Apple ASC API key** → upload to RevenueCat for iOS receipt verification
- [ ] **Google Calendar OAuth** — add production domain to redirect URIs
- [ ] **Compliance URLs live:** privacy policy + account deletion accessible
- [ ] **Review test account works:** `review@aureve.app` / `AureveTest2026`

## Building

- [ ] `npm install -g eas-cli@latest` then `eas login`
- [ ] Fill `ascAppId` and `appleTeamId` in `eas.json`
- [ ] `eas build --platform ios --profile production`
- [ ] `eas build --platform android --profile production`
- [ ] Test preview builds in TestFlight + Play internal track first

## App Store Connect

- [ ] Create app — bundle ID `com.emergent.wardrobeai.l0r5ay`, language: English (Australia)
- [ ] Name: Aureve, Subtitle: AI Wardrobe Stylist, Category: Lifestyle
- [ ] Privacy Policy URL: `https://wardrobe-ai-311.preview.emergentagent.com/api/privacy` (update to prod domain)
- [ ] Upload screenshots from `store-assets/ios-6.9/` (required), `ios-6.5/`, `ios-12.9-ipad/`
- [ ] Enter description + keywords from `memory/ASO_store_listing.md`
- [ ] App Review: demo account `review@aureve.app` / `AureveTest2026`
- [ ] Submit IAPs alongside binary
- [ ] Upload .ipa, submit for review

## Play Console

- [ ] Create app — package `com.emergent.wardrobeai.l0r5ay`
- [ ] Store listing: upload from `store-assets/android-phone/`, `android-7-tablet/`, `android-10-tablet/`
- [ ] Feature graphic: `store-assets/feature-graphic.png` (1024×500)
- [ ] App icon: export `frontend/assets/images/icon.png` at 512×512
- [ ] Data safety: email, photos, location; account deletion URL
- [ ] App access: restricted, provide test credentials
- [ ] Upload .aab to internal track, test IAP, promote to production

## RevenueCat

- [ ] Verify webhook receiving events
- [ ] Verify entitlement grants on purchase
- [ ] Remove test entitlements
- [ ] Verify restore purchases on both platforms

## Final Checks

- [ ] `TRIAL_UNLOCK_ALL=false`, no test RC keys in production build
- [ ] All compliance URLs live and accessible
- [ ] IAP flow end-to-end tested
- [ ] Deep links work: `aureve://` scheme
- [ ] Version: `1.0.0`, versionCode: `103`
- [ ] No placeholder text in store listings

## Key Values

| Item | Value |
|------|-------|
| iOS Bundle ID | `com.emergent.wardrobeai.l0r5ay` |
| Android Package | `com.emergent.wardrobeai.l0r5ay` |
| Version | `1.0.0` / versionCode `103` |
| Developer Email | `houseoffmr@gmail.com` |
| Test Account | `review@aureve.app` / `AureveTest2026` |
| Entitlement | `premium` |
| Privacy Policy | `https://wardrobe-ai-311.preview.emergentagent.com/api/privacy` |
| Account Deletion | `https://wardrobe-ai-311.preview.emergentagent.com/api/account-deletion` |
