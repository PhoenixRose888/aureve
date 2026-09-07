import React, { useState, useEffect, useCallback } from "react";
import { View, StyleSheet, Pressable, ActivityIndicator, TextInput, ScrollView } from "react-native";
import { Image } from "expo-image";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts, CATEGORIES, SEASONS } from "@/src/theme";
import { api } from "@/src/api/client";
import PhotoPickerModal from "@/src/components/PhotoPickerModal";
import PhotoTips from "@/src/components/PhotoTips";
import { diag } from "@/src/utils/diag";
import { useRotatingMessage } from "@/src/hooks/useRotatingMessage";
import * as haptics from "@/src/utils/haptics";

type Photos = { photo?: string; worn_photo?: string };

export default function AddItem() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const editing = !!id;

  const [photos, setPhotos] = useState<Photos>({});
  const [origPhoto, setOrigPhoto] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("Tops");
  const [colour, setColour] = useState("");
  const [fabric, setFabric] = useState("");
  const [pattern, setPattern] = useState("");
  const [season, setSeason] = useState("All");
  const [brand, setBrand] = useState("");
  const [size, setSize] = useState("");
  const [price, setPrice] = useState("");
  const [fitNotes, setFitNotes] = useState("");
  const [condition, setCondition] = useState("");
  const [flatters, setFlatters] = useState<boolean | null>(null);
  const [ai, setAi] = useState<{ style?: string; sleeve_length?: string; formality?: string; tone?: string }>({});

  const [pickerTarget, setPickerTarget] = useState<null | "photo" | "worn_photo">(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [lowConf, setLowConf] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [lastPhoto, setLastPhoto] = useState<string | null>(null);

  const analyzeMsg = useRotatingMessage(analyzing, [
    "Reading the piece…",
    "Identifying colour & fabric…",
    "Tidying up the details…",
  ]);

  useEffect(() => {
    if (!editing) return;
    (async () => {
      try {
        const it = await api<any>(`/items/${id}`);
        setPhotos({ photo: it.photo, worn_photo: it.worn_photo });
        setName(it.name || "");
        setCategory(it.category || "Tops");
        setColour(it.colour || "");
        setFabric(it.fabric || "");
        setPattern(it.pattern || "");
        setSeason(it.season || "All");
        setBrand(it.brand || "");
        setSize(it.size || "");
        setPrice(it.price != null ? String(it.price) : "");
        setFitNotes(it.fit_notes || "");
        setCondition(it.condition || "");
        setFlatters(it.flatters ?? null);
        setAi({ style: it.style, sleeve_length: it.sleeve_length, formality: it.formality, tone: it.tone });
      } catch {}
    })();
  }, [editing, id]);

  const runClean = useCallback(async (base64: string) => {
    setCleaning(true);
    diag("clean.start");
    try {
      const res = await api<any>("/clean-photo", {
        method: "POST",
        body: { image: base64 },
        timeoutMs: 90000,
      });
      if (res.clean_image) {
        setOrigPhoto(base64);
        setPhotos((p) => (p.photo === base64 ? { ...p, photo: res.clean_image } : p));
        diag("clean.done");
      } else {
        diag("clean.empty");
      }
    } catch (e: any) {
      diag("clean.failed", { error: String(e?.message || e), status: e?.status });
    }
    setCleaning(false);
  }, []);

  const runAnalyze = useCallback(
    async (base64: string, worn = false) => {
      setLastPhoto(base64);
      setAnalyzing(true);
      setError("");
      const kb = Math.round((base64.length * 3) / 4 / 1024);
      diag("analyze.start", { kb, worn });
      let res: any = null;
      for (let attempt = 1; attempt <= 2 && !res; attempt++) {
        try {
          res = await api<any>("/capture", {
            method: "POST",
            body: { image: base64, clean: false, worn },
            timeoutMs: 60000,
          });
        } catch (e: any) {
          diag("analyze.error", { attempt, status: e?.status, timeout: !!e?.timeout, error: String(e?.message || e) });
          if (attempt === 2) {
            setError("Couldn't auto-detect this one. Add the details below, or try again.");
            haptics.warn();
          }
        }
      }
      setAnalyzing(false);
      if (!res) return;
      const r = res.analysis || {};
      diag("analyze.done", { name: r.name, category: r.category, confidence: r.confidence });
      if (!r.name && !r.category) {
        setError("Couldn't auto-detect this one. Add the details below, or try again.");
        haptics.warn();
        return;
      }
      if (r.name && !name) setName(r.name);
      if (r.category && CATEGORIES.includes(r.category)) setCategory(r.category);
      setLowConf(typeof r.confidence === "number" && r.confidence < 60);
      if (r.colour) setColour(r.colour);
      if (r.fabric) setFabric(r.fabric);
      if (r.pattern) setPattern(r.pattern);
      if (r.season && SEASONS.includes(r.season)) setSeason(r.season);
      if (r.condition) setCondition(r.condition);
      setAi({ style: r.style, sleeve_length: r.sleeve_length, formality: r.formality, tone: r.tone });
      haptics.success();
      if (!worn) runClean(base64);
    },
    [name, runClean]
  );

  const onPicked = useCallback(
    async (base64: string) => {
      if (pickerTarget === "worn_photo") {
        setPhotos((p) => ({ ...p, worn_photo: base64 }));
        if (!photos.photo) runAnalyze(base64, true);
        return;
      }
      setPhotos((p) => ({ ...p, photo: base64 }));
      setOrigPhoto(null);
      runAnalyze(base64);
    },
    [pickerTarget, runAnalyze, photos.photo]
  );

  const save = async () => {
    if (!photos.photo && !photos.worn_photo) {
      setError("Add a photo of the item before saving.");
      haptics.warn();
      return;
    }
    setSaving(true);
    setError("");
    const finalName = name.trim() || (colour ? `${colour} ${category.toLowerCase()}` : `New ${category.toLowerCase()}`);
    const body: any = {
      name: finalName,
      category,
      colour,
      fabric,
      pattern,
      season,
      style: ai.style || "",
      sleeve_length: ai.sleeve_length || "",
      formality: ai.formality || "",
      tone: ai.tone || "",
      brand,
      size,
      fit_notes: fitNotes,
      condition,
      price: price ? parseFloat(price) : null,
      photo: photos.photo || null,
      worn_photo: photos.worn_photo || null,
      flatters,
    };
    try {
      if (editing) {
        await api(`/items/${id}`, { method: "PUT", body });
      } else {
        await api("/items", { method: "POST", body });
      }
      router.back();
    } catch (e: any) {
      setError(e.message || "Failed to save");
      setSaving(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="add-item-close" hitSlop={12}>
          <Feather name="x" size={24} color={colors.onSurface} />
        </Pressable>
        <Display weight="semibold" style={styles.headerTitle}>{editing ? "Edit piece" : "New piece"}</Display>
        {editing ? (
          <View style={{ width: 56 }} />
        ) : (
          <Pressable style={styles.bulkBtn} onPress={() => router.replace("/bulk-add")} testID="add-item-bulk" hitSlop={8}>
            <Feather name="layers" size={13} color={colors.onSurface} />
            <Txt style={styles.bulkLink}>Bulk Add</Txt>
          </Pressable>
        )}
      </View>

      <KeyboardAwareScrollView
        style={{ flex: 1 }}
        contentContainerStyle={styles.scroll}
        bottomOffset={90}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.photoRow}>
          <Pressable style={styles.photoBox} testID="add-photo-hanging" onPress={() => setPickerTarget("photo")}>
            {photos.photo ? (
              <Image source={{ uri: `data:image/jpeg;base64,${photos.photo}` }} style={styles.photoImg} contentFit="cover" />
            ) : (
              <View style={styles.photoEmpty}>
                <Feather name="camera" size={22} color={colors.onSurfaceTertiary} />
                <Txt style={styles.photoLabel}>Hanging photo</Txt>
              </View>
            )}
            {analyzing && (
              <View style={styles.analyzeOverlay}>
                <ActivityIndicator color={colors.onSurfaceInverse} />
                <Txt style={styles.analyzeTxt}>{analyzeMsg}</Txt>
              </View>
            )}
            {!analyzing && cleaning ? (
              <View style={styles.cleanPill} testID="cleaning-pill">
                <ActivityIndicator size="small" color={colors.onSurfaceInverse} />
                <Txt style={styles.cleanTxt}>Tidying photo…</Txt>
              </View>
            ) : null}
            {!analyzing && origPhoto && photos.photo ? (
              <Pressable
                style={styles.revertPill}
                testID="revert-photo"
                onPress={() => {
                  setPhotos((p) => ({ ...p, photo: origPhoto }));
                  setOrigPhoto(null);
                }}
              >
                <Feather name="rotate-ccw" size={11} color={colors.onBrandPrimary} />
                <Txt style={styles.revertTxt}>Original</Txt>
              </Pressable>
            ) : null}
          </Pressable>
          <Pressable style={styles.photoBox} testID="add-photo-worn" onPress={() => setPickerTarget("worn_photo")}>
            {photos.worn_photo ? (
              <Image source={{ uri: `data:image/jpeg;base64,${photos.worn_photo}` }} style={styles.photoImg} contentFit="cover" />
            ) : (
              <View style={styles.photoEmpty}>
                <Feather name="user" size={22} color={colors.onSurfaceTertiary} />
                <Txt style={styles.photoLabel}>Worn photo</Txt>
                <Txt style={styles.photoHint}>Optional — Aureve can read the piece from this too</Txt>
              </View>
            )}
          </Pressable>
        </View>

        {error ? (
          <View style={styles.errorRow}>
            <Txt style={styles.error} testID="add-item-error">{error}</Txt>
            {lastPhoto ? (
              <Pressable style={styles.retryBtn} testID="analyze-retry" onPress={() => runAnalyze(lastPhoto)}>
                <Feather name="refresh-cw" size={13} color={colors.onSurface} />
                <Txt style={styles.retryTxt}>Try again</Txt>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        <PhotoTips />

        <Field label="Name (optional — AI fills it)" value={name} onChangeText={setName} placeholder="e.g. Cream linen blazer" testID="field-name" />

        <Txt style={styles.groupLabel}>CATEGORY</Txt>
        {lowConf ? (
          <View style={styles.confirmBanner} testID="low-confidence-banner">
            <Feather name="help-circle" size={15} color={colors.warning} />
            <Txt style={styles.confirmTxt}>
              Aureve is not fully sure about this one — please check the name and category below before saving.
            </Txt>
          </View>
        ) : null}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipContent}>
          {CATEGORIES.map((c) => (
            <Pressable key={c} testID={`cat-${c}`} style={[styles.chip, category === c && styles.chipActive]} onPress={() => setCategory(c)}>
              <Txt style={[styles.chipTxt, category === c && styles.chipTxtActive]}>{c}</Txt>
            </Pressable>
          ))}
        </ScrollView>

        <View style={styles.row2}>
          <Field label="Colour" value={colour} onChangeText={setColour} placeholder="Cream" flex testID="field-colour" />
          <Field label="Pattern" value={pattern} onChangeText={setPattern} placeholder="Solid" flex testID="field-pattern" />
        </View>

        <Txt style={styles.groupLabel}>SEASON</Txt>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipContent}>
          {SEASONS.map((s) => (
            <Pressable key={s} testID={`season-${s}`} style={[styles.chip, season === s && styles.chipActive]} onPress={() => setSeason(s)}>
              <Txt style={[styles.chipTxt, season === s && styles.chipTxtActive]}>{s}</Txt>
            </Pressable>
          ))}
        </ScrollView>

        <Field label="Fit notes" value={fitNotes} onChangeText={setFitNotes} placeholder="Runs small, flattering waist…" multiline testID="field-fit" />
      </KeyboardAwareScrollView>

      <KeyboardStickyView offset={{ closed: 0, opened: 0 }}>
        <View style={[styles.footer, { paddingBottom: insets.bottom || spacing.lg }]}>
          <Pressable style={styles.saveBtn} testID="save-item-button" onPress={save} disabled={saving}>
            {saving ? (
              <ActivityIndicator color={colors.onBrandPrimary} />
            ) : (
              <Txt style={styles.saveTxt}>{editing ? "Save changes" : "Add to wardrobe"}</Txt>
            )}
          </Pressable>
        </View>
      </KeyboardStickyView>

      <PhotoPickerModal
        visible={pickerTarget !== null}
        onClose={() => setPickerTarget(null)}
        onPicked={onPicked}
        title={pickerTarget === "worn_photo" ? "Add a worn photo" : "Add item photo"}
      />
    </View>
  );
}

function Field({ label, flex, multiline, testID, ...rest }: any) {
  return (
    <View style={[styles.field, flex && { flex: 1 }]}>
      <Txt style={styles.fieldLabel}>{label}</Txt>
      <TextInput
        style={[styles.input, multiline && styles.inputMulti]}
        placeholderTextColor={colors.onSurfaceTertiary}
        multiline={multiline}
        testID={testID}
        {...rest}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.xl,
    paddingBottom: spacing.md,
    borderBottomWidth: 0.5,
    borderBottomColor: colors.border,
  },
  headerTitle: { fontSize: 22 },
  bulkBtn: {
    flexDirection: "row", alignItems: "center", gap: 5,
    borderWidth: 0.5, borderColor: colors.borderStrong, borderRadius: radius.pill,
    paddingHorizontal: spacing.md, height: 32,
  },
  bulkLink: { fontSize: 14, color: colors.brand },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  photoRow: { flexDirection: "row", gap: spacing.md },
  photoBox: {
    flex: 1,
    aspectRatio: 0.8,
    borderRadius: radius.md,
    borderWidth: 0.5,
    borderColor: colors.border,
    overflow: "hidden",
    backgroundColor: colors.surfaceSecondary,
  },
  photoImg: { width: "100%", height: "100%" },
  photoEmpty: { flex: 1, alignItems: "center", justifyContent: "center", gap: 6, padding: spacing.md },
  photoLabel: { fontSize: 13, color: colors.onSurfaceSecondary },
  photoHint: { fontSize: 10, color: colors.onSurfaceTertiary, textAlign: "center" },
  analyzeOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(26,26,26,0.55)", alignItems: "center", justifyContent: "center", gap: 8 },
  analyzeTxt: { color: colors.onSurfaceInverse, fontSize: 12 },
  revertPill: { position: "absolute", bottom: 6, right: 6, flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary, paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill },
  revertTxt: { color: colors.onBrandPrimary, fontSize: 10 },
  error: { color: colors.error, fontSize: 13, flex: 1, lineHeight: 18 },
  errorRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.lg },
  retryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    borderWidth: 0.5, borderColor: colors.borderStrong, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, height: 36,
  },
  retryTxt: { fontSize: 13, color: colors.onSurface },
  cleanPill: {
    position: "absolute", bottom: 6, left: 6, flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: "rgba(26,26,26,0.6)", paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill,
  },
  cleanTxt: { color: colors.onSurfaceInverse, fontSize: 10 },
  field: { marginTop: spacing.xl },
  fieldLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginBottom: spacing.sm },
  input: {
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.onSurface,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    paddingVertical: spacing.sm,
  },
  inputMulti: { minHeight: 60, textAlignVertical: "top" },
  row2: { flexDirection: "row", gap: spacing.lg },
  groupLabel: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginTop: spacing.xl, marginBottom: spacing.md },
  chipContent: { gap: spacing.sm, paddingRight: spacing.xl },
  confirmBanner: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, padding: spacing.md, marginBottom: spacing.md },
  confirmTxt: { flex: 1, fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 18 },
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
  footer: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    borderTopWidth: 0.5,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  saveBtn: {
    backgroundColor: colors.brandPrimary,
    height: 54,
    borderRadius: radius.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  saveTxt: { color: colors.onBrandPrimary, fontSize: 16, fontFamily: fonts.displayBold },
});
