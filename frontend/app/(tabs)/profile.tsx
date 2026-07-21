import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl, Modal, TextInput } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/context/AuthContext";
import { useProfiles } from "@/src/context/ProfileContext";
import GarmentImage from "@/src/components/GarmentImage";

export default function Profile() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { profiles, active, switchTo, createProfile, deleteProfile } = useProfiles();
  const premium = !!user?.premium;
  const [data, setData] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [missing, setMissing] = useState<any>(null);
  const [missingLoading, setMissingLoading] = useState(false);
  const [showSwitcher, setShowSwitcher] = useState(false);
  const [newName, setNewName] = useState("");
  const [calConnected, setCalConnected] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api<any>("/insights");
      setData(d);
    } catch {}
    try {
      const s = await api<any>("/calendar/status");
      setCalConnected(!!s.connected);
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
    if (!premium) {
      router.push("/premium");
      return;
    }
    setMissingLoading(true);
    setMissing(null);
    try {
      const r = await api<any>("/insights/missing-piece", { method: "POST" });
      setMissing(r);
    } catch (e: any) {
      if (e.status === 402) router.push("/premium");
    }
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
            <Pressable style={styles.switcherTrigger} testID="profile-switcher-trigger" onPress={() => setShowSwitcher(true)}>
              <View style={styles.avatar}>
                <Txt style={styles.avatarEmoji}>{active?.emoji || "👤"}</Txt>
              </View>
              <View style={{ flex: 1 }}>
                <Txt style={styles.accountName}>{user?.name || "Account"}</Txt>
                <View style={styles.activeRow}>
                  <Display weight="medium" style={styles.name}>{active?.name || "Wardrobe"}</Display>
                  <Feather name="chevron-down" size={18} color={colors.onSurfaceSecondary} />
                </View>
              </View>
            </Pressable>
            <Pressable onPress={logout} testID="logout-button" hitSlop={10}>
              <Feather name="log-out" size={20} color={colors.onSurfaceSecondary} />
            </Pressable>
          </View>
        </View>

        <View style={styles.body}>
          {/* Style profile */}
          <Pressable style={styles.styleProfileCta} testID="open-style-profile" onPress={() => router.push("/profile-edit")}>
            <View style={styles.spIcon}>
              <Feather name="user" size={18} color={colors.onSurface} />
            </View>
            <View style={{ flex: 1 }}>
              <Txt style={styles.spTitle}>Your style profile</Txt>
              <Txt style={styles.spSub}>
                {active?.profile && Object.keys(active.profile).length > 0
                  ? "Measurements & skin tone added — tap to edit"
                  : "Add measurements & skin tone for better fits"}
              </Txt>
            </View>
            <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />
          </Pressable>

          {/* Hair & makeup */}
          <Pressable style={styles.beautyCta} testID="open-beauty" onPress={() => (premium ? router.push("/beauty") : router.push("/premium"))}>
            <View style={styles.beautyIcon}>
              <Feather name="feather" size={18} color={colors.onBrandTertiary} />
            </View>
            <View style={{ flex: 1 }}>
              <Txt style={styles.spTitle}>Hair & makeup for your colouring</Txt>
              <Txt style={styles.spSub}>AI colour analysis from your skin tone & undertone</Txt>
            </View>
            {!premium ? <Feather name="lock" size={16} color={colors.onSurfaceTertiary} /> : <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />}
          </Pressable>

          {/* Google Calendar */}
          <Pressable
            style={styles.premiumActiveCta}
            testID="profile-calendar-cta"
            onPress={async () => {
              if (calConnected) {
                await api("/calendar/disconnect", { method: "DELETE" }).catch(() => {});
                setCalConnected(false);
              } else {
                try {
                  const { url } = await api<any>("/calendar/authorize");
                  await WebBrowser.openBrowserAsync(url);
                  const s = await api<any>("/calendar/status");
                  setCalConnected(!!s.connected);
                } catch {}
              }
            }}
          >
            <Feather name="calendar" size={18} color={colors.brand} />
            <View style={{ flex: 1 }}>
              <Txt style={styles.spTitle}>Google Calendar</Txt>
              <Txt style={styles.spSub}>{calConnected ? "Connected — Dress Me uses your schedule. Tap to disconnect." : "Connect so Dress Me styles for your day"}</Txt>
            </View>
            <Feather name={calConnected ? "check" : "chevron-right"} size={20} color={colors.onSurfaceTertiary} />
          </Pressable>

          {/* Premium status */}
          <Pressable style={premium ? styles.premiumActiveCta : styles.premiumUpsell} testID="profile-premium-cta" onPress={() => router.push("/premium")}>
            <Feather name="award" size={18} color={premium ? colors.brand : colors.brandTertiary} />
            <View style={{ flex: 1 }}>
              <Txt style={premium ? styles.spTitle : styles.premiumUpsellTitle}>
                {premium ? "Premium active" : "Go Premium"}
              </Txt>
              <Txt style={premium ? styles.spSub : styles.premiumUpsellSub}>
                {premium
                  ? (user?.premium_until ? `Until ${new Date(user.premium_until).toLocaleDateString()}` : "Full AI stylist unlocked")
                  : "Unlock the full AI stylist for your household"}
              </Txt>
            </View>
            <Feather name="chevron-right" size={20} color={premium ? colors.onSurfaceTertiary : colors.brandTertiary} />
          </Pressable>

          <View style={styles.metricRow}>
            <Metric value={data?.total_items ?? 0} label="Pieces" />
            <View style={styles.mDiv} />
            <Metric value={data?.avg_cost_per_wear != null ? `$${data.avg_cost_per_wear}` : "—"} label="Avg cost/wear" />
            <View style={styles.mDiv} />
            <Metric value={data?.outfits_logged ?? 0} label="Looks logged" />
          </View>

          {/* Monthly wardrobe health report */}
          <Pressable style={styles.reportCta} testID="open-health-report" onPress={() => (premium ? router.push("/health-report") : router.push("/premium"))}>
            <View style={styles.reportIcon}>
              <Feather name="activity" size={18} color={colors.onSurfaceInverse} />
            </View>
            <View style={{ flex: 1 }}>
              <Txt style={styles.reportTitle}>Monthly wardrobe health report</Txt>
              <Txt style={styles.reportSub}>Wasted money + your #1 unlocking buy</Txt>
            </View>
            {!premium ? <Feather name="lock" size={16} color={colors.onSurfaceTertiary} /> : <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />}
          </Pressable>

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
                  You have not worn {unworn.length} {unworn.length === 1 ? "piece" : "pieces"} yet. Style them, sell, or donate to keep your wardrobe lean.
                </Txt>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.md, paddingRight: spacing.xl, marginTop: spacing.md }}>
                {unworn.map((it: any) => (
                  <Pressable key={it.id} style={styles.simCard} onPress={() => router.push(`/item/${it.id}`)}>
                    <GarmentImage photo={it.photo} category={it.category} style={styles.simImg} iconSize={18} />
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

      <Modal visible={showSwitcher} transparent animationType="slide" onRequestClose={() => setShowSwitcher(false)}>
        <Pressable style={styles.backdrop} onPress={() => setShowSwitcher(false)}>
          <Pressable style={styles.switchSheet} onPress={(e) => e.stopPropagation()}>
            <Display weight="medium" style={styles.switchTitle}>Wardrobes</Display>
            <Txt style={styles.switchSub}>
              {premium ? "One account, a wardrobe for everyone in the household." : "Add family wardrobes with Premium."}
            </Txt>
            {profiles.map((p) => (
              <View key={p.id} style={styles.profRow}>
                <Pressable
                  style={styles.profMain}
                  testID={`switch-profile-${p.id}`}
                  onPress={async () => { await switchTo(p.id); setShowSwitcher(false); load(); }}
                >
                  <View style={[styles.profAvatar, active?.id === p.id && styles.profAvatarActive]}>
                    <Txt style={styles.avatarEmoji}>{p.emoji || "👤"}</Txt>
                  </View>
                  <Txt style={styles.profName}>{p.name}</Txt>
                  {active?.id === p.id && <Feather name="check" size={18} color={colors.brand} />}
                </Pressable>
                {profiles.length > 1 && (
                  <Pressable onPress={() => deleteProfile(p.id)} testID={`delete-profile-${p.id}`} hitSlop={8}>
                    <Feather name="trash-2" size={16} color={colors.onSurfaceTertiary} />
                  </Pressable>
                )}
              </View>
            ))}
            <View style={styles.addRow}>
              <TextInput
                style={styles.addInput}
                value={newName}
                onChangeText={setNewName}
                placeholder="Add a wardrobe (e.g. David, Emily)"
                placeholderTextColor={colors.onSurfaceTertiary}
                testID="new-profile-input"
              />
              <Pressable
                style={styles.addBtn}
                testID="add-profile-button"
                onPress={async () => {
                  if (!premium) {
                    setShowSwitcher(false);
                    router.push("/premium");
                    return;
                  }
                  if (!newName.trim()) return;
                  try {
                    await createProfile(newName.trim(), "👤", "individual");
                  } catch (e: any) {
                    if (e.status === 402) {
                      setShowSwitcher(false);
                      router.push("/premium");
                      return;
                    }
                  }
                  setNewName("");
                  setShowSwitcher(false);
                  load();
                }}
              >
                <Feather name={premium ? "plus" : "lock"} size={18} color={colors.onBrandPrimary} />
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
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
          <GarmentImage photo={it.photo} category={it.category} style={styles.rankImg} iconSize={16} />
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
  switcherTrigger: { flexDirection: "row", alignItems: "center", gap: spacing.md, flex: 1 },
  avatar: { width: 52, height: 52, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  avatarEmoji: { fontSize: 24 },
  accountName: { fontSize: 12, color: colors.onSurfaceTertiary },
  activeRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  name: { fontSize: 24 },
  backdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.45)", justifyContent: "flex-end" },
  switchSheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, paddingBottom: spacing["2xl"] },
  switchTitle: { fontSize: 24 },
  switchSub: { fontSize: 13, color: colors.onSurfaceTertiary, marginTop: 2, marginBottom: spacing.lg },
  profRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm },
  profMain: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.md },
  profAvatar: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  profAvatarActive: { borderWidth: 1.5, borderColor: colors.brand },
  profName: { flex: 1, fontSize: 16, color: colors.onSurface },
  addRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.lg, borderTopWidth: 0.5, borderTopColor: colors.divider, paddingTop: spacing.lg },
  addInput: { flex: 1, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface, borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: spacing.sm },
  addBtn: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  body: { paddingHorizontal: spacing.xl, paddingTop: spacing.xl },
  styleProfileCta: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.lg },
  spIcon: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  spTitle: { fontSize: 15, color: colors.onSurface },
  spSub: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  beautyCta: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.lg },
  beautyIcon: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  premiumUpsell: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.lg, backgroundColor: colors.surfaceInverse },
  premiumUpsellTitle: { fontSize: 15, color: colors.onSurfaceInverse },
  premiumUpsellSub: { fontSize: 12, color: "rgba(250,250,250,0.6)", marginTop: 1 },
  premiumActiveCta: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.lg },
  metricRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.lg, borderBottomWidth: 0.5, borderColor: colors.divider },
  metric: { flex: 1, alignItems: "center", gap: 4 },
  mDiv: { width: 0.5, height: 40, backgroundColor: colors.divider },
  metricValue: { fontSize: 28, color: colors.onSurface },
  metricLabel: { fontSize: 11, color: colors.onSurfaceTertiary, textAlign: "center" },
  missingCard: { marginTop: spacing.xl, backgroundColor: colors.surfaceInverse, borderRadius: radius.md, padding: spacing.xl },
  reportCta: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginTop: spacing.xl,
    borderWidth: 0.5,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    padding: spacing.lg,
  },
  reportIcon: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  reportTitle: { fontSize: 15, color: colors.onSurface },
  reportSub: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
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
