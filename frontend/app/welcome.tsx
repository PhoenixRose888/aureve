import React, { useEffect } from "react";
import { View, StyleSheet, Pressable, useWindowDimensions } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withDelay,
  Easing,
} from "react-native-reanimated";
import { Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { storage } from "@/src/utils/storage";
import WelcomeDecor from "@/src/components/WelcomeDecor";

/**
 * First-launch welcome screen. Shown once, then never again (gated by the
 * `aureve_launched` flag). Get Started begins onboarding.
 */
export default function Welcome() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();

  // Subtle fade + slight upward entrance.
  const opacity = useSharedValue(0);
  const ty = useSharedValue(18);
  useEffect(() => {
    opacity.value = withTiming(1, { duration: 650, easing: Easing.out(Easing.cubic) });
    ty.value = withDelay(60, withTiming(0, { duration: 700, easing: Easing.out(Easing.cubic) }));
  }, [opacity, ty]);
  const aStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: ty.value }],
  }));

  const getStarted = async () => {
    await storage.setItem("aureve_launched", true);
    router.replace("/onboarding");
  };

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.content, aStyle, { paddingTop: insets.top + height * 0.16 }]}>
        {/* Official Aureve wordmark — upper third */}
        <Txt style={styles.wordmark}>Aureve</Txt>

        <View style={{ flex: 1 }} />

        <Txt style={styles.headline}>Your AI Personal Stylist</Txt>
        <Txt style={styles.support}>Create smarter outfits from the clothes you already own.</Txt>

        <View style={{ flex: 1.5 }} />
      </Animated.View>

      {/* Subtle fabric-inspired graphic near the bottom */}
      <WelcomeDecor />

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.xl }]}>
        <Pressable style={styles.cta} testID="welcome-get-started" onPress={getStarted}>
          <Txt style={styles.ctaTxt}>Get Started</Txt>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  content: { flex: 1, alignItems: "center", paddingHorizontal: spacing.xl },
  wordmark: {
    fontFamily: fonts.serif,
    fontSize: 54,
    color: colors.onSurface,
    letterSpacing: 1,
    includeFontPadding: false,
  },
  headline: {
    fontFamily: fonts.display,
    fontSize: 24,
    color: colors.onSurface,
    letterSpacing: -0.4,
    textAlign: "center",
  },
  support: {
    fontSize: 15,
    color: colors.onSurfaceSecondary,
    textAlign: "center",
    lineHeight: 22,
    marginTop: spacing.md,
    paddingHorizontal: spacing.md,
  },
  footer: { paddingHorizontal: spacing.xl },
  cta: {
    alignSelf: "stretch",
    backgroundColor: colors.sage,
    height: 54,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  ctaTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayBold },
});
