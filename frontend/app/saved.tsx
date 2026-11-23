import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl, useWindowDimensions } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";

function when(iso?: string) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const day = 86400000;
  if (diff < day) return "Today";
  if (diff < 2 * day) return "Yesterday";
  const days = Math.floor(diff / day);
  if (days < 7) return `${days} days ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Saved — outfits the user explicitly kept for later (Dress Me saves and
 *  outfits they built by hand both live here). */
export default function Saved() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const CARD_W = (width - spacing.lg * 2 - spacing.md) / 2;
  const [outfits, setOutfits] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api<any[]>("/outfits");
      setOutfits(Array.isArray(data) ? data : []);
    } catch {
      setOutfits([]);
    } finally {
      setLoaded(true);
    }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="saved-back">
          <Feather name="chevron-left" size={26} color={colors.onSurface} />
        </Pressable>
        <BrandMark style={{ marginBottom: 0 }} />
        <View style={{ width: 26 }} />
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: spacing["3xl"] }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.onSurface} />}
      >
        <View style={styles.titleBlock}>
          <Txt style={styles.kicker}>MY COLLECTIONS</Txt>
          <Display weight="semibold" style={styles.title}>Saved</Display>
          <Txt style={styles.sub}>Outfits you&apos;ve kept for later.</Txt>
        </View>

        {loaded && outfits.length === 0 ? (
          <View style={styles.empty} testID="saved-empty">
            <View style={styles.emptyIcon}><Feather name="bookmark" size={24} color={colors.onSurfaceTertiary} /></View>
            <Display weight="semibold" style={styles.emptyTitle}>Nothing saved yet</Display>
            <Txt style={styles.emptySub}>When Dress Me styles you, tap &lsquo;Save for later&rsquo; and it&apos;ll appear here.</Txt>
            <Pressable style={styles.cta} testID="saved-dressme" onPress={() => router.push("/(tabs)/dressme")}>
              <Txt style={styles.ctaTxt}>Dress Me</Txt>
            </Pressable>
          </View>
        ) : (
          <View style={styles.grid}>
            {outfits.map((o) => (
              <Pressable key={o.id} style={[styles.card, { width: CARD_W }]} testID={`saved-outfit-${o.id}`} onPress={() => router.push(`/outfit/${o.id}`)}>
                <View style={styles.collage}>
                  {o.preview_image ? (
                    <GarmentImage photo={o.preview_image} category="" mime="png" style={styles.collageFull} contentFit="contain" iconSize={28} />
                  ) : (
                    <View style={styles.collageGrid}>
                      {(o.items || []).slice(0, 4).map((it: any, i: number) => (
                        <GarmentImage key={`${o.id}-${it.id || i}`} photo={it.photo} category={it.category} style={styles.collageCell} iconSize={16} />
                      ))}
                      {(o.items || []).length === 0 && (
                        <View style={styles.collageCell}><Feather name="layers" size={18} color={colors.onSurfaceTertiary} /></View>
                      )}
                    </View>
                  )}
                </View>
                <Txt style={styles.cardName} numberOfLines={1}>{o.name || "Outfit"}</Txt>
                <Txt style={styles.cardTime}>{when(o.created_at)}</Txt>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  titleBlock: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.lg },
  kicker: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium, marginBottom: spacing.xs },
  title: { fontSize: 30, letterSpacing: -0.5 },
  sub: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: spacing.xs },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, paddingHorizontal: spacing.lg },
  card: { marginBottom: spacing.sm },
  collage: { width: "100%", aspectRatio: 0.82, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, overflow: "hidden", borderWidth: 0.5, borderColor: colors.border },
  collageFull: { width: "100%", height: "100%" },
  collageGrid: { flex: 1, flexDirection: "row", flexWrap: "wrap" },
  collageCell: { width: "50%", height: "50%", alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  cardName: { fontSize: 14, color: colors.onSurface, fontFamily: fonts.displayMedium, marginTop: spacing.sm },
  cardTime: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  empty: { alignItems: "center", paddingHorizontal: spacing.xl, paddingTop: spacing["2xl"] },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.cream, alignItems: "center", justifyContent: "center", marginBottom: spacing.lg },
  emptyTitle: { fontSize: 20, marginBottom: spacing.sm },
  emptySub: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 21, marginBottom: spacing.xl },
  cta: { backgroundColor: colors.sage, paddingHorizontal: spacing["2xl"], paddingVertical: spacing.md, borderRadius: radius.md },
  ctaTxt: { color: colors.onSage, fontSize: 15, fontFamily: fonts.displayBold },
});
