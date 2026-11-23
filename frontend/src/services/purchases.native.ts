// Native (iOS/Android) RevenueCat implementation. Guarded so it degrades
// gracefully in Expo Go (native module not linked) and when the public SDK
// keys aren't configured yet. Uses the modern react-native-purchases +
// react-native-purchases-ui (Paywalls & Customer Center).
import { Platform } from "react-native";
import type { Pkg } from "./purchases";

// Aureve is a single-tier product, so ANY active entitlement in CustomerInfo
// unlocks Premium. We deliberately do NOT filter by entitlement identifier,
// product id or subscription type: a lifetime/promotional/"unlimited duration"
// entitlement has no expiry and no subscription product, and must still unlock.
export const ENTITLEMENT_ID = process.env.EXPO_PUBLIC_REVENUECAT_ENTITLEMENT || "";

let Purchases: any = null;
let RevenueCatUI: any = null;
let configured = false;

const IOS_KEY = process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY || "";
const ANDROID_KEY = process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_KEY || "";

try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  Purchases = require("react-native-purchases").default;
} catch {
  Purchases = null;
}
try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  RevenueCatUI = require("react-native-purchases-ui").default;
} catch {
  RevenueCatUI = null;
}

function apiKey(): string {
  return Platform.OS === "ios" ? IOS_KEY : ANDROID_KEY;
}

export function isPurchasesAvailable(): boolean {
  return !!Purchases && !!apiKey() && configured;
}

export async function initPurchases(userId: string): Promise<void> {
  if (!Purchases || !apiKey()) return; // Expo Go or keys not set yet
  try {
    if (!configured) {
      await Purchases.configure({ apiKey: apiKey(), appUserID: userId });
      configured = true;
    } else {
      // Already configured this launch (e.g. account switch) — rebind identity.
      await Purchases.logIn(userId);
    }
  } catch {
    configured = false;
  }
}

function activeEntitlements(info: any): any[] {
  const active = info?.entitlements?.active || {};
  return Object.values(active);
}

function isEntitled(info: any): boolean {
  return activeEntitlements(info).length > 0;
}

/** The entitlement state the backend needs, read straight from CustomerInfo. */
export function entitlementState(info: any): {
  active: boolean;
  entitlement_id: string | null;
  expires_at: string | null;
  product_id: string | null;
  app_user_id: string | null;
} {
  const ents = activeEntitlements(info);
  // Prefer the configured entitlement if present, otherwise the first active one.
  const chosen =
    (ENTITLEMENT_ID && info?.entitlements?.active?.[ENTITLEMENT_ID]) || ents[0] || null;
  return {
    active: ents.length > 0,
    entitlement_id: chosen?.identifier ?? null,
    // null for lifetime / promotional / "unlimited duration" entitlements.
    expires_at: chosen?.expirationDate ?? null,
    product_id: chosen?.productIdentifier ?? null,
    app_user_id: info?.originalAppUserId ?? null,
  };
}

/** Force a fresh CustomerInfo fetch (used on launch and on app foreground). */
export async function refreshCustomerInfo(): Promise<any | null> {
  if (!isPurchasesAvailable()) return null;
  try {
    if (Purchases.invalidateCustomerInfoCache) await Purchases.invalidateCustomerInfoCache();
    return await Purchases.getCustomerInfo();
  } catch {
    return null;
  }
}

/** Reactive entitlement updates (purchase, renewal, restore, grant). */
export function addCustomerInfoListener(cb: (info: any) => void): () => void {
  if (!Purchases?.addCustomerInfoUpdateListener) return () => {};
  Purchases.addCustomerInfoUpdateListener(cb);
  return () => {
    try { Purchases.removeCustomerInfoUpdateListener(cb); } catch {}
  };
}

function periodOf(p: any): Pkg["period"] {
  const t = (p?.packageType || "").toUpperCase();
  if (t === "ANNUAL") return "annual";
  if (t === "MONTHLY") return "monthly";
  if (t === "LIFETIME") return "lifetime";
  return "other";
}

export async function getPackages(): Promise<Pkg[]> {
  if (!isPurchasesAvailable()) return [];
  try {
    const offerings = await Purchases.getOfferings();
    const pkgs = offerings?.current?.availablePackages ?? [];
    return pkgs.map((p: any) => ({
      id: p.identifier,
      title: p.product?.title || p.identifier,
      priceString: p.product?.priceString || "",
      period: periodOf(p),
      raw: p,
    }));
  } catch {
    return [];
  }
}

export async function purchasePackage(pkg: Pkg): Promise<{ premium: boolean; info?: any }> {
  if (!isPurchasesAvailable() || !pkg.raw) return { premium: false };
  const { customerInfo } = await Purchases.purchasePackage(pkg.raw);
  return { premium: isEntitled(customerInfo), info: customerInfo };
}

export async function restorePurchases(): Promise<{ premium: boolean; info?: any }> {
  if (!isPurchasesAvailable()) return { premium: false };
  const info = await Purchases.restorePurchases();
  return { premium: isEntitled(info), info };
}

export async function getIsPremium(): Promise<boolean> {
  if (!isPurchasesAvailable()) return false;
  const info = await refreshCustomerInfo();
  return isEntitled(info);
}

// Presents the paywall you designed in the RevenueCat dashboard. Returns true
// if the user ends the flow entitled/purchased.
export async function presentPaywall(): Promise<{ premium: boolean; info?: any }> {
  if (!RevenueCatUI || !isPurchasesAvailable()) return { premium: false };
  try {
    await RevenueCatUI.presentPaywall();
  } catch {
    /* user dismissed or error */
  }
  const info = await refreshCustomerInfo();
  return { premium: isEntitled(info), info };
}

// Presents the RevenueCat Customer Center (manage/cancel/restore, refunds, etc.).
/** Apple's / Google's own subscription-management sheet (StoreKit on iOS). */
export async function showManageSubscriptions(): Promise<boolean> {
  if (!isPurchasesAvailable() || !Purchases.showManageSubscriptions) return false;
  try {
    await Purchases.showManageSubscriptions();
    return true;
  } catch {
    return false;
  }
}

export async function presentCustomerCenter(): Promise<void> {
  if (!RevenueCatUI || !isPurchasesAvailable()) return;
  try {
    await RevenueCatUI.presentCustomerCenter();
  } catch {
    /* dismissed */
  }
}
