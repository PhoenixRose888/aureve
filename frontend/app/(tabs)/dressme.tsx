import React, { useState, useEffect, useCallback } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Modal, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { useWeather } from "@/src/hooks/useWeather";
import { useRotatingMessage } from "@/src/hooks/useRotatingMessage";
import * as haptics from "@/src/utils/haptics";
import GarmentImage from "@/src/components/GarmentImage";
import FlatlayItem from "@/src/components/FlatlayItem";

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function weatherIcon(code?: number) {
  if (code == null) return "cloud";
  if (code === 0 || code === 1) return "sun";
  if (code === 2 || code === 3) return "cloud";
  if (code >= 51 && code <= 82) return "cloud-rain";
  if (code >= 95) return "cloud-lightning";
  return "cloud";
}

export default function DressMe() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { weather, status } = useWeather();

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [wardrobe, setWardrobe] = useState<any[]>([]);
  const [swapIndex, setSwapIndex] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const started = React.useRef(false);

  const now = new Date();
  const dateLine = `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]}`;

  useEffect(() => { api<any[]>("/items").then(setWardrobe).catch(() => {}); }, []);

  const generate = useCallback(async () => {
    setLoading(true);
    setError("");
    setResult(null);
    setSaved(false);
    try {
      const body: any = {};
      if (weather && status === "done") {
        body.temperature = weather.temperature;
        body.weather = weather.description;
      }
      const r = await api<any>("/dressme", { method: "POST", body });
      setResult(r);
      haptics.success();
    } catch (e: any) {
      if (e.status === 402) router.push("/premium");
      else setError(e.message || "Couldn't put a look together.");
    }
    setLoading(false);
  }, [weather, status, router]);

  useEffect(() => {
    if (!started.current && status !== "idle" && status !== "loading") {
      started.current = true;
      generate();
    }
  }, [status, generate]);

  const items = result?.resolved_items || [];

  const saveLook = async () => {
    if (!items.length || saved) return;
    haptics.tap();
    try {
      await api("/outfits", {
        method: "POST",
        body: {
          name: "Dress Me · " + dateLine,
          item_ids: items.map((r: any) => r.item.id),
          occasion: result.occasion_used || "",
          notes: result.summary || "",
          source: "ai",
        },
      });
      setSaved(true);
      haptics.success();
    } catch {}
  };

  const swapItem = (newItem: any) => {
    if (swapIndex == null) return;
    haptics.tap();
    setResult((r: any) => {
      const ri = [...r.resolved_items];
      ri[swapIndex] = { ...ri[swapIndex], item: newItem };
      return { ...r, resolved_items: ri };
    });
    setSaved(false);
    setSwapIndex(null);
    setSearch("");
  };

  const loadingMsg = useRotatingMessage(loading, [
    "Reading today's weather…",
    "Reviewing your wardrobe…",
    "Checking what you've worn recently…",
    "Matching colours and styles…",
    "Balancing comfort and style…",
    "Building today's outfit…",
  ]);

  const swapCat = swapIndex != null ? items[swapIndex]?.item?.category : null;
  const swapOptions = wardrobe.filter(
    (w) => w.category === swapCat && (!search || (w.name || "").toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        {router.canGoBack() ? (
          <Pressable onPress={() => router.back()} testID="dressme-back" hitSlop={12}>
            <Feather name="chevron-left" size={26} color={colors.onSurface} />
          </Pressable>
        ) : (
          <View style={{ width: 26 }} />
        )}
        <Display weight="medium" style={styles.headerTitle}>{result ? "Perfect for Today" : "Dress Me"}</Display>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {loading && (
          <View style={styles.loadingWrap}>
            <ActivityIndicator size="large" color={colors.sage} />
            <Txt style={styles.loadingTxt}>{loadingMsg}</Txt>
          </View>
        )}

        {error && !loading ? (
          <View style={styles.errorWrap}>
            <Feather name="cloud-off" size={30} color={colors.onSurfaceTertiary} />
            <Txt style={styles.errorTxt} testID="dressme-error">{error}</Txt>
            <Pressable style={styles.primaryBtn} onPress={generate} testID="dressme-retry">
              <Txt style={styles.primaryTxt}>Create Another Look</Txt>
            </Pressable>
          </View>
        ) : null}

        {result && !loading ? (
          <>
            <View style={styles.weatherChip}>
              <Feather name={weatherIcon(weather?.code) as any} size={14} color={colors.onSurfaceSecondary} />
              <Txt style={styles.weatherChipTxt}>
                {status === "done" && weather ? `${Math.round(weather.temperature)}°C · ${weather.description}` : "Your wardrobe, styled"}
              </Txt>
            </View>

            <View style={styles.flatlay}>
              {items.map((r: any, i: number) => (
                <Pressable key={i} onPress={() => { setSwapIndex(i); setSearch(""); }} testID={`dressme-item-${i}`}>
                  <FlatlayItem photo={r.item.photo} category={r.item.category} index={i} style={styles.stackImg} iconSize={38} />
                </Pressable>
              ))}
            </View>
            <Txt style={styles.tapHint}>Tap any item to change</Txt>

            {result.summary ? (
              <View style={styles.explainWrap}>
                <Txt style={styles.explain}>{result.summary}</Txt>
              </View>
            ) : null}

            <View style={styles.actions}>
              <Pressable style={[styles.primaryBtn, saved && styles.primaryDone]} onPress={saveLook} disabled={saved} testID="dressme-save">
                {saved ? <Feather name="check" size={18} color={colors.onSage} /> : null}
                <Txt style={styles.primaryTxt}>{saved ? "Saved to My Outfits" : "Save to My Outfits"}</Txt>
              </Pressable>
              <Pressable style={styles.secondaryBtn} onPress={generate} testID="dressme-again">
                <Txt style={styles.secondaryTxt}>Create Another Look</Txt>
              </Pressable>
            </View>
          </>
        ) : null}
      </ScrollView>

      {/* Swap picker */}
      <Modal visible={swapIndex != null} animationType="slide" transparent onRequestClose={() => setSwapIndex(null)}>
        <View style={styles.sheetBackdrop}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={styles.sheetHead}>
              <Display weight="medium" style={styles.sheetTitle}>Change {swapCat}</Display>
              <Pressable onPress={() => setSwapIndex(null)} hitSlop={10}><Feather name="x" size={22} color={colors.onSurface} /></Pressable>
            </View>
            <View style={styles.searchBar}>
              <Feather name="search" size={16} color={colors.onSurfaceTertiary} />
              <TextInput style={styles.searchInput} placeholder="Search your wardrobe" placeholderTextColor={colors.onSurfaceTertiary} value={search} onChangeText={setSearch} />
            </View>
            <ScrollView showsVerticalScrollIndicator={false}>
              {swapOptions.length === 0 ? (
                <Txt style={styles.pickerEmpty}>No other {(swapCat || "").toLowerCase()} in your wardrobe.</Txt>
              ) : (
                <View style={styles.pickerGrid}>
                  {swapOptions.map((it) => {
                    const on = swapIndex != null && items[swapIndex]?.item?.id === it.id;
                    return (
                      <Pressable key={it.id} style={styles.pickerCell} testID={`swap-${it.id}`} onPress={() => swapItem(it)}>
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
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { fontSize: 18 },
  scroll: { paddingBottom: spacing["3xl"] },
  loadingWrap: { alignItems: "center", paddingTop: spacing["3xl"] * 2, gap: spacing.xl },
  loadingTxt: { color: colors.onSurfaceSecondary, fontSize: 15, fontStyle: "italic", textAlign: "center" },
  errorWrap: { alignItems: "center", paddingTop: spacing["3xl"] * 1.5, paddingHorizontal: spacing.xl, gap: spacing.lg },
  errorTxt: { color: colors.onSurfaceSecondary, fontSize: 15, textAlign: "center" },
  weatherChip: { flexDirection: "row", alignItems: "center", alignSelf: "center", gap: 6, backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: 20, marginTop: spacing.md },
  weatherChipTxt: { fontSize: 12, color: colors.onSurfaceSecondary },
  flatlay: { alignItems: "center", paddingTop: spacing.lg, gap: spacing.xs },
  stackImg: { width: 230, height: 170, backgroundColor: "transparent" },
  tapHint: { textAlign: "center", fontSize: 13, color: colors.onSurfaceTertiary, marginTop: spacing.sm },
  explainWrap: { paddingHorizontal: spacing["2xl"], marginTop: spacing.xl },
  explain: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 22, textAlign: "center" },
  actions: { paddingHorizontal: spacing.lg, marginTop: spacing["2xl"], gap: spacing.md },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.sage, height: 52, borderRadius: radius.md },
  primaryDone: { backgroundColor: colors.sagePressed },
  primaryTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayBold },
  secondaryBtn: { alignItems: "center", justifyContent: "center", height: 52, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  secondaryTxt: { color: colors.onSurface, fontSize: 16, fontFamily: fonts.displayBold },
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
});
