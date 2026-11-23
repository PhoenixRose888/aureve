// Web / fallback stub. react-native-purchases(-ui) is NEVER bundled on web —
// Metro resolves purchases.native.ts on iOS/Android and this file elsewhere.
export type Pkg = {
  id: string;
  title: string;
  priceString: string;
  period: "monthly" | "annual" | "lifetime" | "other";
  raw?: any;
};

export const ENTITLEMENT_ID = process.env.EXPO_PUBLIC_REVENUECAT_ENTITLEMENT || "";

export function isPurchasesAvailable(): boolean {
  return false;
}

export async function initPurchases(_userId: string): Promise<void> {
  /* no-op on web */
}

export async function getPackages(): Promise<Pkg[]> {
  return [];
}

export async function purchasePackage(_pkg: Pkg): Promise<{ premium: boolean; info?: any }> {
  return { premium: false };
}

export async function restorePurchases(): Promise<{ premium: boolean; info?: any }> {
  return { premium: false };
}

export async function getIsPremium(): Promise<boolean> {
  return false;
}

export async function presentPaywall(): Promise<{ premium: boolean; info?: any }> {
  return { premium: false };
}

export function entitlementState(_info: any) {
  return { active: false, entitlement_id: null, expires_at: null, product_id: null, app_user_id: null };
}

export async function refreshCustomerInfo(): Promise<any | null> {
  return null;
}

export function addCustomerInfoListener(_cb: (info: any) => void): () => void {
  return () => {};
}

export async function showManageSubscriptions(): Promise<boolean> {
  return false;
}

export async function presentCustomerCenter(): Promise<void> {
  /* no-op on web */
}
