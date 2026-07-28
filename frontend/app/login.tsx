import React, { useEffect, useState } from "react";
import { View, StyleSheet, Pressable, ActivityIndicator, useWindowDimensions, TextInput, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "@/src/context/AuthContext";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, fonts, radius } from "@/src/theme";

const HERO =
  "https://images.unsplash.com/photo-1578102718171-ec1f91680562?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1Nzl8MHwxfHNlYXJjaHwxfHxjaGljJTIwc3RyZWV0JTIwc3R5bGUlMjBvdXRmaXR8ZW58MHx8fHwxNzg0MDQ2MTUwfDA&ixlib=rb-4.1.0&q=85";

export default function Login() {
  const { user, login, guestLogin, loginEmail, registerEmail, signingIn, loading } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();

  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) router.replace("/(tabs)");
  }, [user, router]);

  const submitEmail = async () => {
    setError("");
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setBusy(true);
    try {
      if (mode === "signup") await registerEmail(email.trim(), password);
      else await loginEmail(email.trim(), password);
    } catch (e: any) {
      setError(e?.message || "Something went wrong. Please try again.");
    }
    setBusy(false);
  };

  return (
    <View style={styles.container} testID="login-screen">
      <Image source={{ uri: HERO }} style={[styles.hero, { height: height * 0.55 }]} contentFit="cover" transition={300} />
      <LinearGradient
        colors={["rgba(26,26,26,0.1)", "rgba(26,26,26,0.6)", colors.surfaceInverse]}
        locations={[0, 0.45, 0.85]}
        style={StyleSheet.absoluteFill}
      />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView
          contentContainerStyle={[styles.scroll, { paddingTop: insets.top + height * 0.16, paddingBottom: insets.bottom + spacing.xl }]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Txt style={styles.kicker}>YOUR PERSONAL STYLIST</Txt>
          <Display weight="medium" style={styles.title}>Wear everything{"\n"}you own.</Display>

          <View style={styles.form}>
            <TextInput
              testID="login-email"
              style={styles.input}
              placeholder="Email"
              placeholderTextColor="rgba(250,250,250,0.5)"
              autoCapitalize="none"
              keyboardType="email-address"
              autoComplete="email"
              value={email}
              onChangeText={setEmail}
            />
            <TextInput
              testID="login-password"
              style={styles.input}
              placeholder="Password"
              placeholderTextColor="rgba(250,250,250,0.5)"
              secureTextEntry
              value={password}
              onChangeText={setPassword}
            />
            {error ? <Txt style={styles.error} testID="login-error">{error}</Txt> : null}

            <Pressable style={styles.primaryBtn} testID="email-submit" onPress={submitEmail} disabled={busy || signingIn}>
              {busy ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <Txt style={styles.primaryTxt}>{mode === "signup" ? "Create account" : "Sign in"}</Txt>
              )}
            </Pressable>

            <Pressable onPress={() => { setError(""); setMode(mode === "signup" ? "signin" : "signup"); }} testID="toggle-mode" hitSlop={8}>
              <Txt style={styles.toggle}>
                {mode === "signup" ? "Already have an account? Sign in" : "New to Aureve? Create an account"}
              </Txt>
            </Pressable>
          </View>

          <View style={styles.divider}>
            <View style={styles.line} /><Txt style={styles.or}>or</Txt><View style={styles.line} />
          </View>

          <Pressable testID="google-login-button" style={styles.googleBtn} onPress={login} disabled={signingIn || loading}>
            {signingIn ? (
              <ActivityIndicator color={colors.onSurface} />
            ) : (
              <>
                <Feather name="log-in" size={18} color={colors.onSurface} />
                <Txt style={styles.googleTxt}>Continue with Google</Txt>
              </>
            )}
          </Pressable>
          <Pressable testID="guest-login-button" style={styles.guestBtn} onPress={guestLogin} disabled={signingIn || loading}>
            <Txt style={styles.guestTxt}>Explore as guest</Txt>
          </Pressable>

          <View style={styles.legalRow}>
            <Pressable onPress={() => router.push({ pathname: "/legal", params: { doc: "privacy" } })} hitSlop={8}>
              <Txt style={styles.legalLink}>Privacy Policy</Txt>
            </Pressable>
            <Txt style={styles.legalDot}>·</Txt>
            <Pressable onPress={() => router.push({ pathname: "/legal", params: { doc: "terms" } })} hitSlop={8}>
              <Txt style={styles.legalLink}>Terms</Txt>
            </Pressable>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surfaceInverse },
  hero: { position: "absolute", top: 0, left: 0, right: 0 },
  scroll: { flexGrow: 1, justifyContent: "flex-end", paddingHorizontal: spacing.xl },
  kicker: { color: colors.brandTertiary, fontSize: 12, letterSpacing: 3, marginBottom: spacing.md },
  title: { color: colors.onSurfaceInverse, fontSize: 40, lineHeight: 44, marginBottom: spacing.xl },
  form: { gap: spacing.md },
  input: {
    backgroundColor: "rgba(255,255,255,0.10)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.18)",
    borderRadius: radius.md,
    height: 52,
    paddingHorizontal: spacing.lg,
    fontFamily: fonts.body,
    fontSize: 15,
    color: colors.onSurfaceInverse,
  },
  error: { color: "#F0B4A8", fontSize: 13, marginTop: -2 },
  primaryBtn: { backgroundColor: colors.sage, height: 54, borderRadius: radius.md, alignItems: "center", justifyContent: "center", marginTop: spacing.xs },
  primaryTxt: { color: colors.onSage, fontSize: 16, fontFamily: fonts.displayBold },
  toggle: { color: "rgba(250,250,250,0.85)", fontSize: 14, textAlign: "center", marginTop: spacing.sm, textDecorationLine: "underline" },
  divider: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginVertical: spacing.lg },
  line: { flex: 1, height: 1, backgroundColor: "rgba(255,255,255,0.2)" },
  or: { color: "rgba(250,250,250,0.6)", fontSize: 12 },
  googleBtn: { backgroundColor: colors.surface, height: 54, borderRadius: radius.md, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  googleTxt: { color: colors.onSurface, fontSize: 16, fontFamily: fonts.displayBold },
  guestBtn: { height: 50, borderRadius: radius.md, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  guestTxt: { color: colors.onSurfaceInverse, fontSize: 15, fontFamily: fonts.body, textDecorationLine: "underline" },
  legalRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, marginTop: spacing.lg },
  legalLink: { color: "rgba(250,250,250,0.55)", fontSize: 12, textDecorationLine: "underline" },
  legalDot: { color: "rgba(250,250,250,0.4)", fontSize: 12 },
});
