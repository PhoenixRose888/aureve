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

type Row = { thumb: string; name: string; category: string; status: "done" | "failed"; dupe?: boolean };

export default function BulkAdd() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [phase, setPhase] = useState<"idle" | "processing" | "done">("idle");
  const [total, setTotal] = useState(0);
  const [progress, setProgress] = useState(0);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const busy = useRef(false);

  const run = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setError("");
    const picked = await pickMultipleFromLibrary(15);
    if ("error" in picked) {
      busy.current = false;
      if (picked.error === "blocked") {
        setError("Photo access is off. Enable it in Settings to add several at once.");
      } else if (picked.error !== "cancelled") {
        setError("Couldn't open your photos.");
      }
      if (phase === "idle") router.back();
      return;
    }
    const imgs = picked.images;
    setTotal(imgs.length);
    setProgress(0);
    setRows([]);
    setPhase("processing");
    for (let i = 0; i < imgs.length; i++) {
      const base64 = imgs[i];
      try {
        const res = await api<any>("/capture", { method: "POST", body: { image: base64, clean: true } });
        const a = res.analysis || {};
        const photo = res.clean_image || base64;
        const name = a.name || "New piece";
        const category = a.category || "Tops";
        const dupe = Array.isArray(res.duplicates) && res.duplicates.length > 0;
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
            price: a.estimated_value ? Number(a.estimated_value) : null,
            photo,
            style: a.style || "",
            sleeve_length: a.sleeve_length || "",
            formality: a.formality || "",
            tone: a.tone || "",
          },
        });
        setRows((r) => [...r, { thumb: photo, name, category, status: "done", dupe }]);
      } catch {
        setRows((r) => [...r, { thumb: base64, name: "Couldn't add", category: "", status: "failed" }]);
      }
      setProgress(i + 1);
    }
    setPhase("done");
    busy.current = false;
  }, [phase, router]);

  // Kick off the picker on first mount.
  React.useEffect(() => { run(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const added = rows.filter((r) => r.status === "done").length;
  const dupes = rows.filter((r) => r.status === "done" && r.dupe).length;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="bulk-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt style={styles.kicker}>ADD SEVERAL</Txt>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {phase === "processing" ? (
          <>
            <Display weight="medium" style={styles.title}>Cataloguing your pieces…</Display>
            <Txt style={styles.sub}>Auto-tagging and cleaning up each photo. {progress} of {total} done.</Txt>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${total ? (progress / total) * 100 : 0}%` }]} />
            </View>
            <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xl }} />
          </>
        ) : phase === "done" ? (
          <>
            <Display weight="medium" style={styles.title}>{added} {added === 1 ? "piece" : "pieces"} added</Display>
            <Txt style={styles.sub}>{dupes > 0 ? `All set — ${dupes} may be a duplicate of something you own (flagged below). Review and delete any you don't need.` : "All set — they're in your wardrobe now."}</Txt>
          </>
        ) : (
          <Display weight="medium" style={styles.title}>Choose photos…</Display>
        )}

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
              <Txt style={[styles.cellName, r.dupe && styles.cellNameDupe]} numberOfLines={1}>{r.dupe ? `⚠ ${r.name}` : r.name}</Txt>
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
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  title: { fontSize: 28, color: colors.onSurface },
  sub: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: spacing.sm, lineHeight: 21 },
  progressTrack: { height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, marginTop: spacing.xl, overflow: "hidden" },
  progressFill: { height: 6, borderRadius: 3, backgroundColor: colors.brand },
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
  cellNameDupe: { color: colors.warning },
  footer: { flexDirection: "row", gap: spacing.md, padding: spacing.xl, paddingTop: spacing.md, borderTopWidth: 0.5, borderTopColor: colors.border },
  secondaryBtn: { flex: 1, height: 52, borderRadius: radius.sm, borderWidth: 0.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center" },
  secondaryTxt: { fontSize: 15, color: colors.onSurface },
  primaryBtn: { flex: 1, height: 52, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryTxt: { fontSize: 15, color: colors.onBrandPrimary },
});
