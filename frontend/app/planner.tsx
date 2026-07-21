import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput, Modal } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";

function dateKey(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function buildDays(n: number) {
  return Array.from({ length: n }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i);
    return d;
  });
}

export default function Planner() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const days = buildDays(7);
  const [plans, setPlans] = useState<Record<string, any>>({});
  const [outfits, setOutfits] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [occasion, setOccasion] = useState("");
  const [styling, setStyling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const from = dateKey(days[0]);
      const to = dateKey(days[days.length - 1]);
      const [pl, o] = await Promise.all([
        api<any[]>(`/plans?from_date=${from}&to_date=${to}`),
        api<any[]>("/outfits"),
      ]);
      const map: Record<string, any> = {};
      pl.forEach((p) => {
        if (!map[p.date]) map[p.date] = p;
      });
      setPlans(map);
      setOutfits(o);
    } catch {}
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const openPlanner = (dk: string) => {
    setActiveDate(dk);
    setTitle("");
    setOccasion("");
  };

  const assignSavedLook = async (o: any) => {
    if (!activeDate) return;
    await api("/plans", {
      method: "POST",
      body: { date: activeDate, outfit_id: o.id, title: o.name, occasion },
    });
    setActiveDate(null);
    load();
  };

  const autoStyle = async () => {
    if (!activeDate) return;
    setStyling(true);
    try {
      const r = await api<any>("/stylist/suggest", {
        method: "POST",
        body: { occasion: occasion || "everyday" },
      });
      const ids = (r.resolved_items || []).map((x: any) => x.item.id);
      if (ids.length) {
        await api("/plans", {
          method: "POST",
          body: { date: activeDate, item_ids: ids, title: title || "AI look", occasion },
        });
      }
      setActiveDate(null);
      load();
    } catch {}
    setStyling(false);
  };

  const removePlan = async (id: string) => {
    await api(`/plans/${id}`, { method: "DELETE" });
    load();
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="planner-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Display weight="semibold" style={styles.headerTitle}>The week ahead</Display>
        <View style={{ width: 24 }} />
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.onSurface} /></View>
      ) : (
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          {days.map((d, i) => {
            const dk = dateKey(d);
            const plan = plans[dk];
            const weekday = d.toLocaleDateString("en-US", { weekday: "short" });
            const dayNum = d.getDate();
            return (
              <View key={dk} style={styles.dayRow} testID={`day-${dk}`}>
                <View style={styles.dateCol}>
                  <Txt style={[styles.weekday, i === 0 && styles.today]}>{i === 0 ? "TODAY" : weekday.toUpperCase()}</Txt>
                  <Display weight="medium" style={styles.dayNum}>{dayNum}</Display>
                </View>
                <View style={styles.planCol}>
                  {plan ? (
                    <View style={styles.planCard}>
                      <View style={styles.planTop}>
                        <View style={{ flex: 1 }}>
                          <Txt style={styles.planTitle} numberOfLines={1}>{plan.title || "Planned look"}</Txt>
                          {plan.occasion ? <Txt style={styles.planOcc}>{plan.occasion}</Txt> : null}
                        </View>
                        <Pressable onPress={() => removePlan(plan.id)} testID={`remove-plan-${dk}`} hitSlop={8}>
                          <Feather name="x" size={16} color={colors.onSurfaceTertiary} />
                        </Pressable>
                      </View>
                      <View style={styles.thumbs}>
                        {(plan.items || []).slice(0, 5).map((it: any) => (
                          <GarmentImage key={it.id} photo={it.photo} category={it.category} style={styles.thumb} iconSize={11} />
                        ))}
                      </View>
                    </View>
                  ) : (
                    <Pressable style={styles.planEmpty} testID={`plan-day-${dk}`} onPress={() => openPlanner(dk)}>
                      <Feather name="plus" size={16} color={colors.onSurfaceTertiary} />
                      <Txt style={styles.planEmptyTxt}>Plan this day</Txt>
                    </Pressable>
                  )}
                </View>
              </View>
            );
          })}
        </ScrollView>
      )}

      {/* Plan a day modal */}
      <Modal visible={!!activeDate} transparent animationType="slide" onRequestClose={() => setActiveDate(null)}>
        <Pressable style={styles.backdrop} onPress={() => setActiveDate(null)}>
          <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
            <Display weight="medium" style={styles.sheetTitle}>Plan an outfit</Display>

            <TextInput
              testID="plan-occasion-input"
              style={styles.input}
              value={occasion}
              onChangeText={setOccasion}
              placeholder="Occasion (e.g. client meeting)"
              placeholderTextColor={colors.onSurfaceTertiary}
            />

            <Pressable style={styles.autoBtn} testID="plan-auto-style" onPress={autoStyle} disabled={styling}>
              {styling ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <>
                  <Feather name="feather" size={16} color={colors.onBrandPrimary} />
                  <Txt style={styles.autoTxt}>Auto-style with AI</Txt>
                </>
              )}
            </Pressable>

            <Txt style={styles.orLabel}>OR PICK A SAVED LOOK</Txt>
            <ScrollView style={{ maxHeight: 260 }} showsVerticalScrollIndicator={false}>
              {outfits.length === 0 ? (
                <Txt style={styles.noLooks}>No saved looks yet. Save some from the Stylist first.</Txt>
              ) : (
                outfits.map((o) => (
                  <Pressable key={o.id} style={styles.lookRow} testID={`assign-${o.id}`} onPress={() => assignSavedLook(o)}>
                    <View style={styles.lookThumbs}>
                      {(o.items || []).slice(0, 3).map((it: any) => (
                        <GarmentImage key={it.id} photo={it.photo} category={it.category} style={styles.lookThumb} iconSize={11} />
                      ))}
                    </View>
                    <Txt style={styles.lookName} numberOfLines={1}>{o.name}</Txt>
                    <Feather name="chevron-right" size={18} color={colors.onSurfaceTertiary} />
                  </Pressable>
                ))
              )}
            </ScrollView>

            <Pressable style={styles.cancel} onPress={() => setActiveDate(null)}>
              <Txt style={styles.cancelTxt}>Cancel</Txt>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  headerTitle: { fontSize: 22 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  dayRow: { flexDirection: "row", gap: spacing.lg, marginBottom: spacing.lg },
  dateCol: { width: 52, alignItems: "center", paddingTop: spacing.sm },
  weekday: { fontSize: 11, letterSpacing: 1, color: colors.onSurfaceTertiary },
  today: { color: colors.brand },
  dayNum: { fontSize: 26, color: colors.onSurface },
  planCol: { flex: 1 },
  planCard: { borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md },
  planTop: { flexDirection: "row", alignItems: "flex-start", marginBottom: spacing.md },
  planTitle: { fontSize: 15, color: colors.onSurface },
  planOcc: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  thumbs: { flexDirection: "row", gap: spacing.sm },
  thumb: { width: 42, height: 52, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  ph: { alignItems: "center", justifyContent: "center" },
  planEmpty: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderWidth: 0.5, borderStyle: "dashed", borderColor: colors.border, borderRadius: radius.md, paddingVertical: spacing.lg, paddingHorizontal: spacing.lg },
  planEmptyTxt: { fontSize: 13, color: colors.onSurfaceTertiary },
  backdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.45)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, paddingBottom: spacing["2xl"] },
  sheetTitle: { fontSize: 24, marginBottom: spacing.lg },
  input: { fontFamily: fonts.body, fontSize: 16, color: colors.onSurface, borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: spacing.sm, marginBottom: spacing.lg },
  autoBtn: { backgroundColor: colors.brandPrimary, height: 50, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  autoTxt: { color: colors.onBrandPrimary, fontSize: 15 },
  orLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginTop: spacing.xl, marginBottom: spacing.md },
  noLooks: { fontSize: 13, color: colors.onSurfaceTertiary, paddingVertical: spacing.md },
  lookRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: 0.5, borderColor: colors.divider },
  lookThumbs: { flexDirection: "row", gap: 3 },
  lookThumb: { width: 32, height: 40, borderRadius: 3, backgroundColor: colors.surfaceSecondary },
  lookName: { flex: 1, fontSize: 14, color: colors.onSurface },
  cancel: { alignItems: "center", paddingVertical: spacing.md, marginTop: spacing.md },
  cancelTxt: { fontSize: 15, color: colors.onSurfaceTertiary },
});
