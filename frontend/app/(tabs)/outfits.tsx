import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl, useWindowDimensions } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";

function timeAgo(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  const diff = Date.now() - d;
  const day = 86400000;
  if (diff < day) return "Today";
  if (diff < 2 * day) return "Yesterday";
  const days = Math.floor(diff / day);
  if (days < 7) return `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks} week${weeks > 1 ? "s" : ""} ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const SEGMENTS = ["All", "Recent", "Saved"] as const;

export default function OutfitsHub() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const CARD_W = (width - spacing.lg * 2 - spacing.md) / 2;
  const [outfits, setOutfits] = useState<any[]>([]);
  const [seg, setSeg] = useState<(typeof SEGMENTS)[number]>("All");
  const [refreshing, setRefreshing] = useState(false);
  const [loaded, setLoaded] = useState(false);

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

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const filtered = outfits.filter((o) => {
    if (seg === "Recent") return Date.now() - new Date(o.created_at).getTime() < 14 * 86400000;
    if (seg === "Saved") return o.source && o.source !== "manual";
    return true;
  });

  return (
    <View style={styles.container}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] + 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.onSurface} />}
      >
        <View style={styles.header}>
          <Display weight="semibold" style={styles.title}>My Outfits</Display>
        </View>

        <View style={styles.segments}>
          {SEGMENTS.map((s) => (
            <Pressable key={s} style={styles.segBtn} testID={`outfits-seg-${s}`} onPress={() => setSeg(s)}>
              <Txt style={[styles.segTxt, seg === s && styles.segTxtActive]}>{s}</Txt>
              {seg === s && <View style={styles.segUnderline} />}
            </Pressable>
          ))}
        </View>

        {loaded && filtered.length === 0 ? (
          <View style={styles.empty}>
            <View style={styles.emptyIcon}><Feather name="layers" size={26} color={colors.onSurfaceTertiary} /></View>
            <Display weight="semibold" style={styles.emptyTitle}>No outfits yet</Display>
            <Txt style={styles.emptySub}>
              Tap &lsquo;Dress Me&rsquo; to create your first look in seconds, or build one by hand.
            </Txt>
            <Pressable style={styles.emptyCta} testID="outfits-empty-dressme" onPress={() => router.push("/(tabs)/dressme")}>
              <Txt style={styles.emptyCtaTxt}>Dress Me</Txt>
            </Pressable>
          </View>
        ) : (
          <View style={styles.grid}>
            {filtered.map((o) => (
              <Pressable key={o.id} style={[styles.card, { width: CARD_W }]} testID={`outfit-card-${o.id}`} onPress={() => router.push(`/outfit/${o.id}`)}>
                <View style={styles.collage}>
                  {o.preview_image ? (
                    <GarmentImage photo={o.preview_image} category="" mime="png" style={styles.collageFull} contentFit="contain" iconSize={28} />
                  ) : (
                    <View style={styles.collageGrid}>
                      {(o.items || []).slice(0, 4).map((it: any, i: number) => (
                        <GarmentImage key={i} photo={it.photo} category={it.category} style={styles.collageCell} iconSize={16} />
                      ))}
                      {(o.items || []).length === 0 && (
                        <View style={styles.collageCell}><Feather name="layers" size={18} color={colors.onSurfaceTertiary} /></View>
                      )}
                    </View>
                  )}
                </View>
                <Txt style={styles.cardName} numberOfLines={1}>{o.name || "Outfit"}</Txt>
                <Txt style={styles.cardTime}>{timeAgo(o.created_at)}</Txt>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>

      <Pressable
        style={[styles.calendarBtn, { bottom: insets.bottom + 8 }]}
        testID="outfits-view-calendar"
        onPress={() => router.push("/planner")}
      >
        <Feather name="calendar" size={16} color={colors.onSurface} />
        <Txt style={styles.calendarTxt}>View Calendar</Txt>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  title: { fontSize: 30, letterSpacing: -0.5 },
  segments: { flexDirection: "row", gap: spacing.xl, paddingHorizontal: spacing.lg, marginBottom: spacing.lg, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  segBtn: { paddingBottom: spacing.sm },
  segTxt: { fontSize: 15, color: colors.onSurfaceTertiary },
  segTxtActive: { color: colors.onSurface, fontFamily: fonts.displayMedium },
  segUnderline: { position: "absolute", bottom: -0.5, left: 0, right: 0, height: 2, backgroundColor: colors.sage, borderRadius: 2 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, paddingHorizontal: spacing.lg },
  card: { marginBottom: spacing.sm },
  collage: { width: "100%", aspectRatio: 0.82, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, overflow: "hidden", borderWidth: 0.5, borderColor: colors.border },
  collageFull: { width: "100%", height: "100%" },
  collageGrid: { flex: 1, flexDirection: "row", flexWrap: "wrap" },
  collageCell: { width: "50%", height: "50%", alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  cardName: { fontSize: 14, color: colors.onSurface, fontFamily: fonts.displayMedium, marginTop: spacing.sm },
  cardTime: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  empty: { alignItems: "center", paddingHorizontal: spacing.xl, paddingTop: spacing["3xl"] },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", marginBottom: spacing.lg },
  emptyTitle: { fontSize: 20, marginBottom: spacing.sm },
  emptySub: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 21, marginBottom: spacing.xl },
  emptyCta: { backgroundColor: colors.sage, paddingHorizontal: spacing["2xl"], paddingVertical: spacing.md, borderRadius: radius.md },
  emptyCtaTxt: { color: colors.onSage, fontSize: 15, fontFamily: fonts.displayBold },
  calendarBtn: { position: "absolute", left: spacing.lg, right: spacing.lg, height: 48, borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, shadowColor: "#000", shadowOpacity: 0.06, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  calendarTxt: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium },
});
