import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";

function dayLabel(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  const yesterday = new Date(today.getTime() - 86400000);
  if (same(d, today)) return "Today";
  if (same(d, yesterday)) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

function timeLabel(iso?: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

/** Worn — every wear the user explicitly confirmed. Several looks can be
 *  recorded on the same day, so entries are grouped by date. */
export default function Worn() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [logs, setLogs] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api<any[]>("/wear");
      setLogs(Array.isArray(data) ? data : []);
    } catch {
      setLogs([]);
    } finally {
      setLoaded(true);
    }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const groups: { label: string; rows: any[] }[] = [];
  logs.forEach((lg) => {
    const label = dayLabel(lg.created_at);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.rows.push(lg);
    else groups.push({ label, rows: [lg] });
  });

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="worn-back">
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
          <Display weight="semibold" style={styles.title}>Worn</Display>
          <Txt style={styles.sub}>Outfits you confirmed you wore.</Txt>
        </View>

        {loaded && logs.length === 0 ? (
          <View style={styles.empty} testID="worn-empty">
            <View style={styles.emptyIcon}><Feather name="check-circle" size={24} color={colors.onSurfaceTertiary} /></View>
            <Display weight="semibold" style={styles.emptyTitle}>No wears recorded yet</Display>
            <Txt style={styles.emptySub}>Tap &lsquo;Wear this today&rsquo; on a look and it&apos;ll be recorded here.</Txt>
            <Pressable style={styles.cta} testID="worn-dressme" onPress={() => router.push("/(tabs)/dressme")}>
              <Txt style={styles.ctaTxt}>Dress Me</Txt>
            </Pressable>
          </View>
        ) : (
          groups.map((g) => (
            <View key={g.label} style={styles.group}>
              <Txt style={styles.groupLabel}>{g.label.toUpperCase()}</Txt>
              {g.rows.map((lg) => (
                <Pressable key={lg.id} style={({ pressed }) => [styles.row, pressed && styles.pressed]} testID={`worn-log-${lg.id}`} onPress={() => router.push(`/worn/${lg.id}`)}>
                  <View style={styles.thumbs}>
                    {(lg.items || []).slice(0, 4).map((it: any, i: number) => (
                      <GarmentImage key={`${lg.id}-${it.id || i}`} photo={it.photo} category={it.category} style={styles.thumb} iconSize={13} />
                    ))}
                    {(lg.items || []).length === 0 && (
                      <View style={styles.thumb}><Feather name="layers" size={16} color={colors.onSurfaceTertiary} /></View>
                    )}
                  </View>
                  <View style={styles.rowBody}>
                    <Txt style={styles.rowName} numberOfLines={1}>{lg.name || lg.occasion || "Outfit"}</Txt>
                    <Txt style={styles.rowMeta}>
                      {[timeLabel(lg.created_at), `${(lg.items || []).length} ${(lg.items || []).length === 1 ? "piece" : "pieces"}`]
                        .filter(Boolean)
                        .join(" · ")}
                    </Txt>
                  </View>
                  <Feather name="chevron-right" size={18} color={colors.onSurfaceTertiary} />
                </Pressable>
              ))}
            </View>
          ))
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
  group: { paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  groupLabel: { fontSize: 10.5, letterSpacing: 1.6, color: colors.onSurfaceTertiary, marginBottom: spacing.sm, fontFamily: fonts.displayMedium },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    padding: spacing.md, marginBottom: spacing.sm, borderRadius: radius.lg,
    backgroundColor: colors.cream, borderWidth: 0.5, borderColor: colors.border,
  },
  pressed: { opacity: 0.85 },
  thumbs: { width: 60, height: 60, borderRadius: radius.md, overflow: "hidden", flexDirection: "row", flexWrap: "wrap", backgroundColor: colors.surfaceSecondary },
  thumb: { width: "50%", height: "50%", alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  rowBody: { flex: 1 },
  rowName: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium },
  rowMeta: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 2 },
  empty: { alignItems: "center", paddingHorizontal: spacing.xl, paddingTop: spacing["2xl"] },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.eucalyptus, alignItems: "center", justifyContent: "center", marginBottom: spacing.lg },
  emptyTitle: { fontSize: 20, marginBottom: spacing.sm },
  emptySub: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 21, marginBottom: spacing.xl },
  cta: { backgroundColor: colors.sage, paddingHorizontal: spacing["2xl"], paddingVertical: spacing.md, borderRadius: radius.md },
  ctaTxt: { color: colors.onSage, fontSize: 15, fontFamily: fonts.displayBold },
});
