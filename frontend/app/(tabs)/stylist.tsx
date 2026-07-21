import React, { useState } from "react";
import { View, StyleSheet, Pressable, TextInput, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { useWeather } from "@/src/hooks/useWeather";

const OCCASIONS = [
  "Corporate boss",
  "Date night",
  "Girls' lunch",
  "Airport / travel",
  "School pickup",
  "Wedding guest",
  "First impression",
  "Lazy Sunday",
  "Funeral",
  "Evening event",
];

export default function Stylist() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { weather, status } = useWeather();

  const [occasion, setOccasion] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  // rating
  const [showRate, setShowRate] = useState(false);
  const [flattering, setFlattering] = useState(4);
  const [comfort, setComfort] = useState(4);
  const [confidence, setConfidence] = useState(4);
  const [logged, setLogged] = useState(false);
  const [moveToLaundry, setMoveToLaundry] = useState(false);

  const generate = async () => {
    if (!occasion.trim()) {
      setError("Tell Aureve what you're dressing for.");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    setSaved(false);
    setLogged(false);
    setShowRate(false);
    try {
      const body: any = { occasion: occasion.trim(), notes };
      if (weather && status === "done") {
        body.temperature = weather.temperature;
        body.weather = weather.description;
      }
      const r = await api<any>("/stylist/suggest", { method: "POST", body });
      setResult(r);
    } catch (e: any) {
      if (e.status === 402) {
        router.push("/premium");
      } else {
        setError(e.message || "Couldn't build an outfit");
      }
    }
    setLoading(false);
  };

  const saveLook = async () => {
    if (!result?.resolved_items?.length) return;
    try {
      await api("/outfits", {
        method: "POST",
        body: {
          name: occasion || "AI look",
          item_ids: result.resolved_items.map((r: any) => r.item.id),
          occasion,
          notes: result.summary || "",
          source: "ai",
        },
      });
      setSaved(true);
    } catch {}
  };

  const logWear = async () => {
    if (!result?.resolved_items?.length) return;
    try {
      await api("/wear", {
        method: "POST",
        body: {
          item_ids: result.resolved_items.map((r: any) => r.item.id),
          occasion,
          flattering,
          comfort,
          confidence,
          mark_dirty: moveToLaundry,
        },
      });
      setLogged(true);
      setShowRate(false);
    } catch {}
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Txt style={styles.kicker}>AI STYLIST</Txt>
        <Display weight="medium" style={styles.title}>Style me</Display>
      </View>

      <KeyboardAwareScrollView
        style={{ flex: 1 }}
        contentContainerStyle={styles.scroll}
        bottomOffset={20}
        showsVerticalScrollIndicator={false}
      >
        {/* Weather chip */}
        <View style={styles.weatherRow}>
          <Feather name="map-pin" size={13} color={colors.onSurfaceTertiary} />
          <Txt style={styles.weatherTxt}>
            {status === "done" && weather
              ? `${weather.city ? weather.city + " · " : ""}${Math.round(weather.temperature)}°C, ${weather.description}`
              : status === "loading"
              ? "Fetching weather…"
              : "Styling without live weather"}
          </Txt>
        </View>

        <Txt style={styles.groupLabel}>WHAT ARE YOU DRESSING FOR?</Txt>
        <TextInput
          testID="occasion-input"
          style={styles.input}
          value={occasion}
          onChangeText={setOccasion}
          placeholder="e.g. Casual lunch, polished but not overdressed"
          placeholderTextColor={colors.onSurfaceTertiary}
        />

        <View style={styles.presetRow}>
          {OCCASIONS.map((o) => (
            <Pressable key={o} testID={`occasion-${o}`} style={styles.preset} onPress={() => setOccasion(o)}>
              <Txt style={styles.presetTxt}>{o}</Txt>
            </Pressable>
          ))}
        </View>

        <TextInput
          testID="notes-input"
          style={[styles.input, styles.inputMulti]}
          value={notes}
          onChangeText={setNotes}
          placeholder="Anything else? (some walking, want to wear the boots…)"
          placeholderTextColor={colors.onSurfaceTertiary}
          multiline
        />

        {error ? <Txt style={styles.error} testID="stylist-error">{error}</Txt> : null}

        <Pressable style={styles.generateBtn} testID="generate-outfit-button" onPress={generate} disabled={loading}>
          {loading ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <>
              <Feather name="feather" size={17} color={colors.onBrandPrimary} />
              <Txt style={styles.generateTxt}>Build my outfit</Txt>
            </>
          )}
        </Pressable>

        {loading && <Txt style={styles.loadingTxt}>Styling your look from your wardrobe…</Txt>}

        {result && (
          <View style={styles.result} testID="stylist-result">
            {typeof result.confidence_score === "number" && (
              <View style={styles.scoreCard} testID="confidence-score">
                <View style={styles.scoreTop}>
                  <View>
                    <Txt style={styles.scoreKicker}>OUTFIT CONFIDENCE</Txt>
                    <View style={styles.scoreNumRow}>
                      <Display weight="bold" style={styles.scoreNum}>{result.confidence_score}</Display>
                      <Txt style={styles.scoreOutOf}>/100</Txt>
                    </View>
                  </View>
                  <View style={styles.scoreRing}>
                    <Feather
                      name={result.confidence_score >= 85 ? "award" : result.confidence_score >= 70 ? "thumbs-up" : "check"}
                      size={22}
                      color={colors.onBrandPrimary}
                    />
                  </View>
                </View>
                {result.score_reasons?.length > 0 && (
                  <View style={styles.scoreReasons}>
                    {result.score_reasons.map((r: string, i: number) => (
                      <View key={i} style={styles.scoreReasonRow}>
                        <Feather name="check" size={13} color={colors.brandTertiary} />
                        <Txt style={styles.scoreReasonTxt}>{r}</Txt>
                      </View>
                    ))}
                  </View>
                )}
              </View>
            )}

            {result.summary ? (
              <Display weight="regular" style={styles.resultSummary}>{result.summary}</Display>
            ) : null}

            <View style={styles.collage}>
              {result.resolved_items?.map((r: any, i: number) => (
                <Pressable key={i} style={styles.collageItem} onPress={() => router.push(`/item/${r.item.id}`)}>
                  {r.item.photo ? (
                    <Image source={{ uri: `data:image/jpeg;base64,${r.item.photo}` }} style={styles.collageImg} contentFit="cover" />
                  ) : (
                    <View style={[styles.collageImg, styles.collagePlaceholder]}>
                      <Feather name="image" size={20} color={colors.onSurfaceTertiary} />
                    </View>
                  )}
                  <Txt style={styles.slot}>{r.slot}</Txt>
                  <Txt style={styles.itemName} numberOfLines={1}>{r.item.name}</Txt>
                </Pressable>
              ))}
            </View>

            {result.resolved_items?.map((r: any, i: number) =>
              r.reason ? (
                <View key={`reason-${i}`} style={styles.reasonRow}>
                  <Txt style={styles.reasonSlot}>{r.slot}</Txt>
                  <Txt style={styles.reasonTxt}>{r.reason}</Txt>
                </View>
              ) : null
            )}

            {result.styling_notes ? <DetailBlock icon="edit-3" title="Styling" text={result.styling_notes} /> : null}
            {result.hair ? <DetailBlock icon="scissors" title="Hair" text={result.hair} /> : null}
            {result.makeup ? <DetailBlock icon="droplet" title="Makeup" text={result.makeup} /> : null}
            {result.confidence_tip ? <DetailBlock icon="zap" title="Confidence" text={result.confidence_tip} /> : null}

            {/* Actions */}
            <View style={styles.actionRow}>
              <Pressable style={[styles.actionBtn, styles.actionOutline]} testID="save-look-button" onPress={saveLook} disabled={saved}>
                <Feather name={saved ? "check" : "bookmark"} size={16} color={colors.onSurface} />
                <Txt style={styles.actionTxt}>{saved ? "Saved" : "Save look"}</Txt>
              </Pressable>
              <Pressable style={[styles.actionBtn, styles.actionDark]} testID="wore-this-button" onPress={() => setShowRate((s) => !s)}>
                <Feather name="heart" size={16} color={colors.onBrandPrimary} />
                <Txt style={[styles.actionTxt, { color: colors.onBrandPrimary }]}>{logged ? "Logged ✓" : "I wore this"}</Txt>
              </Pressable>
            </View>

            {showRate && !logged && (
              <View style={styles.rateCard} testID="rate-card">
                <Txt style={styles.rateHead}>How did it feel? This teaches Aureve your style.</Txt>
                <Rating label="Flattering" value={flattering} onChange={setFlattering} />
                <Rating label="Comfort" value={comfort} onChange={setComfort} />
                <Rating label="Confidence" value={confidence} onChange={setConfidence} />
                <Pressable style={styles.laundryToggle} testID="move-laundry-toggle" onPress={() => setMoveToLaundry((v) => !v)}>
                  <Feather name={moveToLaundry ? "check-square" : "square"} size={18} color={colors.onBrandTertiary} />
                  <Txt style={styles.laundryToggleTxt}>Move these pieces to the laundry</Txt>
                </Pressable>
                <Pressable style={styles.logBtn} testID="log-wear-button" onPress={logWear}>
                  <Txt style={styles.logTxt}>Save feedback</Txt>
                </Pressable>
              </View>
            )}
          </View>
        )}
      </KeyboardAwareScrollView>
    </View>
  );
}

function DetailBlock({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <View style={styles.detailBlock}>
      <View style={styles.detailHead}>
        <Feather name={icon as any} size={14} color={colors.brand} />
        <Txt style={styles.detailTitle}>{title}</Txt>
      </View>
      <Txt style={styles.detailTxt}>{text}</Txt>
    </View>
  );
}

function Rating({ label, value, onChange }: { label: string; value: number; onChange: (n: number) => void }) {
  return (
    <View style={styles.ratingRow}>
      <Txt style={styles.ratingLabel}>{label}</Txt>
      <View style={{ flexDirection: "row", gap: 8 }}>
        {[1, 2, 3, 4, 5].map((n) => (
          <Pressable key={n} testID={`${label}-${n}`} onPress={() => onChange(n)} hitSlop={6}>
            <View style={[styles.dot, n <= value && styles.dotActive]} />
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: {
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: colors.border,
  },
  kicker: { fontSize: 11, letterSpacing: 2, color: colors.onSurfaceTertiary, marginBottom: 2 },
  title: { fontSize: 34 },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  weatherRow: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: spacing.lg },
  weatherTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  groupLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginBottom: spacing.sm },
  input: {
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.onSurface,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    paddingVertical: spacing.sm,
  },
  inputMulti: { minHeight: 54, textAlignVertical: "top", marginTop: spacing.lg },
  presetRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md },
  preset: {
    borderWidth: 0.5,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 7,
  },
  presetTxt: { fontSize: 12, color: colors.onSurfaceSecondary },
  error: { color: colors.error, fontSize: 13, marginTop: spacing.lg },
  generateBtn: {
    backgroundColor: colors.brandPrimary,
    height: 54,
    borderRadius: radius.sm,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    marginTop: spacing.xl,
  },
  generateTxt: { color: colors.onBrandPrimary, fontSize: 16 },
  loadingTxt: { textAlign: "center", color: colors.onSurfaceTertiary, fontSize: 13, marginTop: spacing.lg, fontStyle: "italic" },
  result: { marginTop: spacing["2xl"] },
  scoreCard: { backgroundColor: colors.surfaceInverse, borderRadius: radius.md, padding: spacing.xl, marginBottom: spacing.xl },
  scoreTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  scoreKicker: { fontSize: 11, letterSpacing: 2, color: colors.brandTertiary, marginBottom: spacing.xs },
  scoreNumRow: { flexDirection: "row", alignItems: "flex-end" },
  scoreNum: { fontSize: 56, lineHeight: 58, color: colors.onSurfaceInverse },
  scoreOutOf: { fontSize: 18, color: "rgba(250,250,250,0.5)", marginBottom: 8, marginLeft: 2 },
  scoreRing: { width: 52, height: 52, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brand, alignItems: "center", justifyContent: "center" },
  scoreReasons: { marginTop: spacing.lg, gap: spacing.sm },
  scoreReasonRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  scoreReasonTxt: { flex: 1, fontSize: 13, color: "rgba(250,250,250,0.85)", lineHeight: 18 },
  resultSummary: { fontSize: 22, lineHeight: 28, marginBottom: spacing.xl, color: colors.onSurface },
  collage: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  collageItem: { width: "47%" },
  collageImg: { width: "100%", aspectRatio: 0.8, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  collagePlaceholder: { alignItems: "center", justifyContent: "center" },
  slot: { fontSize: 10, letterSpacing: 1.5, color: colors.brand, marginTop: spacing.sm },
  itemName: { fontSize: 13, color: colors.onSurface },
  reasonRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.lg },
  reasonSlot: { fontSize: 11, letterSpacing: 1, color: colors.onSurfaceTertiary, width: 70, paddingTop: 2 },
  reasonTxt: { flex: 1, fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 19 },
  detailBlock: { marginTop: spacing.xl, borderTopWidth: 0.5, borderTopColor: colors.divider, paddingTop: spacing.lg },
  detailHead: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: spacing.sm },
  detailTitle: { fontSize: 12, letterSpacing: 1, color: colors.onSurface },
  detailTxt: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21 },
  actionRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing["2xl"] },
  actionBtn: {
    flex: 1,
    height: 50,
    borderRadius: radius.sm,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  actionOutline: { borderWidth: 0.5, borderColor: colors.borderStrong },
  actionDark: { backgroundColor: colors.brandPrimary },
  actionTxt: { fontSize: 14, color: colors.onSurface },
  rateCard: {
    marginTop: spacing.lg,
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
  },
  rateHead: { fontSize: 13, color: colors.onBrandTertiary, marginBottom: spacing.lg, lineHeight: 19 },
  ratingRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  ratingLabel: { fontSize: 14, color: colors.onSurface },
  dot: { width: 18, height: 18, borderRadius: 9, borderWidth: 1, borderColor: colors.brand },
  dotActive: { backgroundColor: colors.brand },
  logBtn: { backgroundColor: colors.brandPrimary, height: 46, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  logTxt: { color: colors.onBrandPrimary, fontSize: 15 },
  laundryToggle: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm, marginBottom: spacing.xs },
  laundryToggleTxt: { fontSize: 13, color: colors.onBrandTertiary },
});
