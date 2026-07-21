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
  fallbackPhoto?: string | null;   // e.g. a worn photo to use if the main photo is missing/broken
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
 * - main photo missing → try the fallback (worn) photo
 * - decode/render failure → one silent retry, then the next candidate
 * - all candidates exhausted → clean category placeholder
 * The item's name/details are rendered by callers separately, so they always stay visible.
 */
export default function GarmentImage({
  photo,
  fallbackPhoto,
  category,
  style,
  mime = "jpeg",
  contentFit = "cover",
  transition = 200,
  iconSize = 26,
  testID,
}: Props) {
  // Ordered list of base64 sources to try (main first, then fallback).
  const candidates = React.useMemo(
    () => [photo, fallbackPhoto].filter((c): c is string => !!c && !!c.trim()),
    [photo, fallbackPhoto]
  );
  const [idx, setIdx] = useState(0);
  const [failures, setFailures] = useState(0);

  // Reset when the sources change (e.g. item edited/updated).
  useEffect(() => {
    setIdx(0);
    setFailures(0);
  }, [photo, fallbackPhoto]);

  const current = candidates[idx];
  const showPlaceholder = !current;

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
      source={{ uri: `data:image/${mime};base64,${current}` }}
      style={style}
      contentFit={contentFit}
      transition={transition}
      // base64 changes remount cleanly; retry key nudges a fresh decode attempt.
      recyclingKey={`${idx}-${failures}`}
      onError={() => {
        // Retry the current source once, then advance to the next candidate.
        if (failures === 0) {
          setFailures(1);
        } else {
          setIdx((i) => i + 1);
          setFailures(0);
        }
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
