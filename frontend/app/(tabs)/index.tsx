import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { useAuth } from "@/src/context/AuthContext";
import { useWeather } from "@/src/hooks/useWeather";
import { api } from "@/src/api/client";

const HERO =
  "https://images.unsplash.com/photo-1578102718171-ec1f91680562?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1Nzl8MHwxfHNlYXJjaHwxfHxjaGljJTIwc3RyZWV0JTIwc3R5bGUlMjBvdXRmaXR8ZW58MHx8fHwxNzg0MDQ2MTUwfDA&ixlib=rb-4.1.0&q=85";

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
  const { user } = useAuth();
  const { weather, status, reload } = useWeather();
  const [recent, setRecent] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const premium = !!user?.premium;
  const trialEligible = !!user?.trial_eligible;
  const go = (path: string, premiumOnly?: boolean) =>
    premiumOnly && !premium ? router.push("/premium") : router.push(path as any);

  const loadRecent = useCallback(async () => {
    try {
      const items = await api<any[]>("/items");
      setRecent(items.slice(0, 10));
    } catch {}
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadRecent();
    }, [loadRecent])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([reload(), loadRecent()]);
    setRefreshing(false);
  };

  const firstName = user?.name?.split(" ")[0] || "there";

  return (
    <View style={styles.container}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: spacing["3xl"] }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.onSurface} />}
      >
        {/* Hero */}
        <View style={styles.hero}>
          <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" transition={250} />
          <LinearGradient
            colors={["rgba(26,26,26,0.35)", "rgba(26,26,26,0.05)", "rgba(26,26,26,0.85)"]}
            locations={[0, 0.4, 1]}
            style={StyleSheet.absoluteFill}
          />
          <View style={[styles.heroTop, { paddingTop: insets.top + spacing.md }]}>
            <Txt style={styles.brandMark}>AUREVE</Txt>
            <View style={styles.weatherPill} testID="weather-pill">
              <Feather name={weatherIcon(weather?.code) as any} size={14} color={colors.onSurfaceInverse} />
              <Txt style={styles.weatherPillTxt}>
                {status === "done" && weather
                  ? `${Math.round(weather.temperature)}°`
                  : status === "loading"
                  ? "…"
                  : "—°"}
              </Txt>
            </View>
          </View>

          <View style={styles.heroBottom}>
            <Txt style={styles.greeting}>{greeting()}, {firstName}</Txt>
            <Display weight="medium" style={styles.heroTitle}>
              What shall we{"\n"}wear today?
            </Display>
            {weather && status === "done" ? (
              <Txt style={styles.weatherLine}>
                {weather.city ? `${weather.city} · ` : ""}
                {Math.round(weather.temperature)}°C · {weather.description}
              </Txt>
            ) : status === "loading" ? null : (
              <Txt style={styles.weatherLine}>Enable location for weather-aware looks</Txt>
            )}
          </View>
        </View>

        {/* Primary CTA — flagship Dress Me */}
        <View style={styles.body}>
          <Pressable
            style={styles.dressCta}
            testID="home-dress-me-button"
            onPress={() => go("/dressme", true)}
          >
            <View style={styles.dressIcon}>
              <Feather name="sun" size={20} color={colors.onBrandTertiary} />
            </View>
            <View style={{ flex: 1 }}>
              <Txt style={styles.dressKicker}>DRESS ME</Txt>
              <Display weight="medium" style={styles.dressTitle}>My outfit for today</Display>
              <Txt style={styles.dressSub}>One tap. Weather, plans and your wardrobe — sorted.</Txt>
            </View>
            {!premium ? (
              <Feather name="lock" size={18} color="rgba(250,249,246,0.6)" />
            ) : (
              <Feather name="arrow-up-right" size={22} color={colors.onBrandPrimary} />
            )}
          </Pressable>

          <Pressable
            style={styles.styleCta}
            testID="home-style-me-button"
            onPress={() => router.push("/(tabs)/stylist")}
          >
            <View style={{ flex: 1 }}>
              <Txt style={styles.ctaKicker}>AI STYLIST</Txt>
              <Txt style={styles.ctaTitleSm}>Style me for a specific occasion</Txt>
            </View>
            <Feather name="arrow-up-right" size={20} color={colors.onSurface} />
          </Pressable>

          {/* Quick actions */}
          <View style={styles.quickRow}>
            <Pressable style={styles.quickCard} testID="home-add-item-button" onPress={() => router.push("/add-item")}>
              <Feather name="plus" size={20} color={colors.onSurface} />
              <Txt style={styles.quickTxt}>Add item</Txt>
              <Txt style={styles.quickSub}>Catalogue a piece</Txt>
            </Pressable>
            <Pressable style={styles.quickCard} testID="home-shop-check-button" onPress={() => go("/(tabs)/shop", true)}>
              <Feather name="shopping-bag" size={20} color={colors.onSurface} />
              <Txt style={styles.quickTxt}>Shop check</Txt>
              <Txt style={styles.quickSub}>Buy or skip?</Txt>
              {!premium && <View style={styles.lockDot}><Feather name="lock" size={10} color={colors.onSurfaceInverse} /></View>}
            </Pressable>
          </View>

          {!premium && (
            <Pressable style={styles.premiumBanner} testID="home-premium-banner" onPress={() => router.push("/premium")}>
              <Feather name={trialEligible ? "gift" : "award"} size={20} color={colors.brandTertiary} />
              <View style={{ flex: 1 }}>
                <Txt style={styles.premiumBannerTitle}>{trialEligible ? "Try Premium free for 7 days" : "Unlock your AI stylist"}</Txt>
                <Txt style={styles.premiumBannerSub}>{trialEligible ? "Dress Me, packing & colour analysis — on us" : "Dress Me, packing, colour analysis & more"}</Txt>
              </View>
              <Feather name="arrow-up-right" size={18} color={colors.brandTertiary} />
            </Pressable>
          )}

          {/* Pack a trip */}
          <Pressable style={styles.tripCta} testID="home-packing-button" onPress={() => go("/packing", true)}>
            <Feather name="briefcase" size={20} color={colors.onSurface} />
            <View style={{ flex: 1 }}>
              <Txt style={styles.tripTitle}>Pack for a trip</Txt>
              <Txt style={styles.tripSub}>A carry-on capsule from your wardrobe</Txt>
            </View>
            {!premium ? <Feather name="lock" size={15} color={colors.onSurfaceTertiary} /> : <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />}
          </Pressable>

          {/* My looks */}
          <Pressable style={styles.tripCta} testID="home-looks-button" onPress={() => router.push("/looks")}>
            <Feather name="bookmark" size={20} color={colors.onSurface} />
            <View style={{ flex: 1 }}>
              <Txt style={styles.tripTitle}>My looks</Txt>
              <Txt style={styles.tripSub}>Saved outfits & your wear history</Txt>
            </View>
            <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />
          </Pressable>

          {/* Plan the week */}
          <Pressable style={styles.tripCta} testID="home-planner-button" onPress={() => router.push("/planner")}>
            <Feather name="calendar" size={20} color={colors.onSurface} />
            <View style={{ flex: 1 }}>
              <Txt style={styles.tripTitle}>Plan the week</Txt>
              <Txt style={styles.tripSub}>Set outfits for the days ahead</Txt>
            </View>
            <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />
          </Pressable>

          {/* Capsule builder */}
          <Pressable style={styles.tripCta} testID="home-capsule-button" onPress={() => go("/capsule", true)}>
            <Feather name="layers" size={20} color={colors.onSurface} />
            <View style={{ flex: 1 }}>
              <Txt style={styles.tripTitle}>Build a capsule</Txt>
              <Txt style={styles.tripSub}>A season or work capsule from your closet</Txt>
            </View>
            {!premium ? <Feather name="lock" size={15} color={colors.onSurfaceTertiary} /> : <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />}
          </Pressable>

          {/* Recent items */}
          <View style={styles.sectionHead}>
            <Display weight="medium" style={styles.sectionTitle}>Recently added</Display>
            <Pressable onPress={() => router.push("/(tabs)/wardrobe")} testID="home-see-all-button">
              <Txt style={styles.seeAll}>See all</Txt>
            </Pressable>
          </View>

          {recent.length === 0 ? (
            <Pressable style={styles.emptyStrip} onPress={() => router.push("/add-item")} testID="home-empty-wardrobe">
              <Feather name="camera" size={22} color={colors.onSurfaceTertiary} />
              <Txt style={styles.emptyTxt}>Your wardrobe is empty. Add your first piece.</Txt>
            </Pressable>
          ) : (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: spacing.md, paddingRight: spacing.xl }}
            >
              {recent.map((it) => (
                <Pressable key={it.id} style={styles.recentCard} onPress={() => router.push(`/item/${it.id}`)}>
                  {it.photo ? (
                    <Image source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={styles.recentImg} contentFit="cover" />
                  ) : (
                    <View style={[styles.recentImg, styles.recentPlaceholder]}>
                      <Feather name="image" size={20} color={colors.onSurfaceTertiary} />
                    </View>
                  )}
                  <Txt style={styles.recentName} numberOfLines={1}>{it.name}</Txt>
                  <Txt style={styles.recentCat}>{it.category}</Txt>
                </Pressable>
              ))}
            </ScrollView>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  hero: { height: 420, justifyContent: "space-between" },
  heroTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.xl,
  },
  brandMark: { color: colors.onSurfaceInverse, fontFamily: fonts.body, fontSize: 14, letterSpacing: 4 },
  weatherPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(26,26,26,0.4)",
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  weatherPillTxt: { color: colors.onSurfaceInverse, fontSize: 13 },
  heroBottom: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xl },
  greeting: { color: "rgba(250,250,250,0.85)", fontSize: 13, marginBottom: spacing.xs, letterSpacing: 0.5 },
  heroTitle: { color: colors.onSurfaceInverse, fontSize: 44, lineHeight: 46 },
  weatherLine: { color: "rgba(250,250,250,0.75)", fontSize: 13, marginTop: spacing.sm },
  body: { paddingHorizontal: spacing.xl, paddingTop: spacing.xl },
  dressCta: {
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.md,
    padding: spacing.xl,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.lg,
  },
  dressIcon: { width: 46, height: 46, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  dressKicker: { color: colors.brandTertiary, fontSize: 11, letterSpacing: 2, marginBottom: 3 },
  dressTitle: { color: colors.onBrandPrimary, fontSize: 24 },
  dressSub: { color: "rgba(250,249,246,0.6)", fontSize: 12, marginTop: 3, lineHeight: 17 },
  styleCta: {
    borderWidth: 0.5,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    padding: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.md,
  },
  ctaKicker: { color: colors.onSurfaceTertiary, fontSize: 10, letterSpacing: 2, marginBottom: 3 },
  ctaTitle: { color: colors.onBrandPrimary, fontSize: 26 },
  ctaTitleSm: { color: colors.onSurface, fontSize: 16 },
  quickRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.md },
  quickCard: {
    flex: 1,
    borderWidth: 0.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: 6,
    backgroundColor: colors.surface,
  },
  quickTxt: { fontSize: 15, color: colors.onSurface, marginTop: spacing.xs },
  quickSub: { fontSize: 12, color: colors.onSurfaceTertiary },
  lockDot: { position: "absolute", top: spacing.md, right: spacing.md, width: 20, height: 20, borderRadius: 10, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  premiumBanner: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.md, backgroundColor: colors.surfaceInverse, borderRadius: radius.md, padding: spacing.lg },
  premiumBannerTitle: { fontSize: 15, color: colors.onSurfaceInverse },
  premiumBannerSub: { fontSize: 12, color: "rgba(250,250,250,0.6)", marginTop: 1 },
  tripCta: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginTop: spacing.md,
    borderWidth: 0.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
  },
  tripTitle: { fontSize: 15, color: colors.onSurface },
  tripSub: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  sectionHead: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    marginTop: spacing["2xl"],
    marginBottom: spacing.lg,
  },
  sectionTitle: { fontSize: 24, color: colors.onSurface },
  seeAll: { fontSize: 13, color: colors.brand },
  emptyStrip: {
    borderWidth: 0.5,
    borderColor: colors.border,
    borderStyle: "dashed",
    borderRadius: radius.md,
    padding: spacing.xl,
    alignItems: "center",
    gap: spacing.sm,
  },
  emptyTxt: { fontSize: 13, color: colors.onSurfaceTertiary, textAlign: "center" },
  recentCard: { width: 130 },
  recentImg: { width: 130, height: 170, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  recentPlaceholder: { alignItems: "center", justifyContent: "center" },
  recentName: { fontSize: 13, color: colors.onSurface, marginTop: spacing.sm },
  recentCat: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 1 },
});
