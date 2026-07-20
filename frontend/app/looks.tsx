import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, Modal } from "react-native";
import { Image } from "expo-image";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

const sourceLabel: Record<string, string> = { ai: "AI STYLED", manual: "SAVED", capsule: "CAPSULE" };

export default function Looks() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [tab, setTab] = useState<"saved" | "history">("saved");
  const [outfits, setOutfits] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [toDelete, setToDelete] = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [o, h] = await Promise.all([api<any[]>("/outfits"), api<any[]>("/wear")]);
      setOutfits(o);
      setHistory(h);
    } catch {}
    setLoading(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const doDelete = async () => {
    if (!toDelete) return;
    await api(`/outfits/${toDelete.id}`, { method: "DELETE" });
    setToDelete(null);
    load();
  };

  const Thumbs = ({ items }: { items: any[] }) => (
    <View style={styles.thumbs}>
      {items.slice(0, 5).map((it) =>
        it.photo ? (
          <Image key={it.id} source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={styles.thumb} contentFit="cover" />
        ) : (
          <View key={it.id} style={[styles.thumb, styles.placeholder]}>
            <Feather name="image" size={12} color={colors.onSurfaceTertiary} />
          </View>
        )
      )}
      {items.length > 5 ? <View style={[styles.thumb, styles.more]}><Txt style={styles.moreTxt}>+{items.length - 5}</Txt></View> : null}
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="looks-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Display weight="medium" style={styles.headerTitle}>Looks</Display>
        <View style={{ width: 24 }} />
      </View>

      <View style={styles.segment}>
        <Pressable style={[styles.segBtn, tab === "saved" && styles.segActive]} testID="tab-saved" onPress={() => setTab("saved")}>
          <Txt style={[styles.segTxt, tab === "saved" && styles.segTxtActive]}>Saved looks</Txt>
        </Pressable>
        <Pressable style={[styles.segBtn, tab === "history" && styles.segActive]} testID="tab-history" onPress={() => setTab("history")}>
          <Txt style={[styles.segTxt, tab === "history" && styles.segTxtActive]}>History</Txt>
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.onSurface} /></View>
      ) : tab === "saved" ? (
        outfits.length === 0 ? (
          <Empty icon="bookmark" text="No saved looks yet. Save outfits from the Stylist or capsules from Packing." />
        ) : (
          <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
            {outfits.map((o) => (
              <View key={o.id} style={styles.card} testID={`look-${o.id}`}>
                <View style={styles.cardHead}>
                  <View style={{ flex: 1 }}>
                    <Txt style={styles.sourceBadge}>{sourceLabel[o.source] || "SAVED"}</Txt>
                    <Display weight="medium" style={styles.cardTitle}>{o.name}</Display>
                    {o.occasion ? <Txt style={styles.cardMeta}>{o.occasion}</Txt> : null}
                  </View>
                  <Pressable onPress={() => setToDelete(o)} testID={`delete-look-${o.id}`} hitSlop={10}>
                    <Feather name="trash-2" size={18} color={colors.onSurfaceTertiary} />
                  </Pressable>
                </View>
                <Thumbs items={o.items || []} />
              </View>
            ))}
          </ScrollView>
        )
      ) : history.length === 0 ? (
        <Empty icon="clock" text="No wear history yet. Tap 'I wore this' on an outfit or item to start tracking." />
      ) : (
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          {history.map((h) => (
            <View key={h.id} style={styles.card} testID={`history-${h.id}`}>
              <View style={styles.cardHead}>
                <View style={{ flex: 1 }}>
                  <Txt style={styles.sourceBadge}>{fmtDate(h.created_at)}</Txt>
                  <Display weight="medium" style={styles.cardTitle}>{h.occasion || "Everyday look"}</Display>
                </View>
                <View style={styles.ratingChips}>
                  <RatingChip label="Flatter" value={h.flattering} />
                  <RatingChip label="Comfort" value={h.comfort} />
                  <RatingChip label="Confid." value={h.confidence} />
                </View>
              </View>
              <Thumbs items={h.items || []} />
            </View>
          ))}
        </ScrollView>
      )}

      <Modal visible={!!toDelete} transparent animationType="fade" onRequestClose={() => setToDelete(null)}>
        <Pressable style={styles.backdrop} onPress={() => setToDelete(null)}>
          <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
            <Display weight="medium" style={styles.confirmTitle}>Delete this look?</Display>
            <Pressable style={styles.deleteBtn} testID="confirm-delete-look" onPress={doDelete}>
              <Txt style={styles.deleteTxt}>Delete</Txt>
            </Pressable>
            <Pressable style={styles.cancelBtn} onPress={() => setToDelete(null)}>
              <Txt style={styles.cancelTxt}>Keep it</Txt>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function Empty({ icon, text }: { icon: string; text: string }) {
  return (
    <View style={styles.empty}>
      <Feather name={icon as any} size={26} color={colors.onSurfaceTertiary} />
      <Txt style={styles.emptyTxt}>{text}</Txt>
    </View>
  );
}

function RatingChip({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.rChip}>
      <Txt style={styles.rChipVal}>{value}</Txt>
      <Txt style={styles.rChipLabel}>{label}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
  headerTitle: { fontSize: 22 },
  segment: { flexDirection: "row", marginHorizontal: spacing.xl, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.sm, overflow: "hidden", marginBottom: spacing.lg },
  segBtn: { flex: 1, paddingVertical: spacing.md, alignItems: "center" },
  segActive: { backgroundColor: colors.brandPrimary },
  segTxt: { fontSize: 14, color: colors.onSurfaceSecondary },
  segTxtActive: { color: colors.onBrandPrimary },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  scroll: { paddingHorizontal: spacing.xl, paddingBottom: spacing["3xl"] },
  card: { borderBottomWidth: 0.5, borderColor: colors.divider, paddingVertical: spacing.lg },
  cardHead: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: spacing.md },
  sourceBadge: { fontSize: 10, letterSpacing: 1.5, color: colors.brand, marginBottom: 2 },
  cardTitle: { fontSize: 20, lineHeight: 24 },
  cardMeta: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  thumbs: { flexDirection: "row", gap: spacing.sm },
  thumb: { width: 54, height: 68, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  placeholder: { alignItems: "center", justifyContent: "center" },
  more: { alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  moreTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  ratingChips: { flexDirection: "row", gap: spacing.sm },
  rChip: { alignItems: "center" },
  rChipVal: { fontSize: 16, color: colors.onSurface },
  rChipLabel: { fontSize: 9, color: colors.onSurfaceTertiary, letterSpacing: 0.3 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, paddingHorizontal: spacing["2xl"] },
  emptyTxt: { fontSize: 14, color: colors.onSurfaceTertiary, textAlign: "center", lineHeight: 20 },
  backdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.45)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, paddingBottom: spacing["2xl"] },
  confirmTitle: { fontSize: 22, marginBottom: spacing.lg },
  deleteBtn: { backgroundColor: colors.error, height: 52, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  deleteTxt: { color: colors.onError, fontSize: 15 },
  cancelBtn: { alignItems: "center", paddingVertical: spacing.md, marginTop: spacing.sm },
  cancelTxt: { fontSize: 15, color: colors.onSurfaceTertiary },
});
