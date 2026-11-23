import React from "react";
import { View, Image, StyleSheet, StyleProp, ViewStyle } from "react-native";
import { spacing } from "@/src/theme";

/**
 * The one Aureve brand treatment for standard screens: the gold "A" glyph,
 * centred above the page title at a consistent size and weight. Screens with
 * specialised header controls (chat, modals) keep their own layout.
 */
export default function BrandMark({ style }: { style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[styles.wrap, style]}>
      <Image
        source={require("@/assets/images/aureve-mark.png")}
        style={styles.mark}
        resizeMode="contain"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", justifyContent: "center", marginBottom: spacing.sm, pointerEvents: "none" },
  mark: { width: 38, height: 28, opacity: 0.95 },
});
