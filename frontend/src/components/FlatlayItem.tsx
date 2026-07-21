import React from "react";
import { StyleProp, ImageStyle, ViewStyle } from "react-native";
import Animated from "react-native-reanimated";
import { withDelay, withTiming, Easing } from "react-native-reanimated";
import GarmentImage from "@/src/components/GarmentImage";

type Props = {
  photo?: string | null;
  category?: string | null;
  index: number;
  style?: StyleProp<ImageStyle>;
  iconSize?: number;
  testID?: string;
  wrapperStyle?: StyleProp<ViewStyle>;
};

// Signature Aureve reveal: each piece fades + gently scales into place in
// sequence. Runs entirely on the UI thread (Reanimated) so it stays smooth on
// low-powered devices. Total sequence for 3-4 items lands ~600-800ms.
export default function FlatlayItem({ photo, category, index, style, iconSize, testID, wrapperStyle }: Props) {
  const entering = () => {
    "worklet";
    const delay = index * 110;
    const cfg = { duration: 320, easing: Easing.out(Easing.cubic) };
    return {
      initialValues: { opacity: 0, transform: [{ scale: 0.94 }, { translateY: 10 }] },
      animations: {
        opacity: withDelay(delay, withTiming(1, cfg)),
        transform: [
          { scale: withDelay(delay, withTiming(1, cfg)) },
          { translateY: withDelay(delay, withTiming(0, cfg)) },
        ],
      },
    };
  };

  return (
    <Animated.View entering={entering} style={wrapperStyle}>
      <GarmentImage photo={photo} category={category} style={style} contentFit="contain" iconSize={iconSize} testID={testID} />
    </Animated.View>
  );
}
