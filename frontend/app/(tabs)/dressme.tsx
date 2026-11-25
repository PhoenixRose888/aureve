import React, { useState, useEffect, useCallback } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Modal, TextInput } from "react-native";
import { useRouter, useFocusEffect, useLocalSearchParams } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { useWeather } from "@/src/hooks/useWeather";
import { useRotatingMessage } from "@/src/hooks/useRotatingMessage";
import * as haptics from "@/src/utils/haptics";
import GarmentImage from "@/src/components/GarmentImage";
import FlatlayItem from "@/src/components/FlatlayItem";
import AIGuidance from "@/src/components/AIGuidance";

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Shortcuts only ever fill the text box — the user's own words stay the request.
const SHORTCUTS = [
  "Office all day",
  "Working from home",
  "Dinner out",
  "Date night",
  "Job interview",
  "Errands & dog walk",
  "Wedding reception",
  "Staying home today",
];

// The one shortcut Aureve refuses to style: if you're home, so is your stylist.
const DAY_OFF = "Staying home today";

// One short, genuinely useful follow-up when the request is too broad to style.
const FOLLOWUPS: [RegExp, string][] = [
  [/^(work|office|job)$/, "What kind of work environment — relaxed, smart or formal?"],
  [/^(date|date night)$/, "What are you doing, and how dressy is it?"],
  [/^(event|party|function)$/, "What kind of event, and how dressy is it?"],
  [/^(dinner|drinks|lunch|brunch)$/, "Casual, or somewhere a bit dressier?"],
  [/^(meeting|meetings)$/, "How formal is the meeting?"],
  [/^(out|going out)$/, "Where are you going, and how dressy is it?"],
];

function weatherIcon(code?: number) {
  if (code == null) return "cloud";
  if (code === 0 || code === 1) return "sun";
  if (code === 2 || code === 3) return "cloud";
  if (code >= 51 && code <= 82) return "cloud-rain";
  if (code >= 95) return "cloud-lightning";
  return "cloud";
}

function followupFor(text: string) {
  const t = text.trim().toLowerCase().replace(/[.!?]+$/, "");
  if (t.split(/\s+/).length > 3) return "";
  for (const [re, q] of FOLLOWUPS) if (re.test(t)) return q;
  return "";
}

type Phase = "boot" | "calendar" | "ask" | "followup" | "result" | "dayoff";

export default function DressMe() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { mix, mix_outfit: mixOutfit } = useLocalSearchParams<{ mix?: string; mix_outfit?: string }>();
  const { weather, status } = useWeather();

  const [phase, setPhase] = useState<Phase>("boot");
  const [request, setRequest] = useState("");
  const [calendarLabel, setCalendarLabel] = useState("");
  const [followupQ, setFollowupQ] = useState("");
  const [followupA, setFollowupA] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  // A suggestion is only ever Suggested until the user commits to it.
  const [outcome, setOutcome] = useState<"" | "worn" | "saved">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [wardrobe, setWardrobe] = useState<any[]>([]);
  const [swapIndex, setSwapIndex] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const started = React.useRef(false);

  const localDate = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  const tzOffset = () => -new Date().getTimezoneOffset(); // minutes east of UTC
  const dayRef = React.useRef(localDate());
  const now = new Date();
  const dateLine = `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]}`;

  useEffect(() => { api<any[]>("/items").then(setWardrobe).catch(() => {}); }, []);

  const weatherBody = useCallback(() => {
    const b: any = {};
    if (weather && status === "done") {
      b.temperature = weather.temperature;
      b.weather = weather.description;
    }
    return b;
  }, [weather, status]);

  const generate = useCallback(async (occasion: string, avoid: string[] = []) => {
    setLoading(true);
    setError("");
    setOutcome("");
    try {
      const body: any = { ...weatherBody(), occasion, local_date: localDate(), tz_offset: tzOffset() };
      if (avoid.length) body.avoid_item_ids = avoid;
      const r = await api<any>("/dressme", { method: "POST", body });
      setResult(r);
      setPhase("result");
      haptics.success();
    } catch (e: any) {
      if (e.status === 402) router.push("/premium");
      else setError(e.message || "Couldn't put a look together.");
    }
    setLoading(false);
  }, [weatherBody, router]);

  const mixUp = useCallback(async (source: { wear_log_id?: string; outfit_id?: string }) => {
    setLoading(true);
    setError("");
    setOutcome("");
    try {
      const r = await api<any>("/outfits/mix", {
        method: "POST",
        body: { ...weatherBody(), ...source },
      });
      setResult(r);
      setRequest(r.occasion_used || "");
      setPhase("result");
      haptics.success();
    } catch (e: any) {
      if (e.status === 402) router.push("/premium");
      else setError(e.message || "Couldn't refresh that look.");
    }
    setLoading(false);
  }, [weatherBody, router]);

  // Boot: a Mix It Up request styles straight away; otherwise offer today's
  // calendar event, and failing that just ask what they're dressing for.
  useEffect(() => {
    if (started.current || status === "idle" || status === "loading") return;
    started.current = true;
    if (mix) {
      mixUp({ wear_log_id: String(mix) });
      return;
    }
    if (mixOutfit) {
      mixUp({ outfit_id: String(mixOutfit) });
      return;
    }
    api<any>(`/dressme/context?date=${localDate()}&tz_offset=${tzOffset()}`)
      .then((c) => {
        if (c?.has_context && c?.label) {
          setCalendarLabel(c.label);
          setPhase("calendar");
        } else setPhase("ask");
      })
      .catch(() => setPhase("ask"));
  }, [status, mix, mixOutfit, mixUp]);

  // A new styling day begins at LOCAL midnight.
  useFocusEffect(
    useCallback(() => {
      const check = () => {
        if (dayRef.current === localDate()) return;
        dayRef.current = localDate();
        started.current = false;
        setResult(null);
        setRequest("");
        setOutcome("");
        setPhase("boot");
      };
      check();
      const t = setInterval(check, 60000);
      return () => clearInterval(t);
    }, [])
  );

  const items = result?.resolved_items || [];
  const nec = (r: any) => r?.necessity || "core";
  const coreRows = items.map((r: any, i: number) => ({ r, i })).filter(({ r }: any) => nec(r) === "core");
  const extraRows = items.map((r: any, i: number) => ({ r, i })).filter(({ r }: any) => nec(r) !== "core");
  const itemIds = items.map((r: any) => r.item?.id).filter(Boolean);
  const lookName = result?.occasion_used ? `${result.occasion_used} · ${dateLine}` : `Dress Me · ${dateLine}`;

  const submitRequest = () => {
    const t = request.trim();
    if (!t) return;
    haptics.tap();
    if (t.toLowerCase() === DAY_OFF.toLowerCase()) {
      setPhase("dayoff");
      return;
    }
    const q = followupFor(t);
    if (q) {
      setFollowupQ(q);
      setFollowupA("");
      setPhase("followup");
      return;
    }
    generate(t);
  };

  const submitFollowup = (skip = false) => {
    haptics.tap();
    const base = request.trim();
    const extra = followupA.trim();
    generate(!skip && extra ? `${base} — ${extra}` : base);
  };

  const wearToday = async () => {
    if (busy || !itemIds.length) return;
    setBusy(true);
    haptics.tap();
    try {
      await api("/wear", {
        method: "POST",
        body: { item_ids: itemIds, name: lookName, occasion: result?.occasion_used || request || "", notes: result?.summary || "" },
      });
      setOutcome("worn");
      haptics.success();
    } catch {
      setError("Couldn't record that wear. Try again.");
    }
    setBusy(false);
  };

  const saveForLater = async () => {
    if (busy || !itemIds.length) return;
    setBusy(true);
    haptics.tap();
    try {
      await api("/outfits", {
        method: "POST",
        body: { name: lookName, item_ids: itemIds, occasion: result?.occasion_used || request || "", notes: result?.summary || "", source: "ai" },
      });
      setOutcome("saved");
      haptics.success();
    } catch {
      setError("Couldn't save that look. Try again.");
    }
    setBusy(false);
  };

  const anotherLook = () => {
    haptics.tap();
    generate(result?.occasion_used || request || "a normal day", itemIds);
  };

  const discard = () => {
    haptics.tap();
    setResult(null);
    setOutcome("");
    setRequest("");
    setFollowupQ("");
    setFollowupA("");
    setCalendarLabel("");
    setSwapIndex(null);
    setSearch("");
    setError("");
    setPhase("ask");
  };

  const startOver = () => {
    haptics.tap();
    setResult(null);
    setOutcome("");
    setRequest("");
    setError("");
    setPhase("ask");
  };

  const swapItem = (newItem: any) => {
    if (swapIndex == null) return;
    haptics.tap();
    setResult((r: any) => {
      const ri = [...r.resolved_items];
      ri[swapIndex] = { ...ri[swapIndex], item: newItem };
      return { ...r, resolved_items: ri };
    });
    setOutcome("");
    setSwapIndex(null);
    setSearch("");
  };

  const loadingMsg = useRotatingMessage(loading, [
    "Reading today's weather…",
    "Reviewing your wardrobe…",
    "Checking what you've worn recently…",
    "Matching colours and styles…",
    "Balancing comfort and style…",
    "Building your outfit…",
  ]);

  const swapCat = swapIndex != null ? items[swapIndex]?.item?.category : null;
  const inLook = new Set(itemIds);
  const swapOptions = wardrobe.filter(
    (w) =>
      w.category === swapCat &&
      (w.id === items[swapIndex ?? -1]?.item?.id || !inLook.has(w.id)) &&
      (!search || (w.name || "").toLowerCase().includes(search.toLowerCase()))
  );

  const showResult = phase === "result" && result && !loading;

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
        <BrandMark style={{ marginBottom: 0 }} />
        {/* Balances the back control so the mark stays centred like every other screen. */}
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
        <View style={styles.titleBlock}>
          <Txt style={styles.kicker}>YOUR DAILY EDIT</Txt>
          <Display weight="semibold" style={styles.pageTitle}>{showResult ? "Here's your look" : "Dress Me"}</Display>
          <Txt style={styles.pageSub}>
            {showResult
              ? "Styled from your wardrobe using the latest available conditions."
              : "One considered outfit \u2014 styled from what you already own."}
          </Txt>
        </View>

        <AIGuidance />

        {phase === "calendar" && !loading ? (
          <View style={styles.askCard} testID="dressme-calendar">
            <Txt style={styles.askTitle}>I see you have {calendarLabel} scheduled today.</Txt>
            <Txt style={styles.askSub}>Would you like me to dress you for it?</Txt>
            <View style={styles.yesNoRow}>
              <Pressable
                style={styles.yesBtn}
                testID="dressme-calendar-yes"
                onPress={() => { haptics.tap(); setRequest(calendarLabel); generate(calendarLabel); }}
              >
                <Txt style={styles.yesTxt}>Yes</Txt>
              </Pressable>
              <Pressable style={styles.noBtn} testID="dressme-calendar-no" onPress={() => { haptics.tap(); setPhase("ask"); }}>
                <Txt style={styles.noTxt}>No</Txt>
              </Pressable>
            </View>
          </View>
        ) : null}

        {phase === "ask" && !loading ? (
          <View style={styles.askCard} testID="dressme-ask">
            <Txt style={styles.askTitle}>What am I dressing you for?</Txt>
            <Txt style={styles.askSub}>
              Tell me where you&apos;re going, what you&apos;re doing, or anything your outfit needs to handle.
            </Txt>
            <TextInput
              style={styles.requestInput}
              value={request}
              onChangeText={setRequest}
              placeholder="e.g. Office all day, then drinks after work"
              placeholderTextColor={colors.onSurfaceTertiary}
              multiline
              testID="dressme-request-input"
            />
            <View style={styles.chipRow}>
              {SHORTCUTS.map((s) => (
                <Pressable key={s} style={styles.chip} testID={`dressme-shortcut-${s}`} onPress={() => { haptics.tap(); if (s === DAY_OFF) { setPhase("dayoff"); return; } setRequest(s); }}>
                  <Txt style={styles.chipTxt}>{s}</Txt>
                </Pressable>
              ))}
            </View>
            <Pressable
              style={[styles.primaryBtn, !request.trim() && styles.primaryDisabled]}
              onPress={submitRequest}
              disabled={!request.trim()}
              testID="dressme-request-go"
            >
              <Txt style={styles.primaryTxt}>Style me for this</Txt>
            </Pressable>
          </View>
        ) : null}

        {phase === "dayoff" ? (
          <View style={styles.askCard} testID="dressme-dayoff">
            <Txt style={styles.dayOffTxt}>Oh, you&rsquo;re having a day off?</Txt>
            <Txt style={styles.dayOffTxt}>I&rsquo;m having a day off too. ♡</Txt>
            <Pressable
              style={styles.secondaryBtn}
              testID="dressme-dayoff-back"
              onPress={() => { haptics.tap(); setRequest(""); setPhase("ask"); }}
            >
              <Txt style={styles.secondaryTxt}>Fair enough</Txt>
            </Pressable>
          </View>
        ) : null}

        {phase === "followup" && !loading ? (
          <View style={styles.askCard} testID="dressme-followup">
            <Txt style={styles.askTitle}>{followupQ}</Txt>
            <TextInput
              style={styles.requestInput}
              value={followupA}
              onChangeText={setFollowupA}
              placeholder="A few words is plenty"
              placeholderTextColor={colors.onSurfaceTertiary}
              autoFocus
              testID="dressme-followup-input"
            />
            <Pressable style={styles.primaryBtn} onPress={() => submitFollowup(false)} testID="dressme-followup-go">
              <Txt style={styles.primaryTxt}>Style me</Txt>
            </Pressable>
            <Pressable style={styles.textBtn} onPress={() => submitFollowup(true)} testID="dressme-followup-skip">
              <Txt style={styles.textBtnTxt}>Skip — just style me</Txt>
            </Pressable>
          </View>
        ) : null}

        {loading ? (
          <View style={styles.loadingWrap}>
            <ActivityIndicator size="large" color={colors.sage} />
            <Txt style={styles.loadingTxt}>{loadingMsg}</Txt>
          </View>
        ) : null}

        {error && !loading ? (
          <View style={styles.errorWrap}>
            <Feather name="cloud-off" size={30} color={colors.onSurfaceTertiary} />
            <Txt style={styles.errorTxt} testID="dressme-error">{error}</Txt>
            <Pressable style={styles.secondaryBtn} onPress={startOver} testID="dressme-error-restart">
              <Txt style={styles.secondaryTxt}>Try again</Txt>
            </Pressable>
          </View>
        ) : null}

        {showResult ? (
          <>
            <View style={styles.weatherChip}>
              <Feather name={weatherIcon(weather?.code) as any} size={14} color={colors.onSurfaceSecondary} />
              <Txt style={styles.weatherChipTxt}>
                {status === "done" && weather ? `Latest conditions · ${Math.round(weather.temperature)}°C · ${weather.description}` : "Weather unavailable"}
              </Txt>
            </View>
            {result.occasion_used ? (
              <Txt style={styles.forLine} numberOfLines={2} testID="dressme-for-line">For {result.occasion_used}</Txt>
            ) : null}

            <View style={styles.flatlay} testID="dressme-core">
              {coreRows.map(({ r, i }: any) => (
                <Pressable key={i} onPress={() => { setSwapIndex(i); setSearch(""); }} testID={`dressme-item-${i}`}>
                  <FlatlayItem photo={r.item.photo} category={r.item.category} index={i} style={styles.stackImg} iconSize={38} />
                </Pressable>
              ))}
            </View>
            <Txt style={styles.tapHint}>Tap any piece to swap just that one</Txt>

            {extraRows.length ? (
              <View style={styles.extrasWrap} testID="dressme-extras">
                <Txt style={styles.extrasLabel}>
                  {extraRows.some(({ r }: any) => nec(r) === "recommended") ? "RECOMMENDED · OPTIONAL EXTRAS" : "OPTIONAL EXTRAS"}
                </Txt>
                <View style={styles.extrasRow}>
                  {extraRows.map(({ r, i }: any) => (
                    <Pressable key={i} onPress={() => { setSwapIndex(i); setSearch(""); }} testID={`dressme-item-${i}`}>
                      <FlatlayItem photo={r.item.photo} category={r.item.category} index={i} style={styles.extraImg} iconSize={22} />
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : null}

            {result.summary ? (
              <View style={styles.explainWrap}>
                <Txt style={styles.explain}>{result.summary}</Txt>
              </View>
            ) : null}

            {items.length ? (
              <View style={styles.pieceList}>
                {(
                  [
                    ["core", "CORE OUTFIT"],
                    ["recommended", "RECOMMENDED"],
                    ["optional", "OPTIONAL"],
                  ] as const
                ).map(([group, heading]) => {
                  const rows = items.filter((r: any) => nec(r) === group);
                  if (!rows.length) return null;
                  return (
                    <View key={group} testID={`dressme-group-${group}`}>
                      <Txt style={styles.groupHeading}>{heading}</Txt>
                      {rows.map((r: any) => (
                        <View key={r.item.id} style={styles.pieceRow}>
                          <Txt style={styles.pieceSlot}>{(r.slot || r.item.category || "").toUpperCase()}</Txt>
                          <Txt style={styles.pieceName} numberOfLines={1}>{r.item.name}</Txt>
                        </View>
                      ))}
                    </View>
                  );
                })}
              </View>
            ) : null}

            {outcome ? (
              <View style={styles.doneWrap} testID={`dressme-outcome-${outcome}`}>
                <View style={styles.doneBadge}><Feather name="check" size={16} color={colors.onSage} /></View>
                <Txt style={styles.doneTxt}>
                  {outcome === "worn" ? "Recorded as worn today." : "Saved for later."}
                </Txt>
                <Pressable
                  style={styles.secondaryBtn}
                  testID="dressme-view-collection"
                  onPress={() => { haptics.tap(); router.push(outcome === "worn" ? "/worn" : "/saved"); }}
                >
                  <Txt style={styles.secondaryTxt}>{outcome === "worn" ? "View in Worn" : "View in Saved"}</Txt>
                </Pressable>
                <Pressable style={styles.textBtn} onPress={startOver} testID="dressme-restart">
                  <Txt style={styles.textBtnTxt}>Dress me for something else</Txt>
                </Pressable>
              </View>
            ) : (
              <View style={styles.actions}>
                <Pressable style={styles.primaryBtn} onPress={wearToday} disabled={busy} testID="dressme-wear-today">
                  <Feather name="check" size={17} color={colors.onSage} />
                  <Txt style={styles.primaryTxt}>Wear this today</Txt>
                </Pressable>
                <Pressable style={styles.secondaryBtn} onPress={saveForLater} disabled={busy} testID="dressme-save-later">
                  <Feather name="bookmark" size={16} color={colors.onSurface} />
                  <Txt style={styles.secondaryTxt}>Save for later</Txt>
                </Pressable>
                <Pressable style={styles.secondaryBtn} onPress={anotherLook} disabled={busy} testID="dressme-again">
                  <Feather name="refresh-cw" size={16} color={colors.onSurface} />
                  <Txt style={styles.secondaryTxt}>Create another look</Txt>
                </Pressable>
                <Pressable style={styles.textBtn} onPress={discard} disabled={busy} testID="dressme-discard">
                  <Txt style={styles.textBtnTxt}>Discard this suggestion</Txt>
                </Pressable>
                <Txt style={styles.pageSub}>Clears this suggestion and request. Your wardrobe and saved outfits stay saved.</Txt>
              </View>
            )}
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
                <Txt style={styles.pickerEmpty}>
                  No other {(swapCat || "").toLowerCase()} in your wardrobe yet — add one and it&apos;ll show up here.
                </Txt>
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
  titleBlock: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.lg },
  kicker: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium, marginBottom: spacing.xs },
  pageTitle: { fontSize: 30, letterSpacing: -0.5 },
  pageSub: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20, marginTop: spacing.xs, paddingRight: spacing.xl },
  scroll: { paddingBottom: spacing["3xl"] + 60 },
  askCard: {
    marginHorizontal: spacing.lg, padding: spacing.lg, borderRadius: radius.lg,
    backgroundColor: colors.cream, borderWidth: 0.5, borderColor: colors.border, gap: spacing.sm,
  },
  dayOffTxt: { fontSize: 19, color: colors.onSurface, fontFamily: fonts.displayMedium, lineHeight: 27, textAlign: "center" },
  askTitle: { fontSize: 19, color: colors.onSurface, fontFamily: fonts.displayMedium, lineHeight: 26 },
  askSub: { fontSize: 13.5, color: colors.onSurfaceSecondary, lineHeight: 20 },
  requestInput: {
    minHeight: 84, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingTop: spacing.md, paddingBottom: spacing.md,
    color: colors.onSurface, fontSize: 15, lineHeight: 21, backgroundColor: colors.surface,
    textAlignVertical: "top", marginTop: spacing.xs,
  },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs, marginBottom: spacing.sm },
  chip: {
    minHeight: 40, justifyContent: "center", paddingHorizontal: spacing.md,
    borderRadius: radius.pill, borderWidth: 0.5, borderColor: colors.border, backgroundColor: colors.surface,
  },
  chipTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  yesNoRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.sm },
  yesBtn: { flex: 1, height: 50, borderRadius: radius.md, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
  yesTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayBold },
  noBtn: { flex: 1, height: 50, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  noTxt: { color: colors.onSurface, fontSize: 16, fontFamily: fonts.displayBold },
  loadingWrap: { alignItems: "center", paddingTop: spacing["3xl"] * 1.5, gap: spacing.xl },
  loadingTxt: { color: colors.onSurfaceSecondary, fontSize: 15, fontStyle: "italic", textAlign: "center" },
  errorWrap: { alignItems: "center", paddingTop: spacing["2xl"], paddingHorizontal: spacing.xl, gap: spacing.lg },
  errorTxt: { color: colors.onSurfaceSecondary, fontSize: 15, textAlign: "center" },
  weatherChip: { flexDirection: "row", alignItems: "center", alignSelf: "center", gap: 6, backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: 20, marginTop: spacing.sm },
  weatherChipTxt: { fontSize: 12, color: colors.onSurfaceSecondary },
  forLine: { textAlign: "center", fontSize: 13, color: colors.onSurfaceTertiary, marginTop: spacing.sm, paddingHorizontal: spacing.xl },
  flatlay: { alignItems: "center", paddingTop: spacing.md, gap: spacing.xs },
  stackImg: { width: 230, height: 170, backgroundColor: "transparent" },
  tapHint: { textAlign: "center", fontSize: 13, color: colors.onSurfaceTertiary, marginTop: spacing.sm },
  explainWrap: { paddingHorizontal: spacing["2xl"], marginTop: spacing.xl },
  explain: { fontSize: 15, color: colors.onSurface, lineHeight: 22, textAlign: "center", fontFamily: fonts.displayMedium },
  pieceList: { marginTop: spacing.xl, marginHorizontal: spacing.xl, borderTopWidth: 0.5, borderTopColor: colors.divider },
  extrasWrap: { marginTop: spacing.lg, alignItems: "center" },
  extrasLabel: { fontSize: 10.5, letterSpacing: 1.6, color: colors.onSurfaceTertiary, marginBottom: spacing.sm },
  extrasRow: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: spacing.sm },
  extraImg: { width: 62, height: 62, borderRadius: radius.sm },
  groupHeading: { fontSize: 10.5, letterSpacing: 1.6, color: colors.onSurfaceTertiary, marginTop: spacing.md, marginBottom: spacing.xs },
  pieceRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.divider },
  pieceSlot: { fontSize: 11, letterSpacing: 1.2, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium },
  pieceName: { flex: 1, fontSize: 14, color: colors.onSurface, textAlign: "right" },
  actions: { paddingHorizontal: spacing.lg, marginTop: spacing["2xl"], gap: spacing.md },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.sage, height: 52, borderRadius: radius.md },
  primaryDisabled: { opacity: 0.45 },
  primaryTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayBold },
  secondaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 52, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  secondaryTxt: { color: colors.onSurface, fontSize: 16, fontFamily: fonts.displayBold },
  textBtn: { alignItems: "center", justifyContent: "center", minHeight: 44 },
  textBtnTxt: { color: colors.onSurfaceTertiary, fontSize: 14 },
  doneWrap: { paddingHorizontal: spacing.lg, marginTop: spacing["2xl"], gap: spacing.md, alignItems: "stretch" },
  doneBadge: { alignSelf: "center", width: 34, height: 34, borderRadius: 17, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
  doneTxt: { textAlign: "center", fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium, marginBottom: spacing.xs },
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
