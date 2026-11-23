import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Modal, ActivityIndicator, useWindowDimensions } from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";
import ConfirmModal from "@/src/components/ConfirmModal";
import * as haptics from "@/src/utils/haptics";

export default function CollectionDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const CARD_W = (width - spacing.lg * 2 - spacing.md) / 2;
  const [coll, setColl] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [allOutfits, setAllOutfits] = useState<any[]>([]);
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try { setColl(await api<any>(`/collections/${id}`)); }
    catch { setColl(null); }
    finally { setLoading(false); }
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openAdd = async () => {
    haptics.tap();
    try { setAllOutfits(await api<any[]>("/outfits")); } catch {}
    setAdding(true);
  };

  const toggleOutfit = async (outfitId: string, inColl: boolean) => {
    haptics.tap();
    const body = inColl ? { remove_outfit: outfitId } : { add_outfit: outfitId };
    try { setColl(await api<any>(`/collections/${id}`, { method: "PATCH", body })); } catch {}
  };

  const doDelete = async () => {
    setDeleting(true);
    try { await api(`/collections/${id}`, { method: "DELETE" }); } catch {}
    setDeleting(false);
    setConfirmDel(false);
    router.back();
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.sage} /></View>;
  if (!coll) return (
    <View style={[styles.center, { paddingTop: insets.top }]}>
      <Txt style={{ color: colors.onSurfaceSecondary }}>Collection not found.</Txt>
      <Pressable onPress={() => router.back()} style={{ marginTop: spacing.lg }}><Txt style={{ color: colors.sage }}>Go back</Txt></Pressable>
    </View>
  );

  const outfits = coll.outfits || [];
  const inCollIds = new Set(coll.outfit_ids || []);

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="collection-back"><Feather name="chevron-left" size={26} color={colors.onSurface} /></Pressable>
        <Display weight="medium" style={styles.topTitle} numberOfLines={1}>{coll.name}</Display>
        <Pressable onPress={() => setConfirmDel(true)} hitSlop={12} testID="collection-menu"><Feather name="trash-2" size={20} color={colors.onSurface} /></Pressable>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] }}>
        <Pressable style={styles.addBtn} testID="collection-add-outfits" onPress={openAdd}>
          <Feather name="plus" size={18} color={colors.onSage} />
          <Txt style={styles.addBtnTxt}>Add outfits</Txt>
        </Pressable>

        {outfits.length === 0 ? (
          <Txt style={styles.emptyTxt}>No outfits in this collection yet. Tap &lsquo;Add outfits&rsquo; to curate your looks.</Txt>
        ) : (
          <View style={styles.grid}>
            {outfits.map((o: any) => (
              <Pressable key={o.id} style={[styles.card, { width: CARD_W }]} testID={`coll-outfit-${o.id}`} onPress={() => router.push(`/outfit/${o.id}`)}>
                <View style={styles.collage}>
                  <View style={styles.collageGrid}>
                    {(o.items || []).slice(0, 4).map((it: any, i: number) => (
                      <GarmentImage key={i} photo={it.photo} category={it.category} style={styles.collageCell} iconSize={14} />
                    ))}
                    {(o.items || []).length === 0 && <View style={styles.collageCell}><Feather name="layers" size={16} color={colors.onSurfaceTertiary} /></View>}
                  </View>
                </View>
                <Txt style={styles.cardName} numberOfLines={1}>{o.name || "Outfit"}</Txt>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>

      <Modal visible={adding} animationType="slide" transparent onRequestClose={() => setAdding(false)}>
        <View style={styles.sheetBackdrop}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={styles.sheetHead}>
              <Display weight="medium" style={styles.sheetTitle}>Add outfits</Display>
              <Pressable onPress={() => setAdding(false)} hitSlop={10}><Feather name="x" size={22} color={colors.onSurface} /></Pressable>
            </View>
            <ScrollView showsVerticalScrollIndicator={false}>
              {allOutfits.length === 0 ? (
                <Txt style={styles.emptyTxt}>You haven&rsquo;t saved any outfits yet.</Txt>
              ) : (
                allOutfits.map((o) => {
                  const inC = inCollIds.has(o.id);
                  return (
                    <Pressable key={o.id} style={styles.pickRow} testID={`add-outfit-${o.id}`} onPress={() => toggleOutfit(o.id, inC)}>
                      <View style={styles.pickThumbs}>
                        {(o.items || []).slice(0, 3).map((it: any, i: number) => (
                          <GarmentImage key={i} photo={it.photo} category={it.category} style={styles.pickThumb} iconSize={12} />
                        ))}
                      </View>
                      <Txt style={styles.pickName} numberOfLines={1}>{o.name || "Outfit"}</Txt>
                      <View style={[styles.check, inC && styles.checkOn]}>{inC ? <Feather name="check" size={14} color={colors.onSage} /> : null}</View>
                    </Pressable>
                  );
                })
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>

      <ConfirmModal
        visible={confirmDel}
        title="Delete collection"
        message="This won't delete the outfits inside — just the collection."
        confirmLabel="Delete"
        destructive
        busy={deleting}
        onConfirm={doDelete}
        onCancel={() => setConfirmDel(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  topTitle: { fontSize: 18, flex: 1, textAlign: "center", marginHorizontal: spacing.sm },
  addBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.sage, height: 48, borderRadius: radius.md, marginBottom: spacing.lg },
  addBtnTxt: { color: colors.onSage, fontSize: 15, fontFamily: fonts.displayMedium },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  card: { marginBottom: spacing.sm },
  collage: { width: "100%", aspectRatio: 0.82, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, overflow: "hidden", borderWidth: 0.5, borderColor: colors.border },
  collageGrid: { flex: 1, flexDirection: "row", flexWrap: "wrap" },
  collageCell: { width: "50%", height: "50%", alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  cardName: { fontSize: 14, color: colors.onSurface, fontFamily: fonts.displayMedium, marginTop: spacing.sm },
  emptyTxt: { fontSize: 14, color: colors.onSurfaceTertiary, textAlign: "center", paddingVertical: spacing["2xl"], lineHeight: 21 },
  sheetBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingHorizontal: spacing.lg, paddingTop: spacing.lg, maxHeight: "82%" },
  sheetHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  sheetTitle: { fontSize: 18 },
  pickRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  pickThumbs: { flexDirection: "row", gap: 3 },
  pickThumb: { width: 34, height: 42, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  pickName: { flex: 1, fontSize: 14, color: colors.onSurface },
  check: { width: 24, height: 24, borderRadius: 12, borderWidth: 1.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  checkOn: { backgroundColor: colors.sage, borderColor: colors.sage },
});
