import React from "react";
import { View, StyleSheet, useWindowDimensions } from "react-native";
import Svg, { Path } from "react-native-svg";
import { colors } from "@/src/theme";

/**
 * Soft flowing decoration for the welcome screen — thin gold ribbons above a
 * gentle sage wave rising from the bottom edge.
 */
export default function WelcomeDecor() {
  const { width } = useWindowDimensions();
  const h = 260;
  const W = 390; // viewBox width; scales to device width
  return (
    <View style={[styles.wrap, { width, height: (h / W) * width }]} pointerEvents="none">
      <Svg width="100%" height="100%" viewBox={`0 0 ${W} ${h}`} fill="none" preserveAspectRatio="none">
        {/* thin gold ribbons */}
        <Path d="M10 70 C 110 40, 280 40, 380 70" stroke={colors.creamDim} strokeWidth={2} fill="none" strokeLinecap="round" />
        <Path d="M20 92 C 120 66, 270 66, 370 92" stroke={colors.goldSoft} strokeWidth={1.4} fill="none" strokeLinecap="round" opacity={0.55} />
        {/* soft sage wave filling the bottom */}
        <Path
          d={`M0 150 C 90 110, 300 110, ${W} 150 L ${W} ${h} L 0 ${h} Z`}
          fill={colors.brandTertiary}
          opacity={0.9}
        />
        <Path
          d={`M0 178 C 120 148, 280 148, ${W} 178 L ${W} ${h} L 0 ${h} Z`}
          fill={colors.sage}
          opacity={0.18}
        />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: "absolute", bottom: 0, left: 0 },
});
