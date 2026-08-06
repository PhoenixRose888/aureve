// Native (iOS/Android) RevenueCat implementation. Guarded so it degrades
// gracefully in Expo Go (native module not linked) and when the public SDK
// keys aren't configured yet. Uses the modern react-native-purchases +
// react-native-purchases-ui (Paywalls & Customer Center).
import { Platform } from "react-native";
import type { Pkg } from "./purchases";

// Entitlement identifier from your RevenueCat dashboard. Leave the env var
// empty to treat ANY active entitlement as "pro" (robust for a single-tier app).
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
    await Purchases.configure({ apiKey: apiKey(), appUserID: userId });
    configured = true;
  } catch {
    configured = false;
  }
}

function isEntitled(info: any): boolean {
  const active = info?.entitlements?.active || {};
  if (ENTITLEMENT_ID) return !!active[ENTITLEMENT_ID];
  return Object.keys(active).length > 0;
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

export async function purchasePackage(pkg: Pkg): Promise<{ premium: boolean }> {
  if (!isPurchasesAvailable() || !pkg.raw) return { premium: false };
  const { customerInfo } = await Purchases.purchasePackage(pkg.raw);
  return { premium: isEntitled(customerInfo) };
}

export async function restorePurchases(): Promise<{ premium: boolean }> {
  if (!isPurchasesAvailable()) return { premium: false };
  const info = await Purchases.restorePurchases();
  return { premium: isEntitled(info) };
}

export async function getIsPremium(): Promise<boolean> {
  if (!isPurchasesAvailable()) return false;
  try {
    const info = await Purchases.getCustomerInfo();
    return isEntitled(info);
  } catch {
    return false;
  }
}

// Presents the paywall you designed in the RevenueCat dashboard. Returns true
// if the user ends the flow entitled/purchased.
export async function presentPaywall(): Promise<{ premium: boolean }> {
  if (!RevenueCatUI || !isPurchasesAvailable()) return { premium: false };
  try {
    await RevenueCatUI.presentPaywall();
  } catch {
    /* user dismissed or error */
  }
  return { premium: await getIsPremium() };
}

// Presents the RevenueCat Customer Center (manage/cancel/restore, refunds, etc.).
export async function presentCustomerCenter(): Promise<void> {
  if (!RevenueCatUI || !isPurchasesAvailable()) return;
  try {
    await RevenueCatUI.presentCustomerCenter();
  } catch {
    /* dismissed */
  }
}
