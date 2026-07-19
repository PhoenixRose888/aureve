import React, { useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";
import PhotoPickerModal from "@/src/components/PhotoPickerModal";

const verdictColor = (v: string) =>
  v === "Buy" ? colors.success : v === "Skip" ? colors.error : colors.warning;

export default function Shop() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [picker, setPicker] = useState(false);
  const [image, setImage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  const onPicked = async (base64: string) => {
    setImage(base64);
    setResult(null);
    setError("");
    setLoading(true);
    try {
      const r = await api<any>("/shop-check", { method: "POST", body: { image: base64 } });
      setResult(r);
    } catch (e: any) {
      setError(e.message || "Couldn't analyze the item");
    }
    setLoading(false);
  };

  const reset = () => {
    setImage(null);
    setResult(null);
    setError("");
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Txt style={styles.kicker}>BEFORE YOU BUY</Txt>
        <Display weight="medium" style={styles.title}>Shop check</Display>
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {!image ? (
          <Pressable style={styles.dropzone} testID="shop-upload-button" onPress={() => setPicker(true)}>
            <View style={styles.dropIcon}>
              <Feather name="shopping-bag" size={28} color={colors.onSurface} />
            </View>
            <Display weight="medium" style={styles.dropTitle}>Eyeing something new?</Display>
            <Txt style={styles.dropSub}>
              Upload a photo of the item and Aura tells you if it fills a real gap — or if it's just Black Jacket Number Eight in disguise.
            </Txt>
            <View style={styles.dropBtn}>
              <Feather name="upload" size={16} color={colors.onBrandPrimary} />
              <Txt style={styles.dropBtnTxt}>Upload item photo</Txt>
            </View>
          </Pressable>
        ) : (
          <View>
            <View style={styles.previewWrap}>
              <Image source={{ uri: `data:image/jpeg;base64,${image}` }} style={styles.preview} contentFit="cover" />
              {loading && (
                <View style={styles.scanOverlay}>
                  <ActivityIndicator color={colors.onSurfaceInverse} />
                  <Txt style={styles.scanTxt}>Comparing to your wardrobe…</Txt>
                </View>
              )}
              <Pressable style={styles.changeBtn} testID="shop-change-photo" onPress={reset}>
                <Feather name="refresh-cw" size={14} color={colors.onSurfaceInverse} />
              </Pressable>
            </View>

            {error ? (
              <View style={styles.errorWrap}>
                <Txt style={styles.error} testID="shop-error">{error}</Txt>
                <Pressable style={styles.retry} onPress={() => onPicked(image)}>
                  <Txt style={styles.retryTxt}>Try again</Txt>
                </Pressable>
              </View>
            ) : null}

            {result && (
              <View style={styles.result} testID="shop-result">
                <View style={[styles.verdictBadge, { borderColor: verdictColor(result.verdict) }]}>
                  <Txt style={[styles.verdictLabel, { color: verdictColor(result.verdict) }]}>
                    {result.verdict?.toUpperCase()}
                  </Txt>
                </View>
                <Display weight="medium" style={styles.itemSummary}>{result.item_summary}</Display>
                <Txt style={styles.reason}>{result.reason}</Txt>

                <View style={styles.statRow}>
                  <View style={styles.stat}>
                    <Display weight="medium" style={styles.statNum}>{result.outfits_added ?? 0}</Display>
                    <Txt style={styles.statLabel}>new outfits</Txt>
                  </View>
                  <View style={styles.statDivider} />
                  <View style={styles.stat}>
                    <Display weight="medium" style={styles.statNum}>{result.similar_items?.length ?? 0}</Display>
                    <Txt style={styles.statLabel}>similar owned</Txt>
                  </View>
                  <View style={styles.statDivider} />
                  <View style={styles.stat}>
                    <Feather
                      name={result.fills_gap ? "check-circle" : "x-circle"}
                      size={22}
                      color={result.fills_gap ? colors.success : colors.error}
                    />
                    <Txt style={styles.statLabel}>{result.fills_gap ? "fills a gap" : "no real gap"}</Txt>
                  </View>
                </View>

                {result.gap_note ? (
                  <View style={styles.gapNote}>
                    <Feather name="info" size={14} color={colors.brand} />
                    <Txt style={styles.gapTxt}>{result.gap_note}</Txt>
                  </View>
                ) : null}

                {result.similar_items?.length > 0 && (
                  <Section title="Similar items you own" items={result.similar_items} router={router} />
                )}
                {result.matches_with?.length > 0 && (
                  <Section title="Would pair with" items={result.matches_with} router={router} />
                )}

                <Pressable style={styles.newCheckBtn} testID="shop-new-check" onPress={reset}>
                  <Txt style={styles.newCheckTxt}>Check another item</Txt>
                </Pressable>
              </View>
            )}
          </View>
        )}
      </ScrollView>

      <PhotoPickerModal visible={picker} onClose={() => setPicker(false)} onPicked={onPicked} title="Photo of the item" />
    </View>
  );
}

function Section({ title, items, router }: { title: string; items: any[]; router: any }) {
  return (
    <View style={styles.section}>
      <Txt style={styles.sectionTitle}>{title}</Txt>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.md, paddingRight: spacing.xl }}>
        {items.map((it) => (
          <Pressable key={it.id} style={styles.simCard} onPress={() => router.push(`/item/${it.id}`)}>
            {it.photo ? (
              <Image source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={styles.simImg} contentFit="cover" />
            ) : (
              <View style={[styles.simImg, styles.simPlaceholder]}>
                <Feather name="image" size={18} color={colors.onSurfaceTertiary} />
              </View>
            )}
            <Txt style={styles.simName} numberOfLines={1}>{it.name}</Txt>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  kicker: { fontSize: 11, letterSpacing: 2, color: colors.onSurfaceTertiary, marginBottom: 2 },
  title: { fontSize: 34 },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  dropzone: {
    borderWidth: 0.5,
    borderColor: colors.border,
    borderStyle: "dashed",
    borderRadius: radius.md,
    padding: spacing["2xl"],
    alignItems: "center",
    marginTop: spacing.lg,
  },
  dropIcon: {
    width: 64, height: 64, borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", marginBottom: spacing.lg,
  },
  dropTitle: { fontSize: 24, marginBottom: spacing.sm, textAlign: "center" },
  dropSub: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 21, marginBottom: spacing.xl },
  dropBtn: {
    backgroundColor: colors.brandPrimary,
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radius.sm,
  },
  dropBtnTxt: { color: colors.onBrandPrimary, fontSize: 15 },
  previewWrap: { borderRadius: radius.md, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  preview: { width: "100%", height: 360 },
  scanOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(26,26,26,0.5)", alignItems: "center", justifyContent: "center", gap: spacing.md },
  scanTxt: { color: colors.onSurfaceInverse, fontSize: 14 },
  changeBtn: {
    position: "absolute", top: spacing.md, right: spacing.md,
    width: 36, height: 36, borderRadius: radius.pill,
    backgroundColor: "rgba(26,26,26,0.5)", alignItems: "center", justifyContent: "center",
  },
  errorWrap: { marginTop: spacing.xl, alignItems: "center" },
  error: { color: colors.error, fontSize: 14, marginBottom: spacing.md },
  retry: { borderWidth: 0.5, borderColor: colors.borderStrong, paddingHorizontal: spacing.xl, paddingVertical: spacing.sm, borderRadius: radius.sm },
  retryTxt: { fontSize: 14, color: colors.onSurface },
  result: { marginTop: spacing.xl },
  verdictBadge: { alignSelf: "flex-start", borderWidth: 1, paddingHorizontal: spacing.lg, paddingVertical: 6, borderRadius: radius.pill },
  verdictLabel: { fontSize: 13, letterSpacing: 2 },
  itemSummary: { fontSize: 26, marginTop: spacing.md, lineHeight: 30 },
  reason: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22, marginTop: spacing.sm },
  statRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginTop: spacing.xl, paddingVertical: spacing.lg,
    borderTopWidth: 0.5, borderBottomWidth: 0.5, borderColor: colors.divider,
  },
  stat: { flex: 1, alignItems: "center", gap: 4 },
  statDivider: { width: 0.5, height: 40, backgroundColor: colors.divider },
  statNum: { fontSize: 30, color: colors.onSurface },
  statLabel: { fontSize: 11, color: colors.onSurfaceTertiary, textAlign: "center" },
  gapNote: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, backgroundColor: colors.brandTertiary, padding: spacing.lg, borderRadius: radius.sm },
  gapTxt: { flex: 1, fontSize: 13, color: colors.onBrandTertiary, lineHeight: 19 },
  section: { marginTop: spacing.xl },
  sectionTitle: { fontSize: 12, letterSpacing: 1, color: colors.onSurfaceTertiary, marginBottom: spacing.md },
  simCard: { width: 100 },
  simImg: { width: 100, height: 130, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  simPlaceholder: { alignItems: "center", justifyContent: "center" },
  simName: { fontSize: 12, color: colors.onSurface, marginTop: 6 },
  newCheckBtn: { marginTop: spacing["2xl"], borderWidth: 0.5, borderColor: colors.borderStrong, height: 50, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  newCheckTxt: { fontSize: 15, color: colors.onSurface },
});
