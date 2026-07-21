import React from "react";
import { View, StyleSheet } from "react-native";
import Svg, { Path, Defs, LinearGradient, Stop } from "react-native-svg";
import { Txt } from "@/src/components/Typography";
import { colors, fonts } from "@/src/theme";

type Props = {
  size?: number;        // glyph size (square)
  showWordmark?: boolean;
  wordmarkSize?: number;
  color?: string;       // override wordmark colour
  tagline?: string;     // optional tagline under the wordmark
};

/**
 * Aureve brand mark — a calligraphic gold "A" whose left stroke flows into a
 * sweeping swash, paired with the serif "Aureve" wordmark. Refined fusion of
 * fashion (the flowing curve) and intelligence.
 */
export default function AureveLogo({
  size = 96,
  showWordmark = true,
  wordmarkSize = 34,
  color = colors.gold,
  tagline,
}: Props) {
  return (
    <View style={styles.wrap}>
      <Svg width={size} height={size} viewBox="0 0 100 100" fill="none">
        <Defs>
          <LinearGradient id="aureveGold" x1="10" y1="90" x2="90" y2="10">
            <Stop offset="0" stopColor={colors.goldDeep} />
            <Stop offset="0.5" stopColor={colors.gold} />
            <Stop offset="1" stopColor={colors.goldSoft} />
          </LinearGradient>
        </Defs>

        {/* Right leg — the confident thick stroke */}
        <Path
          d="M55 15 L88 88"
          stroke="url(#aureveGold)"
          strokeWidth={9}
          strokeLinecap="round"
        />

        {/* Left leg flowing into the signature swash */}
        <Path
          d="M55 15 C 47 38, 42 55, 34 66 C 27 76, 20 74, 9 84"
          stroke="url(#aureveGold)"
          strokeWidth={6}
          strokeLinecap="round"
          fill="none"
        />

        {/* Crossbar — a gentle wave threading the A */}
        <Path
          d="M37 62 C 50 55, 64 69, 78 62"
          stroke="url(#aureveGold)"
          strokeWidth={4.5}
          strokeLinecap="round"
          fill="none"
        />
      </Svg>

      {showWordmark && (
        <Txt style={[styles.wordmark, { fontSize: wordmarkSize, color }]}>Aureve</Txt>
      )}
      {tagline ? <Txt style={styles.tagline}>{tagline}</Txt> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", justifyContent: "center" },
  wordmark: {
    fontFamily: fonts.serif,
    letterSpacing: 1,
    marginTop: 6,
    includeFontPadding: false,
  },
  tagline: {
    fontFamily: fonts.serifRegular,
    fontSize: 13,
    letterSpacing: 3,
    color: colors.creamDim,
    marginTop: 6,
    textTransform: "uppercase",
  },
});
