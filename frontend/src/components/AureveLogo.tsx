import React from "react";
import { View, Image, StyleSheet } from "react-native";
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
 * Aureve brand mark — the official calligraphic gold "A" (flowing swash),
 * paired with the serif "Aureve" wordmark. Refined fusion of fashion and
 * intelligence.
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
      <Image
        source={require("@/assets/images/aureve-mark.png")}
        style={{ width: size, height: size * 0.75 }}
        resizeMode="contain"
      />

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
