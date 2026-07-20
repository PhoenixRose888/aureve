import React, { useState, useEffect, useCallback } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { api } from "@/src/api/client";

function monthLabel() {
  return new Date().toLocaleString("en-US", { month: "long", year: "numeric" });
}

export default function HealthReport() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const r = await api<any>("/insights/health-report", { method: "POST" });
      setReport(r);
    } catch (e: any) {
      setError(e.message || "Couldn't generate your report");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} testID="report-back" hitSlop={12}>
          <Feather name="arrow-left" size={24} color={colors.onSurfaceInverse} />
        </Pressable>
        <Txt style={styles.headerKicker}>WARDROBE HEALTH</Txt>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Txt style={styles.month}>{monthLabel()}</Txt>

        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator color={colors.onSurfaceInverse} />
            <Txt style={styles.loadingTxt}>Auditing your wardrobe…</Txt>
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
            <Display weight="medium" style={styles.headline}>{report.headline}</Display>

            {/* Stat tiles */}
            <View style={styles.tiles}>
              <View style={styles.tile}>
                <Display weight="medium" style={styles.tileNum}>${report.stats?.unworn_value ?? 0}</Display>
                <Txt style={styles.tileLabel}>tied up in {report.stats?.unworn_count ?? 0} unworn pieces</Txt>
              </View>
              <View style={styles.tile}>
                <Display weight="medium" style={styles.tileNum}>${report.stats?.total_value ?? 0}</Display>
                <Txt style={styles.tileLabel}>total wardrobe value</Txt>
              </View>
            </View>

            {report.wasted_summary ? (
              <Block title="Where your money's sitting" text={report.wasted_summary} />
            ) : null}
            {report.lesson ? <Block title="This month's lesson" text={report.lesson} /> : null}

            {/* Missing piece — the hook */}
            {report.missing_piece ? (
              <View style={styles.missingCard}>
                <Txt style={styles.missingKicker}>THE ONE PURCHASE THAT PAYS OFF</Txt>
                <Display weight="medium" style={styles.missingRec}>{report.missing_piece.recommendation}</Display>
                {report.missing_piece.reason ? <Txt style={styles.missingReason}>{report.missing_piece.reason}</Txt> : null}
                {report.missing_piece.unlock_note ? (
                  <View style={styles.unlockRow}>
                    <Feather name="unlock" size={13} color={colors.brand} />
                    <Txt style={styles.unlockTxt}>{report.missing_piece.unlock_note}</Txt>
                  </View>
                ) : null}
              </View>
            ) : null}

            {report.wins?.length > 0 && (
              <View style={styles.listBlock}>
                <Txt style={styles.listTitle}>WINS</Txt>
                {report.wins.map((w: string, i: number) => (
                  <View key={i} style={styles.listRow}>
                    <Feather name="check" size={14} color={colors.success} />
                    <Txt style={styles.listTxt}>{w}</Txt>
                  </View>
                ))}
              </View>
            )}

            {report.nudges?.length > 0 && (
              <View style={styles.listBlock}>
                <Txt style={styles.listTitle}>NUDGES</Txt>
                {report.nudges.map((n: string, i: number) => (
                  <View key={i} style={styles.listRow}>
                    <Feather name="arrow-right" size={14} color={colors.brand} />
                    <Txt style={styles.listTxt}>{n}</Txt>
                  </View>
                ))}
              </View>
            )}
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

function Block({ title, text }: { title: string; text: string }) {
  return (
    <View style={styles.block}>
      <Txt style={styles.blockTitle}>{title}</Txt>
      <Txt style={styles.blockTxt}>{text}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
  headerKicker: { fontSize: 11, letterSpacing: 2, color: colors.brandTertiary },
  scroll: { padding: spacing.xl, paddingBottom: spacing["3xl"] },
  month: { fontSize: 13, color: "rgba(250,250,250,0.6)", marginBottom: spacing.md },
  center: { alignItems: "center", justifyContent: "center", paddingVertical: spacing["3xl"], gap: spacing.md },
  loadingTxt: { color: "rgba(250,250,250,0.7)", fontSize: 13, fontStyle: "italic" },
  errorTxt: { color: colors.brandTertiary, fontSize: 14, textAlign: "center" },
  retry: { borderWidth: 0.5, borderColor: colors.brandTertiary, paddingHorizontal: spacing.xl, paddingVertical: spacing.sm, borderRadius: radius.sm },
  retryTxt: { color: colors.onSurfaceInverse, fontSize: 14 },
  headline: { fontSize: 32, lineHeight: 36, color: colors.onSurfaceInverse },
  tiles: { flexDirection: "row", gap: spacing.md, marginTop: spacing.xl },
  tile: { flex: 1, borderWidth: 0.5, borderColor: "rgba(250,250,250,0.2)", borderRadius: radius.md, padding: spacing.lg },
  tileNum: { fontSize: 30, color: colors.onSurfaceInverse },
  tileLabel: { fontSize: 11, color: "rgba(250,250,250,0.6)", marginTop: 4, lineHeight: 15 },
  block: { marginTop: spacing["2xl"] },
  blockTitle: { fontSize: 11, letterSpacing: 1.5, color: colors.brandTertiary, marginBottom: spacing.sm },
  blockTxt: { fontSize: 15, color: "rgba(250,250,250,0.85)", lineHeight: 23 },
  missingCard: { marginTop: spacing["2xl"], backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.xl },
  missingKicker: { fontSize: 11, letterSpacing: 1.5, color: colors.brand, marginBottom: spacing.sm },
  missingRec: { fontSize: 24, lineHeight: 28, color: colors.onSurface },
  missingReason: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21, marginTop: spacing.sm },
  unlockRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, alignItems: "flex-start" },
  unlockTxt: { flex: 1, fontSize: 13, color: colors.brand, lineHeight: 19 },
  listBlock: { marginTop: spacing["2xl"] },
  listTitle: { fontSize: 11, letterSpacing: 1.5, color: colors.brandTertiary, marginBottom: spacing.md },
  listRow: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start", marginBottom: spacing.md },
  listTxt: { flex: 1, fontSize: 14, color: "rgba(250,250,250,0.85)", lineHeight: 20 },
});
