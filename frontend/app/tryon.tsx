import React, { useState, useEffect, useCallback } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";
import PhotoPickerModal from "@/src/components/PhotoPickerModal";

export default function TryOn() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ items?: string }>();

  const [picker, setPicker] = useState(false);
  const [person, setPerson] = useState<string | null>(null);
  const [items, setItems] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const all = await api<any[]>("/items");
      setItems(all.filter((i) => i.photo));
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  useEffect(() => {
    if (params.items) setSelected(String(params.items).split(",").filter(Boolean));
  }, [params.items]);

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const generate = async () => {
    if (!person) { setError("Add a full-body photo of yourself first."); return; }
    if (selected.length === 0) { setError("Pick at least one piece to try on."); return; }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const r = await api<any>("/tryon", { method: "POST", body: { person_image: person, item_ids: selected } });
      setResult(r.image);
    } catch (e: any) {
      if (e.status === 402) router.push("/premium");
      else setError(e.message || "Couldn't generate your try-on. Try a clearer full-body photo.");
    }
    setLoading(false);
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="tryon-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt style={styles.kicker}>VIRTUAL TRY-ON</Txt>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Display weight="medium" style={styles.title}>See it on you</Display>
        <Txt style={styles.sub}>Add a full-body photo, pick pieces from your wardrobe, and preview the look on you.</Txt>

        <Txt style={styles.groupLabel}>YOUR PHOTO</Txt>
        <Pressable style={styles.photoCard} testID="tryon-pick-photo" onPress={() => setPicker(true)}>
          {person ? (
            <Image source={{ uri: `data:image/jpeg;base64,${person}` }} style={styles.photoImg} contentFit="cover" />
          ) : (
            <View style={styles.photoEmpty}>
              <Feather name="camera" size={26} color={colors.onSurfaceTertiary} />
              <Txt style={styles.photoEmptyTxt}>Add a full-body photo</Txt>
            </View>
          )}
          {person ? (
            <View style={styles.photoEditPill}>
              <Feather name="refresh-cw" size={12} color={colors.onBrandPrimary} />
              <Txt style={styles.photoEditTxt}>Change</Txt>
            </View>
          ) : null}
        </Pressable>

        <Txt style={styles.groupLabel}>PICK PIECES {selected.length > 0 ? `· ${selected.length}` : ""}</Txt>
        {items.length === 0 ? (
          <Txt style={styles.hint}>Add photos to your wardrobe items to try them on.</Txt>
        ) : (
          <View style={styles.grid}>
            {items.map((it) => {
              const on = selected.includes(it.id);
              return (
                <Pressable key={it.id} style={styles.gridItem} testID={`tryon-item-${it.id}`} onPress={() => toggle(it.id)}>
                  <Image source={{ uri: `data:image/jpeg;base64,${it.photo}` }} style={[styles.gridImg, on && styles.gridImgOn]} contentFit="cover" />
                  {on && (
                    <View style={styles.check}><Feather name="check" size={13} color={colors.onBrandPrimary} /></View>
                  )}
                  <Txt style={styles.gridName} numberOfLines={1}>{it.name}</Txt>
                </Pressable>
              );
            })}
          </View>
        )}

        {error ? <Txt style={styles.error} testID="tryon-error">{error}</Txt> : null}

        <Pressable style={styles.genBtn} testID="tryon-generate" onPress={generate} disabled={loading}>
          {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : (
            <>
              <Feather name="image" size={17} color={colors.onBrandPrimary} />
              <Txt style={styles.genTxt}>{result ? "Try again" : "Try it on"}</Txt>
            </>
          )}
        </Pressable>
        {loading && <Txt style={styles.loadingTxt}>Styling the look onto your photo… this takes a moment.</Txt>}

        {result && !loading ? (
          <View style={styles.resultWrap} testID="tryon-result">
            <Image source={{ uri: `data:image/png;base64,${result}` }} style={styles.resultImg} contentFit="contain" />
            <Txt style={styles.resultNote}>AI-generated preview — fit and detail may vary.</Txt>
          </View>
        ) : null}
      </ScrollView>

      <PhotoPickerModal
        visible={picker}
        onClose={() => setPicker(false)}
        onPicked={(b64) => { setPerson(b64); setResult(null); }}
        title="Add your photo"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  kicker: { fontSize: 11, letterSpacing: 2, color: colors.onSurfaceTertiary },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  title: { fontSize: 30, color: colors.onSurface },
  sub: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21, marginTop: spacing.sm },
  groupLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginTop: spacing.xl, marginBottom: spacing.md },
  photoCard: { height: 220, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, overflow: "hidden", justifyContent: "center", alignItems: "center" },
  photoImg: { ...StyleSheet.absoluteFillObject },
  photoEmpty: { alignItems: "center", gap: spacing.sm },
  photoEmptyTxt: { fontSize: 13, color: colors.onSurfaceTertiary },
  photoEditPill: { position: "absolute", bottom: spacing.md, right: spacing.md, flexDirection: "row", alignItems: "center", gap: 5, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill },
  photoEditTxt: { color: colors.onBrandPrimary, fontSize: 12 },
  hint: { fontSize: 13, color: colors.onSurfaceTertiary, fontStyle: "italic" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  gridItem: { width: "30%" },
  gridImg: { width: "100%", aspectRatio: 0.8, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary, borderWidth: 2, borderColor: "transparent" },
  gridImgOn: { borderColor: colors.brand },
  check: { position: "absolute", top: 6, right: 6, width: 22, height: 22, borderRadius: 11, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  gridName: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 4 },
  error: { color: colors.error, fontSize: 13, marginTop: spacing.lg },
  genBtn: { backgroundColor: colors.brandPrimary, height: 54, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, marginTop: spacing.xl },
  genTxt: { color: colors.onBrandPrimary, fontSize: 16 },
  loadingTxt: { textAlign: "center", color: colors.onSurfaceTertiary, fontSize: 13, marginTop: spacing.md, fontStyle: "italic" },
  resultWrap: { marginTop: spacing.xl },
  resultImg: { width: "100%", height: 460, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  resultNote: { fontSize: 12, color: colors.onSurfaceTertiary, textAlign: "center", marginTop: spacing.sm },
});
