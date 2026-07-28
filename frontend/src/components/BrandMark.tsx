import React from "react";
import { Image, StyleProp, ImageStyle } from "react-native";

/**
 * Subtle Aureve brand mark — the gold "A" glyph (transparent background) for
 * placing quietly in screen headers so each page "owns" the Aureve identity.
 */
export default function BrandMark({ style }: { style?: StyleProp<ImageStyle> }) {
  return (
    <Image
      source={require("@/assets/images/aureve-mark.png")}
      style={[{ width: 34, height: 25, opacity: 0.85 }, style]}
      resizeMode="contain"
    />
  );
}
