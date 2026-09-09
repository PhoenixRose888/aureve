import React, { useCallback, useState } from "react";
import { View, StyleSheet, FlatList, Pressable, ScrollView, ActivityIndicator, useWindowDimensions, Modal } from "react-native";
import { Image } from "expo-image";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts, CATEGORIES } from "@/src/theme";
import { api } from "@/src/api/client";
import { usePremiumAccess } from "@/src/hooks/usePremiumAccess";
import { useProfiles } from "@/src/context/ProfileContext";
import GarmentImage from "@/src/components/GarmentImage";
import WardrobeSwitcher from "@/src/components/WardrobeSwitcher";

const GUTTER = spacing.md;

const FILTERS = ["All", ...CATEGORIES];

const EMPTY_IMG =
  "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzl8MHwxfHNlYXJjaHwxfHxtaW5pbWFsaXN0JTIwd2FyZHJvYmUlMjBjbG90aGluZyUyMHJhY2t8ZW58MHx8fHwxNzg0MDQ2MTUwfDA&ixlib=rb-4.1.0&q=85";

export default function Wardrobe() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { premium } = usePremiumAccess();
  const { active, profiles, loading: profileLoading } = useProfiles();
  const { width } = useWindowDimensions();
  const COL_W = (width - spacing.xl * 2 - GUTTER) / 2;
  const [items, setItems] = useState<any[]>([]);
  const [filter, setFilter] = useState("All");
  const [loading, setLoading] = useState(true);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showSwitcher, setShowSwitcher] = useState(false);

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
      // Wait until the active profile is resolved so /items is always scoped to
      // the correct profile (never a null-header fallback to the default one).
      if (!profileLoading) load();
    }, [load, profileLoading])
  );

  const filtered = filter === "All" ? items : items.filter((i) => i.category === filter);

  const exitSelect = () => {
    setSelectMode(false);
    setSelected([]);
  };

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const allShownSelected = filtered.length > 0 && filtered.every((i) => selected.includes(i.id));

  const toggleSelectAll = () =>
    setSelected(allShownSelected ? [] : filtered.map((i) => i.id));

  const deleteSelected = async () => {
    setDeleting(true);
    try {
      await api("/items/bulk-delete", { method: "POST", body: { item_ids: selected } });
      setConfirmDelete(false);
      exitSelect();
      await load();
    } catch {}
    setDeleting(false);
  };

  const renderItem = ({ item, index }: { item: any; index: number }) => {
    const isSel = selected.includes(item.id);
    return (
    <Pressable
      testID={`wardrobe-item-${item.id}`}
      style={[styles.card, { width: COL_W, marginRight: index % 2 === 0 ? GUTTER : 0 }]}
      onPress={() => (selectMode ? toggle(item.id) : router.push(`/item/${item.id}`))}
      onLongPress={() => {
        if (!selectMode) {
          setSelectMode(true);
          setSelected([item.id]);
        }
      }}
    >
      <GarmentImage photo={item.photo} fallbackPhoto={item.worn_photo} category={item.category} style={[styles.cardImg, { width: COL_W, height: COL_W * 1.3 }, selectMode && isSel && styles.cardImgSelected]} iconSize={28} testID={`wardrobe-img-${item.id}`} />
      {selectMode && (
        <View style={[styles.selectDot, isSel && styles.selectDotOn]} testID={`select-dot-${item.id}`}>
          {isSel ? <Feather name="check" size={13} color={colors.onBrandPrimary} /> : null}
        </View>
      )}
      {(item.pairs_count || 0) > 0 && (
        <View style={styles.pairsBadge}>
          <Txt style={styles.pairsBadgeTxt}>Pairs with {item.pairs_count}</Txt>
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
            {selectMode ? (
              <Txt style={styles.kicker}>{selected.length} SELECTED</Txt>
            ) : (
              <Pressable style={styles.switcherChip} testID="wardrobe-switcher-chip" onPress={() => setShowSwitcher(true)}>
                <Txt style={styles.switcherTxt}>{active?.name || "My wardrobe"}</Txt>
                <Feather name="chevron-down" size={13} color={colors.onSurfaceSecondary} />
                {profiles.length > 1 ? <Txt style={styles.switcherCount}>{profiles.length}</Txt> : null}
              </Pressable>
            )}
            <Display weight="semibold" style={styles.title}>Wardrobe</Display>
          </View>
          {selectMode ? (
            <View style={styles.headerActions}>
              <Pressable style={styles.textBtn} testID="select-all" onPress={toggleSelectAll}>
                <Txt style={styles.textBtnTxt}>{allShownSelected ? "Clear" : "Select all"}</Txt>
              </Pressable>
              <Pressable
                style={[styles.addBtn, selected.length === 0 && styles.btnDisabled]}
                testID="delete-selected"
                disabled={selected.length === 0}
                onPress={() => setConfirmDelete(true)}
              >
                <Feather name="trash-2" size={18} color={colors.onBrandPrimary} />
              </Pressable>
              <Pressable style={styles.textBtn} testID="cancel-select" onPress={exitSelect}>
                <Txt style={styles.textBtnTxt}>Cancel</Txt>
              </Pressable>
            </View>
          ) : (
          <View style={styles.headerActions}>
            <Pressable
              style={styles.iconBtn}
              testID="wardrobe-select-button"
              onPress={() => setSelectMode(true)}
            >
              <Feather name="check-square" size={19} color={colors.onSurface} />
            </Pressable>
            <Pressable style={styles.addBtn} testID="wardrobe-add-button" onPress={() => router.push("/add-item")}>
              <Feather name="plus" size={20} color={colors.onBrandPrimary} />
            </Pressable>
          </View>
          )}
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

      {!selectMode && (
        <Pressable
          style={styles.shopIqBanner}
          testID="shopping-intelligence-entry"
          onPress={() => router.push(premium ? "/shop" : "/premium")}
        >
          <View style={styles.shopIqIcon}>
            <Feather name="trending-up" size={16} color={colors.brand} />
          </View>
          <View style={styles.shopIqText}>
            <Txt style={styles.shopIqTitle}>Shopping Intelligence</Txt>
            <Txt style={styles.shopIqSub} numberOfLines={1}>Find the gaps worth filling — shop smarter</Txt>
          </View>
          <Feather name={premium ? "chevron-right" : "lock"} size={16} color={colors.onSurfaceTertiary} />
        </Pressable>
      )}

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.onSurface} /></View>
      ) : filtered.length === 0 ? (
        <ScrollView contentContainerStyle={styles.emptyWrap}>
          <Image source={{ uri: EMPTY_IMG }} style={styles.emptyImg} contentFit="cover" />
          <Display weight="semibold" style={styles.emptyTitle}>
            {filter === "All" ? "Your wardrobe is a blank canvas" : `No ${filter.toLowerCase()} yet`}
          </Display>
          <Txt style={styles.emptySub}>Snap or upload a photo to catalogue your first piece.</Txt>
          <Pressable style={styles.emptyBtn} testID="wardrobe-empty-add" onPress={() => router.push("/add-item")}>
            <Txt style={styles.emptyBtnTxt}>Add first piece</Txt>
          </Pressable>
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

      <WardrobeSwitcher visible={showSwitcher} onClose={() => setShowSwitcher(false)} />

      <Modal visible={confirmDelete} transparent animationType="fade" onRequestClose={() => setConfirmDelete(false)}>
        <Pressable style={styles.backdrop} onPress={() => setConfirmDelete(false)}>
          <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
            <Display weight="semibold" style={styles.sheetTitle}>
              Remove {selected.length} {selected.length === 1 ? "piece" : "pieces"}?
            </Display>
            <Txt style={styles.sheetSub}>
              They will be removed from your wardrobe and from any saved looks. This can&apos;t be undone.
            </Txt>
            <Pressable style={styles.deleteBtn} testID="confirm-bulk-delete" onPress={deleteSelected} disabled={deleting}>
              {deleting ? (
                <ActivityIndicator color={colors.onSurfaceInverse} />
              ) : (
                <Txt style={styles.deleteTxt}>Delete</Txt>
              )}
            </Pressable>
            <Pressable style={styles.keepBtn} testID="cancel-bulk-delete" onPress={() => setConfirmDelete(false)}>
              <Txt style={styles.keepTxt}>Keep them</Txt>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
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
  iconBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    borderWidth: 0.5,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
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
  cardImgSelected: { opacity: 0.55, borderWidth: 2, borderColor: colors.brandPrimary },
  selectDot: {
    position: "absolute", top: spacing.sm, right: spacing.sm,
    width: 24, height: 24, borderRadius: 12,
    borderWidth: 1.5, borderColor: colors.onSurfaceInverse,
    backgroundColor: "rgba(26,26,26,0.35)",
    alignItems: "center", justifyContent: "center",
  },
  selectDotOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  switcherChip: { flexDirection: "row", alignItems: "center", gap: 5, paddingVertical: 4, minHeight: 28 },
  switcherTxt: { fontSize: 12, letterSpacing: 1, color: colors.onSurfaceSecondary, textTransform: "uppercase" },
  switcherCount: {
    fontSize: 10, color: colors.onSurfaceTertiary, borderWidth: 0.5, borderColor: colors.border,
    borderRadius: radius.pill, paddingHorizontal: 5, paddingVertical: 1, overflow: "hidden",
  },
  textBtn: { height: 44, paddingHorizontal: spacing.sm, justifyContent: "center" },
  textBtnTxt: { fontSize: 14, color: colors.onSurfaceSecondary },
  btnDisabled: { opacity: 0.4 },
  backdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.45)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.xl, paddingBottom: spacing["2xl"],
  },
  sheetTitle: { fontSize: 22, marginBottom: spacing.sm },
  sheetSub: { fontSize: 14, color: colors.onSurfaceSecondary, marginBottom: spacing.xl, lineHeight: 20 },
  deleteBtn: { backgroundColor: colors.error, height: 52, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  deleteTxt: { color: colors.onSurfaceInverse, fontSize: 15 },
  keepBtn: { alignItems: "center", paddingVertical: spacing.md, marginTop: spacing.sm },
  keepTxt: { fontSize: 15, color: colors.onSurfaceTertiary },
  placeholder: { alignItems: "center", justifyContent: "center" },
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
  shopIqBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    marginHorizontal: spacing.xl,
    marginTop: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
    borderWidth: 0.5,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  shopIqIcon: {
    width: 34, height: 34, borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center",
  },
  shopIqText: { flex: 1 },
  shopIqTitle: { fontSize: 14, color: colors.onSurface, fontFamily: fonts.displayMedium },
  shopIqSub: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  cardName: { fontSize: 14, color: colors.onSurface, marginTop: spacing.sm },
  cardMeta: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyWrap: { padding: spacing.xl, alignItems: "center", paddingTop: spacing["2xl"] },
  emptyImg: { width: "100%", height: 260, borderRadius: radius.md, marginBottom: spacing.xl },
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
