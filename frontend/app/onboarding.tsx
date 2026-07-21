import React, { useRef, useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, Dimensions } from "react-native";
import { useRouter } from "expo-router";
import { Feather, MaterialCommunityIcons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { storage } from "@/src/utils/storage";

const { width } = Dimensions.get("window");

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
  const scrollRef = useRef<ScrollView>(null);
  const [page, setPage] = useState(0);
  const total = 1 + VALUE_SLIDES.length; // welcome + value slides

  const goTo = (p: number) => {
    scrollRef.current?.scrollTo({ x: p * width, animated: true });
    setPage(p);
  };

  const finish = async () => {
    await storage.setItem("aureve_onboarded", true);
    router.replace("/login");
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
        <View style={[styles.slide, { paddingTop: insets.top + spacing["3xl"] }]}>
          <Txt style={styles.wordmark}>AUREVE</Txt>
          <View style={styles.heroCircle}>
            <MaterialCommunityIcons name="wardrobe-outline" size={64} color={colors.onBrandTertiary} />
          </View>
          <Display weight="semibold" style={styles.welcomeTitle}>Your Personal Stylist</Display>
          <Txt style={styles.welcomeBody}>
            Build your digital wardrobe, get AI-powered outfit recommendations, and never wonder what to
            wear again.
          </Txt>
          <View style={{ flex: 1 }} />
          <Pressable style={styles.primaryBtn} testID="onb-get-started" onPress={() => goTo(1)}>
            <Txt style={styles.primaryTxt}>Get Started</Txt>
          </Pressable>
          <Pressable style={styles.signIn} testID="onb-signin" onPress={finish}>
            <Txt style={styles.signInTxt}>Sign In</Txt>
          </Pressable>
          <View style={{ height: insets.bottom + spacing.lg }} />
        </View>

        {/* Value props */}
        {VALUE_SLIDES.map((s, i) => (
          <View key={i} style={[styles.slide, { paddingTop: insets.top + spacing["3xl"] }]}>
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
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  slide: { width, flex: 1, paddingHorizontal: spacing.xl, alignItems: "center" },
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
});
