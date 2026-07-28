import React, { useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/context/AuthContext";
import { isPurchasesAvailable, getPackages, purchasePackage, restorePurchases, Pkg } from "@/src/services/purchases";

const FEATURES = [
  "Unlimited AI styling & outfits",
  "Dress Me — one tap every morning",
  "Packing Assistant for any trip",
  "Shopping Intelligence (skip duplicates)",
  "Colour analysis + hair & makeup",
  "Capsule wardrobes & occasion planning",
  "Household — one plan for everyone",
];

export default function Premium() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const [plan, setPlan] = useState<"annual" | "monthly">("annual");
  const [loading, setLoading] = useState(false);
  const [trialLoading, setTrialLoading] = useState(false);
  const [error, setError] = useState("");
  const [iapPkgs, setIapPkgs] = useState<Pkg[]>([]);
  const [restoring, setRestoring] = useState(false);
  const iapReady = iapPkgs.length > 0;

  React.useEffect(() => {
    if (isPurchasesAvailable()) {
      getPackages().then(setIapPkgs).catch(() => {});
    }
  }, []);

  const alreadyPremium = !!user?.premium;
  const trialEligible = !!user?.trial_eligible;

  const restore = async () => {
    setRestoring(true);
    setError("");
    try {
      const r = await restorePurchases();
      await refreshUser();
      if (!r.premium) setError("No previous purchases found to restore.");
    } catch (e: any) {
      setError(e?.message || "Couldn't restore purchases.");
    }
    setRestoring(false);
  };

  const startTrial = async () => {
    setTrialLoading(true);
    setError("");
    try {
      await api("/membership/trial", { method: "POST" });
      await refreshUser();
      router.replace("/(tabs)/dressme");
    } catch (e: any) {
      setError(e.message || "Couldn't start your trial");
    }
    setTrialLoading(false);
  };

  const start = async () => {
    setLoading(true);
    setError("");
    try {
      // Native in-app purchase (App Store / Play Billing) when available.
      if (iapReady) {
        const pkg = iapPkgs.find((p) => p.period === plan) || iapPkgs[0];
        const r = await purchasePackage(pkg);
        await refreshUser();
        if (r.premium) router.replace("/(tabs)/dressme");
        setLoading(false);
        return;
      }
      // Web fallback — Stripe hosted checkout.
      const origin =
        Platform.OS === "web"
          ? window.location.origin
          : (process.env.EXPO_PUBLIC_BACKEND_URL as string);
      const r = await api<{ url: string }>("/payments/checkout", {
        method: "POST",
        body: { plan, origin_url: origin },
      });
      if (Platform.OS === "web") {
        window.location.href = r.url;
      } else {
        await WebBrowser.openBrowserAsync(r.url);
        await refreshUser();
      }
    } catch (e: any) {
      if (!/cancel/i.test(e?.message || "")) setError(e.message || "Couldn't start checkout");
    }
    setLoading(false);
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="premium-back" hitSlop={12}>
          <Feather name="x" size={24} color={colors.onSurfaceInverse} />
        </Pressable>
        <Txt style={styles.headerKicker}>AUREVE PREMIUM</Txt>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Display weight="medium" style={styles.title}>Your personal{"\n"}AI stylist.</Display>
        <Txt style={styles.sub}>
          Keep your whole wardrobe free forever. Premium unlocks the AI that dresses you every day.
        </Txt>

        <View style={styles.featureList}>
          {FEATURES.map((f) => (
            <View key={f} style={styles.featureRow}>
              <Feather name="check" size={16} color={colors.brandTertiary} />
              <Txt style={styles.featureTxt}>{f}</Txt>
            </View>
          ))}
        </View>

        {alreadyPremium ? (
          <View style={styles.activeCard} testID="premium-active">
            <Feather name="award" size={22} color={colors.brandTertiary} />
            <Txt style={styles.activeTxt}>You are on Premium.</Txt>
            {user?.premium_until ? (
              <Txt style={styles.activeSub}>
                Active until {new Date(user.premium_until).toLocaleDateString()}
              </Txt>
            ) : null}
            <Txt style={styles.activeSub}>Renew below to extend your household plan.</Txt>
          </View>
        ) : null}

        {trialEligible && !alreadyPremium ? (
          <Pressable style={styles.trialCta} testID="start-trial-button" onPress={startTrial} disabled={trialLoading}>
            {trialLoading ? (
              <ActivityIndicator color={colors.onBrandTertiary} />
            ) : (
              <>
                <Feather name="gift" size={18} color={colors.onBrandTertiary} />
                <View>
                  <Txt style={styles.trialTitle}>Start 7 days free</Txt>
                  <Txt style={styles.trialSub}>Full access. No card required.</Txt>
                </View>
              </>
            )}
          </Pressable>
        ) : null}

        <Txt style={styles.plansHeading}>
          {trialEligible && !alreadyPremium ? "OR CHOOSE A PLAN" : "CHOOSE A PLAN"}
        </Txt>
        <View style={styles.plans}>
          <Pressable
            style={[styles.planCard, plan === "annual" && styles.planActive]}
            testID="plan-annual"
            onPress={() => setPlan("annual")}
          >
            <View style={styles.popular}><Txt style={styles.popularTxt}>⭐ MOST POPULAR · SAVE 33%</Txt></View>
            <View style={styles.planTop}>
              <Txt style={[styles.planName, plan === "annual" && styles.planNameActive]}>Annual</Txt>
              <View style={[styles.radio, plan === "annual" && styles.radioActive]}>
                {plan === "annual" && <Feather name="check" size={13} color={colors.surfaceInverse} />}
              </View>
            </View>
            <Txt style={[styles.planPrice, plan === "annual" && styles.planPriceActive]}>$79.99<Txt style={styles.planPer}>/year</Txt></Txt>
            <Txt style={styles.planNote}>Just $6.67/month</Txt>
          </Pressable>

          <Pressable
            style={[styles.planCard, plan === "monthly" && styles.planActive]}
            testID="plan-monthly"
            onPress={() => setPlan("monthly")}
          >
            <View style={styles.planTop}>
              <Txt style={[styles.planName, plan === "monthly" && styles.planNameActive]}>Monthly</Txt>
              <View style={[styles.radio, plan === "monthly" && styles.radioActive]}>
                {plan === "monthly" && <Feather name="check" size={13} color={colors.surfaceInverse} />}
              </View>
            </View>
            <Txt style={[styles.planPrice, plan === "monthly" && styles.planPriceActive]}>$9.99<Txt style={styles.planPer}>/month</Txt></Txt>
            <Txt style={styles.planNote}>Cancel anytime</Txt>
          </Pressable>
        </View>

        {error ? <Txt style={styles.error} testID="premium-error">{error}</Txt> : null}

        <Pressable style={styles.cta} testID="start-premium-button" onPress={start} disabled={loading}>
          {loading ? (
            <ActivityIndicator color={colors.surfaceInverse} />
          ) : (
            <Txt style={styles.ctaTxt}>{alreadyPremium ? "Extend Premium" : "Start Premium"}</Txt>
          )}
        </Pressable>

        {Platform.OS !== "web" ? (
          <Pressable style={styles.restoreBtn} testID="restore-button" onPress={restore} disabled={restoring}>
            {restoring ? (
              <ActivityIndicator color={colors.brandTertiary} />
            ) : (
              <Txt style={styles.restoreTxt}>Restore purchases</Txt>
            )}
          </Pressable>
        ) : null}

        <Txt style={styles.legal}>
          One plan covers your whole household (up to 6 members).{" "}
          {Platform.OS === "web"
            ? "Secure checkout by Stripe."
            : "Billed through your App Store / Google Play account; manage or cancel anytime in your store settings."}
        </Txt>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
  headerKicker: { fontSize: 11, letterSpacing: 3, color: colors.brandTertiary },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  title: { fontSize: 40, lineHeight: 44, color: colors.onSurfaceInverse },
  sub: { fontSize: 15, color: "rgba(250,250,250,0.7)", lineHeight: 22, marginTop: spacing.md },
  featureList: { marginTop: spacing["2xl"], gap: spacing.md },
  featureRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  featureTxt: { flex: 1, fontSize: 15, color: "rgba(250,250,250,0.9)" },
  activeCard: { marginTop: spacing["2xl"], borderWidth: 0.5, borderColor: colors.brand, borderRadius: radius.md, padding: spacing.lg, alignItems: "center", gap: 4 },
  activeTxt: { fontSize: 16, color: colors.onSurfaceInverse },
  activeSub: { fontSize: 12, color: "rgba(250,250,250,0.6)" },
  plans: { marginTop: spacing.md, gap: spacing.md },
  trialCta: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginTop: spacing["2xl"], minHeight: 64, justifyContent: "center" },
  trialTitle: { fontSize: 16, color: colors.onBrandTertiary },
  trialSub: { fontSize: 12, color: colors.onBrandTertiary, opacity: 0.75, marginTop: 1 },
  plansHeading: { fontSize: 11, letterSpacing: 2, color: "rgba(250,249,246,0.5)", marginTop: spacing["2xl"], marginBottom: spacing.xs },
  planCard: { borderWidth: 1, borderColor: "rgba(250,250,250,0.2)", borderRadius: radius.md, padding: spacing.lg },
  planActive: { borderColor: colors.brandTertiary, backgroundColor: "rgba(232,223,216,0.08)" },
  popular: { alignSelf: "flex-start", backgroundColor: colors.brandTertiary, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 3, marginBottom: spacing.sm },
  popularTxt: { fontSize: 10, letterSpacing: 1, color: colors.onBrandTertiary },
  planTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  planName: { fontSize: 16, color: "rgba(250,250,250,0.8)" },
  planNameActive: { color: colors.onSurfaceInverse },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 1, borderColor: "rgba(250,250,250,0.4)", alignItems: "center", justifyContent: "center" },
  radioActive: { backgroundColor: colors.brandTertiary, borderColor: colors.brandTertiary },
  planPrice: { fontSize: 28, color: "rgba(250,250,250,0.85)", marginTop: spacing.sm },
  planPriceActive: { color: colors.onSurfaceInverse },
  planPer: { fontSize: 14, color: "rgba(250,250,250,0.5)" },
  planNote: { fontSize: 12, color: "rgba(250,250,250,0.5)", marginTop: 2 },
  error: { color: colors.brandTertiary, fontSize: 13, marginTop: spacing.lg, textAlign: "center" },
  cta: { backgroundColor: colors.brandTertiary, height: 56, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  ctaTxt: { color: colors.onBrandTertiary, fontSize: 16 },
  restoreBtn: { height: 44, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  restoreTxt: { color: "rgba(250,250,250,0.75)", fontSize: 14, textDecorationLine: "underline" },
  legal: { fontSize: 11, color: "rgba(250,250,250,0.5)", textAlign: "center", marginTop: spacing.md, lineHeight: 16 },
});
