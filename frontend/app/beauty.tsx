import React, { useState, useCallback } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";

const OCCASIONS = ["Everyday", "Work", "Evening", "Wedding", "Date", "Interview"];

export default function Beauty() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [occasion, setOccasion] = useState("Everyday");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [needsProfile, setNeedsProfile] = useState(false);

  const generate = useCallback(async () => {
    setLoading(true);
    setError("");
    setNeedsProfile(false);
    setResult(null);
    try {
      const r = await api<any>("/beauty/suggest", { method: "POST", body: { occasion } });
      setResult(r);
    } catch (e: any) {
      const msg = e.message || "Couldn't generate recommendations";
      if (msg.toLowerCase().includes("skin tone")) setNeedsProfile(true);
      setError(msg);
    }
    setLoading(false);
  }, [occasion]);

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="beauty-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt style={styles.headerKicker}>HAIR & MAKEUP</Txt>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Display weight="medium" style={styles.title}>Beauty for your colouring</Display>
        <Txt style={styles.sub}>Hair and makeup tuned to your skin tone and undertone — colour theory, not guesswork.</Txt>

        <Txt style={styles.groupLabel}>OCCASION</Txt>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipContent}>
          {OCCASIONS.map((o) => (
            <Pressable
              key={o}
              testID={`beauty-occasion-${o}`}
              style={[styles.chip, occasion === o && styles.chipActive]}
              onPress={() => setOccasion(o)}
            >
              <Txt style={[styles.chipTxt, occasion === o && styles.chipTxtActive]}>{o}</Txt>
            </Pressable>
          ))}
        </ScrollView>

        <Pressable style={styles.genBtn} testID="beauty-generate" onPress={generate} disabled={loading}>
          {loading ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <Txt style={styles.genTxt}>{result ? "Regenerate" : "Get my hair & makeup"}</Txt>
          )}
        </Pressable>

        {loading && (
          <View style={styles.center}>
            <Txt style={styles.loadingTxt}>Analysing your colouring…</Txt>
          </View>
        )}

        {error && !loading ? (
          <View style={styles.errorBox}>
            <Txt style={styles.errorTxt} testID="beauty-error">{error}</Txt>
            {needsProfile && (
              <Pressable style={styles.profileBtn} testID="beauty-open-profile" onPress={() => router.push("/profile-edit")}>
                <Feather name="user" size={15} color={colors.onBrandPrimary} />
                <Txt style={styles.profileBtnTxt}>Add skin tone & undertone</Txt>
              </Pressable>
            )}
          </View>
        ) : null}

        {result && !loading ? (
          <View testID="beauty-result">
            <Txt style={styles.summary}>{result.summary}</Txt>

            {result.palette?.length > 0 && (
              <View style={styles.section}>
                <Txt style={styles.sectionTitle}>YOUR COLOURS</Txt>
                <View style={styles.paletteWrap}>
                  {result.palette.map((c: string, i: number) => (
                    <View key={i} style={styles.paletteChip}>
                      <Txt style={styles.paletteTxt}>{c}</Txt>
                    </View>
                  ))}
                </View>
              </View>
            )}

            {result.makeup && (
              <View style={styles.section}>
                <Txt style={styles.sectionTitle}>MAKEUP</Txt>
                <Row label="Base" text={result.makeup.foundation} />
                <Row label="Blush" text={result.makeup.blush} />
                <Row label="Lip" text={result.makeup.lip} />
                <Row label="Eye" text={result.makeup.eye} />
                {result.makeup.tip ? <Tip text={result.makeup.tip} /> : null}
              </View>
            )}

            {result.hair && (
              <View style={styles.section}>
                <Txt style={styles.sectionTitle}>HAIR</Txt>
                <Row label="Colour" text={result.hair.colour} />
                <Row label="Style" text={result.hair.style} />
                {result.hair.tip ? <Tip text={result.hair.tip} /> : null}
              </View>
            )}

            {result.avoid?.length > 0 && (
              <View style={styles.section}>
                <Txt style={styles.sectionTitle}>WORTH AVOIDING</Txt>
                {result.avoid.map((a: string, i: number) => (
                  <View key={i} style={styles.avoidRow}>
                    <Feather name="x" size={14} color={colors.warning} />
                    <Txt style={styles.avoidTxt}>{a}</Txt>
                  </View>
                ))}
              </View>
            )}

            {result.occasion_note ? (
              <View style={styles.noteCard}>
                <Feather name="star" size={14} color={colors.brand} />
                <Txt style={styles.noteTxt}>{result.occasion_note}</Txt>
              </View>
            ) : null}
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

function Row({ label, text }: { label: string; text?: string }) {
  if (!text) return null;
  return (
    <View style={styles.row}>
      <Txt style={styles.rowLabel}>{label}</Txt>
      <Txt style={styles.rowTxt}>{text}</Txt>
    </View>
  );
}

function Tip({ text }: { text: string }) {
  return (
    <View style={styles.tipRow}>
      <Feather name="info" size={13} color={colors.onSurfaceTertiary} />
      <Txt style={styles.tipTxt}>{text}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  headerKicker: { fontSize: 11, letterSpacing: 2, color: colors.onSurfaceTertiary },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  title: { fontSize: 30, color: colors.onSurface },
  sub: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21, marginTop: spacing.sm },
  groupLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginTop: spacing.xl, marginBottom: spacing.md },
  chipContent: { gap: spacing.sm, paddingRight: spacing.xl },
  chip: { height: 38, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 0.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  chipTxtActive: { color: colors.onBrandPrimary },
  genBtn: { backgroundColor: colors.brandPrimary, height: 54, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  genTxt: { color: colors.onBrandPrimary, fontSize: 16 },
  center: { alignItems: "center", paddingVertical: spacing.xl },
  loadingTxt: { color: colors.onSurfaceTertiary, fontSize: 13, fontStyle: "italic" },
  errorBox: { marginTop: spacing.xl, gap: spacing.md },
  errorTxt: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 20 },
  profileBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 48, borderRadius: radius.sm, backgroundColor: colors.brandPrimary },
  profileBtnTxt: { color: colors.onBrandPrimary, fontSize: 15 },
  summary: { fontSize: 18, color: colors.onSurface, lineHeight: 26, marginTop: spacing.xl, fontStyle: "italic" },
  section: { marginTop: spacing["2xl"] },
  sectionTitle: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginBottom: spacing.md },
  paletteWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  paletteChip: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.pill, borderWidth: 0.5, borderColor: colors.borderStrong, backgroundColor: colors.surfaceSecondary },
  paletteTxt: { fontSize: 13, color: colors.onSurface, textTransform: "capitalize" },
  row: { marginBottom: spacing.lg },
  rowLabel: { fontSize: 11, letterSpacing: 1, color: colors.onSurfaceTertiary, marginBottom: 3 },
  rowTxt: { fontSize: 15, color: colors.onSurface, lineHeight: 22 },
  tipRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", marginTop: spacing.xs },
  tipTxt: { flex: 1, fontSize: 13, color: colors.onSurfaceTertiary, lineHeight: 19, fontStyle: "italic" },
  avoidRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", marginBottom: spacing.sm },
  avoidTxt: { flex: 1, fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  noteCard: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start", backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginTop: spacing["2xl"] },
  noteTxt: { flex: 1, fontSize: 14, color: colors.onBrandTertiary, lineHeight: 21 },
});
