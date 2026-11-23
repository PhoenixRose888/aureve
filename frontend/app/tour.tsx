import React, { useState } from "react";
import { View, StyleSheet, Pressable } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { storage } from "@/src/utils/storage";

type Step = { icon: keyof typeof Feather.glyphMap; title: string; body: string };

/** Very short first-run tour. Replayable from Profile → How Aureve Works. */
const STEPS: Step[] = [
  { icon: "home", title: "Home", body: "This is your daily styling hub. Dress Me, plans and recommendations live here." },
  { icon: "plus-circle", title: "Add / Bulk Add", body: "Start building your wardrobe here. Add one piece or upload several at once." },
  { icon: "grid", title: "Wardrobe", body: "Browse your clothes by category and narrow them using filters." },
  { icon: "sun", title: "Dress Me", body: "Tell Aureve what you're doing and get an outfit from your own wardrobe." },
  { icon: "user", title: "Profile", body: "Manage your style profile, account, subscription and settings here." },
];

export default function Tour() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState(0);
  const s = STEPS[step];
  const last = step === STEPS.length - 1;

  const close = async () => {
    await storage.setItem("aureve_tour_pending", false);
    router.back();
  };

  return (
    <View style={styles.backdrop} testID="app-tour">
      <View style={[styles.card, { marginBottom: insets.bottom + spacing.xl }]}>
        <View style={styles.iconWrap}>
          <Feather name={s.icon} size={24} color={colors.onBrandTertiary} />
        </View>
        <Display weight="semibold" style={styles.title}>{s.title}</Display>
        <Txt style={styles.body}>{s.body}</Txt>

        <View style={styles.dots}>
          {STEPS.map((_, i) => (
            <View key={i} style={[styles.dot, i === step && styles.dotActive]} />
          ))}
        </View>

        <Pressable
          style={styles.primary}
          testID="tour-next"
          onPress={() => (last ? close() : setStep(step + 1))}
        >
          <Txt style={styles.primaryTxt}>{last ? "Done" : "Next"}</Txt>
        </Pressable>
        <Pressable style={styles.skip} testID="tour-skip" onPress={close} hitSlop={8}>
          <Txt style={styles.skipTxt}>Skip</Txt>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.55)", justifyContent: "flex-end", paddingHorizontal: spacing.lg },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center" },
  iconWrap: {
    width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center", marginBottom: spacing.lg,
  },
  title: { fontSize: 22, color: colors.onSurface, marginBottom: spacing.sm },
  body: { fontSize: 14.5, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 21 },
  dots: { flexDirection: "row", gap: 6, marginTop: spacing.lg, marginBottom: spacing.lg },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.border },
  dotActive: { backgroundColor: colors.sage, width: 18 },
  primary: {
    alignSelf: "stretch", backgroundColor: colors.sage, height: 52, borderRadius: radius.md,
    alignItems: "center", justifyContent: "center",
  },
  primaryTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayBold },
  skip: { height: 44, alignItems: "center", justifyContent: "center", alignSelf: "stretch" },
  skipTxt: { fontSize: 14, color: colors.onSurfaceSecondary, textDecorationLine: "underline" },
});
