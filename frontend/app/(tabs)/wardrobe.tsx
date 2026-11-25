import { shortItemName } from "@/src/utils/itemLabel";
import React, { useCallback, useState } from "react";
import { View, StyleSheet, FlatList, Pressable, ScrollView, ActivityIndicator, useWindowDimensions, Modal } from "react-native";
import { Image } from "expo-image";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather, MaterialCommunityIcons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { useProfiles } from "@/src/context/ProfileContext";
import { useAuth } from "@/src/context/AuthContext";
import { FREE_ITEM_CAP, WARDROBE_FULL_TITLE, WARDROBE_FULL_BODY } from "@/src/utils/limits";
import GarmentImage from "@/src/components/GarmentImage";
import WardrobeSwitcher from "@/src/components/WardrobeSwitcher";
import { MAIN_CATEGORIES, SUB_ORDER, hasThirdLevel, displayCategory, primarySub } from "@/src/utils/taxonomy";
import { getCachedItems, setCachedItems, wardrobeIsFresh, markWardrobeDirty } from "@/src/utils/wardrobeCache";

const GUTTER = spacing.md;

// Remembered between visits so opening a piece and coming back lands you where
// you left off rather than at the top of the catalogue.
let lastFilter: string | null = null;
let lastSub: string | null = null;
let lastLeaf: string | null = null;
let lastOffset = 0;

// Restrained per-category cues for the browse levels (no garment photos).
const CATEGORY_META: Record<string, { icon: any; tone: string }> = {
  Tops: { icon: "tshirt-crew-outline", tone: colors.taupe },
  Bottoms: { icon: "human-handsdown", tone: colors.champagne },
  Dresses: { icon: "tshirt-v-outline", tone: colors.plum },
  Outerwear: { icon: "coat-rack", tone: colors.eucalyptus },
  Shoes: { icon: "shoe-heel", tone: colors.cream },
  Accessories: { icon: "sunglasses", tone: colors.creamDim },
};

const EMPTY_IMG =
  "https://images.unsplash.com/photo-1558769132-cb1aea458c5e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzl8MHwxfHNlYXJjaHwxfHxtaW5pbWFsaXN0JTIwd2FyZHJvYmUlMjBjbG90aGluZyUyMHJhY2t8ZW58MHx8fHwxNzg0MDQ2MTUwfDA&ixlib=rb-4.1.0&q=85";

export default function Wardrobe() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { active, profiles, loading: profileLoading } = useProfiles();
  const { width } = useWindowDimensions();
  const COL_W = (width - spacing.xl * 2 - GUTTER) / 2;
  const { user } = useAuth();
  const [items, setItems] = useState<any[]>(() => getCachedItems() || []);
  // Browsing levels use a photo-free summary; garment images are only fetched
  // and rendered once you reach the final level.
  const [summary, setSummary] = useState<any[]>(() => getCachedItems() || []);
  const [filter, setFilter] = useState<string | null>(lastFilter);
  const [sub, setSub] = useState<string | null>(lastSub);
  const [leaf, setLeaf] = useState<string | null>(lastLeaf);
  const listRef = React.useRef<FlatList<any>>(null);
  const restored = React.useRef(false);
  const [loading, setLoading] = useState(true);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showSwitcher, setShowSwitcher] = useState(false);

  const [capacityFull, setCapacityFull] = useState(false);

  const summaryInFlight = React.useRef(false);
  const loadSummary = useCallback(async () => {
    if (summaryInFlight.current) return;
    summaryInFlight.current = true;
    try {
      const data = await api<any[]>("/items?summary=1");
      setSummary(data);
    } catch {}
    try {
      const cap = await api<any>("/items/capacity");
      setCapacityFull(!!cap?.full);
    } catch {}
    summaryInFlight.current = false;
  }, []);

  const inFlight = React.useRef(false);
  const load = useCallback(async (silent = false) => {
    // One request at a time: focus can fire more than once while the profile
    // resolves, and the catalogue must not be fetched two or three times.
    if (inFlight.current) return;
    inFlight.current = true;
    if (!silent) setLoading(true);
    try {
      const data = await api<any[]>("/items");
      setItems(data);
      setCachedItems(data);
    } catch {}
    inFlight.current = false;
    setLoading(false);
  }, []);

  // ---- progressive browsing ------------------------------------------------
  // Wardrobe → main category → subcategory (where it exists) → garments.
  const subLevels = filter ? SUB_ORDER[filter] : null;
  const needsSub = !!filter && !!subLevels && !sub;
  const leafLevels = filter && sub && hasThirdLevel(filter, sub) ? SUB_ORDER[sub] : null;
  const needsLeaf = !!leafLevels && !leaf;
  const wardrobeFull = !user?.premium && (capacityFull || items.length >= FREE_ITEM_CAP);
  const atItems = !!filter && !needsSub && !needsLeaf;

  const inCategory = (i: any) => displayCategory(i) === filter;
  const inSub = (i: any) => !sub || primarySub(i, filter as string) === sub;
  const inLeaf = (i: any) => !leaf || primarySub(i, sub as string) === leaf;

  const count = (rows: any[], pred: (i: any) => boolean) => rows.filter(pred).length;
  const categoryRows = MAIN_CATEGORIES.map((c) => ({
    label: c,
    count: count(summary, (i) => displayCategory(i) === c),
  }));
  const subRows = (subLevels || []).map((label) => ({
    label,
    count: count(summary, (i) => inCategory(i) && primarySub(i, filter as string) === label),
  })).filter((r) => r.count > 0);
  const leafRows = (leafLevels || []).map((label) => ({
    label,
    count: count(summary, (i) => inCategory(i) && inSub(i) && primarySub(i, sub as string) === label),
  })).filter((r) => r.count > 0);

  const filtered = items.filter((i) => inCategory(i) && inSub(i) && inLeaf(i));

  const chooseFilter = (f: string) => {
    setFilter(f);
    setSub(null);
    setLeaf(null);
    lastFilter = f;
    lastSub = null;
    lastLeaf = null;
    lastOffset = 0;
    restored.current = true;
    if (!SUB_ORDER[f]) load(items.length > 0);
  };

  const chooseSub = (label: string) => {
    setSub(label);
    setLeaf(null);
    lastSub = label;
    lastLeaf = null;
    lastOffset = 0;
    restored.current = true;
    if (!hasThirdLevel(filter as string, label)) load(items.length > 0);
  };

  const chooseLeaf = (label: string) => {
    setLeaf(label);
    lastLeaf = label;
    lastOffset = 0;
    restored.current = true;
    load(items.length > 0);
  };

  const goBackLevel = () => {
    exitSelect();
    lastOffset = 0;
    if (leaf) { setLeaf(null); lastLeaf = null; return; }
    if (sub) { setSub(null); lastSub = null; return; }
    setFilter(null);
    lastFilter = null;
  };

  const crumb = [filter, sub, leaf].filter(Boolean).join(" · ");

  useFocusEffect(
    useCallback(() => {
      // Coming back from an item: keep the grid mounted (no loading flash) and
      // allow the saved scroll offset to be restored again.
      restored.current = false;
      const cache = getCachedItems();
      if (cache && cache !== items) setItems(cache);
      // Wait until the active profile is resolved so /items is always scoped to
      // the correct profile (never a null-header fallback to the default one).
      if (profileLoading) return;
      if (wardrobeIsFresh()) {
        // Nothing changed and the catalogue was just loaded → keep what we have.
        setLoading(false);
        if (cache) setSummary(cache);
        return;
      }
      loadSummary();
      if (atItems) load((cache || items).length > 0);
      else setLoading(false);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [load, loadSummary, profileLoading, atItems])
  );


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
      markWardrobeDirty();
      setConfirmDelete(false);
      exitSelect();
      await load();
      // Freeing a slot restores Add straight away.
      await loadSummary();
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
    >
      <GarmentImage photo={item.photo} fallbackPhoto={item.worn_photo} category={item.category} style={[styles.cardImg, { width: COL_W, height: COL_W * 1.3 }, selectMode && isSel && styles.cardImgSelected]} iconSize={28} testID={`wardrobe-img-${item.id}`} />
      {selectMode && (
        <View style={[styles.selectDot, isSel && styles.selectDotOn]} testID={`select-dot-${item.id}`}>
          {isSel ? <Feather name="check" size={13} color={colors.onBrandPrimary} /> : null}
        </View>
      )}
      {(item.pairs_count || 0) > 0 && (
        <View style={styles.pairsBadge}>
          <Txt style={styles.pairsBadgeTxt}>
            Pairs with {item.pairs_count} {item.pairs_count === 1 ? "piece" : "pieces"}
          </Txt>
        </View>
      )}
      <Txt style={styles.cardName} numberOfLines={1}>{shortItemName(item.name)}</Txt>
      <Txt style={styles.cardMeta} numberOfLines={1}>
        {item.brand ? `${item.brand} · ` : ""}{displayCategory(item)}
      </Txt>
    </Pressable>
    );
  };

  return (
    <View style={styles.container}>
      {/* Sticky header */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <BrandMark />
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            {selectMode ? (
              <Txt style={styles.kicker}>{selected.length} SELECTED</Txt>
            ) : filter ? (
              <Pressable style={styles.backChip} testID="wardrobe-back-level" onPress={goBackLevel}>
                <Feather name="chevron-left" size={15} color={colors.onSurfaceSecondary} />
                <Txt style={styles.switcherTxt}>{sub ? (leaf ? sub : filter) : "Wardrobe"}</Txt>
              </Pressable>
            ) : (
              <Pressable style={styles.switcherChip} testID="wardrobe-switcher-chip" onPress={() => setShowSwitcher(true)}>
                <Txt style={styles.switcherTxt}>{active?.name || "My wardrobe"}</Txt>
                <Feather name="chevron-down" size={13} color={colors.onSurfaceSecondary} />
                {profiles.length > 1 ? <Txt style={styles.switcherCount}>{profiles.length}</Txt> : null}
              </Pressable>
            )}
            <Display weight="semibold" style={styles.title} numberOfLines={1}>
              {leaf || sub || filter || "Wardrobe"}
            </Display>
            {crumb && (leaf || sub) ? <Txt style={styles.crumb}>{crumb}</Txt> : null}
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
              {atItems ? (
                <Pressable
                  style={styles.iconBtn}
                  testID="wardrobe-select-button"
                  onPress={() => setSelectMode(true)}
                >
                  <Feather name="check-square" size={19} color={colors.onSurface} />
                </Pressable>
              ) : null}
              {wardrobeFull ? (
                <Pressable style={styles.fullBtn} testID="wardrobe-full-upgrade" onPress={() => router.push("/premium")}>
                  <Feather name="award" size={16} color={colors.onSurface} />
                  <Txt style={styles.fullBtnTxt}>Wardrobe full</Txt>
                </Pressable>
              ) : (
                <Pressable style={styles.addBtn} testID="wardrobe-add-button" onPress={() => router.push("/add-item")}>
                  <Feather name="plus" size={20} color={colors.onBrandPrimary} />
                </Pressable>
              )}
            </View>
          )}
        </View>
      </View>

      {!atItems ? (
        <ScrollView contentContainerStyle={styles.levelList} showsVerticalScrollIndicator={false}>
          {wardrobeFull && !needsSub && !needsLeaf ? (
            <View style={styles.fullCard} testID="wardrobe-full-card">
              <Txt style={styles.fullCardTitle}>{WARDROBE_FULL_TITLE}</Txt>
              <Txt style={styles.fullCardBody}>{WARDROBE_FULL_BODY}</Txt>
              <Pressable style={styles.fullCardBtn} testID="wardrobe-full-card-upgrade" onPress={() => router.push("/premium")}>
                <Feather name="award" size={15} color={colors.onSage} />
                <Txt style={styles.fullCardBtnTxt}>Upgrade to Premium</Txt>
              </Pressable>
            </View>
          ) : null}
          {(needsLeaf ? leafRows : needsSub ? subRows : categoryRows).map((row) => {
            const meta = CATEGORY_META[row.label];
            const top = !filter;
            return (
              <Pressable
                key={row.label}
                testID={`wardrobe-level-${row.label}`}
                style={({ pressed }) => [
                  top ? styles.catRow : styles.levelRow,
                  top && meta ? { backgroundColor: meta.tone, borderColor: meta.tone } : null,
                  pressed && styles.rowPressed,
                ]}
                onPress={() =>
                  needsLeaf ? chooseLeaf(row.label) : needsSub ? chooseSub(row.label) : chooseFilter(row.label)
                }
              >
                {top && meta ? (
                  <View style={styles.catPuck}>
                    <MaterialCommunityIcons name={meta.icon} size={19} color={colors.onSurface} />
                  </View>
                ) : (
                  <View style={styles.subDot} />
                )}
                <View style={{ flex: 1 }}>
                  <Display weight="semibold" style={top ? styles.catLabel : styles.levelLabel}>
                    {row.label}
                  </Display>
                  {top ? (
                    <Txt style={styles.levelCount}>
                      {row.count} {row.count === 1 ? "piece" : "pieces"}
                    </Txt>
                  ) : null}
                </View>
                {!top ? (
                  <View style={styles.countPill}>
                    <Txt style={styles.countPillTxt}>{row.count}</Txt>
                  </View>
                ) : null}
                <Feather name="chevron-right" size={18} color={colors.onSurfaceTertiary} />
              </Pressable>
            );
          })}
          {(needsLeaf ? leafRows : needsSub ? subRows : categoryRows).length === 0 ? (
            <View style={styles.levelEmpty}>
              <Txt style={styles.emptySub}>Nothing here yet.</Txt>
              <Pressable style={styles.emptyBtn} testID="wardrobe-empty-add" onPress={() => router.push("/add-item")}>
                <Txt style={styles.emptyBtnTxt}>Add Item</Txt>
              </Pressable>
              <Pressable style={styles.emptyBtnAlt} testID="wardrobe-empty-bulk" onPress={() => router.push("/bulk-add")}>
                <Txt style={styles.emptyBtnAltTxt}>Bulk Add</Txt>
              </Pressable>
            </View>
          ) : null}
        </ScrollView>
      ) : loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.onSurface} /></View>
      ) : filtered.length === 0 ? (
        <ScrollView contentContainerStyle={styles.emptyWrap}>
          <Image source={{ uri: EMPTY_IMG }} style={styles.emptyImg} contentFit="cover" />
          <Display weight="semibold" style={styles.emptyTitle}>
            No {(leaf || sub || filter || "").toLowerCase()} yet
          </Display>
          <Txt style={styles.emptySub}>Add your clothes to start getting personalised outfits.</Txt>
          <Pressable style={styles.emptyBtn} testID="wardrobe-empty-add" onPress={() => router.push("/add-item")}>
            <Txt style={styles.emptyBtnTxt}>Add Item</Txt>
          </Pressable>
          <Pressable style={styles.emptyBtnAlt} testID="wardrobe-empty-bulk" onPress={() => router.push("/bulk-add")}>
            <Txt style={styles.emptyBtnAltTxt}>Bulk Add</Txt>
          </Pressable>
        </ScrollView>
      ) : (
        <FlatList
          ref={listRef}
          data={filtered}
          keyExtractor={(i) => i.id}
          renderItem={renderItem}
          numColumns={2}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.grid}
          columnWrapperStyle={{ justifyContent: "flex-start" }}
          onScroll={(e) => { lastOffset = e.nativeEvent.contentOffset.y; }}
          scrollEventThrottle={80}
          onContentSizeChange={() => {
            if (restored.current || lastOffset <= 0) return;
            restored.current = true;
            listRef.current?.scrollToOffset({ offset: lastOffset, animated: false });
          }}
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
  fullCard: {
    backgroundColor: colors.cream, borderWidth: 0.5, borderColor: colors.goldSoft,
    borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md,
  },
  fullCardTitle: { fontSize: 16.5, color: colors.onSurface, fontFamily: fonts.displayMedium },
  fullCardBody: { fontSize: 13.5, color: colors.onSurfaceSecondary, marginTop: spacing.xs, lineHeight: 20 },
  fullCardBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    height: 48, borderRadius: radius.md, backgroundColor: colors.sage, marginTop: spacing.md,
  },
  fullCardBtnTxt: { fontSize: 15, color: colors.onSage, fontFamily: fonts.displayBold },
  fullBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, height: 40,
    paddingHorizontal: spacing.md, borderRadius: radius.pill,
    borderWidth: 0.5, borderColor: colors.goldSoft, backgroundColor: colors.cream,
  },
  fullBtnTxt: { fontSize: 13, color: colors.onSurface, fontFamily: fonts.displayMedium },
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
  crumb: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 2 },
  backChip: { flexDirection: "row", alignItems: "center", gap: 2, marginBottom: 2, alignSelf: "flex-start" },
  levelList: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg, paddingBottom: spacing["3xl"] },
  levelRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingVertical: spacing.md, paddingHorizontal: spacing.lg, marginBottom: spacing.sm,
    borderRadius: radius.md, borderWidth: 0.5, borderColor: colors.border,
    backgroundColor: colors.surface, minHeight: 58,
  },
  catRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.lg,
    paddingVertical: spacing.lg, paddingHorizontal: spacing.lg, marginBottom: spacing.md,
    borderRadius: radius.lg, borderWidth: 0.5, minHeight: 82,
    shadowColor: "#232323", shadowOpacity: 0.05, shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 }, elevation: 1,
  },
  rowPressed: { opacity: 0.92 },
  catPuck: {
    width: 42, height: 42, borderRadius: 21, backgroundColor: colors.surface,
    alignItems: "center", justifyContent: "center",
  },
  catLabel: { fontSize: 17.5, color: colors.onSurface, letterSpacing: -0.2 },
  subDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: colors.sage },
  countPill: {
    minWidth: 26, height: 22, paddingHorizontal: 7, borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center",
  },
  countPillTxt: { fontSize: 11.5, color: colors.onSurfaceSecondary },
  levelLabel: { fontSize: 16, color: colors.onSurface },
  levelCount: { fontSize: 12.5, color: colors.onSurfaceTertiary, marginTop: 2 },
  levelEmpty: { alignItems: "center", paddingTop: spacing["2xl"] },
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
  subContent: { gap: spacing.sm, paddingHorizontal: spacing.xl, paddingBottom: spacing.sm },
  subChip: {
    height: 30, paddingHorizontal: spacing.md, borderRadius: radius.pill,
    borderWidth: 0.5, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  subChipActive: { backgroundColor: colors.surfaceSecondary, borderColor: colors.borderStrong },
  subChipTxt: { fontSize: 12, color: colors.onSurfaceTertiary },
  subChipTxtActive: { color: colors.onSurface },
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
  cardName: { fontSize: 14, color: colors.onSurface, marginTop: spacing.sm },
  cardMeta: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyWrap: { padding: spacing.xl, alignItems: "center", paddingTop: spacing["2xl"] },
  emptyImg: { width: "100%", height: 260, borderRadius: radius.md, marginBottom: spacing.xl },
  emptyTitle: { fontSize: 20, textAlign: "center", marginBottom: spacing.sm, letterSpacing: -0.3 },
  emptySub: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", marginBottom: spacing.xl },
  emptyBtnAlt: {
    marginTop: spacing.md,
    paddingHorizontal: spacing["2xl"],
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  emptyBtnAltTxt: { color: colors.onSurface, fontSize: 15, fontFamily: fonts.displayMedium },
  emptyBtn: {
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing["2xl"],
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
  },
  emptyBtnTxt: { color: colors.onBrandPrimary, fontSize: 15, fontFamily: fonts.displayBold },
});
