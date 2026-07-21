import React, { useState, useEffect, useCallback } from "react";
import { View, StyleSheet, Pressable, ActivityIndicator, TextInput, ScrollView, Modal } from "react-native";
import { Image } from "expo-image";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts, CATEGORIES, SEASONS } from "@/src/theme";
import { api } from "@/src/api/client";
import PhotoPickerModal from "@/src/components/PhotoPickerModal";
import { useRotatingMessage } from "@/src/hooks/useRotatingMessage";
import * as haptics from "@/src/utils/haptics";
import GarmentImage from "@/src/components/GarmentImage";

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
  const [hintPhoto, setHintPhoto] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [duplicates, setDuplicates] = useState<any[]>([]);

  const analyzeMsg = useRotatingMessage(analyzing, [
    "Reading the piece…",
    "Identifying colour & fabric…",
    "Removing the background…",
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

  const runAnalyze = useCallback(
    async (base64: string, hint?: string) => {
      if (hint && CATEGORIES.includes(hint)) setCategory(hint);
      setAnalyzing(true);
      setError("");
      try {
        const res = await api<any>("/capture", {
          method: "POST",
          body: { image: base64, category_hint: hint || null, clean: true },
        });
        const r = res.analysis || {};
        // Swap in the clean, background-removed photo (fall back to the original).
        if (res.clean_image) {
          setOrigPhoto(base64);
          setPhotos((p) => ({ ...p, photo: res.clean_image }));
        }
        if (r.name && !name) setName(r.name);
        if (r.category && CATEGORIES.includes(r.category) && !hint) setCategory(r.category);
        if (r.colour) setColour(r.colour);
        if (r.fabric) setFabric(r.fabric);
        if (r.pattern) setPattern(r.pattern);
        if (r.season && SEASONS.includes(r.season)) setSeason(r.season);
        if (r.condition) setCondition(r.condition);
        if (r.estimated_value && !price) setPrice(String(r.estimated_value));
        setAi({ style: r.style, sleeve_length: r.sleeve_length, formality: r.formality, tone: r.tone });
        setDuplicates(Array.isArray(res.duplicates) ? res.duplicates : []);
        haptics.success();
      } catch {
        setError("Couldn't auto-detect. Fill details manually.");
        haptics.warn();
      }
      setAnalyzing(false);
    },
    [name, price]
  );

  const onPicked = useCallback(
    async (base64: string) => {
      if (pickerTarget === "worn_photo") {
        setPhotos((p) => ({ ...p, worn_photo: base64 }));
        return;
      }
      setPhotos((p) => ({ ...p, photo: base64 }));
      // Ask which piece to focus on before AI reads it (handles worn / multi-garment photos)
      setHintPhoto(base64);
    },
    [pickerTarget]
  );

  const save = async () => {
    if (!photos.photo) {
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
          <Pressable onPress={() => router.replace("/bulk-add")} testID="add-item-bulk" hitSlop={8}>
            <Txt style={styles.bulkLink}>Several</Txt>
          </Pressable>
        )}
      </View>

      <KeyboardAwareScrollView
        style={{ flex: 1 }}
        contentContainerStyle={styles.scroll}
        bottomOffset={90}
        showsVerticalScrollIndicator={false}
      >
        {/* Photos */}
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
                <Txt style={styles.photoHint}>Helps Aureve learn what flatters you</Txt>
              </View>
            )}
          </Pressable>
        </View>

        {error ? <Txt style={styles.error} testID="add-item-error">{error}</Txt> : null}

        {duplicates.length > 0 ? (
          <View style={styles.dupBanner} testID="add-item-duplicates">
            <View style={styles.dupHeader}>
              <Feather name="copy" size={15} color={colors.onSurface} />
              <Txt style={styles.dupTitle}>You may already own this</Txt>
              <Pressable onPress={() => setDuplicates([])} testID="dup-dismiss" hitSlop={10}>
                <Feather name="x" size={16} color={colors.onSurfaceTertiary} />
              </Pressable>
            </View>
            <Txt style={styles.dupSub}>Similar pieces in your wardrobe — add anyway or skip to avoid a duplicate.</Txt>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.dupRow}>
              {duplicates.map((d) => (
                <Pressable key={d.id} style={styles.dupCard} testID={`dup-${d.id}`} onPress={() => router.push({ pathname: "/item/[id]", params: { id: d.id } })}>
                  <GarmentImage photo={d.photo} category={d.category} style={styles.dupImg} iconSize={18} />
                  <Txt style={styles.dupName} numberOfLines={1}>{d.name || d.category}</Txt>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        ) : null}

        <Field label="Name (optional — AI fills it)" value={name} onChangeText={setName} placeholder="e.g. Cream linen blazer" testID="field-name" />

        <Txt style={styles.groupLabel}>CATEGORY</Txt>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipContent}>
          {CATEGORIES.map((c) => (
            <Pressable key={c} testID={`cat-${c}`} style={[styles.chip, category === c && styles.chipActive]} onPress={() => setCategory(c)}>
              <Txt style={[styles.chipTxt, category === c && styles.chipTxtActive]}>{c}</Txt>
            </Pressable>
          ))}
        </ScrollView>

        <View style={styles.row2}>
          <Field label="Colour" value={colour} onChangeText={setColour} placeholder="Cream" flex testID="field-colour" />
          <Field label="Fabric" value={fabric} onChangeText={setFabric} placeholder="Linen" flex testID="field-fabric" />
        </View>
        <View style={styles.row2}>
          <Field label="Brand" value={brand} onChangeText={setBrand} placeholder="—" flex testID="field-brand" />
          <Field label="Size" value={size} onChangeText={setSize} placeholder="M" flex testID="field-size" />
        </View>
        <View style={styles.row2}>
          <Field label="Pattern" value={pattern} onChangeText={setPattern} placeholder="Solid" flex testID="field-pattern" />
          <Field label="Price" value={price} onChangeText={setPrice} placeholder="0" keyboardType="numeric" flex testID="field-price" />
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

        <Txt style={styles.groupLabel}>DOES IT FLATTER YOU?</Txt>
        <View style={styles.flatterRow}>
          {[
            { v: true, label: "Yes", icon: "thumbs-up" },
            { v: false, label: "Not really", icon: "thumbs-down" },
          ].map((o) => (
            <Pressable
              key={o.label}
              testID={`flatter-${o.label}`}
              style={[styles.flatterBtn, flatters === o.v && styles.flatterActive]}
              onPress={() => setFlatters(o.v)}
            >
              <Feather name={o.icon as any} size={16} color={flatters === o.v ? colors.onBrandPrimary : colors.onSurface} />
              <Txt style={[styles.flatterTxt, flatters === o.v && { color: colors.onBrandPrimary }]}>{o.label}</Txt>
            </Pressable>
          ))}
        </View>
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

      <Modal visible={hintPhoto !== null} transparent animationType="fade" onRequestClose={() => setHintPhoto(null)}>
        <View style={styles.hintBackdrop}>
          <View style={styles.hintSheet}>
            <Display weight="medium" style={styles.hintTitle}>Which piece is this?</Display>
            <Txt style={styles.hintSub}>
              Wearing more than one thing? Tell Aureve which garment to focus on for an accurate read.
            </Txt>
            <View style={styles.hintChips}>
              {CATEGORIES.map((c) => (
                <Pressable
                  key={c}
                  testID={`hint-${c}`}
                  style={styles.hintChip}
                  onPress={() => {
                    const b64 = hintPhoto!;
                    setHintPhoto(null);
                    runAnalyze(b64, c);
                  }}
                >
                  <Txt style={styles.hintChipTxt}>{c}</Txt>
                </Pressable>
              ))}
            </View>
            <Pressable
              style={styles.hintAuto}
              testID="hint-auto"
              onPress={() => {
                const b64 = hintPhoto!;
                setHintPhoto(null);
                runAnalyze(b64);
              }}
            >
              <Feather name="zap" size={16} color={colors.onBrandPrimary} />
              <Txt style={styles.hintAutoTxt}>Just detect it for me</Txt>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function Field({
  label,
  flex,
  multiline,
  testID,
  ...rest
}: any) {
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
  bulkLink: { fontSize: 14, color: colors.brand },
  dupBanner: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 0.5, borderColor: colors.border, padding: spacing.md, marginBottom: spacing.lg },
  dupHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  dupTitle: { flex: 1, fontSize: 14, color: colors.onSurface, fontFamily: fonts.displayMedium },
  dupSub: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 4, lineHeight: 17 },
  dupRow: { gap: spacing.md, paddingTop: spacing.md },
  dupCard: { width: 72 },
  dupImg: { width: 72, height: 90, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  dupImgEmpty: { alignItems: "center", justifyContent: "center" },
  dupName: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 4 },
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
  error: { color: colors.error, fontSize: 13, marginTop: spacing.lg },
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
  flatterRow: { flexDirection: "row", gap: spacing.md },
  flatterBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    height: 48,
    borderRadius: radius.sm,
    borderWidth: 0.5,
    borderColor: colors.border,
  },
  flatterActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  flatterTxt: { fontSize: 14, color: colors.onSurface },
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
  hintBackdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.5)", justifyContent: "flex-end" },
  hintSheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.xl,
    paddingBottom: spacing["2xl"],
  },
  hintTitle: { fontSize: 24 },
  hintSub: { fontSize: 13, color: colors.onSurfaceTertiary, marginTop: 4, marginBottom: spacing.lg, lineHeight: 19 },
  hintChips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  hintChip: {
    paddingHorizontal: spacing.lg,
    height: 40,
    borderRadius: radius.pill,
    borderWidth: 0.5,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  hintChipTxt: { fontSize: 14, color: colors.onSurface },
  hintAuto: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    height: 50,
    borderRadius: radius.sm,
    backgroundColor: colors.brandPrimary,
    marginTop: spacing.lg,
  },
  hintAutoTxt: { color: colors.onBrandPrimary, fontSize: 15 },
});
