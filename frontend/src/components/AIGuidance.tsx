import React from "react";
import { Pressable, View } from "react-native";
import { useRouter } from "expo-router";
import { Txt } from "@/src/components/Typography";
import { colors, spacing } from "@/src/theme";

export default function AIGuidance() {
  const router = useRouter();
  return (
    <View style={{ gap: spacing.xs, marginVertical: spacing.md }}>
      <Txt style={{ color: colors.onSurfaceSecondary, fontSize: 12, lineHeight: 17 }}>
        AI can make mistakes. Check the suggestions and choose what suits you and the occasion.
      </Txt>
      <Pressable accessibilityRole="link" onPress={() => router.push({ pathname: "/legal", params: { doc: "help" } })} hitSlop={8}>
        <Txt style={{ color: colors.brand, fontSize: 12 }}>Help &amp; feedback</Txt>
      </Pressable>
    </View>
  );
}
