import React, { useEffect } from "react";
import { View, StyleSheet, Pressable, ActivityIndicator, Dimensions } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useAuth } from "@/src/context/AuthContext";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, fonts } from "@/src/theme";

const { height } = Dimensions.get("window");

const HERO =
  "https://images.unsplash.com/photo-1578102718171-ec1f91680562?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1Nzl8MHwxfHNlYXJjaHwxfHxjaGljJTIwc3RyZWV0JTIwc3R5bGUlMjBvdXRmaXR8ZW58MHx8fHwxNzg0MDQ2MTUwfDA&ixlib=rb-4.1.0&q=85";

export default function Login() {
  const { user, login, guestLogin, signingIn, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user) router.replace("/(tabs)");
  }, [user, router]);

  return (
    <View style={styles.container} testID="login-screen">
      <Image source={{ uri: HERO }} style={styles.hero} contentFit="cover" transition={300} />
      <LinearGradient
        colors={["rgba(26,26,26,0.1)", "rgba(26,26,26,0.55)", colors.surfaceInverse]}
        locations={[0, 0.5, 0.92]}
        style={StyleSheet.absoluteFill}
      />
      <View style={styles.content}>
        <Txt style={styles.kicker}>YOUR PERSONAL STYLIST</Txt>
        <Display weight="medium" style={styles.title}>
          Wear everything{"\n"}you own.
        </Display>
        <Txt style={styles.subtitle}>
          Catalogue your wardrobe, build outfits from what you actually own, and let Aureve learn what
          truly flatters you.
        </Txt>

        <Pressable
          testID="google-login-button"
          style={styles.googleBtn}
          onPress={login}
          disabled={signingIn || loading}
        >
          {signingIn ? (
            <ActivityIndicator color={colors.onSurface} />
          ) : (
            <>
              <Feather name="log-in" size={18} color={colors.onSurface} />
              <Txt style={styles.googleTxt}>Continue with Google</Txt>
            </>
          )}
        </Pressable>
        <Pressable
          testID="guest-login-button"
          style={styles.guestBtn}
          onPress={guestLogin}
          disabled={signingIn || loading}
        >
          <Txt style={styles.guestTxt}>Explore as guest</Txt>
        </Pressable>
        <Txt style={styles.terms}>
          Start building your wardrobe now — sign in anytime to back it up.
        </Txt>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  hero: { position: "absolute", top: 0, left: 0, right: 0, height: height * 0.75 },
  content: { flex: 1, justifyContent: "flex-end", paddingHorizontal: spacing.xl, paddingBottom: spacing["3xl"] },
  kicker: {
    color: colors.brandTertiary,
    fontSize: 12,
    letterSpacing: 3,
    marginBottom: spacing.md,
  },
  title: { color: colors.onSurfaceInverse, fontSize: 52, lineHeight: 54, marginBottom: spacing.lg },
  subtitle: {
    color: "rgba(250,250,250,0.8)",
    fontSize: 15,
    lineHeight: 22,
    marginBottom: spacing["2xl"],
  },
  googleBtn: {
    backgroundColor: colors.surface,
    height: 56,
    borderRadius: 4,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  googleTxt: { color: colors.onSurface, fontSize: 16, fontFamily: fonts.body },
  guestBtn: {
    height: 52,
    borderRadius: 4,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.md,
  },
  guestTxt: { color: colors.onSurfaceInverse, fontSize: 15, fontFamily: fonts.body, textDecorationLine: "underline" },
  terms: { color: "rgba(250,250,250,0.5)", fontSize: 12, textAlign: "center", marginTop: spacing.lg },
});
