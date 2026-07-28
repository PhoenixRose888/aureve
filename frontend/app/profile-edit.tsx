import React, { useState, useEffect } from "react";
import { View, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, Modal } from "react-native";
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

type GuideItem = { term: string; desc: string };
const GUIDES: Record<string, { title: string; intro?: string; items: GuideItem[]; tip?: string }> = {
  measure: {
    title: "How to measure yourself",
    intro: "Use a soft tape measure over light clothing. Keep the tape snug but not tight, and stand relaxed — don't suck in.",
    items: [
      { term: "Bust / chest", desc: "Around the fullest part of your chest, keeping the tape level all the way round." },
      { term: "Waist", desc: "Around the narrowest part of your middle, usually just above the belly button." },
      { term: "Hips", desc: "Around the fullest part of your seat, with your feet together." },
      { term: "Inseam (inner leg)", desc: "From the crotch seam straight down the inside of the leg to your ankle bone." },
      { term: "Outseam (outer leg)", desc: "From your natural waist down the outside of the leg to the ankle." },
      { term: "Arm length", desc: "From the tip of your shoulder, down a slightly bent arm, to the wrist bone." },
      { term: "Shoulder", desc: "Across your back, from the tip of one shoulder to the tip of the other." },
    ],
    tip: "Tip: if you can, ask someone to help — it's far more accurate than measuring alone.",
  },
  skin: {
    title: "Find your skin tone & undertone",
    intro: "Do this in natural daylight, with a bare, clean face. Skin tone is how light or deep your skin is; undertone is the subtle colour beneath.",
    items: [
      { term: "Skin tone", desc: "Look at your jaw/neck in daylight and match from Fair → Light → Medium → Olive → Tan → Deep → Dark." },
      { term: "Vein test", desc: "Look at the veins on your inner wrist: greenish = warm, blue/purple = cool, a mix = neutral." },
      { term: "Jewellery test", desc: "Gold tends to flatter warm undertones, silver flatters cool. If both look great, you're likely neutral." },
      { term: "White-paper test", desc: "Hold white paper to your face: skin looking yellow/peachy = warm, pink/rosy = cool, balanced = neutral." },
      { term: "Sun test", desc: "Burn easily and rarely tan? Often cool. Tan easily and rarely burn? Often warm." },
    ],
    tip: "Tip: undertone stays the same even when a tan changes your surface tone.",
  },
  shape: {
    title: "Find your body shape",
    intro: "Measure your bust, waist and hips (see the measuring guide), then compare which is widest.",
    items: [
      { term: "Hourglass", desc: "Bust and hips are roughly equal, with a clearly defined, narrower waist." },
      { term: "Pear / triangle", desc: "Hips are noticeably wider than your bust and shoulders." },
      { term: "Apple / round", desc: "Weight sits around the middle; waist is the widest point, with a fuller bust." },
      { term: "Rectangle", desc: "Bust, waist and hips are fairly similar, with little waist definition." },
      { term: "Inverted triangle", desc: "Shoulders and bust are wider than your hips." },
      { term: "Athletic", desc: "A straighter, toned frame with subtle waist definition." },
    ],
    tip: "It's a guide, not a rule — always dress for how you want to feel.",
  },
};

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
  const [guide, setGuide] = useState<null | "measure" | "skin" | "shape">(null);
  const [goingBeauty, setGoingBeauty] = useState(false);

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

  const persist = async () => {
    const measurements = Object.fromEntries(Object.entries(meas).filter(([, v]) => v && String(v).trim()));
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
  };

  const save = async () => {
    setSaving(true);
    try {
      await persist();
      setSaved(true);
      setTimeout(() => {
        if (router.canGoBack()) router.back();
        else router.replace("/(tabs)/profile");
      }, 400);
    } catch {
      setSaving(false);
    }
  };

  const goBeauty = async () => {
    if (!skinTone && !undertone) {
      setGuide("skin");
      return;
    }
    setGoingBeauty(true);
    try {
      await persist();
      router.push("/beauty");
    } catch {}
    setGoingBeauty(false);
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="profile-edit-close" hitSlop={12}>
          <Feather name="x" size={24} color={colors.onSurface} />
        </Pressable>
        <Display weight="semibold" style={styles.headerTitle}>Style profile</Display>
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

        <View style={styles.groupHeaderRow}>
          <Txt style={styles.groupLabelInline}>MEASUREMENTS</Txt>
          <Pressable onPress={() => setGuide("measure")} testID="guide-measure" hitSlop={8}>
            <Txt style={styles.helpLink}>Not sure how? →</Txt>
          </Pressable>
        </View>
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

        <View style={styles.groupHeaderRow}>
          <Txt style={styles.groupLabelInline}>BODY SHAPE</Txt>
          <Pressable onPress={() => setGuide("shape")} testID="guide-shape" hitSlop={8}>
            <Txt style={styles.helpLink}>How to find yours →</Txt>
          </Pressable>
        </View>
        <ChipRow options={BODY_SHAPES} value={bodyShape} onChange={setBodyShape} prefix="shape" />

        <View style={styles.groupHeaderRow}>
          <Txt style={styles.groupLabelInline}>SKIN TONE</Txt>
          <Pressable onPress={() => setGuide("skin")} testID="guide-skin" hitSlop={8}>
            <Txt style={styles.helpLink}>How to find yours →</Txt>
          </Pressable>
        </View>
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

        <View style={styles.beautyBlock}>
          <Txt style={styles.groupLabel}>HAIR & MAKEUP</Txt>
          <Txt style={styles.beautyIntro}>
            Get hair and makeup tuned to your skin tone and undertone — colour theory, not guesswork.
          </Txt>
          <Pressable style={styles.beautyBtn} testID="open-beauty-from-profile" onPress={goBeauty} disabled={goingBeauty}>
            {goingBeauty ? (
              <ActivityIndicator color={colors.onBrandTertiary} />
            ) : (
              <>
                <Feather name="feather" size={17} color={colors.onBrandTertiary} />
                <Txt style={styles.beautyBtnTxt}>Get my hair & makeup</Txt>
              </>
            )}
          </Pressable>
        </View>
      </KeyboardAwareScrollView>

      <KeyboardStickyView offset={{ closed: 0, opened: 0 }}>
        <View style={[styles.footer, { paddingBottom: insets.bottom || spacing.lg }]}>
          <Pressable style={styles.saveBtn} testID="save-profile-button" onPress={save} disabled={saving}>
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Txt style={styles.saveTxt}>{saved ? "Saved ✓" : "Save profile"}</Txt>}
          </Pressable>
        </View>
      </KeyboardStickyView>

      <Modal visible={guide != null} transparent animationType="slide" onRequestClose={() => setGuide(null)}>
        <Pressable style={styles.guideBackdrop} onPress={() => setGuide(null)}>
          <Pressable style={[styles.guideSheet, { paddingBottom: (insets.bottom || spacing.lg) + spacing.lg }]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.guideHandle} />
            {guide ? (
              <ScrollView showsVerticalScrollIndicator={false}>
                <Display weight="semibold" style={styles.guideTitle}>{GUIDES[guide].title}</Display>
                {GUIDES[guide].intro ? <Txt style={styles.guideIntro}>{GUIDES[guide].intro}</Txt> : null}
                {GUIDES[guide].items.map((it, i) => (
                  <View key={i} style={styles.guideRow}>
                    <Txt style={styles.guideTerm}>{it.term}</Txt>
                    <Txt style={styles.guideDesc}>{it.desc}</Txt>
                  </View>
                ))}
                {GUIDES[guide].tip ? (
                  <View style={styles.guideTipCard}>
                    <Feather name="info" size={14} color={colors.brand} />
                    <Txt style={styles.guideTipTxt}>{GUIDES[guide].tip}</Txt>
                  </View>
                ) : null}
                <Pressable style={styles.guideClose} testID="guide-close" onPress={() => setGuide(null)}>
                  <Txt style={styles.guideCloseTxt}>Got it</Txt>
                </Pressable>
              </ScrollView>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>
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
  groupHeaderRow: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginTop: spacing.xl, marginBottom: spacing.md },
  groupLabelInline: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary },
  helpLink: { fontSize: 12, color: colors.brand, fontFamily: fonts.displayMedium },
  beautyBlock: { marginTop: spacing["2xl"], borderTopWidth: 0.5, borderTopColor: colors.divider, paddingTop: spacing.md },
  beautyIntro: { fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 19, marginBottom: spacing.md },
  beautyBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 52, borderRadius: radius.md, backgroundColor: colors.brandTertiary },
  beautyBtnTxt: { color: colors.onBrandTertiary, fontSize: 15, fontFamily: fonts.displayBold },
  guideBackdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.45)", justifyContent: "flex-end" },
  guideSheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, paddingHorizontal: spacing.xl, paddingTop: spacing.md, maxHeight: "82%" },
  guideHandle: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.surfaceTertiary, marginBottom: spacing.lg },
  guideTitle: { fontSize: 22, letterSpacing: -0.4, color: colors.onSurface },
  guideIntro: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21, marginTop: spacing.sm, marginBottom: spacing.lg },
  guideRow: { marginBottom: spacing.lg },
  guideTerm: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium, marginBottom: 2 },
  guideDesc: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21 },
  guideTipCard: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start", backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginTop: spacing.sm },
  guideTipTxt: { flex: 1, fontSize: 13, color: colors.onBrandTertiary, lineHeight: 20 },
  guideClose: { height: 50, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  guideCloseTxt: { color: colors.onBrandPrimary, fontSize: 15, fontFamily: fonts.displayBold },
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
