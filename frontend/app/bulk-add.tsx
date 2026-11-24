import React, { useState, useCallback, useRef } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";
import { pickMultipleFromLibrary, openSettings } from "@/src/utils/image";
import PhotoTips from "@/src/components/PhotoTips";
import { diag } from "@/src/utils/diag";
import { markWardrobeDirty } from "@/src/utils/wardrobeCache";
import { WARDROBE_FULL_TITLE, WARDROBE_FULL_BODY, WARDROBE_LIMIT_LABEL } from "@/src/utils/limits";

type Row = {
  thumb: string; name: string; category: string; status: "done" | "failed";
  dupe?: boolean; dupeReason?: string; photoNote?: string;
  // Failures keep their reason and their source image so they can be retried
  // without the user hunting for the photos again.
  reason?: string; src?: string; blocked?: boolean; limited?: boolean;
};

/** Turn an API error into something the user can act on. */
function failureReason(e: any): { reason: string; blocked: boolean } {
  const status = e?.status;
  const detail = String(e?.message || "").trim();
  if (e?.timeout) return { reason: "Took too long on this connection — retry when you have better signal.", blocked: false };
  // 402 is the wardrobe/Premium gate: the server message is the useful one.
  if (status === 402) return { reason: detail || "Your free wardrobe is full.", blocked: true };  // wardrobe/Premium gate
  if (status === 401 || status === 403) return { reason: "Your session expired — sign in again and retry.", blocked: true };
  if (status === 413) return { reason: "That photo is too large. Retake it a little smaller and retry.", blocked: false };
  if (status === 400) return { reason: detail || "That photo couldn't be read.", blocked: false };
  return { reason: detail || "Upload didn't complete.", blocked: false };
}

export default function BulkAdd() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [phase, setPhase] = useState<"idle" | "processing" | "cleaning" | "done">("idle");
  const [total, setTotal] = useState(0);
  const [progress, setProgress] = useState(0);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [opening, setOpening] = useState(false);
  const busy = useRef(false);
  const rowsRef = useRef<Row[]>([]);

  const setRowsBoth = useCallback((next: Row[]) => {
    rowsRef.current = next;
    setRows(next);
  }, []);

  const processImages = useCallback(async (imgs: string[]) => {
    // Check the room available FIRST so photos that can never be saved are
    // never uploaded or analysed — they're marked as limit-reached instead.
    let slots = imgs.length;
    try {
      const cap = await api<any>("/items/capacity");
      if (cap && cap.remaining !== null && cap.remaining !== undefined) slots = Math.min(imgs.length, cap.remaining);
    } catch {
      /* if we can't check, let the server be the authority */
    }
    const toProcess = imgs.slice(0, slots);
    const overLimit = imgs.slice(slots);
    setTotal(toProcess.length);
    setProgress(0);
    setPhase("processing");
    // Each created piece remembers WHICH row it belongs to, so a cleaned photo
    // can never land on a different item's tile.
    const created: { id: string; rowIdx: number }[] = [];
    const markLimited = (sources: string[]) =>
      setRowsBoth([
        ...rowsRef.current,
        ...sources.map((src) => ({
          thumb: src, name: WARDROBE_LIMIT_LABEL, category: "",
          status: "failed" as const, reason: WARDROBE_FULL_BODY,
          blocked: true, limited: true, src,
        })),
      ]);
    if (overLimit.length) markLimited(overLimit);
    for (let i = 0; i < toProcess.length; i++) {
      const base64 = toProcess[i];
      const rowIdx = rowsRef.current.length;
      try {
        diag("bulk.analyze.start", { index: i + 1, of: toProcess.length });
        const res = await api<any>("/capture", {
          method: "POST",
          body: { image: base64, clean: false },
          timeoutMs: 60000,
        });
        const a = res.analysis || {};
        const photo = base64;
        const name = a.name || "New piece";
        const category = a.category || "Tops";
        diag("bulk.analyze.done", { index: i + 1, name: a.name, category: a.category, confidence: a.confidence });
        const dupeList = Array.isArray(res.duplicates) ? res.duplicates : [];
        const dupe = dupeList.length > 0;
        const dupeReason = dupe
          ? dupeList[0].reason || `Looks like the ${dupeList[0].name} already in your wardrobe`
          : "";
        const poorPhoto = String(a.photo_quality || "").toLowerCase() === "poor";
        const photoNote = poorPhoto
          ? a.photo_quality_note || "Lighting or shadows may be affecting the colour or detail."
          : "";
        const createdItem = await api<any>("/items", {
          method: "POST",
          body: {
            name,
            category,
            brand: a.brand || "",
            colour: a.colour || "",
            fabric: a.fabric || "",
            pattern: a.pattern || "",
            season: a.season || "All",
            condition: a.condition || "",
            photo,
            style: a.style || "",
            sleeve_length: a.sleeve_length || "",
            formality: a.formality || "",
            tone: a.tone || "",
          },
        });
        // Only count it as added once the wardrobe record actually exists.
        if (!createdItem?.id) throw new Error("The piece didn't save. Please retry.");
        created.push({ id: createdItem.id, rowIdx });
        setRowsBoth([...rowsRef.current, { thumb: photo, name, category, status: "done", dupe, dupeReason, photoNote }]);
      } catch (e: any) {
        const { reason, blocked } = failureReason(e);
        diag("bulk.analyze.failed", { index: i + 1, status: e?.status, timeout: !!e?.timeout, error: String(e?.message || e) });
        const limited = e?.status === 402;
        setRowsBoth([...rowsRef.current, {
          thumb: base64, name: limited ? WARDROBE_LIMIT_LABEL : "Couldn't add", category: "",
          status: "failed", reason, blocked, limited, src: base64,
        }]);
        if (limited) {
          // The wardrobe just filled up: don't analyse anything else.
          markLimited(toProcess.slice(i + 1));
          setProgress(toProcess.length);
          break;
        }
      }
      setProgress(i + 1);
    }
    // Bulk pieces get the SAME background cleanup as a single Add. It runs after
    // cataloguing so recognition stays fast, and any failure simply leaves that
    // piece with its original photo instead of failing the batch.
    if (created.length) {
      setPhase("cleaning");
      setProgress(0);
      setTotal(created.length);
      for (let i = 0; i < created.length; i++) {
        try {
          const res = await api<any>(`/items/${created[i].id}/clean`, { method: "POST", timeoutMs: 90000 });
          if (res?.photo) {
            const idx = created[i].rowIdx;
            setRowsBoth(rowsRef.current.map((row, r) => (r === idx ? { ...row, thumb: res.photo } : row)));
          }
          diag("bulk.clean.done", { index: i + 1, cleaned: !!res?.cleaned });
        } catch (e: any) {
          diag("bulk.clean.failed", { index: i + 1, error: String(e?.message || e) });
        }
        setProgress(i + 1);
      }
    }
    if (created.length) markWardrobeDirty();
    setPhase("done");
  }, [setRowsBoth]);

  const run = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setError("");
    setOpening(true);
    diag("bulk.picker.open");
    let picked;
    try {
      picked = await pickMultipleFromLibrary(15);
    } catch (e: any) {
      diag("bulk.picker.failed", { error: String(e?.message || e) });
      picked = { error: "failed" as const };
    }
    setOpening(false);
    if ("error" in picked) {
      busy.current = false;
      diag("bulk.picker.cancelled", { reason: picked.error });
      if (picked.error === "blocked") {
        setError("Photo access is off. Enable it in Settings to add several at once.");
      } else if (picked.error !== "cancelled") {
        setError("Couldn't open your photos.");
      }
      return;
    }
    const imgs = picked.images;
    diag("bulk.picker.picked", { count: imgs.length });
    setRowsBoth([]);
    await processImages(imgs);
    busy.current = false;
  }, [processImages, setRowsBoth]);

  /** Retry only the pieces that failed, using the photos already picked. */
  const retryFailed = useCallback(async () => {
    if (busy.current) return;
    const retry = rowsRef.current
      .filter((r) => r.status === "failed" && !r.limited && r.src)
      .map((r) => r.src as string);
    if (!retry.length) return;
    busy.current = true;
    diag("bulk.retry", { count: retry.length });
    setRowsBoth(rowsRef.current.filter((r) => r.status === "done" || r.limited));
    await processImages(retry);
    busy.current = false;
  }, [processImages, setRowsBoth]);

  const added = rows.filter((r) => r.status === "done").length;
  const failed = rows.filter((r) => r.status === "failed").length;
  const limited = rows.filter((r) => r.status === "failed" && r.limited).length;
  const retryable = rows.filter((r) => r.status === "failed" && !r.limited && r.src).length;
  const dupes = rows.filter((r) => r.status === "done" && r.dupe).length;
  const attempted = rows.length;
  const blocked = rows.some((r) => r.status === "failed" && r.blocked);

  const doneTitle = failed === 0
    ? `${added} ${added === 1 ? "piece" : "pieces"} added`
    : added === 0
      ? "0 pieces added"
      : `${added} of ${attempted} pieces added`;

  const allLimited = failed > 0 && limited === failed;
  const doneSub = failed === 0
    ? (dupes > 0
        ? `All set — ${dupes} look like a piece you already own. The reason is shown under each one, so you can open it and delete either copy.`
        : "All set — they're in your wardrobe now.")
    : allLimited
      ? (added === 0
          ? WARDROBE_FULL_BODY
          : `${failed} ${failed === 1 ? "piece wasn't" : "pieces weren't"} added — your Free wardrobe is now full. Upgrade to Premium for unlimited wardrobe uploads.`)
      : added === 0
        ? "We couldn't add these items. Please try again."
        : `${failed} ${failed === 1 ? "piece" : "pieces"} didn't save. The reason is under each one — you can retry just those.`;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="bulk-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt style={styles.kicker}>BULK ADD</Txt>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {phase === "cleaning" ? (
          <>
            <Display weight="medium" style={styles.title}>Preparing and cleaning your wardrobe photos…</Display>
            <Txt style={styles.sub}>
              Tidying photo {progress + 1 > total ? total : progress + 1} of {total} — {progress} done.
            </Txt>
            <Txt style={styles.note}>
              Your photos are still being cleaned. You can leave this screen and it&apos;ll continue in the
              background; if a photo can&apos;t be cleaned we simply keep your original.
            </Txt>
            <View style={styles.barTrack}>
              <View style={[styles.barFill, { width: `${total ? (progress / total) * 100 : 0}%` }]} />
            </View>
          </>
        ) : phase === "processing" ? (
          <>
            <Display weight="medium" style={styles.title}>Cataloguing your pieces…</Display>
            <Txt style={styles.sub}>
              Uploading and analysing {progress + 1 > total ? total : progress + 1} of {total} — {progress} done.
            </Txt>
            <Txt style={styles.note}>
              Your pieces are still processing. You can leave this screen and they&apos;ll keep going in
              the background — larger batches take a little longer on a slow connection.
            </Txt>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${total ? (progress / total) * 100 : 0}%` }]} />
            </View>
            <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xl }} />
          </>
        ) : phase === "done" ? (
          <>
            <Display weight="medium" style={styles.title} testID="bulk-result-title">
              {allLimited && added === 0 ? WARDROBE_FULL_TITLE : doneTitle}
            </Display>
            <Txt style={styles.sub} testID="bulk-result-sub">{doneSub}</Txt>
            {retryable > 0 ? (
              <Pressable style={styles.retryBtn} testID="bulk-retry-failed" onPress={retryFailed}>
                <Feather name="refresh-cw" size={16} color={colors.onBrandPrimary} />
                <Txt style={styles.retryTxt}>
                  Retry failed {retryable === 1 ? "item" : "items"}
                </Txt>
              </Pressable>
            ) : null}
            {blocked ? (
              <Pressable style={styles.upgradeBtn} testID="bulk-go-premium" onPress={() => router.push("/premium")}>
                <Feather name="award" size={16} color={colors.onSurface} />
                <Txt style={styles.upgradeTxt}>{limited > 0 ? "Upgrade to Premium" : "See Premium"}</Txt>
              </Pressable>
            ) : null}
          </>
        ) : (
          <>
            <Display weight="medium" style={styles.title}>Add several pieces at once</Display>
            <Txt style={styles.sub}>
              Pick up to 15 photos of your pieces and Aureve will name, categorise and catalogue each one for you.
            </Txt>
            <Pressable style={styles.chooseBtn} testID="bulk-choose-photos" onPress={run} disabled={opening}>
              {opening ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <>
                  <Feather name="image" size={17} color={colors.onBrandPrimary} />
                  <Txt style={styles.chooseTxt}>Choose photos</Txt>
                </>
              )}
            </Pressable>
          </>
        )}

        <PhotoTips />

        {error ? (
          <View style={styles.errBox}>
            <Txt style={styles.errTxt}>{error}</Txt>
            <Pressable style={styles.errBtn} onPress={openSettings}><Txt style={styles.errBtnTxt}>Open Settings</Txt></Pressable>
          </View>
        ) : null}

        <View style={styles.grid}>
          {rows.map((r, i) => (
            <View key={i} style={styles.cell}>
              <Image source={{ uri: `data:image/jpeg;base64,${r.thumb}` }} style={[styles.cellImg, r.status === "failed" && styles.cellFailed]} contentFit="cover" />
              {r.status === "done" ? (
                r.dupe ? (
                  <View style={styles.dupeBadge}><Feather name="copy" size={10} color={colors.onSurface} /></View>
                ) : (
                  <View style={styles.tick}><Feather name="check" size={11} color={colors.onBrandPrimary} /></View>
                )
              ) : (
                <View style={styles.cross}><Feather name="x" size={11} color={colors.onSurfaceInverse} /></View>
              )}
              <Txt style={[styles.cellName, r.dupe && styles.cellNameDupe]} numberOfLines={1}>{r.name}</Txt>
              {r.reason ? <Txt style={styles.cellFail} numberOfLines={4}>{r.reason}</Txt> : null}
              {r.dupeReason ? <Txt style={styles.cellFlag} numberOfLines={3}>Possible duplicate — {r.dupeReason}</Txt> : null}
              {r.photoNote ? <Txt style={styles.cellFlag} numberOfLines={3}>Photo may not show it accurately — {r.photoNote}</Txt> : null}
            </View>
          ))}
        </View>
      </ScrollView>

      {phase === "done" ? (
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          {limited === 0 ? (
            <Pressable style={styles.secondaryBtn} testID="bulk-more" onPress={run}>
              <Txt style={styles.secondaryTxt}>Add more</Txt>
            </Pressable>
          ) : null}
          <Pressable style={styles.primaryBtn} testID="bulk-done" onPress={() => router.replace("/(tabs)/wardrobe")}>
            <Txt style={styles.primaryTxt}>Done</Txt>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  kicker: { fontSize: 11, letterSpacing: 2, color: colors.onSurfaceTertiary },
  chooseBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    height: 52, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, marginTop: spacing.xl,
  },
  chooseTxt: { color: colors.onBrandPrimary, fontSize: 16 },
  retryBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    height: 52, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, marginTop: spacing.lg,
  },
  retryTxt: { color: colors.onBrandPrimary, fontSize: 16 },
  upgradeBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    height: 52, borderRadius: radius.sm, borderWidth: 0.5, borderColor: colors.borderStrong, marginTop: spacing.md,
  },
  upgradeTxt: { color: colors.onSurface, fontSize: 16 },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  title: { fontSize: 28, color: colors.onSurface },
  sub: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: spacing.sm, lineHeight: 21 },
  note: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: spacing.sm, lineHeight: 18 },
  progressTrack: { height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, marginTop: spacing.xl, overflow: "hidden" },
  progressFill: { height: 6, borderRadius: 3, backgroundColor: colors.brand },
  barTrack: { height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, marginTop: spacing.xl, overflow: "hidden" },
  barFill: { height: 6, borderRadius: 3, backgroundColor: colors.brand },
  errBox: { marginTop: spacing.xl, gap: spacing.md },
  errTxt: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  errBtn: { alignSelf: "flex-start", borderWidth: 0.5, borderColor: colors.borderStrong, borderRadius: radius.sm, paddingHorizontal: spacing.lg, height: 44, justifyContent: "center" },
  errBtnTxt: { fontSize: 14, color: colors.onSurface },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.xl },
  cell: { width: "30%" },
  cellImg: { width: "100%", aspectRatio: 0.8, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  cellFailed: { opacity: 0.4 },
  tick: { position: "absolute", top: 6, right: 6, width: 20, height: 20, borderRadius: 10, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  dupeBadge: { position: "absolute", top: 6, right: 6, width: 20, height: 20, borderRadius: 10, backgroundColor: colors.warning, alignItems: "center", justifyContent: "center" },
  cross: { position: "absolute", top: 6, right: 6, width: 20, height: 20, borderRadius: 10, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" },
  cellName: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 4 },
  cellFail: { fontSize: 10, color: colors.error, lineHeight: 14, marginTop: 2 },
  cellFlag: { fontSize: 10, color: colors.onSurfaceTertiary, lineHeight: 14, marginTop: 2 },
  cellNameDupe: { color: colors.warning },
  footer: { flexDirection: "row", gap: spacing.md, padding: spacing.xl, paddingTop: spacing.md, borderTopWidth: 0.5, borderTopColor: colors.border },
  secondaryBtn: { flex: 1, height: 52, borderRadius: radius.sm, borderWidth: 0.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  secondaryTxt: { fontSize: 15, color: colors.onSurface },
  primaryBtn: { flex: 1, height: 52, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryTxt: { fontSize: 15, color: colors.onBrandPrimary },
});
