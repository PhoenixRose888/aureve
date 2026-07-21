import React, { useState, useEffect } from "react";
import { View, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { useProfiles } from "@/src/context/ProfileContext";

const BODY_SHAPES = ["Hourglass", "Pear", "Apple", "Rectangle", "Inverted triangle", "Athletic"];
const SKIN_TONES = ["Fair", "Light", "Medium", "Olive", "Tan", "Deep", "Dark"];
const UNDERTONES = ["Warm", "Cool", "Neutral"];
const FIT_PREFS = ["Fitted", "Tailored", "Regular", "Relaxed", "Oversized"];
const STYLE_PREFS = ["Minimal", "Classic", "Casual", "Smart casual", "Streetwear", "Bohemian", "Sporty", "Edgy", "Romantic", "Business"];
const MEAS = [
  { key: "height", label: "Height", unit: "cm" },
  { key: "weight", label: "Weight", unit: "kg" },
  { key: "bust", label: "Bust / chest", unit: "cm" },
  { key: "waist", label: "Waist", unit: "cm" },
  { key: "hips", label: "Hips", unit: "cm" },
  { key: "inseam", label: "Leg / inseam", unit: "cm" },
  { key: "arm", label: "Arm length", unit: "cm" },
  { key: "shoulder", label: "Shoulder", unit: "cm" },
  { key: "shoe", label: "Shoe size", unit: "" },
];

export default function ProfileEdit() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { active, refresh } = useProfiles();
  const existing = active?.profile || {};

  const [meas, setMeas] = useState<Record<string, string>>(existing.measurements || {});
  const [bodyShape, setBodyShape] = useState(existing.body_shape || "");
  const [skinTone, setSkinTone] = useState(existing.skin_tone || "");
  const [undertone, setUndertone] = useState(existing.undertone || "");
  const [fitPref, setFitPref] = useState(existing.fit_pref || "");
  const [sizesTop, setSizesTop] = useState(existing.sizes_top || "");
  const [sizesBottom, setSizesBottom] = useState(existing.sizes_bottom || "");
  const [stylePrefs, setStylePrefs] = useState<string[]>(existing.style_prefs || []);
  const [notes, setNotes] = useState(existing.notes || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const toggleStyle = (s: string) =>
    setStylePrefs((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));

  // Re-sync form state once the profile hydrates (or when switching profiles),
  // so values populate correctly on hard reload / deep-link.
  useEffect(() => {
    const p = active?.profile || {};
    setMeas(p.measurements || {});
    setBodyShape(p.body_shape || "");
    setSkinTone(p.skin_tone || "");
    setUndertone(p.undertone || "");
    setFitPref(p.fit_pref || "");
    setSizesTop(p.sizes_top || "");
    setSizesBottom(p.sizes_bottom || "");
    setStylePrefs(p.style_prefs || []);
    setNotes(p.notes || "");
  }, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    setSaving(true);
    const measurements = Object.fromEntries(Object.entries(meas).filter(([, v]) => v && String(v).trim()));
    try {
      await api("/profile", {
        method: "PUT",
        body: {
          measurements,
          body_shape: bodyShape,
          skin_tone: skinTone,
          undertone,
          fit_pref: fitPref,
          sizes_top: sizesTop,
          sizes_bottom: sizesBottom,
          style_prefs: stylePrefs,
          notes,
        },
      });
      await refresh();
      setSaved(true);
      setTimeout(() => {
        if (router.canGoBack()) router.back();
        else router.replace("/(tabs)/profile");
      }, 400);
    } catch {
      setSaving(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="profile-edit-close" hitSlop={12}>
          <Feather name="x" size={24} color={colors.onSurface} />
        </Pressable>
        <Display weight="medium" style={styles.headerTitle}>Style profile</Display>
        <View style={{ width: 24 }} />
      </View>

      <KeyboardAwareScrollView style={{ flex: 1 }} contentContainerStyle={styles.scroll} bottomOffset={90} showsVerticalScrollIndicator={false}>
        <Txt style={styles.intro}>
          A few quick taps help Aureve dress you better — fit, sizes and the styles you love.
          Everything is optional, and you can add more detail below.
        </Txt>

        <Txt style={styles.groupLabel}>FIT PREFERENCE</Txt>
        <ChipRow options={FIT_PREFS} value={fitPref} onChange={setFitPref} prefix="fit" />

        <Txt style={styles.groupLabel}>CLOTHING SIZES</Txt>
        <View style={styles.sizeRow}>
          <View style={styles.sizeField}>
            <Txt style={styles.measLabel}>Tops</Txt>
            <TextInput
              testID="size-top"
              style={styles.input}
              value={sizesTop}
              onChangeText={setSizesTop}
              placeholder="e.g. M / 10"
              placeholderTextColor={colors.onSurfaceTertiary}
            />
          </View>
          <View style={styles.sizeField}>
            <Txt style={styles.measLabel}>Bottoms</Txt>
            <TextInput
              testID="size-bottom"
              style={styles.input}
              value={sizesBottom}
              onChangeText={setSizesBottom}
              placeholder="e.g. 30 / 12"
              placeholderTextColor={colors.onSurfaceTertiary}
            />
          </View>
        </View>

        <Txt style={styles.groupLabel}>STYLE — PICK A FEW</Txt>
        <View style={styles.wrapChips}>
          {STYLE_PREFS.map((s) => {
            const on = stylePrefs.includes(s);
            return (
              <Pressable key={s} testID={`style-${s}`} style={[styles.chip, on && styles.chipActive]} onPress={() => toggleStyle(s)}>
                <Txt style={[styles.chipTxt, on && styles.chipTxtActive]}>{s}</Txt>
              </Pressable>
            );
          })}
        </View>

        <Txt style={styles.groupLabel}>MEASUREMENTS</Txt>
        <View style={styles.measGrid}>
          {MEAS.map((m) => (
            <View key={m.key} style={styles.measField}>
              <Txt style={styles.measLabel}>{m.label}{m.unit ? ` (${m.unit})` : ""}</Txt>
              <TextInput
                testID={`meas-${m.key}`}
                style={styles.input}
                value={meas[m.key] ?? ""}
                onChangeText={(v) => setMeas((prev) => ({ ...prev, [m.key]: v }))}
                placeholder="—"
                placeholderTextColor={colors.onSurfaceTertiary}
                keyboardType="numeric"
              />
            </View>
          ))}
        </View>

        <Txt style={styles.groupLabel}>BODY SHAPE</Txt>
        <ChipRow options={BODY_SHAPES} value={bodyShape} onChange={setBodyShape} prefix="shape" />

        <Txt style={styles.groupLabel}>SKIN TONE</Txt>
        <ChipRow options={SKIN_TONES} value={skinTone} onChange={setSkinTone} prefix="skin" />

        <Txt style={styles.groupLabel}>UNDERTONE</Txt>
        <ChipRow options={UNDERTONES} value={undertone} onChange={setUndertone} prefix="undertone" />

        <Txt style={styles.groupLabel}>ANYTHING ELSE</Txt>
        <TextInput
          testID="profile-notes"
          style={[styles.input, styles.inputMulti]}
          value={notes}
          onChangeText={setNotes}
          placeholder="e.g. I avoid high necklines, love defined waists, never wear orange…"
          placeholderTextColor={colors.onSurfaceTertiary}
          multiline
        />
      </KeyboardAwareScrollView>

      <KeyboardStickyView offset={{ closed: 0, opened: 0 }}>
        <View style={[styles.footer, { paddingBottom: insets.bottom || spacing.lg }]}>
          <Pressable style={styles.saveBtn} testID="save-profile-button" onPress={save} disabled={saving}>
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Txt style={styles.saveTxt}>{saved ? "Saved ✓" : "Save profile"}</Txt>}
          </Pressable>
        </View>
      </KeyboardStickyView>
    </View>
  );
}

function ChipRow({ options, value, onChange, prefix }: { options: string[]; value: string; onChange: (v: string) => void; prefix: string }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipContent}>
      {options.map((o) => {
        const active = value === o;
        return (
          <Pressable key={o} testID={`${prefix}-${o}`} style={[styles.chip, active && styles.chipActive]} onPress={() => onChange(active ? "" : o)}>
            <Txt style={[styles.chipTxt, active && styles.chipTxtActive]}>{o}</Txt>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  headerTitle: { fontSize: 22 },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  intro: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21 },
  groupLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginTop: spacing.xl, marginBottom: spacing.md },
  measGrid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  measField: { width: "47%", marginBottom: spacing.lg },
  sizeRow: { flexDirection: "row", gap: spacing.lg },
  sizeField: { flex: 1 },
  wrapChips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  measLabel: { fontSize: 12, color: colors.onSurfaceTertiary, marginBottom: 4 },
  input: { fontFamily: fonts.body, fontSize: 16, color: colors.onSurface, borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: spacing.sm },
  inputMulti: { minHeight: 60, textAlignVertical: "top" },
  chipContent: { gap: spacing.sm, paddingRight: spacing.xl },
  chip: { height: 40, flexShrink: 0, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 0.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  chipTxtActive: { color: colors.onBrandPrimary },
  footer: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, borderTopWidth: 0.5, borderTopColor: colors.border, backgroundColor: colors.surface },
  saveBtn: { backgroundColor: colors.brandPrimary, height: 54, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  saveTxt: { color: colors.onBrandPrimary, fontSize: 16, fontFamily: fonts.displayBold },
});
