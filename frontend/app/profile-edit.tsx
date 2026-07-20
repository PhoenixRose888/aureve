import React, { useState } from "react";
import { View, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/context/AuthContext";

const BODY_SHAPES = ["Hourglass", "Pear", "Apple", "Rectangle", "Inverted triangle", "Athletic"];
const SKIN_TONES = ["Fair", "Light", "Medium", "Olive", "Tan", "Deep", "Dark"];
const UNDERTONES = ["Warm", "Cool", "Neutral"];
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
  const { user, refreshUser } = useAuth();
  const existing = (user as any)?.profile || {};

  const [meas, setMeas] = useState<Record<string, string>>(existing.measurements || {});
  const [bodyShape, setBodyShape] = useState(existing.body_shape || "");
  const [skinTone, setSkinTone] = useState(existing.skin_tone || "");
  const [undertone, setUndertone] = useState(existing.undertone || "");
  const [notes, setNotes] = useState(existing.notes || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

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
          notes,
        },
      });
      await refreshUser();
      setSaved(true);
      setTimeout(() => router.back(), 400);
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
          Add as much or as little as you like. Aura uses this to pick cuts, lengths and colours that flatter
          you — tall or petite, and your skin tone. Everything's optional.
        </Txt>

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
  saveTxt: { color: colors.onBrandPrimary, fontSize: 16 },
});
