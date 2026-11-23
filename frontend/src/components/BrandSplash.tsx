import React, { useEffect } from "react";
import { StyleSheet } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import Animated, { useSharedValue, useAnimatedStyle, withTiming, withDelay, Easing } from "react-native-reanimated";
import AureveLogo from "@/src/components/AureveLogo";
import { colors } from "@/src/theme";

/**
 * Full-screen branded splash shown while the app boots / checks the session.
 * Ink background with a gold Aureve lockup that fades + rises into place.
 */
export default function BrandSplash() {
  const opacity = useSharedValue(0);
  const translateY = useSharedValue(14);

  useEffect(() => {
    opacity.value = withTiming(1, { duration: 700, easing: Easing.out(Easing.cubic) });
    translateY.value = withDelay(80, withTiming(0, { duration: 800, easing: Easing.out(Easing.cubic) }));
  }, [opacity, translateY]);

  const logoStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }));

  return (
    <LinearGradient
      colors={[colors.ink, "#141414"]}
      style={styles.container}
      testID="brand-splash"
    >
      <Animated.View style={logoStyle}>
        <AureveLogo size={120} wordmarkSize={44} tagline="Style · Intelligence · You" />
      </Animated.View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center" },
});
