import React, { useState, useCallback } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";
import { useWeather } from "@/src/hooks/useWeather";

const OCCASIONS = ["Everyday", "Work", "Evening", "Wedding", "Date", "Interview"];
const NECKLINES = ["Not sure", "High / crew", "V-neck", "Strapless", "Collared", "Halter", "Scoop"];
const LENGTHS = ["Not sure", "Short", "Mid-length", "Long"];
const TYPES = ["Not sure", "Straight", "Wavy", "Curly", "Coily"];

export default function Hair() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { weather, status } = useWeather();
  const [occasion, setOccasion] = useState("Everyday");
  const [neckline, setNeckline] = useState("Not sure");
  const [length, setLength] = useState("Not sure");
  const [hairType, setHairType] = useState("Not sure");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");

  const generate = useCallback(async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const body: any = { occasion };
      if (neckline !== "Not sure") body.neckline = neckline;
      if (length !== "Not sure") body.hair_length = length;
      if (hairType !== "Not sure") body.hair_type = hairType;
      if (weather && status === "done") {
        body.temperature = weather.temperature;
        body.weather = weather.description;
      }
      setResult(await api<any>("/beauty/suggest", { method: "POST", body }));
    } catch (e: any) {
      if (e.status === 402) {
        router.push("/premium");
        setLoading(false);
        return;
      }
      setError(e.message || "Couldn't generate hairstyles");
    }
    setLoading(false);
  }, [occasion, neckline, length, hairType, weather, status, router]);

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="beauty-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt style={styles.headerKicker}>HAIR</Txt>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Display weight="semibold" style={styles.title}>How to wear your hair</Display>
        <Txt style={styles.sub}>
          Hairstyles chosen for the occasion, your outfit&apos;s neckline and the weather.
        </Txt>

        <Chips label="OCCASION" options={OCCASIONS} value={occasion} onChange={setOccasion} testPrefix="beauty-occasion" />
        <Chips label="OUTFIT NECKLINE" options={NECKLINES} value={neckline} onChange={setNeckline} testPrefix="hair-neckline" />
        <Chips label="HAIR LENGTH" options={LENGTHS} value={length} onChange={setLength} testPrefix="hair-length" />
        <Chips label="HAIR TYPE" options={TYPES} value={hairType} onChange={setHairType} testPrefix="hair-type" />

        <Pressable style={styles.genBtn} testID="beauty-generate" onPress={generate} disabled={loading}>
          {loading ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <Txt style={styles.genTxt}>{result ? "Try other styles" : "Get my hairstyles"}</Txt>
          )}
        </Pressable>

        {loading && (
          <View style={styles.center}>
            <Txt style={styles.loadingTxt}>Working out what suits…</Txt>
          </View>
        )}

        {error && !loading ? (
          <View style={styles.errorBox}>
            <Txt style={styles.errorTxt} testID="beauty-error">{error}</Txt>
          </View>
        ) : null}

        {result && !loading ? (
          <View testID="beauty-result">
            {result.summary ? <Txt style={styles.summary}>{result.summary}</Txt> : null}

            {(result.styles || []).map((st: any, i: number) => (
              <View key={i} style={styles.styleCard}>
                <Txt style={styles.styleName}>{st.name}</Txt>
                {st.why ? <Txt style={styles.styleWhy}>{st.why}</Txt> : null}
                {st.how ? <Txt style={styles.styleHow}>{st.how}</Txt> : null}
              </View>
            ))}

            {result.tip ? (
              <View style={styles.tipRow}>
                <Feather name="info" size={13} color={colors.onSurfaceTertiary} />
                <Txt style={styles.tipTxt}>{result.tip}</Txt>
              </View>
            ) : null}

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

function Chips({
  label,
  options,
  value,
  onChange,
  testPrefix,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
  testPrefix: string;
}) {
  return (
    <>
      <Txt style={styles.groupLabel}>{label}</Txt>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipContent}>
        {options.map((o) => (
          <Pressable
            key={o}
            testID={`${testPrefix}-${o}`}
            style={[styles.chip, value === o && styles.chipActive]}
            onPress={() => onChange(o)}
          >
            <Txt style={[styles.chipTxt, value === o && styles.chipTxtActive]}>{o}</Txt>
          </Pressable>
        ))}
      </ScrollView>
    </>
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
  summary: { fontSize: 18, color: colors.onSurface, lineHeight: 26, marginTop: spacing.xl, fontStyle: "italic" },
  styleCard: {
    marginTop: spacing.lg, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.lg, gap: 4,
  },
  styleName: { fontSize: 16, color: colors.onSurface },
  styleWhy: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  styleHow: { fontSize: 13, color: colors.onSurfaceTertiary, lineHeight: 19 },
  tipRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", marginTop: spacing.lg },
  tipTxt: { flex: 1, fontSize: 13, color: colors.onSurfaceTertiary, lineHeight: 19, fontStyle: "italic" },
  noteCard: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start", backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginTop: spacing["2xl"] },
  noteTxt: { flex: 1, fontSize: 14, color: colors.onBrandTertiary, lineHeight: 21 },
});
