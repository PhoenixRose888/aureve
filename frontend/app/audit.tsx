import React, { useCallback, useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { Display, Txt } from "@/src/components/Typography";
import { api } from "@/src/api/client";
import { colors, spacing, radius } from "@/src/theme";

type Wardrobe = {
  profile_id: string;
  name: string;
  created_at?: string;
  items_total: number;
  items_real: number;
  items_demo_seeded: number;
  items_without_photo: number;
  first_item_at?: string | null;
  last_item_at?: string | null;
};

const day = (s?: string | null) => (s ? String(s).slice(0, 10) : "—");

/** Read-only account audit: exactly which wardrobe every catalogued piece
 *  belongs to. Diagnostic screen — it never writes anything. */
export default function AuditScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [scanEmail, setScanEmail] = useState("");
  const [scan, setScan] = useState<any>(null);
  const [scanning, setScanning] = useState(false);

  const runScan = useCallback(async () => {
    setScanning(true);
    try {
      const q = scanEmail.trim() ? `?email=${encodeURIComponent(scanEmail.trim())}` : "";
      setScan(await api<any>(`/diag/wardrobe-scan${q}`, { timeoutMs: 60000 }));
    } catch (e: any) {
      setError(e?.message || "Couldn't run the scan.");
    }
    setScanning(false);
  }, [scanEmail]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api<any>("/diag/my-wardrobe-audit", { timeoutMs: 60000 }));
    } catch (e: any) {
      setError(e?.message || "Couldn't load the audit.");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={[styles.wrap, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="audit-back">
          <Feather name="x" size={22} color={colors.onSurface} />
        </Pressable>
        <Display weight="medium" style={styles.title}>Wardrobe audit</Display>
        <Pressable onPress={load} hitSlop={12} testID="audit-refresh">
          <Feather name="refresh-cw" size={18} color={colors.onSurface} />
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brand} /></View>
      ) : error ? (
        <View style={styles.center}><Txt style={styles.error}>{error}</Txt></View>
      ) : (
        <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
          <Txt style={styles.sub}>
            Read-only. Shows every wardrobe on your account and exactly where each catalogued piece lives.
          </Txt>

          <View style={styles.card}>
            <Txt style={styles.kicker}>ACCOUNT</Txt>
            <Txt style={styles.line}>{data.account_email || "(guest)"}</Txt>
            <Txt style={styles.dim}>
              {data.provider || "email"}{data.is_guest ? " · guest session" : ""}
            </Txt>
            <Txt style={styles.big}>{data.items_total_all_wardrobes} pieces in total</Txt>
            {data.items_stranded_on_account_id > 0 ? (
              <Txt style={styles.warn}>
                {data.items_stranded_on_account_id} piece(s) are stranded outside a wardrobe — tell Aureve support so they can be re-linked.
              </Txt>
            ) : null}
          </View>

          {(data.wardrobes || []).map((w: Wardrobe) => (
            <View key={w.profile_id} style={styles.card} testID={`audit-wardrobe-${w.profile_id}`}>
              <Txt style={styles.kicker}>WARDROBE</Txt>
              <Txt style={styles.line}>{w.name}</Txt>
              <Txt style={styles.big}>{w.items_total} pieces</Txt>
              <Txt style={styles.dim}>
                {w.items_real} yours · {w.items_demo_seeded} sample · {w.items_without_photo} missing a photo
              </Txt>
              <Txt style={styles.dim}>
                added between {day(w.first_item_at)} and {day(w.last_item_at)}
              </Txt>
              <Txt style={styles.id}>{w.profile_id}</Txt>
            </View>
          ))}

          {(data.other_accounts_same_email || []).length > 0 ? (
            <View style={styles.card} testID="audit-other-accounts">
              <Txt style={styles.kicker}>ANOTHER ACCOUNT USES THIS EMAIL</Txt>
              {data.other_accounts_same_email.map((o: any) => (
                <View key={o.user_id} style={{ marginTop: 4 }}>
                  <Txt style={styles.line}>signed up with {o.provider || "email"}</Txt>
                  {(o.wardrobes || []).map((w: any, i: number) => (
                    <Txt key={i} style={styles.dim}>
                      {w.name}: {w.items_total} pieces ({w.items_real} yours)
                    </Txt>
                  ))}
                </View>
              ))}
              <Txt style={styles.warn}>
                Your pieces may be catalogued under that sign-in method — try signing in that way.
              </Txt>
            </View>
          ) : null}

          <View style={styles.card}>
            <Txt style={styles.kicker}>FIND PIECES THAT AREN&apos;T SHOWING</Txt>
            <Txt style={styles.dim}>
              Enter the email you signed up with. Aureve will look for other sign-in methods and for wardrobes left behind in guest mode.
            </Txt>
            <TextInput
              style={styles.input}
              value={scanEmail}
              onChangeText={setScanEmail}
              placeholder="you@email.com"
              placeholderTextColor={colors.onSurfaceTertiary}
              autoCapitalize="none"
              keyboardType="email-address"
              testID="scan-email-input"
            />
            <Pressable style={styles.scanBtn} testID="run-scan" onPress={runScan} disabled={scanning}>
              {scanning ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <Txt style={styles.scanTxt}>Find my pieces</Txt>
              )}
            </Pressable>
          </View>

          {scan ? (
            <View style={styles.card} testID="scan-results">
              <Txt style={styles.kicker}>ACCOUNTS FOUND FOR THAT EMAIL</Txt>
              {(scan.accounts_for_email || []).length === 0 ? (
                <Txt style={styles.dim}>None.</Txt>
              ) : (
                scan.accounts_for_email.map((a: any) => (
                  <View key={a.account_id} style={{ marginTop: 4 }}>
                    <Txt style={styles.line}>{a.email} · {a.provider}</Txt>
                    {(a.wardrobes || []).map((w: any) => (
                      <Txt key={w.profile_id} style={styles.dim}>
                        {w.name}: {w.items_real} yours / {w.items_demo} sample
                      </Txt>
                    ))}
                  </View>
                ))
              )}

              <Txt style={styles.kicker}>LARGEST WARDROBES IN THE DATABASE</Txt>
              {(scan.largest_real_wardrobes || []).map((w: any) => (
                <Txt key={w.scope} style={styles.dim}>
                  {w.real_items} pieces · {w.wardrobe_name || "(no wardrobe)"} · {w.owner_provider}
                  {w.owner_is_guest ? " (guest — never signed in)" : ""} · last {day(w.last_item_at)}
                </Txt>
              ))}
              <Txt style={styles.warn}>
                Send this to Aureve support and the matching wardrobe can be re-linked to your account. Nothing is changed by this scan.
              </Txt>
            </View>
          ) : null}

          <Txt style={styles.kicker}>MOST RECENT {(data.recent_items || []).length} PIECES</Txt>
          {(data.recent_items || []).map((it: any, i: number) => (
            <View key={`${it.name}-${i}`} style={styles.row}>
              <Txt style={styles.rowName} numberOfLines={1}>
                {it.name || "(no name)"}{it.demo ? " · sample" : ""}
              </Txt>
              <Txt style={styles.rowMeta}>
                {it.category} · {day(it.created_at)}{it.has_photo ? "" : " · no photo"}
              </Txt>
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.xl, paddingVertical: spacing.md,
  },
  title: { fontSize: 18 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  body: { padding: spacing.xl, paddingBottom: spacing["3xl"], gap: spacing.md },
  sub: { fontSize: 13, color: colors.onSurfaceTertiary, lineHeight: 19 },
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm,
    padding: spacing.lg, gap: 2,
  },
  kicker: { fontSize: 10, letterSpacing: 1.4, color: colors.onSurfaceTertiary, marginTop: spacing.sm },
  line: { fontSize: 16, color: colors.onSurface },
  big: { fontSize: 20, color: colors.onSurface, marginTop: 4 },
  dim: { fontSize: 12, color: colors.onSurfaceSecondary, lineHeight: 18 },
  id: { fontSize: 10, color: colors.onSurfaceTertiary, marginTop: 4 },
  warn: { fontSize: 12, color: colors.warning, lineHeight: 18, marginTop: 4 },
  error: { fontSize: 14, color: colors.error, textAlign: "center" },
  input: {
    height: 46, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, color: colors.onSurface, fontSize: 15,
    backgroundColor: colors.surface, marginTop: spacing.md,
  },
  scanBtn: {
    height: 46, borderRadius: radius.sm, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center", marginTop: spacing.sm,
  },
  scanTxt: { color: colors.onBrandPrimary, fontSize: 15 },
  row: { paddingVertical: spacing.sm, borderBottomWidth: 0.5, borderBottomColor: colors.divider },
  rowName: { fontSize: 14, color: colors.onSurface },
  rowMeta: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2 },
});
