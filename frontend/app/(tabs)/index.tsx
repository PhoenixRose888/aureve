import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl, Image } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather, MaterialCommunityIcons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { useWeather } from "@/src/hooks/useWeather";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";
import * as haptics from "@/src/utils/haptics";

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

// Concise AI styling recommendation — advice only, no weather data repeated
// (temperature/condition/city already live in the top-left weather cluster).
function stylingRecommendation(w: any): string {
  const t = Math.round(w.temperature);
  const c = w.code ?? 3;
  if (c >= 95) return "Stormy today — a waterproof layer is a smart call.";
  if (c >= 71 && c <= 77) return "Snow on the way — layer up and keep it cosy.";
  if (c >= 51 && c <= 82) return "Rain likely — a jacket and closed shoes are ideal.";
  if (t <= 6) return "Bundle up — a warm coat will serve you well today.";
  if (t <= 14) return "A light layer will feel just right today.";
  if (t <= 22) return "Perfect weather for effortless smart-casual layering.";
  if (t <= 28) return "Keep it light and breathable today.";
  return "A hot one — reach for airy, breathable pieces.";
}

function timeAgo(iso?: string) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const day = 86400000;
  if (diff < day) return "Today";
  if (diff < 2 * day) return "Yesterday";
  const days = Math.floor(diff / day);
  if (days < 7) return `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks} week${weeks > 1 ? "s" : ""} ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function Home() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { weather, status, reload } = useWeather();
  const [outfits, setOutfits] = useState<any[]>([]);
  const [itemCount, setItemCount] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [growDismissed, setGrowDismissed] = useState(false);

  const load = useCallback(async () => {
    try {
      const [o, items] = await Promise.all([api<any[]>("/outfits"), api<any[]>("/items")]);
      setOutfits(Array.isArray(o) ? o.slice(0, 8) : []);
      setItemCount(Array.isArray(items) ? items.length : 0);
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([reload(), load()]);
    setRefreshing(false);
  };

  const openDressMe = () => {
    haptics.tap();
    router.push("/(tabs)/dressme");
  };

  const quickActions = [
    { key: "add", label: "Add Item", icon: <Feather name="camera" size={22} color={colors.onSurface} />, onPress: () => router.push("/add-item") },
    { key: "create", label: "Create Outfit", icon: <MaterialCommunityIcons name="hanger" size={24} color={colors.onSurface} />, onPress: () => router.push("/outfit-builder") },
    { key: "stylist", label: "AI Stylist", icon: <Feather name="star" size={22} color={colors.onSurface} />, onPress: () => router.push("/(tabs)/stylist") },
    { key: "collections", label: "My Collections", icon: <Feather name="folder" size={22} color={colors.onSurface} />, onPress: () => router.push("/collections") },
  ];

  const showGrowing = itemCount > 0 && !growDismissed;

  return (
    <View style={styles.container}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingTop: insets.top + spacing.sm, paddingBottom: spacing["3xl"] + 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.onSurface} />}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.weatherCluster}>
            <Feather name={weatherIcon(weather?.code) as any} size={26} color={colors.onSurfaceSecondary} />
            <View style={{ marginLeft: spacing.sm }}>
              <Txt style={styles.temp}>
                {status === "done" && weather ? `${Math.round(weather.temperature)}°C` : status === "loading" ? "—" : "—"}
              </Txt>
              <Txt style={styles.weatherDesc}>{weather?.description || "Weather"}</Txt>
            </View>
          </View>
          <Image source={require("@/assets/images/aureve-mark.png")} style={styles.brandMark} resizeMode="contain" />
          <Pressable hitSlop={10} testID="home-bell" onPress={() => router.push("/(tabs)/profile")}>
            <Feather name="bell" size={22} color={colors.onSurface} />
          </Pressable>
        </View>

        <View style={styles.greetBlock}>
          <Display weight="semibold" style={styles.greeting}>{greeting()}</Display>
          {status === "done" && weather ? (
            <Txt style={styles.suggestion} testID="home-weather-suggestion">{stylingRecommendation(weather)}</Txt>
          ) : status === "loading" ? (
            <Txt style={styles.suggestion}>Preparing today&rsquo;s styling tip.</Txt>
          ) : (
            <Txt style={styles.suggestion}>Let&rsquo;s make the most of your wardrobe today.</Txt>
          )}
        </View>

        {/* Wardrobe growing banner */}
        {showGrowing && (
          <View style={styles.growBanner} testID="home-growing-banner">
            <Feather name="star" size={18} color={colors.onBrandTertiary} />
            <View style={{ flex: 1 }}>
              <Txt style={styles.growTitle}>Your wardrobe is growing!</Txt>
              <Txt style={styles.growSub}>You now have {itemCount} item{itemCount === 1 ? "" : "s"} ready to style.</Txt>
            </View>
            <Pressable hitSlop={8} onPress={() => setGrowDismissed(true)} testID="home-growing-dismiss">
              <Feather name="x" size={18} color={colors.onSurfaceTertiary} />
            </Pressable>
          </View>
        )}

        {/* Hero: Dress Me */}
        <Pressable style={styles.dressBtn} testID="home-dress-me-button" onPress={openDressMe}>
          <Display weight="bold" style={styles.dressTxt}>Dress Me</Display>
          <View style={styles.dressArrow}>
            <Feather name="arrow-right" size={20} color={colors.onSage} />
          </View>
        </Pressable>

        {/* Recent Outfits */}
        <View style={styles.sectionHead}>
          <Txt style={styles.sectionTitle}>Recent Outfits</Txt>
          {outfits.length > 0 && (
            <Pressable hitSlop={8} onPress={() => router.push("/(tabs)/outfits")} testID="home-see-all">
              <Txt style={styles.seeAll}>See all recent</Txt>
            </Pressable>
          )}
        </View>

        {outfits.length === 0 ? (
          <View style={styles.emptyWrap} testID="home-outfits-empty">
            <View style={styles.ghostRow}>
              <Pressable style={[styles.ghostCard, styles.ghostCreate]} onPress={openDressMe} testID="home-empty-create">
                <View style={styles.ghostPlus}><Feather name="plus" size={18} color={colors.onSage} /></View>
                <Txt style={styles.ghostCreateTxt}>Create a look</Txt>
              </Pressable>
              <View style={styles.ghostCard}><MaterialCommunityIcons name="hanger" size={24} color={colors.onSurfaceTertiary} /></View>
              <View style={styles.ghostCard}><MaterialCommunityIcons name="tshirt-crew-outline" size={24} color={colors.onSurfaceTertiary} /></View>
            </View>
            <Txt style={styles.emptyCopy}>Your styled looks will appear here.</Txt>
          </View>
        ) : (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.recentRow}>
            {outfits.map((o) => (
              <Pressable key={o.id} style={styles.recentCard} testID={`home-outfit-${o.id}`} onPress={() => router.push(`/outfit/${o.id}`)}>
                <View style={styles.recentCollage}>
                  {o.preview_image ? (
                    <GarmentImage photo={o.preview_image} category="" mime="png" style={styles.recentFull} contentFit="contain" iconSize={24} />
                  ) : (
                    <View style={styles.recentGrid}>
                      {(o.items || []).slice(0, 4).map((it: any, i: number) => (
                        <GarmentImage key={i} photo={it.photo} category={it.category} style={styles.recentCell} iconSize={14} />
                      ))}
                      {(o.items || []).length === 0 && <View style={styles.recentCell}><Feather name="layers" size={16} color={colors.onSurfaceTertiary} /></View>}
                    </View>
                  )}
                </View>
                <Txt style={styles.recentName} numberOfLines={1}>{o.name || "Outfit"}</Txt>
                <Txt style={styles.recentTime}>{timeAgo(o.created_at)}</Txt>
              </Pressable>
            ))}
          </ScrollView>
        )}

        {/* Quick Actions */}
        <Txt style={[styles.sectionTitle, { paddingHorizontal: spacing.lg, marginTop: spacing["2xl"], marginBottom: spacing.md }]}>Quick Actions</Txt>
        <View style={styles.quickGrid}>
          {quickActions.map((qa) => (
            <Pressable key={qa.key} style={styles.quickCard} testID={`home-qa-${qa.key}`} onPress={() => { haptics.tap(); qa.onPress(); }}>
              <View style={styles.qaIcon}>{qa.icon}</View>
              <Txt style={styles.quickLabel}>{qa.label}</Txt>
            </Pressable>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  weatherCluster: { flexDirection: "row", alignItems: "center" },
  brandMark: { width: 38, height: 28, opacity: 0.9 },
  temp: { fontSize: 18, color: colors.onSurface, fontFamily: fonts.displayMedium },
  weatherDesc: { fontSize: 12, color: colors.onSurfaceTertiary },
  greetBlock: { paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  greeting: { fontSize: 22, color: colors.onSurface },
  suggestion: { fontSize: 13.5, color: colors.onSurfaceSecondary, marginTop: 3, lineHeight: 19 },
  growBanner: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, marginHorizontal: spacing.lg, marginBottom: spacing.md },
  growTitle: { fontSize: 14, color: colors.onBrandTertiary, fontFamily: fonts.displayMedium },
  growSub: { fontSize: 12, color: colors.onBrandTertiary, opacity: 0.85, marginTop: 1 },
  dressBtn: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.sage, marginHorizontal: spacing.lg, height: 56, borderRadius: radius.lg, paddingHorizontal: spacing.xl, marginBottom: spacing["2xl"] },
  dressTxt: { color: colors.onSage, fontSize: 21 },
  dressArrow: { width: 32, height: 32, borderRadius: 16, backgroundColor: "rgba(255,255,255,0.22)", alignItems: "center", justifyContent: "center" },
  sectionHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  sectionTitle: { fontSize: 16, color: colors.onSurface, fontFamily: fonts.display, letterSpacing: -0.3 },
  seeAll: { fontSize: 13, color: colors.sage },
  recentRow: { paddingHorizontal: spacing.lg, gap: spacing.md },
  recentCard: { width: 150 },
  recentCollage: { width: 150, aspectRatio: 0.88, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, overflow: "hidden", borderWidth: 0.5, borderColor: colors.border },
  recentFull: { width: "100%", height: "100%" },
  recentGrid: { flex: 1, flexDirection: "row", flexWrap: "wrap" },
  recentCell: { width: "50%", height: "50%", alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  recentName: { fontSize: 14, color: colors.onSurface, fontFamily: fonts.displayMedium, marginTop: spacing.sm },
  recentTime: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  emptyWrap: { paddingHorizontal: spacing.lg },
  ghostRow: { flexDirection: "row", gap: spacing.md },
  ghostCard: { flex: 1, aspectRatio: 0.82, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.divider, alignItems: "center", justifyContent: "center", gap: spacing.sm },
  ghostCreate: { backgroundColor: colors.surface, borderColor: colors.sage, borderStyle: "dashed" },
  ghostPlus: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
  ghostCreateTxt: { fontSize: 12, color: colors.onSurfaceSecondary, fontFamily: fonts.displayMedium },
  emptyCopy: { fontSize: 13, color: colors.onSurfaceTertiary, marginTop: spacing.md },
  quickGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, paddingHorizontal: spacing.lg },
  quickCard: { width: "47.6%", flexGrow: 1, height: 100, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", gap: spacing.md },
  qaIcon: { height: 26, alignItems: "center", justifyContent: "center" },
  quickLabel: { fontSize: 14, color: colors.onSurface, fontFamily: fonts.displayMedium },
});
