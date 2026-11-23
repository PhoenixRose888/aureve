import React, { useState, useEffect, useCallback } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import GarmentImage from "@/src/components/GarmentImage";

export default function HealthReport() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [report, setReport] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    // Wear-based numbers come from explicit Worn activity; the written insight
    // is the existing AI report.
    api<any>("/insights").then(setStats).catch(() => {});
    try {
      setReport(await api<any>("/insights/health-report", { method: "POST" }));
    } catch (e: any) {
      setError(e.message || "Couldn't generate your report");
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const month = stats?.month;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="report-back" hitSlop={12}>
          <Feather name="chevron-left" size={26} color={colors.onSurface} />
        </Pressable>
        <BrandMark style={{ marginBottom: 0 }} />
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.titleBlock}>
          <Txt style={styles.kicker}>WARDROBE HEALTH</Txt>
          <Display weight="semibold" style={styles.title}>{month?.label || "This month"}</Display>
          <Txt style={styles.sub}>What you wore, what&apos;s waiting, and what&apos;s worth trying.</Txt>
        </View>

        {(month?.top_worn || []).length ? (
          <View style={styles.block} testID="health-most-worn">
            <Txt style={styles.blockTitle}>MOST WORN THIS MONTH</Txt>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.strip}>
              {month.top_worn.map((row: any) => (
                <Pressable key={row.item.id} style={styles.pieceCard} onPress={() => router.push(`/item/${row.item.id}`)} testID={`health-worn-${row.item.id}`}>
                  <GarmentImage photo={row.item.photo} category={row.item.category} style={styles.pieceImg} iconSize={20} />
                  <Txt style={styles.pieceName} numberOfLines={1}>{row.item.name}</Txt>
                  <Txt style={styles.pieceMeta}>{row.wears}× this month</Txt>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        ) : (
          <View style={styles.emptyNote} testID="health-no-wears">
            <Feather name="info" size={15} color={colors.onSurfaceSecondary} />
            <Txt style={styles.emptyNoteTxt}>
              No wears recorded this month yet. Tap &lsquo;Wear this today&rsquo; on a look and your rotation starts building here.
            </Txt>
          </View>
        )}

        {(month?.unworn || []).length ? (
          <View style={styles.block} testID="health-unworn">
            <Txt style={styles.blockTitle}>STILL WAITING TO BE WORN</Txt>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.strip}>
              {month.unworn.map((it: any) => (
                <Pressable key={it.id} style={styles.pieceCard} onPress={() => router.push(`/item/${it.id}`)} testID={`health-unworn-${it.id}`}>
                  <GarmentImage photo={it.photo} category={it.category} style={styles.pieceImg} iconSize={20} />
                  <Txt style={styles.pieceName} numberOfLines={1}>{it.name}</Txt>
                  <Txt style={styles.pieceMeta}>{it.category}</Txt>
                </Pressable>
              ))}
            </ScrollView>
            <Pressable style={styles.inlineCta} testID="health-style-unworn" onPress={() => router.push("/(tabs)/dressme")}>
              <Feather name="star" size={15} color={colors.onSurface} />
              <Txt style={styles.inlineCtaTxt}>Style one of these today</Txt>
            </Pressable>
          </View>
        ) : null}

        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator color={colors.sage} />
            <Txt style={styles.loadingTxt}>Reading this month&apos;s wardrobe…</Txt>
          </View>
        ) : error ? (
          <View style={styles.center}>
            <Txt style={styles.errorTxt} testID="report-error">{error}</Txt>
            <Pressable style={styles.retry} onPress={load} testID="report-retry">
              <Txt style={styles.retryTxt}>Try again</Txt>
            </Pressable>
          </View>
        ) : report ? (
          <View testID="health-report">
            {report.headline ? (
              <View style={styles.insightCard} testID="health-insight">
                <Txt style={styles.blockTitle}>THIS MONTH&apos;S INSIGHT</Txt>
                <Display weight="medium" style={styles.headline}>{report.headline}</Display>
                {report.lesson ? <Txt style={styles.insightTxt}>{report.lesson}</Txt> : null}
              </View>
            ) : null}

            {report.nudges?.length > 0 && (
              <View style={styles.block} testID="health-nudges">
                <Txt style={styles.blockTitle}>ROTATION NUDGES</Txt>
                {report.nudges.map((n: string, i: number) => (
                  <View key={i} style={styles.listRow}>
                    <Feather name="arrow-right" size={14} color={colors.sageDeep} />
                    <Txt style={styles.listTxt}>{n}</Txt>
                  </View>
                ))}
              </View>
            )}

            {report.wins?.length > 0 && (
              <View style={styles.block} testID="health-wins">
                <Txt style={styles.blockTitle}>WINS</Txt>
                {report.wins.map((w: string, i: number) => (
                  <View key={i} style={styles.listRow}>
                    <Feather name="check" size={14} color={colors.success} />
                    <Txt style={styles.listTxt}>{w}</Txt>
                  </View>
                ))}
              </View>
            )}

            {report.missing_piece ? (
              <View style={styles.buyCard} testID="health-next-buy">
                <Txt style={styles.buyKicker}>YOUR SMARTEST NEXT BUY</Txt>
                <Display weight="medium" style={styles.buyRec}>{report.missing_piece.recommendation}</Display>
                {report.missing_piece.reason ? <Txt style={styles.buyReason}>{report.missing_piece.reason}</Txt> : null}
                {report.missing_piece.unlock_note ? (
                  <View style={styles.unlockRow}>
                    <Feather name="unlock" size={13} color={colors.goldDeep} />
                    <Txt style={styles.unlockTxt}>{report.missing_piece.unlock_note}</Txt>
                  </View>
                ) : null}
                <Pressable style={styles.inlineCta} testID="health-open-shopping" onPress={() => router.push("/(tabs)/shop")}>
                  <Feather name="shopping-bag" size={15} color={colors.onSurface} />
                  <Txt style={styles.inlineCtaTxt}>Open Shopping Intelligence</Txt>
                </Pressable>
              </View>
            ) : null}
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  scroll: { paddingBottom: spacing["3xl"] },
  titleBlock: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.lg },
  kicker: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium, marginBottom: spacing.xs },
  title: { fontSize: 30, letterSpacing: -0.5 },
  sub: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: spacing.xs, lineHeight: 20 },
  block: { marginTop: spacing.xl, paddingHorizontal: spacing.lg },
  blockTitle: { fontSize: 10.5, letterSpacing: 1.6, color: colors.onSurfaceTertiary, marginBottom: spacing.md, fontFamily: fonts.displayMedium },
  strip: { gap: spacing.md, paddingRight: spacing.lg },
  pieceCard: { width: 96 },
  pieceImg: { width: 96, height: 118, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  pieceName: { fontSize: 12.5, color: colors.onSurface, marginTop: 6 },
  pieceMeta: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 1 },
  emptyNote: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", marginTop: spacing.xl, marginHorizontal: spacing.lg, backgroundColor: colors.eucalyptus, borderRadius: radius.lg, padding: spacing.lg },
  emptyNoteTxt: { flex: 1, fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 19 },
  inlineCta: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, marginTop: spacing.md, backgroundColor: colors.surface },
  inlineCtaTxt: { fontSize: 14.5, color: colors.onSurface, fontFamily: fonts.displayMedium },
  center: { alignItems: "center", justifyContent: "center", paddingVertical: spacing["2xl"], gap: spacing.md },
  loadingTxt: { color: colors.onSurfaceSecondary, fontSize: 13, fontStyle: "italic" },
  errorTxt: { color: colors.onSurfaceSecondary, fontSize: 14, textAlign: "center", paddingHorizontal: spacing.xl },
  retry: { borderWidth: 0.5, borderColor: colors.border, paddingHorizontal: spacing.xl, paddingVertical: spacing.sm, borderRadius: radius.md },
  retryTxt: { color: colors.onSurface, fontSize: 14 },
  insightCard: { marginTop: spacing.xl, marginHorizontal: spacing.lg, backgroundColor: colors.taupe, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 0.5, borderColor: colors.border },
  headline: { fontSize: 22, lineHeight: 28, color: colors.onSurface },
  insightTxt: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21, marginTop: spacing.sm },
  listRow: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start", marginBottom: spacing.md },
  listTxt: { flex: 1, fontSize: 14, color: colors.onSurface, lineHeight: 20 },
  buyCard: { marginTop: spacing.xl, marginHorizontal: spacing.lg, backgroundColor: colors.cream, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 0.5, borderColor: colors.goldSoft },
  buyKicker: { fontSize: 10.5, letterSpacing: 1.6, color: colors.goldDeep, marginBottom: spacing.sm, fontFamily: fonts.displayMedium },
  buyRec: { fontSize: 21, lineHeight: 27, color: colors.onSurface },
  buyReason: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21, marginTop: spacing.sm },
  unlockRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, alignItems: "flex-start" },
  unlockTxt: { flex: 1, fontSize: 13, color: colors.goldDeep, lineHeight: 19 },
});
