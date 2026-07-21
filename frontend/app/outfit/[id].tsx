import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";
import ConfirmModal from "@/src/components/ConfirmModal";
import * as haptics from "@/src/utils/haptics";

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function OutfitDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [outfit, setOutfit] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [setToday, setSetToday] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      const all = await api<any[]>("/outfits");
      setOutfit(all.find((o) => o.id === id) || null);
    } catch {
      setOutfit(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const setAsToday = async () => {
    if (busy) return;
    setBusy(true);
    haptics.success();
    try {
      await api("/plans", { method: "POST", body: { date: today(), title: outfit.name, outfit_id: outfit.id, item_ids: outfit.item_ids || [], occasion: outfit.occasion || "" } });
      setSetToday(true);
    } catch {}
    setBusy(false);
  };

  const duplicate = async () => {
    if (busy) return;
    setBusy(true);
    haptics.tap();
    try {
      const dup = await api<any>("/outfits", { method: "POST", body: { name: `${outfit.name} copy`, item_ids: outfit.item_ids || [], occasion: outfit.occasion || "", notes: outfit.notes || "", source: "manual" } });
      router.replace(`/outfit/${dup.id}`);
    } catch {}
    setBusy(false);
  };

  const doDelete = async () => {
    setDeleting(true);
    try { await api(`/outfits/${id}`, { method: "DELETE" }); } catch {}
    setDeleting(false);
    setConfirmDel(false);
    router.back();
  };

  if (loading) {
    return <View style={styles.center}><ActivityIndicator color={colors.sage} /></View>;
  }
  if (!outfit) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <Txt style={{ color: colors.onSurfaceSecondary }}>Outfit not found.</Txt>
        <Pressable onPress={() => router.back()} style={{ marginTop: spacing.lg }}><Txt style={{ color: colors.sage }}>Go back</Txt></Pressable>
      </View>
    );
  }

  const items = outfit.items || [];

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="outfit-back"><Feather name="chevron-left" size={26} color={colors.onSurface} /></Pressable>
        <Display weight="medium" style={styles.topTitle} numberOfLines={1}>{outfit.name || "Outfit"}</Display>
        <Pressable onPress={() => setConfirmDel(true)} hitSlop={10} testID="outfit-menu"><Feather name="more-horizontal" size={24} color={colors.onSurface} /></Pressable>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: spacing["3xl"] }}>
        <View style={styles.flatlay}>
          {items.length === 0 ? (
            <GarmentImage photo={null} category="" style={styles.stackImg} iconSize={40} />
          ) : (
            items.map((it: any) => (
              <Pressable key={it.id} onPress={() => router.push(`/item/${it.id}`)} testID={`outfit-item-${it.id}`}>
                <GarmentImage photo={it.photo} category={it.category} style={styles.stackImg} contentFit="contain" iconSize={40} />
              </Pressable>
            ))
          )}
        </View>

        {outfit.notes ? (
          <View style={styles.explainWrap}>
            <Txt style={styles.explain}>{outfit.notes}</Txt>
          </View>
        ) : null}

        <View style={styles.chips}>
          {outfit.occasion ? (
            <View style={styles.chip}><Feather name="tag" size={13} color={colors.onSurfaceSecondary} /><Txt style={styles.chipTxt}>{outfit.occasion}</Txt></View>
          ) : null}
          <View style={styles.chip}><Feather name="layers" size={13} color={colors.onSurfaceSecondary} /><Txt style={styles.chipTxt}>{items.length} {items.length === 1 ? "piece" : "pieces"}</Txt></View>
        </View>

        <View style={styles.actions}>
          <Pressable style={[styles.primaryBtn, setToday && styles.primaryDone]} testID="outfit-set-today" onPress={setAsToday} disabled={setToday || busy}>
            {setToday ? <Feather name="check" size={18} color={colors.onSage} /> : null}
            <Txt style={styles.primaryTxt}>{setToday ? "Set for today" : "Set as Today's Outfit"}</Txt>
          </Pressable>
          <Pressable style={styles.secondaryBtn} testID="outfit-duplicate" onPress={duplicate} disabled={busy}>
            <Feather name="copy" size={16} color={colors.onSurface} />
            <Txt style={styles.secondaryTxt}>Duplicate</Txt>
          </Pressable>
        </View>
      </ScrollView>

      <ConfirmModal
        visible={confirmDel}
        title="Delete outfit"
        message="This outfit will be removed from your saved looks."
        confirmLabel="Delete"
        destructive
        busy={deleting}
        onConfirm={doDelete}
        onCancel={() => setConfirmDel(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  topTitle: { fontSize: 18, flex: 1, textAlign: "center", marginHorizontal: spacing.sm },
  flatlay: { alignItems: "center", paddingTop: spacing.lg, gap: spacing.sm },
  stackImg: { width: 220, height: 200, backgroundColor: "transparent" },
  explainWrap: { paddingHorizontal: spacing["2xl"], marginTop: spacing.lg },
  explain: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 22, textAlign: "center" },
  chips: { flexDirection: "row", justifyContent: "center", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.lg, paddingHorizontal: spacing.lg },
  chip: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: 20 },
  chipTxt: { fontSize: 12, color: colors.onSurfaceSecondary },
  actions: { paddingHorizontal: spacing.lg, marginTop: spacing["2xl"], gap: spacing.md },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.sage, height: 52, borderRadius: radius.md },
  primaryDone: { backgroundColor: colors.sagePressed },
  primaryTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayMedium },
  secondaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 52, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  secondaryTxt: { color: colors.onSurface, fontSize: 16, fontFamily: fonts.displayMedium },
});
