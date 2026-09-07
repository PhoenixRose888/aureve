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

type Row = { thumb: string; name: string; category: string; status: "done" | "failed"; reason?: string };

const MIN_CONFIDENCE = 60;

export default function BulkAdd() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [phase, setPhase] = useState<"idle" | "processing" | "done">("idle");
  const [total, setTotal] = useState(0);
  const [progress, setProgress] = useState(0);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [opening, setOpening] = useState(false);
  const busy = useRef(false);

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
    setTotal(imgs.length);
    setProgress(0);
    setRows([]);
    setPhase("processing");

    for (let i = 0; i < imgs.length; i++) {
      const base64 = imgs[i];
      try {
        diag("bulk.analyze.start", { index: i + 1, of: imgs.length });
        const res = await api<any>("/capture", {
          method: "POST",
          body: { image: base64, clean: false },
          timeoutMs: 60000,
        });

        const a = res.analysis || {};
        const confidence = Number(a.confidence || 0);
        const recognised = Boolean(a.name && a.category && confidence >= MIN_CONFIDENCE);

        diag("bulk.analyze.done", {
          index: i + 1,
          name: a.name,
          category: a.category,
          confidence,
          recognised,
        });

        if (!recognised) {
          setRows((r) => [
            ...r,
            {
              thumb: base64,
              name: "Item not recognised",
              category: "",
              status: "failed",
              reason: "Try a clearer photo or add this piece individually.",
            },
          ]);
          setProgress(i + 1);
          continue;
        }

        let photo = base64;
        try {
          diag("bulk.clean.start", { index: i + 1 });
          const cleaned = await api<any>("/clean-photo", {
            method: "POST",
            body: { image: base64 },
            timeoutMs: 60000,
          });
          if (cleaned?.clean_image) photo = cleaned.clean_image;
          diag("bulk.clean.done", { index: i + 1, cleaned: Boolean(cleaned?.clean_image) });
        } catch (cleanErr: any) {
          diag("bulk.clean.failed", {
            index: i + 1,
            error: String(cleanErr?.message || cleanErr),
          });
        }

        const name = a.name;
        const category = a.category;

        await api("/items", {
          method: "POST",
          body: {
            name,
            category,
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

        // Duplicate detection remains available server-side for later tuning, but
        // the current signal is intentionally not shown to users at launch.
        setRows((r) => [...r, { thumb: photo, name, category, status: "done" }]);
      } catch (e: any) {
        diag("bulk.analyze.failed", {
          index: i + 1,
          status: e?.status,
          timeout: !!e?.timeout,
          error: String(e?.message || e),
        });
        setRows((r) => [
          ...r,
          {
            thumb: base64,
            name: "Couldn't add",
            category: "",
            status: "failed",
            reason: "Try again or add this piece individually.",
          },
        ]);
      }
      setProgress(i + 1);
    }

    setPhase("done");
    busy.current = false;
  }, []);

  const added = rows.filter((r) => r.status === "done").length;
  const failed = rows.filter((r) => r.status === "failed").length;

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
        {phase === "processing" ? (
          <>
            <Display weight="medium" style={styles.title}>Preparing and cleaning your wardrobe photos…</Display>
            <Txt style={styles.sub}>
              Processing {progress + 1 > total ? total : progress + 1} of {total} — {progress} done.
            </Txt>
            <Txt style={styles.note}>
              Please stay on this screen. Aureve will keep the original if photo cleanup cannot be completed.
            </Txt>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${total ? (progress / total) * 100 : 0}%` }]} />
            </View>
            <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xl }} />
          </>
        ) : phase === "done" ? (
          <>
            <Display weight="medium" style={styles.title}>{added} {added === 1 ? "piece" : "pieces"} added</Display>
            <Txt style={styles.sub}>
              {failed > 0
                ? `${failed} ${failed === 1 ? "photo wasn't" : "photos weren't"} clear enough to catalogue confidently.`
                : "All set — they're in your wardrobe now."}
            </Txt>
          </>
        ) : (
          <>
            <Display weight="medium" style={styles.title}>Add several pieces at once</Display>
            <Txt style={styles.sub}>
              Pick up to 15 photos. Aureve will identify each piece, clean the catalogue photo, and only save items it can recognise confidently.
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
                <View style={styles.tick}><Feather name="check" size={11} color={colors.onBrandPrimary} /></View>
              ) : (
                <View style={styles.cross}><Feather name="x" size={11} color={colors.onSurfaceInverse} /></View>
              )}
              <Txt style={[styles.cellName, r.status === "failed" && styles.cellNameFailed]} numberOfLines={2}>
                {r.name}
              </Txt>
              {r.reason ? <Txt style={styles.cellReason} numberOfLines={2}>{r.reason}</Txt> : null}
            </View>
          ))}
        </View>
      </ScrollView>

      {phase === "done" ? (
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Pressable style={styles.secondaryBtn} testID="bulk-more" onPress={run}>
            <Txt style={styles.secondaryTxt}>Add more</Txt>
          </Pressable>
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
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  title: { fontSize: 28, color: colors.onSurface },
  sub: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: spacing.sm, lineHeight: 21 },
  note: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: spacing.sm, lineHeight: 18 },
  progressTrack: { height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, marginTop: spacing.xl, overflow: "hidden" },
  progressFill: { height: 6, borderRadius: 3, backgroundColor: colors.brand },
  errBox: { marginTop: spacing.xl, gap: spacing.md },
  errTxt: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  errBtn: { alignSelf: "flex-start", borderWidth: 0.5, borderColor: colors.borderStrong, borderRadius: radius.sm, paddingHorizontal: spacing.lg, height: 44, justifyContent: "center" },
  errBtnTxt: { fontSize: 14, color: colors.onSurface },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.xl },
  cell: { width: "30%" },
  cellImg: { width: "100%", aspectRatio: 0.8, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  cellFailed: { opacity: 0.45 },
  tick: { position: "absolute", top: 6, right: 6, width: 20, height: 20, borderRadius: 10, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
  cross: { position: "absolute", top: 6, right: 6, width: 20, height: 20, borderRadius: 10, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" },
  cellName: { fontSize: 11, color: colors.onSurfaceSecondary, marginTop: 4 },
  cellNameFailed: { color: colors.error },
  cellReason: { fontSize: 10, color: colors.onSurfaceTertiary, marginTop: 2, lineHeight: 13 },
  footer: { flexDirection: "row", gap: spacing.md, padding: spacing.xl, paddingTop: spacing.md, borderTopWidth: 0.5, borderTopColor: colors.border },
  secondaryBtn: { flex: 1, height: 52, borderRadius: radius.sm, borderWidth: 0.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  secondaryTxt: { fontSize: 15, color: colors.onSurface },
  primaryBtn: { flex: 1, height: 52, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryTxt: { fontSize: 15, color: colors.onBrandPrimary },
});
