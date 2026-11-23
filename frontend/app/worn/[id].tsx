import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";
import * as haptics from "@/src/utils/haptics";

function fmtWhen(iso?: string) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return `${d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })} · ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  } catch {
    return "";
  }
}

/** A single recorded wear — wear it again, or use it as the starting point for
 *  a refreshed variation. */
export default function WornDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [log, setLog] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [again, setAgain] = useState(false);

  const load = useCallback(async () => {
    try {
      setLog(await api<any>(`/wear/${id}`));
    } catch {
      setLog(null);
    } finally {
      setLoading(false);
    }
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const wearAgain = async () => {
    if (busy || !log) return;
    setBusy(true);
    haptics.tap();
    try {
      await api("/wear", {
        method: "POST",
        body: {
          item_ids: (log.items || []).map((it: any) => it.id),
          name: log.name || log.occasion || "Outfit",
          occasion: log.occasion || "",
          outfit_id: log.outfit_id || null,
        },
      });
      setAgain(true);
      haptics.success();
    } catch {}
    setBusy(false);
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.sage} /></View>;
  if (!log) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <Txt style={{ color: colors.onSurfaceSecondary }}>That wear isn&apos;t in your history.</Txt>
        <Pressable onPress={() => router.back()} style={{ marginTop: spacing.lg }}><Txt style={{ color: colors.sage }}>Go back</Txt></Pressable>
      </View>
    );
  }

  const items = log.items || [];

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="worn-detail-back">
          <Feather name="chevron-left" size={26} color={colors.onSurface} />
        </Pressable>
        <BrandMark style={{ marginBottom: 0 }} />
        <View style={{ width: 26 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: spacing["3xl"] }}>
        <View style={styles.titleBlock}>
          <Txt style={styles.kicker}>WORN</Txt>
          <Display weight="semibold" style={styles.title} numberOfLines={2}>{log.name || log.occasion || "Outfit"}</Display>
          <Txt style={styles.sub}>{fmtWhen(log.created_at)}</Txt>
        </View>

        <View style={styles.flatlay}>
          {items.map((it: any) => (
            <Pressable key={it.id} onPress={() => router.push(`/item/${it.id}`)} testID={`worn-item-${it.id}`}>
              <GarmentImage photo={it.photo} category={it.category} style={styles.stackImg} contentFit="contain" iconSize={40} />
            </Pressable>
          ))}
        </View>

        <View style={styles.pieceList}>
          {items.map((it: any) => (
            <View key={it.id} style={styles.pieceRow}>
              <Txt style={styles.pieceSlot}>{(it.category || "").toUpperCase()}</Txt>
              <Txt style={styles.pieceName} numberOfLines={1}>{it.name}</Txt>
            </View>
          ))}
        </View>

        <View style={styles.actions}>
          <Pressable style={[styles.primaryBtn, again && styles.primaryDone]} onPress={wearAgain} disabled={busy || again} testID="worn-wear-again">
            {again ? <Feather name="check" size={17} color={colors.onSage} /> : null}
            <Txt style={styles.primaryTxt}>{again ? "Recorded again" : "Wear it again"}</Txt>
          </Pressable>
          <Pressable
            style={styles.secondaryBtn}
            testID="worn-mix-up"
            onPress={() => { haptics.tap(); router.push(`/(tabs)/dressme?mix=${log.id}`); }}
          >
            <Feather name="refresh-cw" size={16} color={colors.onSurface} />
            <Txt style={styles.secondaryTxt}>Mix it up</Txt>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  titleBlock: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.lg },
  kicker: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium, marginBottom: spacing.xs },
  title: { fontSize: 26, letterSpacing: -0.4 },
  sub: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: spacing.xs },
  flatlay: { alignItems: "center", gap: spacing.sm },
  stackImg: { width: 220, height: 180, backgroundColor: "transparent" },
  pieceList: { marginTop: spacing.lg, marginHorizontal: spacing.xl, borderTopWidth: 0.5, borderTopColor: colors.divider },
  pieceRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.divider },
  pieceSlot: { fontSize: 11, letterSpacing: 1.2, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium },
  pieceName: { flex: 1, fontSize: 14, color: colors.onSurface, textAlign: "right" },
  actions: { paddingHorizontal: spacing.lg, marginTop: spacing["2xl"], gap: spacing.md },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.sage, height: 52, borderRadius: radius.md },
  primaryDone: { backgroundColor: colors.sagePressed },
  primaryTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayBold },
  secondaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 52, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  secondaryTxt: { color: colors.onSurface, fontSize: 16, fontFamily: fonts.displayBold },
});
