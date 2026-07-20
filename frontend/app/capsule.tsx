import React, { useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";

const THEMES = ["Autumn", "Winter", "Spring", "Summer", "Work", "Weekend", "Travel", "Evening"];

export default function Capsule() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [theme, setTheme] = useState("Autumn");
  const [occasion, setOccasion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const build = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    setSaved(false);
    try {
      setResult(await api<any>("/capsule/build", { method: "POST", body: { theme, occasion } }));
    } catch (e: any) {
      setError(e.message || "Couldn't build a capsule");
    }
    setLoading(false);
  };

  const save = async () => {
    if (!result?.capsule_items?.length) return;
    try {
      await api("/outfits", {
        method: "POST",
        body: {
          name: `${result.theme} capsule`,
          item_ids: result.capsule_items.map((i: any) => i.id),
          occasion: `${result.theme} capsule`,
          source: "capsule",
        },
      });
      setSaved(true);
    } catch {}
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="capsule-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Display weight="medium" style={styles.headerTitle}>Capsule builder</Display>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Txt style={styles.intro}>
          Aura curates a lean, mix-and-match capsule from your wardrobe for any season or purpose.
        </Txt>

        <Txt style={styles.groupLabel}>CHOOSE A THEME</Txt>
        <View style={styles.themeGrid}>
          {THEMES.map((t) => (
            <Pressable
              key={t}
              testID={`theme-${t}`}
              style={[styles.themeChip, theme === t && styles.themeActive]}
              onPress={() => setTheme(t)}
            >
              <Txt style={[styles.themeTxt, theme === t && styles.themeTxtActive]}>{t}</Txt>
            </Pressable>
          ))}
        </View>

        {error ? <Txt style={styles.error} testID="capsule-error">{error}</Txt> : null}

        <Txt style={styles.groupLabel}>PURPOSE (OPTIONAL)</Txt>
        <TextInput
          testID="capsule-occasion-input"
          style={styles.occInput}
          value={occasion}
          onChangeText={setOccasion}
          placeholder="e.g. business + pleasure trip, everyday work…"
          placeholderTextColor={colors.onSurfaceTertiary}
        />

        <Pressable style={styles.buildBtn} testID="build-capsule-button" onPress={build} disabled={loading}>
          {loading ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <>
              <Feather name="layers" size={17} color={colors.onBrandPrimary} />
              <Txt style={styles.buildTxt}>Build {theme.toLowerCase()} capsule</Txt>
            </>
          )}
        </Pressable>
        {loading && <Txt style={styles.loadingTxt}>Curating your capsule…</Txt>}

        {result && (
          <View style={styles.result} testID="capsule-result">
            <Display weight="medium" style={styles.resTheme}>{result.theme} capsule</Display>
            {result.summary ? <Txt style={styles.summary}>{result.summary}</Txt> : null}

            <Txt style={styles.sectionTitle}>THE PIECES ({result.capsule_items?.length || 0})</Txt>
            <View style={styles.grid}>
              {result.capsule_items?.map((it: any) => (
                <Pressable key={it.id} style={styles.gItem} onPress={() => router.push(`/item/${it.id}`)}>
                  {it.photo ? (
                    <Image source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={styles.gImg} contentFit="cover" />
                  ) : (
                    <View style={[styles.gImg, styles.ph]}><Feather name="image" size={16} color={colors.onSurfaceTertiary} /></View>
                  )}
                  <Txt style={styles.gName} numberOfLines={1}>{it.name}</Txt>
                </Pressable>
              ))}
            </View>

            {result.resolved_outfits?.length > 0 && (
              <>
                <Txt style={styles.sectionTitle}>OUTFITS FROM IT</Txt>
                {result.resolved_outfits.map((o: any, i: number) => (
                  <View key={i} style={styles.outfitRow}>
                    <Txt style={styles.outfitName}>{o.name}</Txt>
                    <View style={styles.oThumbs}>
                      {o.items.map((it: any) =>
                        it.photo ? (
                          <Image key={it.id} source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={styles.oThumb} contentFit="cover" />
                        ) : (
                          <View key={it.id} style={[styles.oThumb, styles.ph]} />
                        )
                      )}
                    </View>
                  </View>
                ))}
              </>
            )}

            {result.essentials_missing?.length > 0 && (
              <View style={styles.missingCard}>
                <Txt style={styles.missingLabel}>WOULD COMPLETE IT</Txt>
                {result.essentials_missing.map((m: string, i: number) => (
                  <View key={i} style={styles.missingItem}>
                    <Feather name="plus-circle" size={13} color={colors.onSurfaceTertiary} />
                    <Txt style={styles.missingItemTxt}>{m}</Txt>
                  </View>
                ))}
              </View>
            )}

            {result.capsule_tip ? (
              <View style={styles.tipCard}>
                <Feather name="zap" size={14} color={colors.brand} />
                <Txt style={styles.tipTxt}>{result.capsule_tip}</Txt>
              </View>
            ) : null}

            <Pressable style={styles.saveBtn} testID="save-capsule-button" onPress={save} disabled={saved}>
              <Feather name={saved ? "check" : "bookmark"} size={16} color={colors.onSurface} />
              <Txt style={styles.saveTxt}>{saved ? "Saved to your looks" : "Save this capsule"}</Txt>
            </Pressable>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  headerTitle: { fontSize: 22 },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  intro: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21 },
  groupLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginTop: spacing.xl, marginBottom: spacing.md },
  themeGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  themeChip: { paddingHorizontal: spacing.lg, height: 40, borderRadius: radius.pill, borderWidth: 0.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  themeActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  themeTxt: { fontSize: 14, color: colors.onSurfaceSecondary },
  themeTxtActive: { color: colors.onBrandPrimary },
  error: { color: colors.error, fontSize: 13, marginTop: spacing.lg },
  occInput: { fontFamily: fonts.body, fontSize: 16, color: colors.onSurface, borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: spacing.sm },
  buildBtn: { backgroundColor: colors.brandPrimary, height: 54, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, marginTop: spacing.xl },
  buildTxt: { color: colors.onBrandPrimary, fontSize: 16 },
  loadingTxt: { textAlign: "center", color: colors.onSurfaceTertiary, fontSize: 13, marginTop: spacing.lg, fontStyle: "italic" },
  result: { marginTop: spacing["2xl"] },
  resTheme: { fontSize: 28 },
  summary: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22, marginTop: spacing.sm },
  sectionTitle: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginTop: spacing.xl, marginBottom: spacing.md },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  gItem: { width: "30%" },
  gImg: { width: "100%", aspectRatio: 0.8, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  ph: { alignItems: "center", justifyContent: "center" },
  gName: { fontSize: 11, color: colors.onSurface, marginTop: 4 },
  outfitRow: { marginBottom: spacing.lg, borderBottomWidth: 0.5, borderColor: colors.divider, paddingBottom: spacing.lg },
  outfitName: { fontSize: 15, color: colors.onSurface, marginBottom: spacing.sm },
  oThumbs: { flexDirection: "row", gap: spacing.sm },
  oThumb: { width: 48, height: 60, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  missingCard: { marginTop: spacing.lg, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.lg },
  missingLabel: { fontSize: 10, letterSpacing: 1, color: colors.onSurfaceTertiary, marginBottom: spacing.sm },
  missingItem: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 4 },
  missingItemTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  tipCard: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, alignItems: "center" },
  tipTxt: { flex: 1, fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 19, fontStyle: "italic" },
  saveBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 52, borderWidth: 0.5, borderColor: colors.borderStrong, borderRadius: radius.sm, marginTop: spacing.xl },
  saveTxt: { fontSize: 15, color: colors.onSurface },
});
