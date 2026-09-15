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
 * Welcome / account screen. Shown whenever there is no valid session (fresh
 * install, sign-out or a new device). Start Free runs the normal free account
 * sign-up; Log In returns existing members.
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

  const startFree = async () => {
    await storage.setItem("aureve_launched", true);
    router.replace("/onboarding");
  };

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.content, aStyle, { paddingTop: insets.top + height * 0.14 }]}>
        {/* Official Aureve wordmark — upper third */}
        <Txt style={styles.wordmark}>Aureve</Txt>

        <View style={{ flex: 1 }} />

        <Txt style={styles.headline}>Welcome to Aureve</Txt>
        <Txt style={styles.tagline}>Your wardrobe. Your style. Your personal stylist.</Txt>
        <Txt style={styles.support}>
          Add your wardrobe, discover new combinations and see what Aureve can do with the clothes you already own.
        </Txt>

        <View style={{ flex: 1.5 }} />
      </Animated.View>

      {/* Subtle fabric-inspired graphic near the bottom */}
      <WelcomeDecor />

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.xl }]}>
        <Txt style={styles.footerLabel}>New to Aureve?</Txt>
        <Pressable style={styles.cta} testID="welcome-start-free" onPress={startFree}>
          <Txt style={styles.ctaTxt}>Start Free</Txt>
        </Pressable>
        <Pressable style={styles.secondary} testID="welcome-log-in" onPress={() => router.push("/login")}>
          <Txt style={styles.secondaryTxt}>Already have an account? Log In</Txt>
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
  tagline: {
    fontSize: 15,
    color: colors.onSurface,
    textAlign: "center",
    lineHeight: 22,
    marginTop: spacing.sm,
  },
  support: {
    fontSize: 14,
    color: colors.onSurfaceSecondary,
    textAlign: "center",
    lineHeight: 21,
    marginTop: spacing.md,
    paddingHorizontal: spacing.md,
  },
  footer: { paddingHorizontal: spacing.xl },
  footerLabel: {
    fontSize: 13,
    color: colors.onSurfaceSecondary,
    textAlign: "center",
    marginBottom: spacing.sm,
  },
  cta: {
    alignSelf: "stretch",
    backgroundColor: colors.sage,
    height: 54,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  ctaTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayBold },
  secondary: {
    height: 50,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.xs,
  },
  secondaryTxt: {
    fontSize: 14,
    color: colors.onSurface,
    fontFamily: fonts.body,
    textDecorationLine: "underline",
  },
});
