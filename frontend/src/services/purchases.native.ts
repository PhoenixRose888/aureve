// Native (iOS/Android) RevenueCat implementation. Guarded so it degrades
// gracefully in Expo Go (where the native module isn't linked) and when the
// public SDK keys aren't configured yet.
import { Platform } from "react-native";
import type { Pkg } from "./purchases";

export const ENTITLEMENT_ID = "premium";

let Purchases: any = null;
let configured = false;

const IOS_KEY = process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY || "";
const ANDROID_KEY = process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_KEY || "";

try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  Purchases = require("react-native-purchases").default;
} catch {
  Purchases = null;
}

function apiKey(): string {
  return Platform.OS === "ios" ? IOS_KEY : ANDROID_KEY;
}

export function isPurchasesAvailable(): boolean {
  return !!Purchases && !!apiKey() && configured;
}

export async function initPurchases(userId: string): Promise<void> {
  if (!Purchases || !apiKey()) return; // no SDK linked (Expo Go) or keys not set yet
  try {
    await Purchases.configure({ apiKey: apiKey(), appUserID: userId });
    configured = true;
  } catch {
    configured = false;
  }
}

function periodOf(p: any): Pkg["period"] {
  const t = (p?.packageType || "").toUpperCase();
  if (t === "ANNUAL") return "annual";
  if (t === "MONTHLY") return "monthly";
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

async function entitled(info: any): Promise<boolean> {
  return !!info?.entitlements?.active?.[ENTITLEMENT_ID];
}

export async function purchasePackage(pkg: Pkg): Promise<{ premium: boolean }> {
  if (!isPurchasesAvailable() || !pkg.raw) return { premium: false };
  const { customerInfo } = await Purchases.purchasePackage(pkg.raw);
  return { premium: await entitled(customerInfo) };
}

export async function restorePurchases(): Promise<{ premium: boolean }> {
  if (!isPurchasesAvailable()) return { premium: false };
  const info = await Purchases.restorePurchases();
  return { premium: await entitled(info) };
}
