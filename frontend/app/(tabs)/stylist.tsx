import React, { useCallback, useRef, useState } from "react";
import { View, StyleSheet, Pressable, TextInput, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { useWeather } from "@/src/hooks/useWeather";
import { useRotatingMessage } from "@/src/hooks/useRotatingMessage";
import GarmentImage from "@/src/components/GarmentImage";
import * as haptics from "@/src/utils/haptics";

type Msg = { role: "user" | "assistant"; content: string; outfit?: any; saved?: boolean };

const SUGGESTIONS = [
  { icon: "sun", label: "Help me dress for today" },
  { icon: "grid", label: "Show me outfit ideas" },
  { icon: "moon", label: "What should I wear tonight?" },
];

export default function Stylist() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { weather, status } = useWeather();
  const scrollRef = useRef<ScrollView>(null);

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const typingMsg = useRotatingMessage(sending, [
    "Thinking about your style…",
    "Reviewing your wardrobe…",
    "Pairing pieces that work…",
  ]);

  const scrollDown = () => setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 60);

  const send = useCallback(async (text: string) => {
    const content = text.trim();
    if (!content || sending) return;
    haptics.tap();
    const history = [...messages, { role: "user" as const, content }];
    setMessages(history);
    setInput("");
    setSending(true);
    scrollDown();
    try {
      const body: any = { messages: history.map((m) => ({ role: m.role, content: m.content })) };
      if (weather && status === "done") { body.temperature = weather.temperature; body.weather = weather.description; }
      const r = await api<any>("/stylist/chat", { method: "POST", body });
      setMessages((prev) => [...prev, { role: "assistant", content: r.reply, outfit: r.outfit }]);
      haptics.success();
    } catch (e: any) {
      if (e.status === 402) { router.push("/premium"); }
      else setMessages((prev) => [...prev, { role: "assistant", content: "Sorry — I couldn't reach the styling engine just then. Try again in a moment." }]);
    }
    setSending(false);
    scrollDown();
  }, [messages, sending, weather, status, router]);

  const saveOutfit = async (idx: number) => {
    const m = messages[idx];
    if (!m?.outfit || m.saved) return;
    haptics.tap();
    try {
      await api("/outfits", { method: "POST", body: { name: m.outfit.name || "Stylist look", item_ids: m.outfit.item_ids, source: "ai", notes: m.content } });
      setMessages((prev) => prev.map((x, i) => (i === idx ? { ...x, saved: true } : x)));
      haptics.success();
    } catch {}
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        {router.canGoBack() ? (
          <Pressable onPress={() => router.back()} hitSlop={12}><Feather name="chevron-left" size={26} color={colors.onSurface} /></Pressable>
        ) : <View style={{ width: 26 }} />}
        <Display weight="medium" style={styles.headerTitle}>AI Stylist</Display>
        <Pressable onPress={() => { haptics.tap(); setMessages([]); }} hitSlop={12} testID="stylist-clear"><Feather name="edit" size={20} color={colors.onSurface} /></Pressable>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined} keyboardVerticalOffset={insets.top + 44}>
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={styles.scroll}
          showsVerticalScrollIndicator={false}
          onContentSizeChange={scrollDown}
          keyboardShouldPersistTaps="handled"
        >
          {messages.length === 0 ? (
            <View style={styles.welcome}>
              <View style={styles.avatarLg}><Feather name="star" size={22} color={colors.onBrandTertiary} /></View>
              <View style={styles.bubbleAssistant}>
                <Txt style={styles.bubbleTxt}>
                  Hello! I&rsquo;m your personal stylist. I can help you create outfits, suggest combinations, and answer
                  questions about your wardrobe. What would you like help with today?
                </Txt>
              </View>
              <View style={styles.suggestions}>
                {SUGGESTIONS.map((s) => (
                  <Pressable key={s.label} style={styles.suggestion} testID={`stylist-suggest-${s.icon}`} onPress={() => send(s.label)}>
                    <Feather name={s.icon as any} size={16} color={colors.onSurfaceSecondary} />
                    <Txt style={styles.suggestionTxt}>{s.label}</Txt>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : (
            messages.map((m, i) =>
              m.role === "user" ? (
                <View key={i} style={styles.userRow}>
                  <View style={styles.bubbleUser}>
                    <Txt style={styles.bubbleUserTxt}>{m.content}</Txt>
                    <Txt style={styles.stamp}>Just now</Txt>
                  </View>
                </View>
              ) : (
                <View key={i} style={styles.assistantRow}>
                  <View style={styles.avatarSm}><Feather name="star" size={13} color={colors.onBrandTertiary} /></View>
                  <View style={{ flex: 1 }}>
                    <View style={styles.bubbleAssistant}>
                      <Txt style={styles.bubbleTxt}>{m.content}</Txt>
                    </View>
                    {m.outfit ? (
                      <View style={styles.outfitCard} testID={`stylist-outfit-${i}`}>
                        <Txt style={styles.outfitName}>{m.outfit.name}</Txt>
                        <View style={styles.outfitThumbs}>
                          {(m.outfit.items || []).map((it: any) => (
                            <View key={it.id} style={styles.thumbWrap}>
                              <GarmentImage photo={it.photo} category={it.category} style={styles.thumb} iconSize={16} />
                              <Txt style={styles.thumbName} numberOfLines={1}>{it.name}</Txt>
                            </View>
                          ))}
                        </View>
                        <Pressable style={[styles.saveOutfit, m.saved && styles.saveOutfitDone]} onPress={() => saveOutfit(i)} disabled={m.saved} testID={`stylist-save-${i}`}>
                          {m.saved ? <Feather name="check" size={14} color={colors.onSage} /> : null}
                          <Txt style={styles.saveOutfitTxt}>{m.saved ? "Saved to Outfits" : "Save this outfit"}</Txt>
                        </Pressable>
                      </View>
                    ) : null}
                  </View>
                </View>
              )
            )
          )}

          {sending && (
            <View style={styles.assistantRow}>
              <View style={styles.avatarSm}><Feather name="star" size={13} color={colors.onBrandTertiary} /></View>
              <View style={[styles.bubbleAssistant, styles.typingBubble]}>
                <Txt style={styles.typingTxt}>{typingMsg}</Txt>
              </View>
            </View>
          )}
        </ScrollView>

        <View style={[styles.inputBar, { paddingBottom: insets.bottom + spacing.sm }]}>
          <TextInput
            style={styles.input}
            placeholder="Type a message…"
            placeholderTextColor={colors.onSurfaceTertiary}
            value={input}
            onChangeText={setInput}
            onSubmitEditing={() => send(input)}
            returnKeyType="send"
            testID="stylist-input"
          />
          <Pressable style={styles.sendBtn} onPress={() => send(input)} disabled={!input.trim() || sending} testID="stylist-send">
            <Feather name="arrow-up" size={20} color={colors.onSage} />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  headerTitle: { fontSize: 18 },
  scroll: { padding: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md },
  welcome: { gap: spacing.lg },
  avatarLg: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  avatarSm: { width: 28, height: 28, borderRadius: 14, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", marginTop: 2 },
  bubbleAssistant: { backgroundColor: colors.surfaceSecondary, borderRadius: 18, borderTopLeftRadius: 4, padding: spacing.md, maxWidth: "88%" },
  bubbleTxt: { fontSize: 15, color: colors.onSurface, lineHeight: 22 },
  suggestions: { gap: spacing.sm, marginTop: spacing.sm },
  suggestion: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 48 },
  suggestionTxt: { fontSize: 14, color: colors.onSurface },
  userRow: { alignItems: "flex-end" },
  bubbleUser: { backgroundColor: colors.sage, borderRadius: 18, borderTopRightRadius: 4, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, maxWidth: "82%" },
  bubbleUserTxt: { fontSize: 15, color: colors.onSage, lineHeight: 21 },
  stamp: { fontSize: 10, color: "rgba(255,255,255,0.75)", marginTop: 3, textAlign: "right" },
  assistantRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  outfitCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.sm, maxWidth: "88%" },
  outfitName: { fontSize: 14, color: colors.onSurface, fontFamily: fonts.displayMedium, marginBottom: spacing.sm },
  outfitThumbs: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  thumbWrap: { width: 60 },
  thumb: { width: 60, height: 72, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  thumbName: { fontSize: 10, color: colors.onSurfaceTertiary, marginTop: 2 },
  saveOutfit: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.sage, height: 40, borderRadius: radius.sm, marginTop: spacing.md },
  saveOutfitDone: { backgroundColor: colors.sagePressed },
  saveOutfitTxt: { fontSize: 14, color: colors.onSage, fontFamily: fonts.displayMedium },
  typingBubble: { paddingVertical: spacing.md },
  typingTxt: { fontSize: 14, color: colors.onSurfaceSecondary, fontStyle: "italic" },
  inputBar: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingTop: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.border, backgroundColor: colors.surface },
  input: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: 24, paddingHorizontal: spacing.lg, height: 48, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface },
  sendBtn: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
});
