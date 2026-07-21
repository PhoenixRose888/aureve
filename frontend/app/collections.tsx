import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Modal, TextInput, ActivityIndicator, useWindowDimensions } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";
import * as haptics from "@/src/utils/haptics";

export default function Collections() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const CARD_W = (width - spacing.lg * 2 - spacing.md) / 2;
  const [collections, setCollections] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { setCollections(await api<any[]>("/collections")); } catch {}
    finally { setLoaded(true); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const create = async () => {
    if (!name.trim()) return;
    setSaving(true);
    haptics.tap();
    try {
      const c = await api<any>("/collections", { method: "POST", body: { name: name.trim() } });
      setCreating(false);
      setName("");
      router.push(`/collection/${c.id}`);
    } catch {}
    setSaving(false);
  };

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="collections-back"><Feather name="chevron-left" size={26} color={colors.onSurface} /></Pressable>
        <Display weight="medium" style={styles.topTitle}>Collections</Display>
        <Pressable onPress={() => { haptics.tap(); setCreating(true); }} hitSlop={12} testID="collections-add"><Feather name="plus" size={24} color={colors.onSurface} /></Pressable>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] }}>
        {loaded && collections.length === 0 ? (
          <View style={styles.emptyWrap} testID="collections-empty">
            <Display weight="semibold" style={styles.emptyHeading}>No collections yet</Display>
            <Txt style={styles.emptyCopy}>Group outfits for work, weekends or travel — beautifully organised.</Txt>
            <View style={styles.ghostRow}>
              <Pressable style={[styles.ghostCard, styles.ghostCreate]} testID="collections-empty-create" onPress={() => { haptics.tap(); setCreating(true); }}>
                <View style={styles.ghostPlus}><Feather name="plus" size={18} color={colors.onSage} /></View>
                <Txt style={styles.ghostCreateTxt}>New collection</Txt>
              </Pressable>
              <View style={styles.ghostCard}><Feather name="folder" size={22} color={colors.onSurfaceTertiary} /></View>
              <View style={styles.ghostCard}><Feather name="grid" size={22} color={colors.onSurfaceTertiary} /></View>
            </View>
          </View>
        ) : (
          <View style={styles.grid}>
            {collections.map((c) => (
              <Pressable key={c.id} style={[styles.card, { width: CARD_W }]} testID={`collection-${c.id}`} onPress={() => router.push(`/collection/${c.id}`)}>
                <View style={styles.cover}>
                  {(c.cover || []).length === 0 ? (
                    <View style={styles.coverEmpty}><Feather name="folder" size={22} color={colors.onSurfaceTertiary} /></View>
                  ) : (
                    <View style={styles.coverGrid}>
                      {(c.cover || []).slice(0, 4).map((cv: any, i: number) => (
                        <GarmentImage key={i} photo={cv.photo} category={cv.category} style={styles.coverCell} iconSize={14} />
                      ))}
                    </View>
                  )}
                </View>
                <Txt style={styles.cardName} numberOfLines={1}>{c.name}</Txt>
                <Txt style={styles.cardCount}>{c.count} {c.count === 1 ? "outfit" : "outfits"}</Txt>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>

      <Modal visible={creating} animationType="fade" transparent onRequestClose={() => setCreating(false)}>
        <View style={styles.backdrop}>
          <View style={styles.nameCard}>
            <Display weight="medium" style={styles.nameTitle}>New collection</Display>
            <TextInput style={styles.input} placeholder="e.g. Work, Weekend, Holiday" placeholderTextColor={colors.onSurfaceTertiary} value={name} onChangeText={setName} autoFocus testID="collection-name-input" />
            <View style={styles.row}>
              <Pressable style={styles.cancel} onPress={() => { setCreating(false); setName(""); }}><Txt style={styles.cancelTxt}>Cancel</Txt></Pressable>
              <Pressable style={styles.save} onPress={create} disabled={saving || !name.trim()} testID="collection-create-confirm">
                {saving ? <ActivityIndicator color={colors.onSage} size="small" /> : <Txt style={styles.saveTxt}>Create</Txt>}
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  topTitle: { fontSize: 18 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  card: { marginBottom: spacing.sm },
  cover: { width: "100%", aspectRatio: 1, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, overflow: "hidden", borderWidth: 0.5, borderColor: colors.border },
  coverEmpty: { flex: 1, alignItems: "center", justifyContent: "center" },
  coverGrid: { flex: 1, flexDirection: "row", flexWrap: "wrap" },
  coverCell: { width: "50%", height: "50%", alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  cardName: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium, marginTop: spacing.sm },
  cardCount: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  emptyWrap: { paddingTop: spacing["2xl"] },
  emptyHeading: { fontSize: 22, letterSpacing: -0.4, color: colors.onSurface, marginBottom: spacing.sm },
  emptyCopy: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20, marginBottom: spacing.xl },
  ghostRow: { flexDirection: "row", gap: spacing.md },
  ghostCard: { flex: 1, aspectRatio: 0.82, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.divider, alignItems: "center", justifyContent: "center", gap: spacing.sm },
  ghostCreate: { backgroundColor: colors.surface, borderColor: colors.sage, borderStyle: "dashed" },
  ghostPlus: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
  ghostCreateTxt: { fontSize: 12, color: colors.onSurfaceSecondary, fontFamily: fonts.displayMedium },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", alignItems: "center", justifyContent: "center", padding: spacing.xl },
  nameCard: { width: "100%", backgroundColor: colors.surface, borderRadius: 20, padding: spacing.xl },
  nameTitle: { fontSize: 18, marginBottom: spacing.md },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 48, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface, marginBottom: spacing.lg },
  row: { flexDirection: "row", gap: spacing.md },
  cancel: { flex: 1, height: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  cancelTxt: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium },
  save: { flex: 1, height: 48, borderRadius: radius.md, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
  saveTxt: { fontSize: 15, color: colors.onSage, fontFamily: fonts.displayBold },
});