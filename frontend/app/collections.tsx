import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import * as haptics from "@/src/utils/haptics";

/** My Collections is deliberately two clear destinations — outfits the user
 *  saved for later, and outfits they actually wore. */
export default function Collections() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [savedCount, setSavedCount] = useState<number | null>(null);
  const [wornCount, setWornCount] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, w] = await Promise.all([api<any[]>("/outfits"), api<any[]>("/wear")]);
      setSavedCount(Array.isArray(o) ? o.length : 0);
      setWornCount(Array.isArray(w) ? w.length : 0);
    } catch {
      setSavedCount(0);
      setWornCount(0);
    }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const go = (path: string) => { haptics.tap(); router.push(path as any); };
  const label = (n: number | null, one: string, many: string) =>
    n == null ? " " : `${n} ${n === 1 ? one : many}`;

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="collections-back">
          <Feather name="chevron-left" size={26} color={colors.onSurface} />
        </Pressable>
        <BrandMark style={{ marginBottom: 0 }} />
        <View style={{ width: 26 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: spacing["3xl"] }}>
        <View style={styles.titleBlock}>
          <Txt style={styles.kicker}>YOUR WARDROBE, IN USE</Txt>
          <Display weight="semibold" style={styles.title}>My Collections</Display>
        </View>

        <Pressable style={({ pressed }) => [styles.card, styles.savedCard, pressed && styles.pressed]} testID="collections-saved" onPress={() => go("/saved")}>
          <View style={styles.puck}><Feather name="bookmark" size={20} color={colors.goldDeep} /></View>
          <View style={styles.cardBody}>
            <Display weight="semibold" style={styles.cardTitle}>Saved</Display>
            <Txt style={styles.cardSub}>Outfits you&apos;ve kept for later</Txt>
            <Txt style={styles.cardCount}>{label(savedCount, "outfit", "outfits")}</Txt>
          </View>
          <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />
        </Pressable>

        <Pressable style={({ pressed }) => [styles.card, styles.wornCard, pressed && styles.pressed]} testID="collections-worn" onPress={() => go("/worn")}>
          <View style={styles.puck}><Feather name="check-circle" size={20} color={colors.sageDeep} /></View>
          <View style={styles.cardBody}>
            <Display weight="semibold" style={styles.cardTitle}>Worn</Display>
            <Txt style={styles.cardSub}>Outfits you confirmed you wore</Txt>
            <Txt style={styles.cardCount}>{label(wornCount, "wear", "wears")}</Txt>
          </View>
          <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  titleBlock: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.xl },
  kicker: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium, marginBottom: spacing.xs },
  title: { fontSize: 30, letterSpacing: -0.5 },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    marginHorizontal: spacing.lg, marginBottom: spacing.md,
    padding: spacing.lg, minHeight: 116, borderRadius: radius.lg,
    borderWidth: 0.5, borderColor: colors.border,
    shadowColor: colors.ink, shadowOpacity: 0.05, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 1,
  },
  savedCard: { backgroundColor: colors.cream, borderColor: colors.goldSoft },
  wornCard: { backgroundColor: colors.eucalyptus },
  pressed: { opacity: 0.85 },
  puck: { width: 46, height: 46, borderRadius: 23, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  cardBody: { flex: 1 },
  cardTitle: { fontSize: 20, letterSpacing: -0.3, color: colors.onSurface },
  cardSub: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 2 },
  cardCount: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: spacing.xs, fontFamily: fonts.displayMedium },
});
