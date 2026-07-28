import React, { useCallback, useState } from "react";
import { View, StyleSheet, FlatList, Pressable, ScrollView, ActivityIndicator, useWindowDimensions } from "react-native";
import { Image } from "expo-image";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts, CATEGORIES } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";

const GUTTER = spacing.md;

const FILTERS = ["All", ...CATEGORIES];

const EMPTY_IMG =
  "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzl8MHwxfHNlYXJjaHwxfHxtaW5pbWFsaXN0JTIwd2FyZHJvYmUlMjBjbG90aGluZyUyMHJhY2t8ZW58MHx8fHwxNzg0MDQ2MTUwfDA&ixlib=rb-4.1.0&q=85";

export default function Wardrobe() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const COL_W = (width - spacing.xl * 2 - GUTTER) / 2;
  const [items, setItems] = useState<any[]>([]);
  const [filter, setFilter] = useState("All");
  const [loading, setLoading] = useState(true);
  const [laundryMode, setLaundryMode] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<any[]>("/items");
      setItems(data);
    } catch {}
    setLoading(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const notReady = items.filter((i) => (i.availability || "Ready") !== "Ready");
  const base = laundryMode ? notReady : items;
  const filtered = filter === "All" ? base : base.filter((i) => i.category === filter);

  const renderItem = ({ item, index }: { item: any; index: number }) => {
    const status = item.availability || "Ready";
    return (
    <Pressable
      testID={`wardrobe-item-${item.id}`}
      style={[styles.card, { width: COL_W, marginRight: index % 2 === 0 ? GUTTER : 0 }]}
      onPress={() => router.push(`/item/${item.id}`)}
    >
      <GarmentImage photo={item.photo} fallbackPhoto={item.worn_photo} category={item.category} style={[styles.cardImg, { width: COL_W, height: COL_W * 1.3 }]} iconSize={28} testID={`wardrobe-img-${item.id}`} />
      {status !== "Ready" && (
        <View style={styles.laundryBadge}>
          <Feather name="droplet" size={11} color={colors.onSurfaceInverse} />
          <Txt style={styles.laundryBadgeTxt}>{status}</Txt>
        </View>
      )}
      {status === "Ready" && (item.pairs_count || 0) > 0 && (
        <View style={styles.pairsBadge}>
          <Feather name="link-2" size={10} color={colors.onSurfaceInverse} />
          <Txt style={styles.pairsBadgeTxt}>{item.pairs_count}</Txt>
        </View>
      )}
      <Txt style={styles.cardName} numberOfLines={1}>{item.name}</Txt>
      <Txt style={styles.cardMeta} numberOfLines={1}>
        {item.brand ? `${item.brand} · ` : ""}{item.category}
      </Txt>
    </Pressable>
    );
  };

  return (
    <View style={styles.container}>
      {/* Sticky header */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <BrandMark style={{ alignSelf: "center", marginBottom: spacing.sm }} />
        <View style={styles.headerRow}>
          <View>
            <Txt style={styles.kicker}>{items.length} PIECES</Txt>
            <Display weight="semibold" style={styles.title}>Wardrobe</Display>
          </View>
          <View style={styles.headerActions}>
            <Pressable
              style={[styles.laundryIconBtn, laundryMode && styles.laundryIconBtnActive]}
              testID="wardrobe-laundry-button"
              onPress={() => setLaundryMode((m) => !m)}
            >
              <Feather name="droplet" size={19} color={laundryMode ? colors.onBrandPrimary : colors.onSurface} />
              {notReady.length > 0 && !laundryMode && (
                <View style={styles.laundryCountBadge}>
                  <Txt style={styles.laundryCountTxt}>{notReady.length}</Txt>
                </View>
              )}
            </Pressable>
            <Pressable style={styles.addBtn} testID="wardrobe-add-button" onPress={() => router.push("/add-item")}>
              <Feather name="plus" size={20} color={colors.onBrandPrimary} />
            </Pressable>
          </View>
        </View>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.chipRow}
          contentContainerStyle={styles.chipContent}
        >
          {FILTERS.map((f) => {
            const active = f === filter;
            return (
              <Pressable
                key={f}
                testID={`filter-chip-${f}`}
                style={[styles.chip, active && styles.chipActive]}
                onPress={() => setFilter(f)}
              >
                <Txt style={[styles.chipTxt, active && styles.chipTxtActive]}>{f}</Txt>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      {notReady.length > 0 && (
        <Pressable
          style={[styles.laundryBanner, laundryMode && styles.laundryBannerActive]}
          testID="laundry-banner"
          onPress={() => setLaundryMode((m) => !m)}
        >
          <Feather name="droplet" size={15} color={laundryMode ? colors.onBrandPrimary : colors.brand} />
          <Txt style={[styles.laundryBannerTxt, laundryMode && { color: colors.onBrandPrimary }]}>
            {laundryMode ? "Showing laundry only" : `${notReady.length} in the laundry`}
          </Txt>
          <Feather name={laundryMode ? "x" : "chevron-right"} size={16} color={laundryMode ? colors.onBrandPrimary : colors.onSurfaceTertiary} />
        </Pressable>
      )}

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.onSurface} /></View>
      ) : filtered.length === 0 ? (
        <ScrollView contentContainerStyle={styles.emptyWrap}>
          {laundryMode ? (
            <>
              <View style={styles.laundryEmptyIcon}>
                <Feather name="droplet" size={28} color={colors.brand} />
              </View>
              <Display weight="semibold" style={styles.emptyTitle}>Laundry basket is empty</Display>
              <Txt style={styles.emptySub}>Nothing is in the wash. Mark a piece as Washing from its detail screen and it will appear here.</Txt>
              <Pressable style={styles.emptyBtn} testID="laundry-empty-back" onPress={() => setLaundryMode(false)}>
                <Txt style={styles.emptyBtnTxt}>Back to wardrobe</Txt>
              </Pressable>
            </>
          ) : (
            <>
              <Image source={{ uri: EMPTY_IMG }} style={styles.emptyImg} contentFit="cover" />
              <Display weight="semibold" style={styles.emptyTitle}>
                {filter === "All" ? "Your wardrobe is a blank canvas" : `No ${filter.toLowerCase()} yet`}
              </Display>
              <Txt style={styles.emptySub}>Snap or upload a photo to catalogue your first piece.</Txt>
              <Pressable style={styles.emptyBtn} testID="wardrobe-empty-add" onPress={() => router.push("/add-item")}>
                <Txt style={styles.emptyBtnTxt}>Add first piece</Txt>
              </Pressable>
            </>
          )}
        </ScrollView>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(i) => i.id}
          renderItem={renderItem}
          numColumns={2}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.grid}
          columnWrapperStyle={{ justifyContent: "flex-start" }}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: {
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.xl,
    borderBottomWidth: 0.5,
    borderBottomColor: colors.border,
    paddingBottom: spacing.md,
  },
  headerRow: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  laundryIconBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    borderWidth: 0.5,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  laundryIconBtnActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  laundryCountBadge: {
    position: "absolute",
    top: -2,
    right: -2,
    minWidth: 18,
    height: 18,
    paddingHorizontal: 4,
    borderRadius: 9,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  laundryCountTxt: { color: colors.onSurfaceInverse, fontSize: 10, fontWeight: "600" },
  kicker: { fontSize: 11, letterSpacing: 2, color: colors.onSurfaceTertiary, marginBottom: 2 },
  title: { fontSize: 30, color: colors.onSurface, letterSpacing: -0.5 },
  addBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  chipRow: { marginTop: spacing.lg, height: 40, marginHorizontal: -spacing.xl },
  chipContent: { gap: spacing.sm, paddingHorizontal: spacing.xl, alignItems: "center" },
  chip: {
    height: 36,
    flexShrink: 0,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    borderWidth: 0.5,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  chipTxtActive: { color: colors.onBrandPrimary },
  grid: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  card: { marginBottom: spacing.xl },
  cardImg: { borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  placeholder: { alignItems: "center", justifyContent: "center" },
  laundryBadge: {
    position: "absolute",
    top: spacing.sm,
    left: spacing.sm,
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    backgroundColor: "rgba(26,26,26,0.65)",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  laundryBadgeTxt: { color: colors.onSurfaceInverse, fontSize: 10 },
  pairsBadge: {
    position: "absolute",
    bottom: 44,
    left: spacing.sm,
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    backgroundColor: "rgba(26,26,26,0.6)",
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  pairsBadgeTxt: { color: colors.onSurfaceInverse, fontSize: 10, fontWeight: "600" },
  laundryBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginHorizontal: spacing.xl,
    marginTop: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
    borderWidth: 0.5,
    borderColor: colors.border,
    backgroundColor: colors.brandTertiary,
  },
  laundryBannerActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  laundryBannerTxt: { flex: 1, fontSize: 13, color: colors.onBrandTertiary },
  cardName: { fontSize: 14, color: colors.onSurface, marginTop: spacing.sm },
  cardMeta: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyWrap: { padding: spacing.xl, alignItems: "center", paddingTop: spacing["2xl"] },
  emptyImg: { width: "100%", height: 260, borderRadius: radius.md, marginBottom: spacing.xl },
  laundryEmptyIcon: {
    width: 72,
    height: 72,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xl,
  },
  emptyTitle: { fontSize: 20, textAlign: "center", marginBottom: spacing.sm, letterSpacing: -0.3 },
  emptySub: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", marginBottom: spacing.xl },
  emptyBtn: {
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing["2xl"],
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
  },
  emptyBtnTxt: { color: colors.onBrandPrimary, fontSize: 15, fontFamily: fonts.displayBold },
});
