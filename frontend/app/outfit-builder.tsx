import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Modal, TextInput, ActivityIndicator } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { useAuth } from "@/src/context/AuthContext";
import { useWeather } from "@/src/hooks/useWeather";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";
import * as haptics from "@/src/utils/haptics";

const SLOTS = [
  { key: "Tops", label: "Add Top" },
  { key: "Bottoms", label: "Add Bottom" },
  { key: "Shoes", label: "Add Shoes" },
] as const;

export default function OutfitBuilder() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { weather } = useWeather();
  const premium = !!user?.premium;

  const [items, setItems] = useState<any[]>([]);
  const [selected, setSelected] = useState<Record<string, any>>({});
  const [pickerCat, setPickerCat] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [feedback, setFeedback] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [naming, setNaming] = useState(false);

  const load = useCallback(async () => {
    try { setItems(await api<any[]>("/items")); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const chosen = Object.values(selected).filter(Boolean);
  const ready = chosen.length >= 2;

  const pick = (item: any) => {
    haptics.tap();
    setSelected((s) => ({ ...s, [pickerCat!]: item }));
    setPickerCat(null);
    setSearch("");
    setFeedback("");
  };

  const getInspiration = async () => {
    if (!premium) { router.push("/premium"); return; }
    setAiBusy(true);
    haptics.tap();
    try {
      const body: any = {};
      if (weather) { body.temperature = weather.temperature; body.weather = weather.description; }
      const r = await api<any>("/dressme", { method: "POST", body });
      const next: Record<string, any> = {};
      for (const ri of r.resolved_items || []) {
        const cat = ri.item?.category;
        if (cat === "Tops" || cat === "Bottoms" || cat === "Shoes") next[cat] = ri.item;
      }
      if (Object.keys(next).length) setSelected(next);
      setFeedback(r.rationale || r.explanation || r.notes || "A balanced look pulled from your wardrobe — comfortable, cohesive and ready to wear.");
      haptics.success();
    } catch (e: any) {
      if (String(e?.message || e).includes("402")) router.push("/premium");
    }
    setAiBusy(false);
  };

  const doSave = async () => {
    setSaving(true);
    try {
      const outfit = await api<any>("/outfits", {
        method: "POST",
        body: { name: name.trim() || "My Outfit", item_ids: chosen.map((i) => i.id), source: "manual", notes: feedback || "" },
      });
      haptics.success();
      setNaming(false);
      router.replace(`/outfit/${outfit.id}`);
    } catch {}
    setSaving(false);
  };

  const catItems = items.filter((i) => i.category === pickerCat && (!search || (i.name || "").toLowerCase().includes(search.toLowerCase())));

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Display weight="medium" style={styles.topTitle}>Create Outfit</Display>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="builder-close"><Feather name="x" size={24} color={colors.onSurface} /></Pressable>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] }}>
        {SLOTS.map((slot) => {
          const it = selected[slot.key];
          return (
            <Pressable key={slot.key} style={[styles.slot, it && styles.slotFilled]} testID={`slot-${slot.key}`} onPress={() => { setPickerCat(slot.key); setSearch(""); }}>
              {it ? (
                <>
                  <GarmentImage photo={it.photo} category={it.category} style={styles.slotImg} iconSize={22} />
                  <View style={{ flex: 1 }}>
                    <Txt style={styles.slotName} numberOfLines={1}>{it.name}</Txt>
                    <Txt style={styles.slotCat}>{it.category}</Txt>
                  </View>
                  <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />
                </>
              ) : (
                <View style={styles.slotEmpty}>
                  <Feather name="plus" size={22} color={colors.onSurfaceSecondary} />
                  <Txt style={styles.slotLabel}>{slot.label}</Txt>
                  <Txt style={styles.slotHint}>Tap to add</Txt>
                </View>
              )}
            </Pressable>
          );
        })}

        {feedback ? (
          <View style={styles.feedback} testID="builder-feedback">
            <View style={styles.feedbackHead}><Feather name="star" size={15} color={colors.onBrandTertiary} /><Txt style={styles.feedbackTitle}>You&rsquo;ve nailed this look!</Txt></View>
            <Txt style={styles.feedbackTxt}>{feedback}</Txt>
          </View>
        ) : null}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        {ready && (
          <Pressable style={styles.saveBtn} testID="builder-save" onPress={() => { setNaming(true); haptics.tap(); }}>
            <Txt style={styles.saveTxt}>Save Outfit</Txt>
          </Pressable>
        )}
        <Pressable style={[styles.aiBtn, ready && styles.aiBtnGhost]} testID="builder-ai" onPress={getInspiration} disabled={aiBusy}>
          {aiBusy ? <ActivityIndicator color={ready ? colors.onSurface : colors.onSage} size="small" /> : <Feather name="star" size={16} color={ready ? colors.onSurface : colors.onSage} />}
          <Txt style={[styles.aiTxt, ready && styles.aiTxtGhost]}>Get AI Inspiration</Txt>
        </Pressable>
      </View>

      {/* Item picker */}
      <Modal visible={!!pickerCat} animationType="slide" transparent onRequestClose={() => setPickerCat(null)}>
        <View style={styles.sheetBackdrop}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={styles.sheetHead}>
              <Display weight="medium" style={styles.sheetTitle}>Select {pickerCat === "Tops" ? "Top" : pickerCat === "Bottoms" ? "Bottom" : "Shoes"}</Display>
              <Pressable onPress={() => setPickerCat(null)} hitSlop={10}><Feather name="x" size={22} color={colors.onSurface} /></Pressable>
            </View>
            <View style={styles.searchBar}>
              <Feather name="search" size={16} color={colors.onSurfaceTertiary} />
              <TextInput style={styles.searchInput} placeholder={`Search ${(pickerCat || "").toLowerCase()}`} placeholderTextColor={colors.onSurfaceTertiary} value={search} onChangeText={setSearch} />
            </View>
            <ScrollView showsVerticalScrollIndicator={false}>
              {catItems.length === 0 ? (
                <Txt style={styles.pickerEmpty}>No {(pickerCat || "").toLowerCase()} in your wardrobe yet.</Txt>
              ) : (
                <View style={styles.pickerGrid}>
                  {catItems.map((it) => {
                    const on = selected[pickerCat!]?.id === it.id;
                    return (
                      <Pressable key={it.id} style={styles.pickerCell} testID={`pick-${it.id}`} onPress={() => pick(it)}>
                        <View>
                          <GarmentImage photo={it.photo} category={it.category} style={styles.pickerImg} iconSize={22} />
                          {on && <View style={styles.pickCheck}><Feather name="check" size={12} color={colors.onSage} /></View>}
                        </View>
                        <Txt style={styles.pickerName} numberOfLines={1}>{it.name}</Txt>
                      </Pressable>
                    );
                  })}
                </View>
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Name & save */}
      <Modal visible={naming} animationType="fade" transparent onRequestClose={() => setNaming(false)}>
        <View style={styles.nameBackdrop}>
          <View style={styles.nameCard}>
            <Display weight="medium" style={styles.nameTitle}>Name this look</Display>
            <TextInput style={styles.nameInput} placeholder="e.g. Casual Friday" placeholderTextColor={colors.onSurfaceTertiary} value={name} onChangeText={setName} autoFocus />
            <View style={styles.nameRow}>
              <Pressable style={styles.nameCancel} onPress={() => setNaming(false)}><Txt style={styles.nameCancelTxt}>Cancel</Txt></Pressable>
              <Pressable style={styles.nameSave} onPress={doSave} disabled={saving} testID="builder-save-confirm">
                {saving ? <ActivityIndicator color={colors.onSage} size="small" /> : <Txt style={styles.nameSaveTxt}>Save</Txt>}
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  topTitle: { fontSize: 20 },
  slot: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 96, borderRadius: radius.md, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.border, padding: spacing.md, marginBottom: spacing.md },
  slotFilled: { borderStyle: "solid", backgroundColor: colors.surface, borderColor: colors.border },
  slotImg: { width: 64, height: 78, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  slotName: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium },
  slotCat: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 2 },
  slotEmpty: { flex: 1, alignItems: "center", justifyContent: "center", gap: 2, paddingVertical: spacing.md },
  slotLabel: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium, marginTop: 4 },
  slotHint: { fontSize: 12, color: colors.onSurfaceTertiary },
  feedback: { backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginTop: spacing.sm },
  feedbackHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  feedbackTitle: { fontSize: 15, color: colors.onBrandTertiary, fontFamily: fonts.displayMedium },
  feedbackTxt: { fontSize: 14, color: colors.onBrandTertiary, lineHeight: 21 },
  footer: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, borderTopWidth: 0.5, borderTopColor: colors.border, gap: spacing.md, backgroundColor: colors.surface },
  saveBtn: { backgroundColor: colors.sage, height: 52, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  saveTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayMedium },
  aiBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.sage, height: 52, borderRadius: radius.md },
  aiBtnGhost: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  aiTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayMedium },
  aiTxtGhost: { color: colors.onSurface },
  sheetBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingHorizontal: spacing.lg, paddingTop: spacing.lg, maxHeight: "82%" },
  sheetHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  sheetTitle: { fontSize: 18 },
  searchBar: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44, marginBottom: spacing.md },
  searchInput: { flex: 1, fontFamily: fonts.body, fontSize: 14, color: colors.onSurface },
  pickerGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, paddingBottom: spacing.lg },
  pickerCell: { width: "30.5%" },
  pickerImg: { width: "100%", aspectRatio: 0.82, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  pickCheck: { position: "absolute", top: 6, right: 6, width: 22, height: 22, borderRadius: 11, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
  pickerName: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 4 },
  pickerEmpty: { fontSize: 14, color: colors.onSurfaceTertiary, textAlign: "center", paddingVertical: spacing["2xl"] },
  nameBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", alignItems: "center", justifyContent: "center", padding: spacing.xl },
  nameCard: { width: "100%", backgroundColor: colors.surface, borderRadius: 20, padding: spacing.xl },
  nameTitle: { fontSize: 18, marginBottom: spacing.md },
  nameInput: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 48, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface, marginBottom: spacing.lg },
  nameRow: { flexDirection: "row", gap: spacing.md },
  nameCancel: { flex: 1, height: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  nameCancelTxt: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium },
  nameSave: { flex: 1, height: 48, borderRadius: radius.md, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
  nameSaveTxt: { fontSize: 15, color: colors.onSage, fontFamily: fonts.displayMedium },
});
