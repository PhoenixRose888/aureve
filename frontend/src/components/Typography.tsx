import React from "react";
import { Text, TextProps, StyleSheet } from "react-native";
import { colors, fonts } from "@/src/theme";

type Props = TextProps & { children: React.ReactNode };

// Display headings (Inter) — editorial, tight tracking, premium.
export function Display(props: Props & { weight?: "regular" | "medium" | "semibold" | "bold" }) {
  const { style, weight = "semibold", ...rest } = props;
  const family =
    weight === "bold"
      ? fonts.displayBold
      : weight === "medium"
      ? fonts.displayMedium
      : weight === "regular"
      ? fonts.displayRegular
      : fonts.display;
  return <Text {...rest} style={[styles.display, { fontFamily: family }, style]} />;
}

// Body / UI text (Inter Regular)
export function Txt(props: Props) {
  const { style, ...rest } = props;
  return <Text {...rest} style={[styles.body, style]} />;
}

const styles = StyleSheet.create({
  display: {
    color: colors.onSurface,
    letterSpacing: -0.4,
  },
  body: {
    fontFamily: fonts.body,
    color: colors.onSurface,
    letterSpacing: -0.1,
  },
});
