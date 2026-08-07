import React from "react";
import { View, StyleSheet, ScrollView, Pressable } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, fonts } from "@/src/theme";

const EFFECTIVE = "June 2026";
const CONTACT = "houseoffmr@gmail.com";

type Section = { h: string; b: string };

const PRIVACY: Section[] = [
  { h: "Overview", b: `Aureve ("we", "us") helps you catalogue your wardrobe and generate outfit and styling suggestions. This policy explains what we collect and how we use it. Effective ${EFFECTIVE}.` },
  { h: "What we collect", b: "• Account details you provide (email, name, or a Google sign-in identifier).\n• Wardrobe content you add (clothing photos, item details).\n• Style profile data you choose to enter (measurements, body shape, skin tone/undertone, sizes, preferences).\n• Usage data needed to run features (e.g. outfits generated, items saved).\n• Approximate location or coarse weather data, only to tailor weather-appropriate suggestions." },
  { h: "How we use it", b: "We use your data solely to provide the app's features: storing your wardrobe, generating outfits, and personalising styling, hair and makeup suggestions. We do not sell your personal data." },
  { h: "AI processing", b: "To auto-tag clothing and generate suggestions, item photos and relevant profile details may be sent to AI providers (e.g. OpenAI and Google Gemini, accessed via Emergent) strictly to return results to you. They are not used to identify you." },
  { h: "Payments", b: "If you purchase a subscription, payment is processed by the platform's billing provider (Apple, Google, or Stripe). We do not store your full card details." },
  { h: "Data storage & retention", b: "Your data is stored securely and retained while your account is active. Guest sessions are temporary and expire automatically." },
  { h: "Deleting your data", b: "You can permanently delete your account and all associated data at any time from Profile → Privacy & data → Delete my account. This is immediate and irreversible." },
  { h: "Your choices", b: "You control what you add. Device permissions (camera, photos, location) are optional and requested only when a feature needs them; you can change them anytime in your device settings." },
  { h: "Contact", b: `Questions about your privacy? Contact us at ${CONTACT}.` },
];

const TERMS: Section[] = [
  { h: "Acceptance", b: `By using Aureve you agree to these Terms. If you do not agree, please do not use the app. Effective ${EFFECTIVE}.` },
  { h: "Your account", b: "You are responsible for keeping your login details secure and for activity under your account. You must provide accurate information when creating an account." },
  { h: "Acceptable use", b: "Use Aureve for your personal styling only. Do not upload unlawful content, attempt to disrupt the service, or misuse the AI features." },
  { h: "Styling & AI suggestions", b: "Outfit, hair, makeup and body-shape suggestions are provided for guidance and inspiration only. They are generated automatically and may not always be accurate — use your own judgement." },
  { h: "Subscriptions & payments", b: "Some features may require a paid subscription. Billing, renewals and refunds are handled by the store or payment provider you purchase through (Apple, Google, or Stripe), subject to their terms." },
  { h: "Your content", b: "You keep ownership of the photos and details you add. You grant us a limited licence to process them only to provide the app's features to you." },
  { h: "Termination", b: "You may delete your account at any time. We may suspend accounts that violate these Terms." },
  { h: "Disclaimer & liability", b: "The app is provided \u201Cas is\u201D. To the extent permitted by law, we are not liable for indirect or incidental losses arising from use of the app." },
  { h: "Changes", b: "We may update these Terms from time to time; continued use means you accept the updated version." },
  { h: "Contact", b: `Questions about these Terms? Contact us at ${CONTACT}.` },
];

export default function Legal() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { doc } = useLocalSearchParams<{ doc?: string }>();
  const isTerms = doc === "terms";
  const title = isTerms ? "Terms of Service" : "Privacy Policy";
  const sections = isTerms ? TERMS : PRIVACY;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="legal-back">
          <Feather name="chevron-left" size={26} color={colors.onSurface} />
        </Pressable>
        <Txt style={styles.headerTitle}>{title}</Txt>
        <View style={{ width: 26 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: insets.bottom + spacing["2xl"] }} showsVerticalScrollIndicator={false}>
        <Display weight="semibold" style={styles.docTitle}>{title}</Display>
        {sections.map((s, i) => (
          <View key={i} style={styles.section}>
            <Txt style={styles.h}>{s.h}</Txt>
            <Txt style={styles.b}>{s.b}</Txt>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  headerTitle: { fontSize: 16, fontFamily: fonts.displayMedium, color: colors.onSurface },
  docTitle: { fontSize: 28, letterSpacing: -0.5, color: colors.onSurface, marginBottom: spacing.xl },
  section: { marginBottom: spacing.xl },
  h: { fontSize: 15, fontFamily: fonts.displayMedium, color: colors.onSurface, marginBottom: spacing.xs },
  b: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 22 },
});
