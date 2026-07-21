import React, { useRef, useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, useWindowDimensions, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { Feather, MaterialCommunityIcons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { useSharedValue, useAnimatedStyle, withTiming, Easing, runOnJS } from "react-native-reanimated";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { storage } from "@/src/utils/storage";
import { useAuth } from "@/src/context/AuthContext";
import AureveWelcomeMark from "@/src/components/AureveWelcomeMark";
import WelcomeDecor from "@/src/components/WelcomeDecor";

type Slide = { icon: React.ReactNode; title: string; body: string };

const VALUE_SLIDES: Slide[] = [
  {
    icon: <MaterialCommunityIcons name="hanger" size={44} color={colors.onBrandTertiary} />,
    title: "Build Your\nDigital Wardrobe",
    body: "Snap photos of your clothes and let AI organise everything. Your entire wardrobe, always in your pocket.",
  },
  {
    icon: <Feather name="star" size={40} color={colors.onBrandTertiary} />,
    title: "Get Personalised\nRecommendations",
    body: "Aureve considers the weather, your schedule and your style to suggest perfect outfits every day — like a stylist on call.",
  },
  {
    icon: <Feather name="calendar" size={40} color={colors.onBrandTertiary} />,
    title: "Plan Your Week\nwith Confidence",
    body: "Create outfits in advance, track what you wear, and never repeat the same look too soon.",
  },
];

export default function Onboarding() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guestLogin } = useAuth();
  const { width } = useWindowDimensions();
  const scrollRef = useRef<ScrollView>(null);
  const [page, setPage] = useState(0);
  const [entering, setEntering] = useState(false);
  const total = 1 + VALUE_SLIDES.length; // welcome + value slides

  const fade = useSharedValue(0);
  const fadeStyle = useAnimatedStyle(() => ({ opacity: fade.value }));

  const goTo = (p: number) => {
    scrollRef.current?.scrollTo({ x: p * width, animated: true });
    setPage(p);
  };

  const finish = async () => {
    await storage.setItem("aureve_onboarded", true);
    router.replace("/login");
  };

  // Get Started → fade the welcome out, spin up a guest session, and land the
  // user in the app Home (which surfaces the Dress Me hero).
  const enterApp = async () => {
    if (entering) return;
    setEntering(true);
    await storage.setItem("aureve_onboarded", true);
    try {
      await guestLogin();
    } catch {}
    const go = () => router.replace("/(tabs)");
    fade.value = withTiming(1, { duration: 550, easing: Easing.inOut(Easing.cubic) }, (finished) => {
      if (finished) runOnJS(go)();
    });
  };

  const next = () => (page < total - 1 ? goTo(page + 1) : finish());

  return (
    <View style={styles.container}>
      <ScrollView
        ref={scrollRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        scrollEventThrottle={16}
        onMomentumScrollEnd={(e) => setPage(Math.round(e.nativeEvent.contentOffset.x / width))}
      >
        {/* Welcome */}
        <View style={[styles.slide, styles.welcomeSlide, { width, paddingTop: insets.top + spacing["3xl"] }]}>
          <View style={{ flex: 1 }} />
          <AureveWelcomeMark size={72} />
          <Txt style={styles.brandWord}>Aureve</Txt>
          <Txt style={styles.tagline1}>Your AI Personal Stylist</Txt>
          <Txt style={styles.tagline2}>Make the most of what you already own.</Txt>
          <View style={{ flex: 1.3 }} />
          <WelcomeDecor />
          <Pressable style={styles.primaryBtn} testID="onb-get-started" onPress={enterApp} disabled={entering}>
            {entering ? <ActivityIndicator color={colors.onSage} /> : <Txt style={styles.primaryTxt}>Get Started</Txt>}
          </Pressable>
          <Pressable style={styles.signIn} testID="onb-signin" onPress={finish} disabled={entering}>
            <Txt style={styles.signInTxt}>I already have an account</Txt>
          </Pressable>
          <View style={{ height: insets.bottom + spacing.lg }} />
        </View>

        {/* Value props */}
        {VALUE_SLIDES.map((s, i) => (
          <View key={i} style={[styles.slide, { width, paddingTop: insets.top + spacing["3xl"] }]}>
            <View style={styles.heroCircle}>{s.icon}</View>
            <Display weight="semibold" style={styles.valueTitle}>{s.title}</Display>
            <Txt style={styles.valueBody}>{s.body}</Txt>
            <View style={{ flex: 1 }} />
            <Pressable style={styles.primaryBtn} testID={`onb-continue-${i}`} onPress={next}>
              <Txt style={styles.primaryTxt}>{i === VALUE_SLIDES.length - 1 ? "Get Started" : "Continue"}</Txt>
            </Pressable>
            <Pressable style={styles.signIn} testID={`onb-skip-${i}`} onPress={finish}>
              <Txt style={styles.signInTxt}>Skip</Txt>
            </Pressable>
            <View style={{ height: insets.bottom + spacing.lg }} />
          </View>
        ))}
      </ScrollView>

      {/* Dots */}
      <View style={[styles.dots, { top: insets.top + spacing.md }]} pointerEvents="none">
        {Array.from({ length: total }).map((_, i) => (
          <View key={i} style={[styles.dot, page === i && styles.dotActive]} />
        ))}
      </View>

      {/* Fade-to-cream overlay when entering Dress Me */}
      <Animated.View style={[styles.fadeCover, fadeStyle]} pointerEvents={entering ? "auto" : "none"} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  slide: { flex: 1, paddingHorizontal: spacing.xl, alignItems: "center" },
  welcomeSlide: { justifyContent: "flex-end" },
  brandWord: { fontFamily: fonts.serif, fontSize: 52, color: colors.onSurface, marginTop: spacing.sm, letterSpacing: 1, includeFontPadding: false },
  tagline1: { fontFamily: fonts.serifRegular, fontSize: 18, color: colors.onSurfaceSecondary, marginTop: spacing.lg },
  tagline2: { fontFamily: fonts.body, fontSize: 14, color: colors.onSurfaceTertiary, marginTop: spacing.xs, textAlign: "center" },
  wordmark: { fontSize: 24, letterSpacing: 6, color: colors.onSurface, fontFamily: fonts.displayMedium, marginBottom: spacing["2xl"] },
  heroCircle: { width: 160, height: 160, borderRadius: 80, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", marginBottom: spacing["2xl"] },
  welcomeTitle: { fontSize: 28, textAlign: "center", marginBottom: spacing.md },
  welcomeBody: { fontSize: 15, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 23, paddingHorizontal: spacing.md },
  valueTitle: { fontSize: 27, textAlign: "center", marginBottom: spacing.lg, lineHeight: 34 },
  valueBody: { fontSize: 15, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 23, paddingHorizontal: spacing.sm },
  primaryBtn: { alignSelf: "stretch", backgroundColor: colors.sage, height: 54, borderRadius: radius.md, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  primaryTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayMedium },
  signIn: { paddingVertical: spacing.sm },
  signInTxt: { fontSize: 15, color: colors.onSurfaceSecondary },
  dots: { position: "absolute", left: 0, right: 0, flexDirection: "row", justifyContent: "center", gap: 6 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.surfaceTertiary },
  dotActive: { backgroundColor: colors.sage, width: 18 },
  fadeCover: { ...StyleSheet.absoluteFillObject, backgroundColor: colors.surface },
});
