import { shortItemName, shortItemReferences } from "@/src/utils/itemLabel";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, StyleSheet, Pressable, TextInput, ScrollView, KeyboardAvoidingView, Platform, Modal } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { useWeather } from "@/src/hooks/useWeather";
import { useRotatingMessage } from "@/src/hooks/useRotatingMessage";
import GarmentImage from "@/src/components/GarmentImage";
import StylistMessage from "@/src/components/StylistMessage";
import AIGuidance from "@/src/components/AIGuidance";
import { usePremiumAccess } from "@/src/hooks/usePremiumAccess";
import * as haptics from "@/src/utils/haptics";

type Msg = { role: "user" | "assistant"; content: string; outfit?: any; saved?: boolean };

const SUGGESTIONS = [
  { icon: "help-circle", label: "What am I missing from my wardrobe?" },
  { icon: "edit-3", label: "I want to look more polished. What would you change?" },
  { icon: "layers", label: "Help me style a piece I never wear" },
  { icon: "briefcase", label: "Which of my clothes work best for work?" },
];

const ASKS_WHAT_TO_WEAR =
  /(what should i wear|what do i wear|what to wear|help me dress|dress me|style me|what should i put on|outfit ideas?|pick (?:me )?an outfit)/;
const HAS_OCCASION =
  /\b(work|office|meeting|presentation|conference|interview|wedding|funeral|church|date|dinner|lunch|brunch|drinks|party|birthday|club|nightclub|pub|gig|concert|theatre|movie|movies|cinema|picnic|bbq|barbecue|school|uni|gym|workout|yoga|run|walk|hike|beach|pool|shopping|errands|airport|flight|travel|holiday|vacation|graduation|christening|baby shower|race day|gala|formal|black tie|cocktail|casual|smart casual|home|festival|reunion|girls night|night out|weekend away)\b/;
const VAGUE_TIME = /\b(today|tonight|this morning|this afternoon|this evening|tomorrow|later|the weekend)\b/;

/** Ask what they're doing before styling a vague request — but only once. */
function needsOccasionContext(text: string, history: { role: string; content: string }[]) {
  const t = text.trim().toLowerCase();
  if (!t || !ASKS_WHAT_TO_WEAR.test(t)) return false;
  if (history.some((m) => m.role === "assistant" && m.content.trim().endsWith("?"))) return false;
  const said = history
    .filter((m) => m.role === "user")
    .map((m) => m.content.toLowerCase())
    .concat(t)
    .join(" ");
  return !HAS_OCCASION.test(said);
}

function occasionQuestion(text: string) {
  const when = VAGUE_TIME.exec(text.toLowerCase());
  return `Happy to style you — what are you doing ${when ? when[0] : "today"}? Tell me the occasion (work, dinner, date, church, drinks, something casual…) and I'll build the right look.`;
}

export default function Stylist() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { premium, ready: premiumReady } = usePremiumAccess();
  const { weather, status } = useWeather();
  const scrollRef = useRef<ScrollView>(null);

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  // Pieces the user attaches so the conversation can be about real garments
  // ("what goes with this?", "help me style this").
  const [wardrobe, setWardrobe] = useState<any[]>([]);
  const [attached, setAttached] = useState<any[]>([]);
  const [picker, setPicker] = useState(false);
  const [search, setSearch] = useState("");
  // Conversations live on the server, so leaving the screen never loses one.
  const [threadId, setThreadId] = useState<string | null>(null);
  const [threads, setThreads] = useState<any[]>([]);
  const [history, setHistory] = useState(false);
  const restored = useRef(false);

  useEffect(() => { api<any[]>("/items").then(setWardrobe).catch(() => {}); }, []);

  const loadThreads = useCallback(async () => {
    try { setThreads(await api<any[]>("/stylist/threads")); } catch {}
  }, []);

  const openThread = useCallback(async (id: string) => {
    try {
      const t = await api<any>(`/stylist/threads/${id}`);
      setMessages(
        (t.messages || []).map((m: any) => ({ role: m.role, content: m.content }))
      );
      setThreadId(t.id);
      setHistory(false);
    } catch {}
  }, []);

  // Coming back to the screen restores the conversation that was in progress.
  useFocusEffect(
    useCallback(() => {
      loadThreads();
      if (restored.current) return;
      restored.current = true;
      api<any[]>("/stylist/threads")
        .then((rows) => {
          const live = (rows || []).find((r) => !r.archived);
          if (live) openThread(live.id);
        })
        .catch(() => {});
    }, [loadThreads, openThread])
  );

  const newChat = async () => {
    haptics.tap();
    if (threadId) {
      // Archive keeps the old conversation (with a title + summary) rather than
      // destroying it.
      try { await api(`/stylist/threads/${threadId}/archive`, { method: "POST" }); } catch {}
    }
    setMessages([]);
    setAttached([]);
    setThreadId(null);
    loadThreads();
  };

  const typingMsg = useRotatingMessage(sending, [
    "Thinking about your style…",
    "Reviewing your wardrobe…",
    "Pairing pieces that work…",
  ]);

  const scrollDown = () => setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 60);

  const send = useCallback(async (text: string) => {
    if (!premiumReady) return;
    if (!premium) { router.push("/premium"); return; }
    const content = text.trim();
    if (!content || sending) return;
    haptics.tap();
    const history = [...messages, { role: "user" as const, content }];
    setMessages(history);
    setInput("");
    scrollDown();

    if (needsOccasionContext(content, messages)) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: occasionQuestion(content) },
      ]);
      haptics.success();
      scrollDown();
      return;
    }

    setSending(true);
    try {
      const body: any = { messages: history.map((m) => ({ role: m.role, content: m.content })) };
      if (weather && status === "done") { body.temperature = weather.temperature; body.weather = weather.description; }
      if (attached.length) body.item_ids = attached.map((a) => a.id);
      if (threadId) body.thread_id = threadId;
      const r = await api<any>("/stylist/chat", { method: "POST", body });
      if (r.thread_id) setThreadId(r.thread_id);
      setMessages((prev) => [...prev, { role: "assistant", content: r.reply, outfit: r.outfit }]);
      haptics.success();
    } catch (e: any) {
      if (e.status === 402) { router.push("/premium"); }
      else setMessages((prev) => [...prev, { role: "assistant", content: "Sorry — I couldn't reach the styling engine just then. Try again in a moment." }]);
    }
    setSending(false);
    scrollDown();
  }, [messages, sending, weather, status, router, attached, threadId, premium, premiumReady]);

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

  if (!premiumReady || !premium) {
    return (
      <View style={[styles.container, { paddingTop: insets.top + spacing.xl }]}>
        <View style={styles.welcome}>
          <Display weight="medium">Your AI Stylist</Display>
          <Txt>{premiumReady
            ? "AI Stylist is included with Premium and during your active 7-day complimentary access."
            : "Checking your membership…"}</Txt>
          {premiumReady ? (
            <Pressable onPress={() => router.push("/premium")} testID="stylist-premium-access" style={{ paddingVertical: spacing.lg }}>
              <Txt>View Premium plans →</Txt>
            </Pressable>
          ) : null}
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <View style={styles.headerSide}>
          {router.canGoBack() ? (
            <Pressable onPress={() => router.back()} hitSlop={12} testID="stylist-back"><Feather name="chevron-left" size={26} color={colors.onSurface} /></Pressable>
          ) : null}
        </View>
        <BrandMark style={{ marginBottom: 0 }} />
        <View style={[styles.headerSide, styles.headerSideRight]}>
          <Pressable onPress={() => { haptics.tap(); loadThreads(); setHistory(true); }} hitSlop={12} testID="stylist-history">
            <Feather name="clock" size={20} color={colors.onSurface} />
          </Pressable>
          <Pressable onPress={newChat} hitSlop={12} testID="stylist-clear">
            <Feather name="edit" size={20} color={colors.onSurface} />
          </Pressable>
        </View>
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
          <AIGuidance />
          {messages.length === 0 ? (
            <View style={styles.welcome}>
              <View style={styles.titleBlock}>
                <Txt style={styles.kicker}>YOUR PERSONAL STYLIST</Txt>
                <Display weight="semibold" style={styles.pageTitle}>AI Stylist</Display>
              </View>
              <View style={styles.bubbleAssistant}>
                <Txt style={styles.bubbleTxt}>
                  Let&rsquo;s talk about your clothes. Ask how something looks, what I&rsquo;d change, what to wear with a
                  piece you own, or what your wardrobe is missing — attach a piece with{" "}
                  <Feather name="plus" size={12} color={colors.onSurfaceSecondary} /> and we&rsquo;ll style it together.
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
                      <StylistMessage content={shortItemReferences(m.content, wardrobe)} style={styles.bubbleTxt} />
                    </View>
                    {m.outfit ? (
                      <View style={styles.outfitCard} testID={`stylist-outfit-${i}`}>
                        <Txt style={styles.outfitName}>{m.outfit.name}</Txt>
                        <View style={styles.outfitThumbs}>
                          {(m.outfit.items || []).map((it: any) => (
                            <View key={it.id} style={styles.thumbWrap}>
                              <GarmentImage photo={it.photo} category={it.category} style={styles.thumb} iconSize={16} />
                              <Txt style={styles.thumbName} numberOfLines={1}>{shortItemName(it.name)}</Txt>
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

        {attached.length ? (
          <View style={styles.attachedRow} testID="stylist-attached">
            {attached.map((a) => (
              <Pressable key={a.id} style={styles.attachedChip} onPress={() => setAttached((prev) => prev.filter((x) => x.id !== a.id))} testID={`stylist-attached-${a.id}`}>
                <GarmentImage photo={a.photo} category={a.category} style={styles.attachedImg} iconSize={12} />
                <Txt style={styles.attachedTxt} numberOfLines={1}>{shortItemName(a.name)}</Txt>
                <Feather name="x" size={13} color={colors.onSurfaceTertiary} />
              </Pressable>
            ))}
          </View>
        ) : null}

        <View style={[styles.inputBar, { paddingBottom: insets.bottom + spacing.sm }]}>
          <Pressable style={styles.attachBtn} onPress={() => { haptics.tap(); setPicker(true); setSearch(""); }} testID="stylist-attach">
            <Feather name="plus" size={20} color={colors.onSurface} />
          </Pressable>
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

      <Modal visible={history} animationType="slide" transparent onRequestClose={() => setHistory(false)}>
        <View style={styles.sheetBackdrop}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={styles.sheetHead}>
              <Display weight="medium" style={styles.sheetTitle}>Your styling journal</Display>
              <Pressable onPress={() => setHistory(false)} hitSlop={10}><Feather name="x" size={22} color={colors.onSurface} /></Pressable>
            </View>
            <ScrollView showsVerticalScrollIndicator={false}>
              {threads.length === 0 ? (
                <Txt style={styles.pickerEmpty} testID="stylist-history-empty">
                  Your conversations will be kept here, with a short note of what Aureve suggested.
                </Txt>
              ) : (
                threads.map((t) => (
                  <Pressable key={t.id} style={styles.threadRow} testID={`stylist-thread-${t.id}`} onPress={() => openThread(t.id)}>
                    <View style={styles.threadTop}>
                      <Txt style={styles.threadTitle} numberOfLines={1}>{t.title || "Styling chat"}</Txt>
                      <Txt style={styles.threadDate}>
                        {t.updated_at ? new Date(t.updated_at).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : ""}
                      </Txt>
                    </View>
                    {t.summary ? <Txt style={styles.threadSummary}>{t.summary}</Txt> : null}
                    {(t.recommendations || []).map((r: string, i: number) => (
                      <View key={i} style={styles.threadRecRow}>
                        <Feather name="star" size={11} color={colors.goldDeep} />
                        <Txt style={styles.threadRec}>{r}</Txt>
                      </View>
                    ))}
                    {!t.archived ? <Txt style={styles.threadLive}>In progress</Txt> : null}
                  </Pressable>
                ))
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>

      <Modal visible={picker} animationType="slide" transparent onRequestClose={() => setPicker(false)}>
        <View style={styles.sheetBackdrop}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={styles.sheetHead}>
              <Display weight="medium" style={styles.sheetTitle}>Talk about a piece</Display>
              <Pressable onPress={() => setPicker(false)} hitSlop={10}><Feather name="x" size={22} color={colors.onSurface} /></Pressable>
            </View>
            <View style={styles.searchBar}>
              <Feather name="search" size={16} color={colors.onSurfaceTertiary} />
              <TextInput
                style={styles.searchInput}
                placeholder="Search your wardrobe"
                placeholderTextColor={colors.onSurfaceTertiary}
                value={search}
                onChangeText={setSearch}
                testID="stylist-attach-search"
              />
            </View>
            <ScrollView showsVerticalScrollIndicator={false}>
              <View style={styles.pickerGrid}>
                {wardrobe
                  .filter((w) => !search || (w.name || "").toLowerCase().includes(search.toLowerCase()))
                  .map((it) => (
                    <Pressable
                      key={it.id}
                      style={styles.pickerCell}
                      testID={`stylist-piece-${it.id}`}
                      onPress={() => {
                        haptics.tap();
                        setAttached((prev) => (prev.some((x) => x.id === it.id) ? prev : [...prev, it]));
                        setPicker(false);
                      }}
                    >
                      <GarmentImage photo={it.photo} category={it.category} style={styles.pickerImg} iconSize={22} />
                      <Txt style={styles.pickerName} numberOfLines={1}>{shortItemName(it.name)}</Txt>
                    </Pressable>
                  ))}
              </View>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  scroll: { padding: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md },
  welcome: { gap: spacing.lg },
  headerSide: { width: 56, flexDirection: "row", alignItems: "center", gap: spacing.lg },
  headerSideRight: { justifyContent: "flex-end" },
  threadRow: { paddingVertical: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.divider, gap: 4 },
  threadTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  threadTitle: { flex: 1, fontSize: 15.5, color: colors.onSurface, fontFamily: fonts.displayMedium },
  threadDate: { fontSize: 12, color: colors.onSurfaceTertiary },
  threadSummary: { fontSize: 13, color: colors.onSurfaceSecondary, lineHeight: 19 },
  threadRecRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", marginTop: 2 },
  threadRec: { flex: 1, fontSize: 12.5, color: colors.onSurface, lineHeight: 18 },
  threadLive: { fontSize: 11, color: colors.sageDeep, fontFamily: fonts.displayMedium, marginTop: 2 },
  titleBlock: { marginBottom: spacing.xs },
  kicker: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium, marginBottom: spacing.xs },
  pageTitle: { fontSize: 30, letterSpacing: -0.5 },
  attachedRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  attachedChip: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.cream, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.pill, paddingLeft: 4, paddingRight: spacing.md, paddingVertical: 4, maxWidth: 220 },
  attachedImg: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.surfaceTertiary },
  attachedTxt: { flex: 1, fontSize: 12.5, color: colors.onSurface },
  attachBtn: { width: 44, height: 44, borderRadius: 22, borderWidth: 0.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  sheetBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingHorizontal: spacing.lg, paddingTop: spacing.lg, maxHeight: "82%" },
  sheetHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  sheetTitle: { fontSize: 18 },
  searchBar: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44, marginBottom: spacing.md },
  searchInput: { flex: 1, fontFamily: fonts.body, fontSize: 14, color: colors.onSurface },
  pickerGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, paddingBottom: spacing.lg },
  pickerCell: { width: "30.5%" },
  pickerImg: { width: "100%", aspectRatio: 0.82, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  pickerName: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 4 },
  pickerEmpty: { fontSize: 14, color: colors.onSurfaceTertiary, textAlign: "center", paddingVertical: spacing["2xl"], lineHeight: 20 },
  avatarSm: { width: 28, height: 28, borderRadius: 14, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", marginTop: 2 },
  bubbleAssistant: { backgroundColor: colors.surfaceSecondary, borderRadius: 18, borderTopLeftRadius: 4, padding: spacing.md, maxWidth: "88%" },
  bubbleTxt: { fontSize: 15, color: colors.onSurface, lineHeight: 22 },
  suggestions: { gap: spacing.sm, marginTop: spacing.sm },
  suggestion: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.cream, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.md, minHeight: 48 },
  suggestionTxt: { flex: 1, fontSize: 14, color: colors.onSurface, lineHeight: 20 },
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
  input: { flex: 1, minWidth: 0, backgroundColor: colors.surfaceSecondary, borderRadius: 24, paddingHorizontal: spacing.lg, height: 48, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface },
  sendBtn: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
});
