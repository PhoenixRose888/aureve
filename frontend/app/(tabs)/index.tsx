import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl, useWindowDimensions } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather, MaterialCommunityIcons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { useWeather } from "@/src/hooks/useWeather";
import { api } from "@/src/api/client";
import { useAuth } from "@/src/context/AuthContext";
import BrandMark from "@/src/components/BrandMark";
import { useProfiles } from "@/src/context/ProfileContext";
import * as haptics from "@/src/utils/haptics";
import { storage } from "@/src/utils/storage";

function weatherIcon(code?: number) {
  if (code == null) return "cloud";
  if (code === 0 || code === 1) return "sun";
  if (code === 2 || code === 3) return "cloud";
  if (code >= 45 && code <= 48) return "align-justify";
  if (code >= 51 && code <= 67) return "cloud-drizzle";
  if (code >= 71 && code <= 77) return "cloud-snow";
  if (code >= 80 && code <= 82) return "cloud-rain";
  if (code >= 95) return "cloud-lightning";
  return "cloud";
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function Home() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { weather, status, reload } = useWeather();
  const [refreshing, setRefreshing] = useState(false);
  const [wearCheck, setWearCheck] = useState<any>(null);
  const { user } = useAuth();
  const { active } = useProfiles();
  // Prefer the wardrobe/profile name, then the account name — first name only.
  const firstName = String(active?.name || user?.name || "").trim().split(/\s+/)[0] || "";

  const load = useCallback(async () => {
    // Home is a dashboard: no wardrobe or outfit imagery is fetched here.
    // Ask about YESTERDAY in the user's own local calendar day.
    try {
      const d = new Date();
      d.setDate(d.getDate() - 1);
      const localYesterday = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      const res = await api<any>(`/wear/pending?date=${localYesterday}`);
      setWearCheck(res?.pending ? res : null);
    } catch {}
  }, []);

  const answerWearCheck = useCallback(async (wore: boolean) => {
    const pending = wearCheck;
    setWearCheck(null);
    if (!pending) return;
    try {
      await api("/wear/confirm", {
        method: "POST",
        body: { date: pending.date, item_ids: pending.item_ids, wore },
      });
    } catch {}
  }, [wearCheck]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  // Brand-new accounts get the short first-run tour once.
  React.useEffect(() => {
    let cancelled = false;
    storage.getItem<boolean>("aureve_tour_pending", false).then((pending) => {
      if (pending && !cancelled) router.push("/tour");
    });
    return () => { cancelled = true; };
  }, [router]);

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([reload(), load()]);
    setRefreshing(false);
  };

  const go = (path: string) => {
    haptics.tap();
    router.push(path as any);
  };

  // Fill the space between the greeting and the tab bar without stretching:
  // the two card rows share whatever height is left, within sensible bounds.
  const { height } = useWindowDimensions();
  const chrome = insets.top + insets.bottom + 430 + (wearCheck ? 132 : 0);
  const cardHeight = Math.max(136, Math.min(196, Math.round((height - chrome) / 2)));

  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  // Four core areas — coordinated within the Aureve palette, each with its own
  // tone, a soft icon puck and a quiet one-line description.
  const actions = [
    {
      key: "wardrobe",
      label: "Wardrobe",
      hint: "Browse what you own",
      icon: <MaterialCommunityIcons name="wardrobe-outline" size={21} color={colors.onSurface} />,
      tone: colors.taupe,
      puck: colors.surface,
      tint: colors.onSurface,
      hintTint: colors.onSurfaceSecondary,
      onPress: () => go("/(tabs)/wardrobe"),
    },
    {
      key: "create",
      label: "Create Outfit",
      hint: "Build it yourself",
      icon: <MaterialCommunityIcons name="hanger" size={22} color={colors.onSurface} />,
      tone: colors.champagne,
      puck: colors.surface,
      tint: colors.onSurface,
      hintTint: colors.onSurfaceSecondary,
      onPress: () => go("/outfit-builder"),
    },
    {
      key: "dressme",
      label: "Dress Me",
      hint: "Let Aureve style you",
      icon: <Feather name="sun" size={20} color={colors.sageDeep} />,
      tone: colors.eucalyptus,
      puck: colors.surface,
      tint: colors.onSurface,
      hintTint: colors.onSurfaceSecondary,
      border: "#D6E1D7",
      onPress: () => go("/(tabs)/dressme"),
    },
    {
      key: "stylist",
      label: "AI Stylist",
      hint: "Talk it through",
      icon: <Feather name="message-circle" size={20} color="#6B5468" />,
      tone: colors.plum,
      puck: colors.surface,
      tint: colors.onSurface,
      hintTint: colors.onSurfaceSecondary,
      border: "#DDD0D8",
      onPress: () => go("/(tabs)/stylist"),
    },
  ];

  return (
    <View style={styles.container}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["2xl"] + 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.onSurface} />}
      >
        <BrandMark style={styles.brand} />

        {/* Date · weather */}
        <View style={styles.topRow}>
          <Txt style={styles.date} testID="home-date">{today}</Txt>
          <View style={styles.weatherCluster}>
            <Feather name={weatherIcon(weather?.code) as any} size={15} color={colors.onSurfaceSecondary} />
            <Txt style={styles.weatherTxt} testID="home-weather">
              {status === "done" && weather
                ? `${Math.round(weather.temperature)}°C · ${weather.description || "Now"}`
                : "—"}
            </Txt>
          </View>
        </View>

        <View style={styles.greetBlock}>
          <Display weight="semibold" style={styles.greeting}>
            {firstName ? `${greeting()}, ${firstName}` : greeting()}
          </Display>
          <Txt style={styles.suggestion}>Let&rsquo;s make the most of your wardrobe today.</Txt>
        </View>

        {user?.complimentary_active ? (
          <Pressable style={styles.compPill} testID="complimentary-pill" onPress={() => go("/premium")}>
            <Feather name="award" size={13} color={colors.goldDeep} />
            <Txt style={styles.compTxt}>
              Premium Access · {user.complimentary_days_left}{" "}
              {user.complimentary_days_left === 1 ? "day" : "days"} remaining
            </Txt>
          </Pressable>
        ) : null}

        {wearCheck ? (
          <View style={styles.wearCheck} testID="wear-checkin">
            <Txt style={styles.wearCheckTxt}>
              Quick check-in — did you wear yesterday&apos;s look
              {wearCheck.occasion ? ` for ${wearCheck.occasion}` : ""}?
            </Txt>
            <View style={styles.wearCheckBtns}>
              <Pressable style={styles.wearYes} testID="wear-checkin-yes" onPress={() => answerWearCheck(true)}>
                <Txt style={styles.wearYesTxt}>Yes</Txt>
              </Pressable>
              <Pressable style={styles.wearNo} testID="wear-checkin-no" onPress={() => answerWearCheck(false)}>
                <Txt style={styles.wearNoTxt}>No</Txt>
              </Pressable>
            </View>
          </View>
        ) : null}

        {/* Four core areas */}
        <View style={styles.grid}>
          {actions.map((a) => (
            <Pressable
              key={a.key}
              testID={`home-action-${a.key}`}
              style={({ pressed }) => [
                styles.card,
                { backgroundColor: a.tone, borderColor: a.border || colors.border, height: cardHeight },
                pressed && styles.cardPressed,
              ]}
              onPress={a.onPress}
            >
              <View style={[styles.cardPuck, { backgroundColor: a.puck }]}>{a.icon}</View>
              <View>
                <Display weight="semibold" style={[styles.cardLabel, { color: a.tint }]}>
                  {a.label}
                </Display>
                <Txt style={[styles.cardHint, { color: a.hintTint }]}>{a.hint}</Txt>
              </View>
            </Pressable>
          ))}
        </View>

        {/* My Collections */}
        <Pressable
          style={({ pressed }) => [styles.collections, pressed && styles.cardPressed]}
          testID="home-collections"
          onPress={() => go("/collections")}
        >
          <View style={styles.collectionsHead}>
            <View style={styles.collectionsPuck}>
              <Feather name="bookmark" size={17} color={colors.goldDeep} />
            </View>
            <View style={{ flex: 1 }}>
              <Display weight="semibold" style={styles.collectionsTitle}>My Collections</Display>
              <Txt style={styles.collectionsHint}>Your saved and worn looks</Txt>
            </View>
            <Feather name="chevron-right" size={18} color={colors.onSurfaceTertiary} />
          </View>
          <View style={styles.collectionsTabs}>
            <Pressable
              style={styles.collectionsTab}
              testID="home-collections-saved"
              onPress={() => go("/saved")}
            >
              <Txt style={styles.collectionsTabTxt}>Saved</Txt>
            </Pressable>
            <Pressable
              style={styles.collectionsTab}
              testID="home-collections-worn"
              onPress={() => go("/worn")}
            >
              <Txt style={styles.collectionsTabTxt}>Worn</Txt>
            </Pressable>
          </View>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  brand: { marginBottom: spacing.md },
  topRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, marginBottom: spacing.lg,
  },
  date: { fontSize: 13.5, color: colors.onSurfaceSecondary, fontFamily: fonts.displayMedium },
  weatherCluster: { flexDirection: "row", alignItems: "center", gap: 6 },
  weatherTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  greetBlock: { paddingHorizontal: spacing.lg, marginBottom: spacing.xl },
  greeting: { fontSize: 24, color: colors.onSurface },
  compPill: {
    flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start",
    marginHorizontal: spacing.lg, marginBottom: spacing.md, paddingHorizontal: spacing.md,
    paddingVertical: 7, borderRadius: radius.pill, backgroundColor: colors.cream,
    borderWidth: 0.5, borderColor: colors.goldSoft,
  },
  compTxt: { fontSize: 12, color: colors.onSurface },
  suggestion: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: 4, lineHeight: 20 },
  wearCheck: {
    marginHorizontal: spacing.lg, marginBottom: spacing.lg, padding: spacing.lg,
    borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, gap: spacing.md,
  },
  wearCheckTxt: { fontSize: 14, color: colors.onSurface, lineHeight: 20 },
  wearCheckBtns: { flexDirection: "row", gap: spacing.sm },
  wearYes: { flex: 1, height: 40, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  wearYesTxt: { color: colors.onBrandPrimary, fontSize: 14 },
  wearNo: { flex: 1, height: 40, borderRadius: radius.sm, borderWidth: 0.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  wearNoTxt: { color: colors.onSurface, fontSize: 14 },
  grid: {
    flexDirection: "row", flexWrap: "wrap", gap: spacing.md,
    paddingHorizontal: spacing.lg,
  },
  card: {
    width: "47.6%", flexGrow: 1, borderRadius: radius.lg,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.lg,
    justifyContent: "space-between", borderWidth: 0.5,
    shadowColor: "#232323", shadowOpacity: 0.05, shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 }, elevation: 1,
  },
  cardPressed: { opacity: 0.92, transform: [{ scale: 0.99 }] },
  cardPuck: {
    width: 40, height: 40, borderRadius: 20,
    alignItems: "center", justifyContent: "center",
  },
  cardLabel: { fontSize: 16.5, letterSpacing: -0.2 },
  cardHint: { fontSize: 11.5, marginTop: 3, lineHeight: 16 },
  collections: {
    marginHorizontal: spacing.lg, marginTop: spacing.lg, padding: spacing.lg,
    borderRadius: radius.lg, backgroundColor: colors.cream, gap: spacing.lg,
    borderWidth: 0.75, borderColor: "#E4D7BC",
    shadowColor: "#232323", shadowOpacity: 0.07, shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 }, elevation: 2,
  },
  collectionsHead: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  collectionsPuck: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface,
    alignItems: "center", justifyContent: "center",
    borderWidth: 0.5, borderColor: "#E4D7BC",
  },
  collectionsTitle: { fontSize: 16.5, color: colors.onSurface, letterSpacing: -0.2 },
  collectionsHint: { fontSize: 11.5, color: colors.onSurfaceSecondary, marginTop: 3 },
  collectionsTabs: { flexDirection: "row", gap: spacing.sm },
  collectionsTab: {
    flex: 1, height: 42, borderRadius: radius.pill, borderWidth: 0.5,
    borderColor: "#E4D7BC", backgroundColor: colors.surface,
    alignItems: "center", justifyContent: "center",
  },
  collectionsTabTxt: { fontSize: 13.5, color: colors.onSurface, fontFamily: fonts.displayMedium, letterSpacing: 0.3 },
});
