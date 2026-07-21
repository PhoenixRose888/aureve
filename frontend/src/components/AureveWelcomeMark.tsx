import React from "react";
import { View, StyleSheet } from "react-native";
import Svg, { Path, Ellipse, G } from "react-native-svg";
import { Txt } from "@/src/components/Typography";
import { colors, fonts } from "@/src/theme";

/**
 * Welcome lockup — a serif "A" with a delicate olive sprig crossing its
 * upper-left, matching the Aureve brand welcome board.
 */
export default function AureveWelcomeMark({ size = 68 }: { size?: number }) {
  const sprig = size * 0.9;
  return (
    <View style={styles.wrap}>
      <Txt style={[styles.letter, { fontSize: size }]}>A</Txt>
      <View style={[styles.sprig, { width: sprig, height: sprig, left: -sprig * 0.42, top: -sprig * 0.18 }]} pointerEvents="none">
        <Svg width="100%" height="100%" viewBox="0 0 60 60" fill="none">
          <G stroke={colors.sage} strokeWidth={1.6} strokeLinecap="round">
            {/* stem curving up toward the top-left */}
            <Path d="M52 52 C 40 46, 26 38, 14 12" fill="none" />
          </G>
          {/* leaves along the stem */}
          <G fill={colors.sage}>
            <Ellipse cx="20" cy="24" rx="6" ry="2.6" transform="rotate(-38 20 24)" />
            <Ellipse cx="28" cy="31" rx="6.5" ry="2.8" transform="rotate(-32 28 31)" />
            <Ellipse cx="37" cy="39" rx="6.5" ry="2.8" transform="rotate(-28 37 39)" />
            <Ellipse cx="45" cy="46" rx="6" ry="2.6" transform="rotate(-24 45 46)" />
            <Ellipse cx="13" cy="16" rx="4.5" ry="2.2" transform="rotate(-46 13 16)" />
          </G>
        </Svg>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", justifyContent: "center", paddingLeft: 10 },
  letter: {
    fontFamily: fonts.serif,
    color: colors.onSurface,
    includeFontPadding: false,
    lineHeight: undefined,
  },
  sprig: { position: "absolute" },
});
