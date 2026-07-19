import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { Image } from "expo-image";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/context/AuthContext";

export default function Profile() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [data, setData] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [missing, setMissing] = useState<any>(null);
  const [missingLoading, setMissingLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api<any>("/insights");
      setData(d);
    } catch {}
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const findMissing = async () => {
    setMissingLoading(true);
    setMissing(null);
    try {
      const r = await api<any>("/insights/missing-piece", { method: "POST" });
      setMissing(r);
    } catch {}
    setMissingLoading(false);
  };

  const unworn = data ? (data.least_worn || []).filter((i: any) => (i.wear_count || 0) === 0) : [];

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: spacing["3xl"] }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.onSurface} />}
      >
        <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
          <View style={styles.profileRow}>
            {user?.picture ? (
              <Image source={{ uri: user.picture }} style={styles.avatar} contentFit="cover" />
            ) : (
              <View style={[styles.avatar, styles.avatarFallback]}>
                <Feather name="user" size={22} color={colors.onSurfaceTertiary} />
              </View>
            )}
            <View style={{ flex: 1 }}>
              <Display weight="medium" style={styles.name}>{user?.name || "Stylist"}</Display>
              <Txt style={styles.email}>{user?.email}</Txt>
            </View>
            <Pressable onPress={logout} testID="logout-button" hitSlop={10}>
              <Feather name="log-out" size={20} color={colors.onSurfaceSecondary} />
            </Pressable>
          </View>
        </View>

        <View style={styles.body}>
          {/* Headline metrics */}
          <View style={styles.metricRow}>
            <Metric value={data?.total_items ?? 0} label="Pieces" />
            <View style={styles.mDiv} />
            <Metric value={data?.avg_cost_per_wear != null ? `$${data.avg_cost_per_wear}` : "—"} label="Avg cost/wear" />
            <View style={styles.mDiv} />
            <Metric value={data?.outfits_logged ?? 0} label="Looks logged" />
          </View>

          {/* Missing Piece — the honest gap analyzer */}
          <View style={styles.missingCard}>
            <Txt style={styles.missingKicker}>THE MISSING PIECE</Txt>
            <Display weight="medium" style={styles.missingTitle}>
              What would actually make your wardrobe work harder?
            </Display>
            {missing ? (
              <View style={{ marginTop: spacing.md }}>
                <Txt style={styles.missingItem}>{missing.recommendation}</Txt>
                {missing.reason ? <Txt style={styles.missingReason}>{missing.reason}</Txt> : null}
                {missing.avoid ? (
                  <View style={styles.avoidRow}>
                    <Feather name="alert-triangle" size={13} color={colors.warning} />
                    <Txt style={styles.avoidTxt}>{missing.avoid}</Txt>
                  </View>
                ) : null}
                <Pressable style={styles.missingRedo} onPress={findMissing} testID="missing-redo">
                  <Txt style={styles.missingRedoTxt}>Re-analyze</Txt>
                </Pressable>
              </View>
            ) : (
              <Pressable style={styles.missingBtn} testID="find-missing-button" onPress={findMissing} disabled={missingLoading}>
                {missingLoading ? (
                  <ActivityIndicator color={colors.onBrandPrimary} />
                ) : (
                  <Txt style={styles.missingBtnTxt}>Find my missing piece</Txt>
                )}
              </Pressable>
            )}
          </View>

          {/* Confidence scores */}
          {data?.avg_confidence != null && (
            <View style={styles.section}>
              <Txt style={styles.sectionTitle}>HOW YOUR OUTFITS FEEL</Txt>
              <Bar label="Flattering" value={data.avg_flattering} />
              <Bar label="Comfort" value={data.avg_comfort} />
              <Bar label="Confidence" value={data.avg_confidence} />
            </View>
          )}

          {/* Category breakdown */}
          {data?.categories && Object.keys(data.categories).length > 0 && (
            <View style={styles.section}>
              <Txt style={styles.sectionTitle}>WHAT YOU OWN</Txt>
              {Object.entries(data.categories)
                .sort((a: any, b: any) => b[1] - a[1])
                .map(([cat, count]: any) => {
                  const max = Math.max(...Object.values(data.categories).map((v: any) => v));
                  return (
                    <View key={cat} style={styles.catRow}>
                      <Txt style={styles.catName}>{cat}</Txt>
                      <View style={styles.catBarTrack}>
                        <View style={[styles.catBarFill, { width: `${(count / max) * 100}%` }]} />
                      </View>
                      <Txt style={styles.catCount}>{count}</Txt>
                    </View>
                  );
                })}
            </View>
          )}

          {/* Most worn */}
          {data?.most_worn?.some((i: any) => (i.wear_count || 0) > 0) && (
            <RankList title="MOST WORN" items={data.most_worn.filter((i: any) => (i.wear_count || 0) > 0)} router={router} />
          )}

          {/* Wardrobe health — unworn */}
          {unworn.length > 0 && (
            <View style={styles.section}>
              <Txt style={styles.sectionTitle}>WARDROBE HEALTH</Txt>
              <View style={styles.healthCard}>
                <Feather name="rotate-ccw" size={18} color={colors.brand} />
                <Txt style={styles.healthTxt}>
                  You haven't worn {unworn.length} {unworn.length === 1 ? "piece" : "pieces"} yet. Style them, sell, or donate to keep your wardrobe lean.
                </Txt>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.md, paddingRight: spacing.xl, marginTop: spacing.md }}>
                {unworn.map((it: any) => (
                  <Pressable key={it.id} style={styles.simCard} onPress={() => router.push(`/item/${it.id}`)}>
                    {it.photo ? (
                      <Image source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={styles.simImg} contentFit="cover" />
                    ) : (
                      <View style={[styles.simImg, styles.simPlaceholder]}><Feather name="image" size={16} color={colors.onSurfaceTertiary} /></View>
                    )}
                    <Txt style={styles.simName} numberOfLines={1}>{it.name}</Txt>
                  </Pressable>
                ))}
              </ScrollView>
            </View>
          )}

          {!data || data.total_items === 0 ? (
            <View style={styles.empty}>
              <Txt style={styles.emptyTxt}>Add clothes and log what you wear to unlock insights.</Txt>
            </View>
          ) : null}
        </View>
      </ScrollView>
    </View>
  );
}

function Metric({ value, label }: { value: any; label: string }) {
  return (
    <View style={styles.metric}>
      <Display weight="medium" style={styles.metricValue}>{value}</Display>
      <Txt style={styles.metricLabel}>{label}</Txt>
    </View>
  );
}

function Bar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(1, (value || 0) / 5)) * 100;
  return (
    <View style={styles.barRow}>
      <Txt style={styles.barLabel}>{label}</Txt>
      <View style={styles.barTrack}>
        <View style={[styles.barFill, { width: `${pct}%` }]} />
      </View>
      <Txt style={styles.barVal}>{value?.toFixed(1)}</Txt>
    </View>
  );
}

function RankList({ title, items, router }: { title: string; items: any[]; router: any }) {
  return (
    <View style={styles.section}>
      <Txt style={styles.sectionTitle}>{title}</Txt>
      {items.map((it, i) => (
        <Pressable key={it.id} style={styles.rankRow} onPress={() => router.push(`/item/${it.id}`)}>
          <Txt style={styles.rankNum}>{i + 1}</Txt>
          {it.photo ? (
            <Image source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={styles.rankImg} contentFit="cover" />
          ) : (
            <View style={[styles.rankImg, styles.simPlaceholder]}><Feather name="image" size={14} color={colors.onSurfaceTertiary} /></View>
          )}
          <View style={{ flex: 1 }}>
            <Txt style={styles.rankName} numberOfLines={1}>{it.name}</Txt>
            <Txt style={styles.rankMeta}>{it.wear_count} wears{it.price ? ` · $${(it.price / it.wear_count).toFixed(2)}/wear` : ""}</Txt>
          </View>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.lg, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  profileRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  avatar: { width: 52, height: 52, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary },
  avatarFallback: { alignItems: "center", justifyContent: "center" },
  name: { fontSize: 24 },
  email: { fontSize: 13, color: colors.onSurfaceTertiary },
  body: { paddingHorizontal: spacing.xl, paddingTop: spacing.xl },
  metricRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.lg, borderBottomWidth: 0.5, borderColor: colors.divider },
  metric: { flex: 1, alignItems: "center", gap: 4 },
  mDiv: { width: 0.5, height: 40, backgroundColor: colors.divider },
  metricValue: { fontSize: 28, color: colors.onSurface },
  metricLabel: { fontSize: 11, color: colors.onSurfaceTertiary, textAlign: "center" },
  missingCard: { marginTop: spacing.xl, backgroundColor: colors.surfaceInverse, borderRadius: radius.md, padding: spacing.xl },
  missingKicker: { fontSize: 11, letterSpacing: 2, color: colors.brandTertiary, marginBottom: spacing.sm },
  missingTitle: { fontSize: 24, lineHeight: 28, color: colors.onSurfaceInverse },
  missingItem: { fontSize: 16, color: colors.onSurfaceInverse, lineHeight: 22 },
  missingReason: { fontSize: 14, color: "rgba(250,250,250,0.7)", lineHeight: 21, marginTop: spacing.sm },
  avoidRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, alignItems: "flex-start" },
  avoidTxt: { flex: 1, fontSize: 13, color: colors.warning, lineHeight: 19 },
  missingBtn: { backgroundColor: colors.surface, height: 48, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", marginTop: spacing.lg },
  missingBtnTxt: { color: colors.onSurface, fontSize: 15 },
  missingRedo: { marginTop: spacing.lg, alignSelf: "flex-start" },
  missingRedoTxt: { color: colors.brandTertiary, fontSize: 13, textDecorationLine: "underline" },
  section: { marginTop: spacing["2xl"] },
  sectionTitle: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginBottom: spacing.lg },
  barRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.md },
  barLabel: { fontSize: 13, color: colors.onSurface, width: 90 },
  barTrack: { flex: 1, height: 4, backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, overflow: "hidden" },
  barFill: { height: 4, backgroundColor: colors.brand },
  barVal: { fontSize: 12, color: colors.onSurfaceTertiary, width: 30, textAlign: "right" },
  catRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.md },
  catName: { fontSize: 13, color: colors.onSurface, width: 90 },
  catBarTrack: { flex: 1, height: 4, backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, overflow: "hidden" },
  catBarFill: { height: 4, backgroundColor: colors.onSurface },
  catCount: { fontSize: 12, color: colors.onSurfaceTertiary, width: 30, textAlign: "right" },
  rankRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginBottom: spacing.lg },
  rankNum: { fontSize: 14, color: colors.brand, width: 16 },
  rankImg: { width: 44, height: 56, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  rankName: { fontSize: 14, color: colors.onSurface },
  rankMeta: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  healthCard: { flexDirection: "row", gap: spacing.md, backgroundColor: colors.brandTertiary, padding: spacing.lg, borderRadius: radius.sm, alignItems: "center" },
  healthTxt: { flex: 1, fontSize: 13, color: colors.onBrandTertiary, lineHeight: 19 },
  simCard: { width: 90 },
  simImg: { width: 90, height: 116, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  simPlaceholder: { alignItems: "center", justifyContent: "center" },
  simName: { fontSize: 12, color: colors.onSurface, marginTop: 6 },
  empty: { marginTop: spacing["2xl"], alignItems: "center" },
  emptyTxt: { fontSize: 14, color: colors.onSurfaceTertiary, textAlign: "center" },
});
