import React, { useState } from "react";
import { View, StyleSheet, Pressable } from "react-native";
import { Feather } from "@expo/vector-icons";
import { Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";

const TIPS = [
  "Use good natural light where possible.",
  "Use a plain or uncluttered background.",
  "Photograph one main item at a time.",
  "Make sure the whole item is visible and reasonably in focus.",
  "Avoid heavy shadows or glare.",
];

export default function PhotoTips() {
  const [open, setOpen] = useState(false);
  return (
    <View style={styles.wrap}>
      <Pressable style={styles.head} testID="photo-tips-toggle" onPress={() => setOpen((o) => !o)} hitSlop={8}>
        <Feather name="info" size={14} color={colors.onSurfaceTertiary} />
        <Txt style={styles.headTxt}>Photo tips</Txt>
        <Feather name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.onSurfaceTertiary} />
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
  wrap: { marginTop: spacing.md },
  head: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm },
  headTxt: { flex: 1, fontSize: 13, color: colors.onSurfaceTertiary },
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
