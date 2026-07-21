import React, { useState } from "react";
import { View, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView } from "react-native";
import { Image } from "expo-image";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";

const OCCASION_PRESETS = ["Business trip", "Beach holiday", "City break", "Wedding away", "Family visit"];

export default function Packing() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [destination, setDestination] = useState("");
  const [days, setDays] = useState(4);
  const [startOffset, setStartOffset] = useState(0);
  const [occasions, setOccasions] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const generate = async () => {
    if (!destination.trim()) {
      setError("Where are you going?");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    setSaved(false);
    try {
      const r = await api<any>("/packing/plan", {
        method: "POST",
        body: { destination: destination.trim(), days, start_offset_days: startOffset, occasions },
      });
      setResult(r);
    } catch (e: any) {
      if (e.status === 402) router.push("/premium");
      else setError(e.message || "Couldn't build a capsule");
    }
    setLoading(false);
  };

  const saveCapsule = async () => {
    if (!result?.capsule_items?.length) return;
    try {
      await api("/outfits", {
        method: "POST",
        body: {
          name: `${result.destination} capsule`,
          item_ids: result.capsule_items.map((i: any) => i.id),
          occasion: `${result.days}-day trip`,
          source: "capsule",
        },
      });
      setSaved(true);
    } catch {}
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="packing-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Display weight="medium" style={styles.headerTitle}>Pack a trip</Display>
        <View style={{ width: 24 }} />
      </View>

      <KeyboardAwareScrollView
        style={{ flex: 1 }}
        contentContainerStyle={styles.scroll}
        bottomOffset={20}
        showsVerticalScrollIndicator={false}
      >
        <Txt style={styles.intro}>
          Tell Aureve where and how long. It builds a lean carry-on capsule from your wardrobe, matched to the
          destination forecast.
        </Txt>

        <Txt style={styles.groupLabel}>DESTINATION</Txt>
        <TextInput
          testID="destination-input"
          style={styles.input}
          value={destination}
          onChangeText={setDestination}
          placeholder="e.g. Melbourne, Australia"
          placeholderTextColor={colors.onSurfaceTertiary}
        />

        <Txt style={styles.groupLabel}>HOW MANY DAYS?</Txt>
        <View style={styles.stepper}>
          <Pressable testID="days-minus" style={styles.stepBtn} onPress={() => setDays((d) => Math.max(1, d - 1))}>
            <Feather name="minus" size={18} color={colors.onSurface} />
          </Pressable>
          <Display weight="medium" style={styles.daysNum}>{days}</Display>
          <Pressable testID="days-plus" style={styles.stepBtn} onPress={() => setDays((d) => Math.min(16, d + 1))}>
            <Feather name="plus" size={18} color={colors.onSurface} />
          </Pressable>
        </View>

        <Txt style={styles.groupLabel}>WHEN IS THE TRIP?</Txt>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.whenRow}>
          {[
            { label: "Today", v: 0 },
            { label: "In 3 days", v: 3 },
            { label: "In a week", v: 7 },
            { label: "In 2 weeks", v: 14 },
          ].map((o) => (
            <Pressable
              key={o.v}
              testID={`when-${o.v}`}
              style={[styles.whenChip, startOffset === o.v && styles.whenActive]}
              onPress={() => setStartOffset(o.v)}
            >
              <Txt style={[styles.whenTxt, startOffset === o.v && styles.whenTxtActive]}>{o.label}</Txt>
            </Pressable>
          ))}
        </ScrollView>
        <Txt style={styles.whenHint}>Forecast is checked for your actual travel dates (up to ~2 weeks ahead).</Txt>

        <Txt style={styles.groupLabel}>WHAT IS THE TRIP FOR?</Txt>
        <TextInput
          testID="occasions-input"
          style={styles.input}
          value={occasions}
          onChangeText={setOccasions}
          placeholder="Meetings + dinners, some walking…"
          placeholderTextColor={colors.onSurfaceTertiary}
        />
        <View style={styles.presetRow}>
          {OCCASION_PRESETS.map((o) => (
            <Pressable key={o} testID={`trip-${o}`} style={styles.preset} onPress={() => setOccasions(o)}>
              <Txt style={styles.presetTxt}>{o}</Txt>
            </Pressable>
          ))}
        </View>

        {error ? <Txt style={styles.error} testID="packing-error">{error}</Txt> : null}

        <Pressable style={styles.generateBtn} testID="build-capsule-button" onPress={generate} disabled={loading}>
          {loading ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <>
              <Feather name="briefcase" size={17} color={colors.onBrandPrimary} />
              <Txt style={styles.generateTxt}>Build my capsule</Txt>
            </>
          )}
        </Pressable>
        {loading && <Txt style={styles.loadingTxt}>Checking the forecast and packing light…</Txt>}

        {result && (
          <View style={styles.result} testID="packing-result">
            <Display weight="medium" style={styles.destTitle}>{result.destination}</Display>
            <Txt style={styles.tripMeta}>{result.days} days</Txt>

            <View style={styles.weatherCard}>
              <Feather name="cloud" size={16} color={colors.brand} />
              <Txt style={styles.weatherTxt}>{result.weather_note}</Txt>
            </View>

            <View style={styles.carryRow}>
              <Feather
                name={result.fits_carry_on ? "check-circle" : "alert-circle"}
                size={18}
                color={result.fits_carry_on ? colors.success : colors.warning}
              />
              <Txt style={styles.carryTxt}>
                {result.fits_carry_on ? "Fits in a carry-on" : "May need a checked bag"}
                {result.capsule_items?.length ? ` · ${result.capsule_items.length} pieces` : ""}
              </Txt>
            </View>

            {/* Capsule */}
            <Txt style={styles.sectionTitle}>YOUR CAPSULE</Txt>
            <View style={styles.capsuleGrid}>
              {result.capsule_items?.map((it: any) => (
                <Pressable key={it.id} style={styles.capItem} onPress={() => router.push(`/item/${it.id}`)}>
                  {it.photo ? (
                    <Image source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={styles.capImg} contentFit="cover" />
                  ) : (
                    <View style={[styles.capImg, styles.placeholder]}><Feather name="image" size={16} color={colors.onSurfaceTertiary} /></View>
                  )}
                  <Txt style={styles.capName} numberOfLines={1}>{it.name}</Txt>
                </Pressable>
              ))}
            </View>

            {/* Outfits */}
            {result.resolved_outfits?.length > 0 && (
              <>
                <Txt style={styles.sectionTitle}>OUTFIT COMBINATIONS</Txt>
                {result.resolved_outfits.map((o: any, i: number) => (
                  <View key={i} style={styles.outfitRow}>
                    <Txt style={styles.outfitName}>{o.name}</Txt>
                    <View style={styles.outfitThumbs}>
                      {o.items.map((it: any) => (
                        it.photo ? (
                          <Image key={it.id} source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={styles.thumb} contentFit="cover" />
                        ) : (
                          <View key={it.id} style={[styles.thumb, styles.placeholder]}><Feather name="image" size={12} color={colors.onSurfaceTertiary} /></View>
                        )
                      ))}
                    </View>
                  </View>
                ))}
              </>
            )}

            {result.essentials_missing?.length > 0 && (
              <View style={styles.missingCard}>
                <Txt style={styles.missingLabel}>WORTH PACKING (not in your wardrobe)</Txt>
                {result.essentials_missing.map((m: string, i: number) => (
                  <View key={i} style={styles.missingItem}>
                    <Feather name="plus-circle" size={13} color={colors.onSurfaceTertiary} />
                    <Txt style={styles.missingItemTxt}>{m}</Txt>
                  </View>
                ))}
              </View>
            )}

            {result.packing_tip ? (
              <View style={styles.tipCard}>
                <Feather name="zap" size={14} color={colors.brand} />
                <Txt style={styles.tipTxt}>{result.packing_tip}</Txt>
              </View>
            ) : null}

            <Pressable style={styles.saveCapsuleBtn} testID="save-capsule-button" onPress={saveCapsule} disabled={saved}>
              <Feather name={saved ? "check" : "bookmark"} size={16} color={colors.onSurface} />
              <Txt style={styles.saveCapsuleTxt}>{saved ? "Saved to your looks" : "Save this capsule"}</Txt>
            </Pressable>
          </View>
        )}
      </KeyboardAwareScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  headerTitle: { fontSize: 22 },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  intro: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21 },
  groupLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginTop: spacing.xl, marginBottom: spacing.sm },
  input: { fontFamily: fonts.body, fontSize: 16, color: colors.onSurface, borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: spacing.sm },
  stepper: { flexDirection: "row", alignItems: "center", gap: spacing.xl },
  stepBtn: { width: 44, height: 44, borderRadius: radius.pill, borderWidth: 0.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  daysNum: { fontSize: 32, minWidth: 40, textAlign: "center" },
  presetRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md },
  whenRow: { gap: spacing.sm, paddingRight: spacing.xl },
  whenChip: { height: 40, flexShrink: 0, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 0.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  whenActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  whenTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  whenTxtActive: { color: colors.onBrandPrimary },
  whenHint: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: spacing.sm },
  preset: { borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 7 },
  presetTxt: { fontSize: 12, color: colors.onSurfaceSecondary },
  error: { color: colors.error, fontSize: 13, marginTop: spacing.lg },
  generateBtn: { backgroundColor: colors.brandPrimary, height: 54, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, marginTop: spacing.xl },
  generateTxt: { color: colors.onBrandPrimary, fontSize: 16 },
  loadingTxt: { textAlign: "center", color: colors.onSurfaceTertiary, fontSize: 13, marginTop: spacing.lg, fontStyle: "italic" },
  result: { marginTop: spacing["2xl"] },
  destTitle: { fontSize: 30, lineHeight: 34 },
  tripMeta: { fontSize: 13, color: colors.onSurfaceTertiary, marginTop: 2 },
  weatherCard: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandTertiary, padding: spacing.lg, borderRadius: radius.sm, marginTop: spacing.lg, alignItems: "center" },
  weatherTxt: { flex: 1, fontSize: 13, color: colors.onBrandTertiary, lineHeight: 19 },
  carryRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.lg },
  carryTxt: { fontSize: 14, color: colors.onSurface },
  sectionTitle: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginTop: spacing.xl, marginBottom: spacing.md },
  capsuleGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  capItem: { width: "30%" },
  capImg: { width: "100%", aspectRatio: 0.8, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  placeholder: { alignItems: "center", justifyContent: "center" },
  capName: { fontSize: 11, color: colors.onSurface, marginTop: 4 },
  outfitRow: { marginBottom: spacing.lg, borderBottomWidth: 0.5, borderColor: colors.divider, paddingBottom: spacing.lg },
  outfitName: { fontSize: 15, color: colors.onSurface, marginBottom: spacing.sm },
  outfitThumbs: { flexDirection: "row", gap: spacing.sm },
  thumb: { width: 48, height: 60, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  missingCard: { marginTop: spacing.lg, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.lg },
  missingLabel: { fontSize: 10, letterSpacing: 1, color: colors.onSurfaceTertiary, marginBottom: spacing.sm },
  missingItem: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 4 },
  missingItemTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  tipCard: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, alignItems: "center" },
  tipTxt: { flex: 1, fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 19, fontStyle: "italic" },
  saveCapsuleBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 52, borderWidth: 0.5, borderColor: colors.borderStrong, borderRadius: radius.sm, marginTop: spacing.xl },
  saveCapsuleTxt: { fontSize: 15, color: colors.onSurface },
});
