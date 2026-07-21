import React, { useEffect, useState } from "react";
import { View, StyleSheet, StyleProp, ImageStyle, ViewStyle } from "react-native";
import { Image } from "expo-image";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { colors } from "@/src/theme";

// Category → a recognisable clothing glyph, so a missing/broken photo still reads
// as the right kind of piece instead of a generic broken-image icon.
const CATEGORY_ICON: Record<string, keyof typeof MaterialCommunityIcons.glyphMap> = {
  Tops: "tshirt-crew-outline",
  Dresses: "tshirt-crew-outline",
  Outerwear: "hanger",
  Bottoms: "hanger",
  Shoes: "shoe-sneaker",
  Bags: "bag-personal-outline",
  Accessories: "sunglasses",
  Jewellery: "diamond-stone",
};

type Props = {
  photo?: string | null;
  category?: string | null;
  style?: StyleProp<ImageStyle>;
  mime?: "jpeg" | "png";
  contentFit?: "cover" | "contain";
  transition?: number;
  iconSize?: number;
  testID?: string;
};

/**
 * Renders a wardrobe item's base64 photo with graceful degradation:
 * - no photo → clean category placeholder
 * - decode/render failure → one silent retry, then category placeholder
 * The item's name/details are rendered by callers separately, so they always stay visible.
 */
export default function GarmentImage({
  photo,
  category,
  style,
  mime = "jpeg",
  contentFit = "cover",
  transition = 200,
  iconSize = 26,
  testID,
}: Props) {
  const [failures, setFailures] = useState(0);

  // Reset the failure count if the photo changes (e.g. item edited/updated).
  useEffect(() => {
    setFailures(0);
  }, [photo]);

  const showPlaceholder = !photo || failures >= 2;

  if (showPlaceholder) {
    const icon = (category && CATEGORY_ICON[category]) || "hanger";
    return (
      <View style={[styles.placeholder, style]} testID={testID}>
        <MaterialCommunityIcons name={icon} size={iconSize} color={colors.onSurfaceTertiary} />
      </View>
    );
  }

  return (
    <Image
      testID={testID}
      source={{ uri: `data:image/${mime};base64,${photo}` }}
      style={style}
      contentFit={contentFit}
      transition={transition}
      // base64 changes remount cleanly; retry key nudges a fresh decode attempt.
      recyclingKey={`${failures}`}
      onError={() => {
        setFailures((f) => {
          if (f === 0) {
            console.warn("[GarmentImage] photo failed to render, retrying once", { category });
          } else if (f === 1) {
            console.warn("[GarmentImage] photo failed after retry, showing placeholder", { category });
          }
          return f + 1;
        });
      }}
    />
  );
}

const styles = StyleSheet.create({
  placeholder: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surfaceTertiary,
  } as ViewStyle,
});
