import React, { useState } from "react";
import { View, StyleSheet, Pressable } from "react-native";
import { Feather } from "@expo/vector-icons";
import { Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";

const TIPS = [
  "One item per photo where possible.",
  "Use a plain, uncluttered background.",
  "Good natural, even light works best.",
  "Keep the whole item in frame.",
  "Avoid heavy shadows and glare.",
  "Don't let garments overlap each other.",
  "Hang or lay flat anything that won't hold its shape.",
  "Photograph bags and jewellery separately, one item at a time, so Aureve can identify them clearly.",
];

export default function PhotoTips() {
  const [open, setOpen] = useState(false);
  return (
    <View style={styles.wrap}>
      <Pressable style={styles.head} testID="photo-tips-toggle" onPress={() => setOpen((o) => !o)} hitSlop={8}>
        <Feather name="info" size={15} color={colors.onSurfaceSecondary} />
        <Txt style={styles.headTxt}>Photo Tips</Txt>
        <Feather name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.onSurfaceSecondary} />
      </Pressable>
      {open ? (
        <View style={styles.body} testID="photo-tips-body">
          <Txt style={styles.intro}>These are tips, not requirements — Aureve still reads normal everyday phone photos.</Txt>
          {TIPS.map((t) => (
            <View key={t} style={styles.row}>
              <Txt style={styles.dot}>·</Txt>
              <Txt style={styles.tip}>{t}</Txt>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: spacing.md, gap: spacing.sm },
  head: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    alignSelf: "flex-start", paddingVertical: spacing.sm, paddingHorizontal: spacing.md,
    borderRadius: radius.pill, borderWidth: 0.5, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, minHeight: 36,
  },
  headTxt: { fontSize: 13, color: colors.onSurfaceSecondary },
  body: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    padding: spacing.md,
    gap: 4,
  },
  intro: { fontSize: 12, color: colors.onSurfaceSecondary, lineHeight: 18, marginBottom: 4 },
  row: { flexDirection: "row", gap: spacing.sm },
  dot: { fontSize: 12, color: colors.onSurfaceTertiary },
  tip: { flex: 1, fontSize: 12, color: colors.onSurfaceSecondary, lineHeight: 18 },
});
