import React, { useState, useEffect, useCallback } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";
import { useWeather } from "@/src/hooks/useWeather";
import { useRotatingMessage } from "@/src/hooks/useRotatingMessage";
import * as haptics from "@/src/utils/haptics";

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function DressMe() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { weather, status } = useWeather();

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [logged, setLogged] = useState(false);
  const [cal, setCal] = useState<{ connected: boolean; events: any[] }>({ connected: false, events: [] });
  const started = React.useRef(false);

  const now = new Date();
  const dateLine = `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]}`;

  const loadCal = useCallback(async () => {
    try {
      const s = await api<any>("/calendar/status");
      if (s.connected) {
        const e = await api<any>("/calendar/events");
        setCal({ connected: true, events: e.events || [] });
      } else {
        setCal({ connected: false, events: [] });
      }
    } catch {}
  }, []);

  useEffect(() => { loadCal(); }, [loadCal]);

  const connectCal = useCallback(async () => {
    try {
      const { url } = await api<any>("/calendar/authorize");
      await WebBrowser.openBrowserAsync(url);
      await loadCal();
      started.current = false;
      generateRef.current?.();
    } catch {}
  }, [loadCal]);

  const generateRef = React.useRef<null | (() => void)>(null);

  const generate = useCallback(async () => {
    setLoading(true);
    setError("");
    setResult(null);
    setSaved(false);
    setLogged(false);
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

  generateRef.current = generate;

  // Auto-run once weather has settled (done/denied/error), so the outfit is weather-aware.
  useEffect(() => {
    if (!started.current && status !== "idle" && status !== "loading") {
      started.current = true;
      generate();
    }
  }, [status, generate]);

  const saveLook = async () => {
    if (!result?.resolved_items?.length) return;
    try {
      await api("/outfits", {
        method: "POST",
        body: {
          name: "Dress Me · " + dateLine,
          item_ids: result.resolved_items.map((r: any) => r.item.id),
          occasion: result.occasion_used || "",
          notes: result.summary || "",
          source: "ai",
        },
      });
      setSaved(true);
    } catch {}
  };

  const wearThis = async () => {
    if (!result?.resolved_items?.length) return;
    try {
      await api("/wear", {
        method: "POST",
        body: {
          item_ids: result.resolved_items.map((r: any) => r.item.id),
          occasion: result.occasion_used || "",
          flattering: 4,
          comfort: 4,
          confidence: 4,
        },
      });
      setLogged(true);
    } catch {}
  };

  const tempStr =
    status === "done" && weather ? `${Math.round(weather.temperature)}°C · ${weather.description}` : "Styling without live weather";
  const cityStr = status === "done" && weather?.city ? weather.city : null;

  const loadingMsg = useRotatingMessage(loading, [
    "Reading today's weather…",
    "Checking your schedule…",
    "Pulling from your wardrobe…",
    "Pairing pieces that flatter you…",
    "Adding the finishing touches…",
  ]);

  const saveLookH = () => { haptics.tap(); saveLook(); };
  const wearThisH = () => { haptics.success(); wearThis(); };
  const generateH = () => { haptics.tap(); generate(); };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="dressme-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurfaceInverse} />
        </Pressable>
        <Txt style={styles.kicker}>DRESS ME</Txt>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.today}>
          <Txt style={styles.todayDate}>{dateLine}</Txt>
          <View style={styles.weatherRow}>
            <Feather name="cloud" size={15} color="rgba(250,249,246,0.7)" />
            <Txt style={styles.weatherTxt}>{tempStr}{cityStr ? ` · ${cityStr}` : ""}</Txt>
          </View>
          {result?.occasion_used ? (
            <Txt style={styles.occasionTxt}>
              For {result.from_plan ? `"${result.from_plan}"` : result.occasion_used}
            </Txt>
          ) : null}
        </View>

        {cal.connected && cal.events.length > 0 ? (
          <View style={styles.calBlock}>
            <Txt style={styles.calHead}>TODAY&apos;S SCHEDULE</Txt>
            {cal.events.slice(0, 4).map((e, i) => (
              <View key={i} style={styles.calRow}>
                <Txt style={styles.calTime}>
                  {e.all_day || !e.start ? "All day" : new Date(e.start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </Txt>
                <Txt style={styles.calEvent} numberOfLines={1}>{e.summary}</Txt>
              </View>
            ))}
          </View>
        ) : !cal.connected ? (
          <Pressable style={styles.calConnect} testID="dressme-connect-calendar" onPress={connectCal}>
            <Feather name="calendar" size={15} color={colors.brandTertiary} />
            <Txt style={styles.calConnectTxt}>Connect Google Calendar — dress for your actual day</Txt>
          </Pressable>
        ) : null}

        {loading && (
          <View style={styles.loadingWrap}>
            <ActivityIndicator color={colors.brandTertiary} size="large" />
            <Txt style={styles.loadingTxt}>{loadingMsg}</Txt>
            <View style={styles.skeletonGrid}>
              {[0, 1, 2, 3].map((i) => (
                <View key={i} style={styles.skeletonCell} />
              ))}
            </View>
          </View>
        )}

        {error && !loading ? (
          <View style={styles.errorWrap}>
            <Txt style={styles.errorTxt} testID="dressme-error">{error}</Txt>
            <Pressable style={styles.retry} onPress={generateH} testID="dressme-retry">
              <Txt style={styles.retryTxt}>Try again</Txt>
            </Pressable>
          </View>
        ) : null}

        {result && !loading ? (
          <View testID="dressme-result">
            {typeof result.confidence_score === "number" && (
              <View style={styles.scoreRow}>
                <Display weight="bold" style={styles.scoreNum}>{result.confidence_score}</Display>
                <Txt style={styles.scoreOutOf}>/100 confidence</Txt>
              </View>
            )}
            {result.summary ? <Display weight="medium" style={styles.summary}>{result.summary}</Display> : null}

            <View style={styles.collage}>
              {result.resolved_items?.map((r: any, i: number) => (
                <Pressable key={i} style={styles.collageItem} onPress={() => router.push(`/item/${r.item.id}`)}>
                  {r.item.photo ? (
                    <Image source={{ uri: `data:image/jpeg;base64,${r.item.photo}` }} style={styles.collageImg} contentFit="cover" />
                  ) : (
                    <View style={[styles.collageImg, styles.placeholder]}>
                      <Feather name="image" size={20} color={colors.onSurfaceTertiary} />
                    </View>
                  )}
                  <Txt style={styles.slot}>{r.slot}</Txt>
                  <Txt style={styles.itemName} numberOfLines={1}>{r.item.name}</Txt>
                </Pressable>
              ))}
            </View>

            {result.styling_notes ? (
              <View style={styles.noteBlock}>
                <Feather name="edit-3" size={14} color={colors.brandTertiary} />
                <Txt style={styles.noteTxt}>{result.styling_notes}</Txt>
              </View>
            ) : null}

            <View style={styles.actions}>
              <Pressable style={[styles.actBtn, styles.actGhost]} testID="dressme-save" onPress={saveLookH} disabled={saved}>
                <Feather name={saved ? "check" : "bookmark"} size={16} color={colors.onSurfaceInverse} />
                <Txt style={styles.actGhostTxt}>{saved ? "Saved" : "Save"}</Txt>
              </Pressable>
              <Pressable style={[styles.actBtn, styles.actGhost]} testID="dressme-retry-2" onPress={generateH}>
                <Feather name="refresh-cw" size={16} color={colors.onSurfaceInverse} />
                <Txt style={styles.actGhostTxt}>Try another</Txt>
              </Pressable>
            </View>
            <Pressable style={styles.wearBtn} testID="dressme-wear" onPress={wearThisH} disabled={logged}>
              <Feather name={logged ? "check" : "heart"} size={17} color={colors.onBrandTertiary} />
              <Txt style={styles.wearTxt}>{logged ? "Logged for today" : "Wear this today"}</Txt>
            </Pressable>
            <Pressable
              style={styles.seeOnMe}
              testID="dressme-tryon"
              onPress={() =>
                router.push({
                  pathname: "/tryon",
                  params: { items: result.resolved_items.map((r: any) => r.item.id).join(",") },
                })
              }
            >
              <Feather name="user" size={16} color={colors.onSurfaceInverse} />
              <Txt style={styles.seeOnMeTxt}>See it on me</Txt>
            </Pressable>
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
  kicker: { fontSize: 11, letterSpacing: 3, color: colors.brandTertiary },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  today: { marginBottom: spacing.xl },
  todayDate: { fontSize: 15, color: colors.onSurfaceInverse },
  weatherRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.xs },
  weatherTxt: { fontSize: 13, color: "rgba(250,249,246,0.7)" },
  occasionTxt: { fontSize: 13, color: colors.brandTertiary, marginTop: spacing.sm },
  calBlock: { borderWidth: 0.5, borderColor: "rgba(250,249,246,0.15)", borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.xl },
  calHead: { fontSize: 10, letterSpacing: 1.5, color: "rgba(250,249,246,0.5)", marginBottom: spacing.sm },
  calRow: { flexDirection: "row", gap: spacing.md, paddingVertical: 3 },
  calTime: { fontSize: 13, color: colors.brandTertiary, width: 66 },
  calEvent: { flex: 1, fontSize: 13, color: colors.onSurfaceInverse },
  calConnect: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderWidth: 0.5, borderColor: "rgba(250,249,246,0.2)", borderRadius: radius.sm, padding: spacing.md, marginBottom: spacing.xl },
  calConnectTxt: { flex: 1, fontSize: 13, color: "rgba(250,249,246,0.85)" },
  loadingWrap: { alignItems: "center", paddingVertical: spacing["2xl"], gap: spacing.lg },
  loadingTxt: { color: "rgba(250,249,246,0.7)", fontSize: 14, fontStyle: "italic", textAlign: "center" },
  skeletonGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, width: "100%", marginTop: spacing.md },
  skeletonCell: { width: "47%", aspectRatio: 0.8, borderRadius: radius.sm, backgroundColor: "rgba(250,249,246,0.06)" },
  errorWrap: { alignItems: "center", paddingVertical: spacing["2xl"], gap: spacing.lg },
  errorTxt: { color: "rgba(250,249,246,0.8)", fontSize: 14, textAlign: "center" },
  retry: { borderWidth: 0.5, borderColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.xl, height: 46, alignItems: "center", justifyContent: "center" },
  retryTxt: { color: colors.brandTertiary, fontSize: 15 },
  scoreRow: { flexDirection: "row", alignItems: "flex-end", gap: 6, marginBottom: spacing.md },
  scoreNum: { fontSize: 44, lineHeight: 46, color: colors.onSurfaceInverse },
  scoreOutOf: { fontSize: 14, color: "rgba(250,249,246,0.5)", marginBottom: 8 },
  summary: { fontSize: 24, lineHeight: 30, color: colors.onSurfaceInverse, marginBottom: spacing.xl },
  collage: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  collageItem: { width: "47%" },
  collageImg: { width: "100%", aspectRatio: 0.8, borderRadius: radius.sm, backgroundColor: "rgba(250,249,246,0.08)" },
  placeholder: { alignItems: "center", justifyContent: "center" },
  slot: { fontSize: 10, letterSpacing: 1.5, color: colors.brandTertiary, marginTop: spacing.sm },
  itemName: { fontSize: 13, color: colors.onSurfaceInverse },
  noteBlock: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start", marginTop: spacing.xl, borderTopWidth: 0.5, borderTopColor: "rgba(250,249,246,0.15)", paddingTop: spacing.lg },
  noteTxt: { flex: 1, fontSize: 14, color: "rgba(250,249,246,0.85)", lineHeight: 21 },
  actions: { flexDirection: "row", gap: spacing.md, marginTop: spacing["2xl"] },
  actBtn: { flex: 1, height: 50, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  actGhost: { borderWidth: 0.5, borderColor: "rgba(250,249,246,0.3)" },
  actGhostTxt: { color: colors.onSurfaceInverse, fontSize: 14 },
  wearBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 54, borderRadius: radius.sm, backgroundColor: colors.brandTertiary, marginTop: spacing.md },
  wearTxt: { color: colors.onBrandTertiary, fontSize: 16 },
  seeOnMe: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 50, borderRadius: radius.sm, borderWidth: 0.5, borderColor: "rgba(250,249,246,0.3)", marginTop: spacing.md },
  seeOnMeTxt: { color: colors.onSurfaceInverse, fontSize: 15 },
});
