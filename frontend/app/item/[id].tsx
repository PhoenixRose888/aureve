import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Dimensions, ActivityIndicator, Modal } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";

const { width } = Dimensions.get("window");

export default function ItemDetail() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [item, setItem] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [logged, setLogged] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItem(await api<any>(`/items/${id}`));
    } catch {}
    setLoading(false);
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const photos = item ? [item.photo, item.worn_photo].filter(Boolean) : [];

  const logWear = async () => {
    try {
      await api("/wear", { method: "POST", body: { item_ids: [id], occasion: item?.name } });
      setLogged(true);
      load();
    } catch {}
  };

  const doDelete = async () => {
    try {
      await api(`/items/${id}`, { method: "DELETE" });
      router.back();
    } catch {}
  };

  if (loading) {
    return <View style={styles.center}><ActivityIndicator color={colors.onSurface} /></View>;
  }
  if (!item) {
    return (
      <View style={styles.center}>
        <Txt>Item not found</Txt>
        <Pressable onPress={() => router.back()}><Txt style={{ color: colors.brand, marginTop: 8 }}>Go back</Txt></Pressable>
      </View>
    );
  }

  const cpw = item.price && item.wear_count > 0 ? (item.price / item.wear_count).toFixed(2) : null;

  return (
    <View style={styles.container}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: spacing["3xl"] }}>
        {/* Gallery */}
        <View style={styles.gallery}>
          {photos.length > 0 ? (
            <ScrollView
              horizontal
              pagingEnabled
              showsHorizontalScrollIndicator={false}
              onMomentumScrollEnd={(e) => setPage(Math.round(e.nativeEvent.contentOffset.x / width))}
            >
              {photos.map((p: string, i: number) => (
                <Image key={i} source={{ uri: `data:image/jpeg;base64,${p}` }} style={styles.galleryImg} contentFit="cover" />
              ))}
            </ScrollView>
          ) : (
            <View style={[styles.galleryImg, styles.placeholder]}>
              <Feather name="image" size={40} color={colors.onSurfaceTertiary} />
            </View>
          )}

          {/* top controls */}
          <View style={[styles.topBar, { top: insets.top + spacing.sm }]}>
            <Pressable style={styles.circleBtn} testID="item-back" onPress={() => router.back()}>
              <Feather name="arrow-left" size={20} color={colors.onSurfaceInverse} />
            </Pressable>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Pressable style={styles.circleBtn} testID="item-edit" onPress={() => router.push({ pathname: "/add-item", params: { id } })}>
                <Feather name="edit-2" size={18} color={colors.onSurfaceInverse} />
              </Pressable>
              <Pressable style={styles.circleBtn} testID="item-delete" onPress={() => setConfirmDelete(true)}>
                <Feather name="trash-2" size={18} color={colors.onSurfaceInverse} />
              </Pressable>
            </View>
          </View>

          {photos.length > 1 && (
            <View style={styles.dots}>
              {photos.map((_: any, i: number) => (
                <View key={i} style={[styles.pageDot, page === i && styles.pageDotActive]} />
              ))}
            </View>
          )}
        </View>

        <View style={styles.body}>
          <Txt style={styles.category}>{item.category?.toUpperCase()}{item.brand ? ` · ${item.brand}` : ""}</Txt>
          <Display weight="medium" style={styles.name}>{item.name}</Display>

          {/* Stats */}
          <View style={styles.statRow}>
            <View style={styles.stat}>
              <Display weight="medium" style={styles.statNum}>{item.wear_count || 0}</Display>
              <Txt style={styles.statLabel}>times worn</Txt>
            </View>
            <View style={styles.statDiv} />
            <View style={styles.stat}>
              <Display weight="medium" style={styles.statNum}>{cpw ? `$${cpw}` : "—"}</Display>
              <Txt style={styles.statLabel}>cost / wear</Txt>
            </View>
            <View style={styles.statDiv} />
            <View style={styles.stat}>
              <Display weight="medium" style={styles.statNum}>{item.price ? `$${item.price}` : "—"}</Display>
              <Txt style={styles.statLabel}>bought for</Txt>
            </View>
          </View>

          {/* Flatter tag */}
          {item.flatters != null && (
            <View style={[styles.flatterTag, { backgroundColor: item.flatters ? colors.brandTertiary : colors.surfaceSecondary }]}>
              <Feather name={item.flatters ? "thumbs-up" : "thumbs-down"} size={14} color={item.flatters ? colors.brand : colors.onSurfaceTertiary} />
              <Txt style={[styles.flatterTagTxt, { color: item.flatters ? colors.onBrandTertiary : colors.onSurfaceTertiary }]}>
                {item.flatters ? "This flatters you" : "Not the most flattering"}
              </Txt>
            </View>
          )}

          {/* Attributes */}
          <View style={styles.attrs}>
            <Attr label="Colour" value={item.colour} />
            <Attr label="Fabric" value={item.fabric} />
            <Attr label="Pattern" value={item.pattern} />
            <Attr label="Season" value={item.season} />
            <Attr label="Size" value={item.size} />
            <Attr label="Condition" value={item.condition} />
          </View>

          {item.fit_notes ? (
            <View style={styles.notes}>
              <Txt style={styles.notesLabel}>FIT NOTES</Txt>
              <Txt style={styles.notesTxt}>{item.fit_notes}</Txt>
            </View>
          ) : null}

          <Pressable style={styles.wearBtn} testID="log-wear-item" onPress={logWear} disabled={logged}>
            <Feather name={logged ? "check" : "plus"} size={17} color={colors.onBrandPrimary} />
            <Txt style={styles.wearTxt}>{logged ? "Logged today" : "I wore this today"}</Txt>
          </Pressable>
        </View>
      </ScrollView>

      {/* delete confirm */}
      <Modal visible={confirmDelete} transparent animationType="fade" onRequestClose={() => setConfirmDelete(false)}>
        <Pressable style={styles.backdrop} onPress={() => setConfirmDelete(false)}>
          <Pressable style={styles.confirmSheet} onPress={(e) => e.stopPropagation()}>
            <Display weight="medium" style={styles.confirmTitle}>Remove this piece?</Display>
            <Txt style={styles.confirmSub}>It will be removed from your wardrobe and any looks.</Txt>
            <Pressable style={styles.deleteBtn} testID="confirm-delete-button" onPress={doDelete}>
              <Txt style={styles.deleteTxt}>Delete</Txt>
            </Pressable>
            <Pressable style={styles.cancelBtn} onPress={() => setConfirmDelete(false)}>
              <Txt style={styles.cancelTxt}>Keep it</Txt>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function Attr({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <View style={styles.attrRow}>
      <Txt style={styles.attrLabel}>{label}</Txt>
      <Txt style={styles.attrValue}>{value}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  gallery: { height: width * 1.15, backgroundColor: colors.surfaceSecondary },
  galleryImg: { width, height: width * 1.15 },
  placeholder: { alignItems: "center", justifyContent: "center" },
  topBar: { position: "absolute", left: spacing.lg, right: spacing.lg, flexDirection: "row", justifyContent: "space-between" },
  circleBtn: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: "rgba(26,26,26,0.4)", alignItems: "center", justifyContent: "center" },
  dots: { position: "absolute", bottom: spacing.lg, alignSelf: "center", flexDirection: "row", gap: 6 },
  pageDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "rgba(250,250,250,0.5)" },
  pageDotActive: { backgroundColor: colors.onSurfaceInverse, width: 18 },
  body: { padding: spacing.xl },
  category: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary },
  name: { fontSize: 32, marginTop: spacing.xs, lineHeight: 36 },
  statRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.xl, paddingVertical: spacing.lg, borderTopWidth: 0.5, borderBottomWidth: 0.5, borderColor: colors.divider },
  stat: { flex: 1, alignItems: "center", gap: 4 },
  statDiv: { width: 0.5, height: 36, backgroundColor: colors.divider },
  statNum: { fontSize: 24, color: colors.onSurface },
  statLabel: { fontSize: 11, color: colors.onSurfaceTertiary },
  flatterTag: { flexDirection: "row", alignItems: "center", gap: spacing.sm, alignSelf: "flex-start", paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, marginTop: spacing.lg },
  flatterTagTxt: { fontSize: 13 },
  attrs: { marginTop: spacing.xl },
  attrRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.md, borderBottomWidth: 0.5, borderColor: colors.divider },
  attrLabel: { fontSize: 13, color: colors.onSurfaceTertiary },
  attrValue: { fontSize: 14, color: colors.onSurface, textTransform: "capitalize" },
  notes: { marginTop: spacing.xl },
  notesLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginBottom: spacing.sm },
  notesTxt: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22 },
  wearBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, height: 54, borderRadius: radius.sm, marginTop: spacing["2xl"] },
  wearTxt: { color: colors.onBrandPrimary, fontSize: 16 },
  backdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.45)", justifyContent: "flex-end" },
  confirmSheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, paddingBottom: spacing["2xl"] },
  confirmTitle: { fontSize: 24, marginBottom: spacing.sm },
  confirmSub: { fontSize: 14, color: colors.onSurfaceSecondary, marginBottom: spacing.xl },
  deleteBtn: { backgroundColor: colors.error, height: 52, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  deleteTxt: { color: colors.onError, fontSize: 15 },
  cancelBtn: { alignItems: "center", paddingVertical: spacing.md, marginTop: spacing.sm },
  cancelTxt: { fontSize: 15, color: colors.onSurfaceTertiary },
});
