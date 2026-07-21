import React, { useEffect, useRef, useState } from "react";
import { View, StyleSheet, ActivityIndicator, Pressable } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/context/AuthContext";

const MAX_TRIES = 8;

export default function PremiumSuccess() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { session_id } = useLocalSearchParams<{ session_id?: string }>();
  const { refreshUser } = useAuth();
  const [state, setState] = useState<"checking" | "active" | "pending" | "error">("checking");
  const tries = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (!session_id) {
        setState("error");
        return;
      }
      try {
        const r = await api<any>(`/payments/status/${session_id}`);
        if (cancelled) return;
        if (r.premium || r.payment_status === "paid") {
          await refreshUser();
          setState("active");
          return;
        }
        if (r.status === "expired") {
          setState("error");
          return;
        }
        tries.current += 1;
        if (tries.current >= MAX_TRIES) {
          setState("pending");
          return;
        }
        setTimeout(poll, 2000);
      } catch {
        if (cancelled) return;
        tries.current += 1;
        if (tries.current >= MAX_TRIES) setState("error");
        else setTimeout(poll, 2000);
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [session_id, refreshUser]);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.center}>
        {state === "checking" ? (
          <>
            <ActivityIndicator color={colors.brandTertiary} size="large" />
            <Txt style={styles.checkTxt}>Confirming your subscription…</Txt>
          </>
        ) : state === "active" ? (
          <>
            <View style={styles.badge}><Feather name="award" size={34} color={colors.onBrandTertiary} /></View>
            <Display weight="medium" style={styles.title}>Welcome to Premium</Display>
            <Txt style={styles.sub}>Your whole household now has the full AI stylist. Let us dress you.</Txt>
            <Pressable style={styles.cta} testID="premium-success-continue" onPress={() => router.replace("/(tabs)")}>
              <Txt style={styles.ctaTxt}>Start styling</Txt>
            </Pressable>
          </>
        ) : state === "pending" ? (
          <>
            <Feather name="clock" size={34} color={colors.brandTertiary} />
            <Display weight="medium" style={styles.title}>Almost there</Display>
            <Txt style={styles.sub}>Your payment is still processing. It may take a moment to activate.</Txt>
            <Pressable style={styles.cta} testID="premium-success-continue" onPress={() => router.replace("/(tabs)")}>
              <Txt style={styles.ctaTxt}>Back to app</Txt>
            </Pressable>
          </>
        ) : (
          <>
            <Feather name="alert-circle" size={34} color={colors.brandTertiary} />
            <Display weight="medium" style={styles.title}>Could not confirm</Display>
            <Txt style={styles.sub}>We could not verify the payment. If you were charged, it will activate shortly.</Txt>
            <Pressable style={styles.cta} testID="premium-success-continue" onPress={() => router.replace("/(tabs)")}>
              <Txt style={styles.ctaTxt}>Back to app</Txt>
            </Pressable>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.lg },
  checkTxt: { color: "rgba(250,250,250,0.7)", fontSize: 14, fontStyle: "italic" },
  badge: { width: 72, height: 72, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 32, color: colors.onSurfaceInverse, textAlign: "center" },
  sub: { fontSize: 15, color: "rgba(250,250,250,0.7)", textAlign: "center", lineHeight: 22 },
  cta: { backgroundColor: colors.brandTertiary, height: 54, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing["2xl"], marginTop: spacing.md },
  ctaTxt: { color: colors.onBrandTertiary, fontSize: 16 },
});
