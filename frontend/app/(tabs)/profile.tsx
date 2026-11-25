import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl, Modal, Platform, Linking } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { useRouter, useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Display, Txt } from "@/src/components/Typography";
import BrandMark from "@/src/components/BrandMark";
import { colors, spacing, radius, fonts } from "@/src/theme";
import { api } from "@/src/api/client";
import { showManageSubscriptions } from "@/src/services/purchases";
import { usePremiumAccess } from "@/src/hooks/usePremiumAccess";
import { useAuth } from "@/src/context/AuthContext";
import { useProfiles } from "@/src/context/ProfileContext";
import WardrobeSwitcher from "@/src/components/WardrobeSwitcher";

export default function Profile() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, logout, deleteAccount } = useAuth();
  const { active } = useProfiles();
  const { premium, ready: premiumReady } = usePremiumAccess();
  const initials = (user?.name || user?.email || "?")
    .split(/\s+/)
    .map((w: string) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
  const [refreshing, setRefreshing] = useState(false);
  const [showSwitcher, setShowSwitcher] = useState(false);
  const [calConnected, setCalConnected] = useState(false);
  const [confirmCalendarDisconnect, setConfirmCalendarDisconnect] = useState(false);
  const [calendarBusy, setCalendarBusy] = useState(false);
  const [calendarError, setCalendarError] = useState("");

  const disconnectCalendar = async () => {
    setCalendarBusy(true);
    setCalendarError("");
    try {
      await api("/calendar/disconnect", { method: "DELETE" });
      setCalConnected(false);
      setConfirmCalendarDisconnect(false);
    } catch {
      setCalendarError("Couldn't disconnect your calendar. Please try again.");
    } finally {
      setCalendarBusy(false);
    }
  };

  const load = useCallback(async () => {
    try {
      const s = await api<any>("/calendar/status");
      setCalConnected(!!s.connected);
    } catch {}
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };


  const handleSignOut = async () => {
    await logout();
    router.replace("/welcome");
  };

  // Subscriptions are billed by the store, so management belongs there: we open
  // Apple's own StoreKit sheet (or Google's) and only fall back to the store's
  // subscription page if the native sheet isn't available.
  const manageSubscription = async () => {
    if (Platform.OS === "web") {
      router.push("/premium");
      return;
    }
    if (await showManageSubscriptions()) return;
    const url =
      Platform.OS === "ios"
        ? "https://apps.apple.com/account/subscriptions"
        : "https://play.google.com/store/account/subscriptions";
    try { await Linking.openURL(url); } catch { router.push("/premium"); }
  };

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteAccount();
      setConfirmDelete(false);
      router.replace("/welcome");
    } catch {
      setDeleting(false);
    }
  };

  return (
    <View style={styles.container}>
      {/* Opaque status-bar strip: content scrolling up can never sit under the
          iOS clock/indicators. Height is 0 where there is no top inset. */}
      <View style={[styles.statusCover, { height: insets.top, pointerEvents: "none" }]} />
      <ScrollView
        contentContainerStyle={{ paddingBottom: spacing["3xl"] }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.onSurface} />}
      >
        <View style={[styles.header, { paddingTop: insets.top + spacing.lg }]}>
          <BrandMark />
          <View style={styles.titleBlock}>
            <Txt style={styles.kicker}>YOUR ACCOUNT</Txt>
            <View style={styles.titleRow}>
              <Display weight="semibold" style={styles.pageTitle}>Profile</Display>
            </View>
            <Txt style={styles.pageSub}>Your wardrobe, your style profile and your preferences.</Txt>
          </View>
          <View style={styles.accountCard}>
            <View style={styles.avatarLg}>
              <Txt style={styles.avatarInitials}>{initials}</Txt>
            </View>
            <View style={{ flex: 1 }}>
              <Display weight="medium" style={styles.accountNameLg} numberOfLines={1}>{user?.name || "Your account"}</Display>
              {user?.email ? <Txt style={styles.accountEmail} numberOfLines={1}>{user.email}</Txt> : null}
              <View style={premium ? styles.badgePremium : styles.badgeFree}>
                <Feather name={premium ? "award" : "user"} size={11} color={premium ? colors.onSage : colors.onSurfaceSecondary} />
                <Txt style={premium ? styles.badgePremiumTxt : styles.badgeFreeTxt}>{premium ? "Premium" : "Free plan"}</Txt>
              </View>
            </View>
          </View>

          <Pressable style={styles.switcherRow} testID="profile-switcher-trigger" onPress={() => setShowSwitcher(true)}>
            <View style={styles.avatarSm}><Txt style={styles.avatarEmoji}>{active?.emoji || "👤"}</Txt></View>
            <View style={{ flex: 1 }}>
              <Txt style={styles.switcherLabel}>ACTIVE WARDROBE</Txt>
              <Txt style={styles.switcherName}>{active?.name || "Wardrobe"}</Txt>
            </View>
            <Feather name="chevron-down" size={18} color={colors.onSurfaceSecondary} />
          </Pressable>
        </View>

        <View style={styles.body}>
          {/* Style profile */}
          <Pressable style={styles.styleProfileCta} testID="open-style-profile" onPress={() => router.push("/profile-edit")}>
            <View style={styles.spIcon}>
              <Feather name="user" size={18} color={colors.onSurface} />
            </View>
            <View style={{ flex: 1 }}>
              <Txt style={styles.spTitle}>Your style profile</Txt>
              <Txt style={styles.spSub}>
                {active?.profile && Object.keys(active.profile).length > 0
                  ? "Measurements, colouring & hairstyles — tap to edit"
                  : "Add measurements & colouring for better fit advice"}
              </Txt>
            </View>
            <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />
          </Pressable>

          {/* Google Calendar */}
          <Pressable
            style={styles.premiumActiveCta}
            testID="profile-calendar-cta"
            disabled={calendarBusy}
            onPress={async () => {
              setCalendarError("");
              if (calConnected) {
                setConfirmCalendarDisconnect(true);
              } else {
                setCalendarBusy(true);
                try {
                  const { url } = await api<any>("/calendar/authorize");
                  await WebBrowser.openBrowserAsync(url);
                  const s = await api<any>("/calendar/status");
                  setCalConnected(!!s.connected);
                } catch {
                  setCalendarError("Couldn't connect your calendar. Please try again.");
                } finally {
                  setCalendarBusy(false);
                }
              }
            }}
          >
            <Feather name="calendar" size={18} color={colors.brand} />
            <View style={{ flex: 1 }}>
              <Txt style={styles.spTitle}>Google Calendar</Txt>
              <Txt style={styles.spSub}>{calConnected ? "Connected — Dress Me uses your schedule. Tap to manage." : "Connect so Dress Me styles for your day"}</Txt>
            </View>
            <Feather name={calConnected ? "check" : "chevron-right"} size={20} color={colors.onSurfaceTertiary} />
          </Pressable>

          {calendarError && !confirmCalendarDisconnect ? <Txt accessibilityRole="alert" style={styles.calendarError}>{calendarError}</Txt> : null}

          <Modal visible={confirmCalendarDisconnect} transparent animationType="fade" onRequestClose={() => { if (!calendarBusy) setConfirmCalendarDisconnect(false); }}>
            <View style={styles.confirmBackdrop}>
              <View style={styles.confirmCard}>
                <Display weight="semibold" style={styles.confirmTitle}>Google Calendar</Display>
                <Txt style={styles.confirmBody}>Your calendar is connected. Disconnecting stops Aureve using your schedule for outfit suggestions. You can reconnect later.</Txt>
                {calendarError ? <Txt accessibilityRole="alert" style={styles.calendarError}>{calendarError}</Txt> : null}
                <Pressable style={styles.confirmDeleteBtn} testID="confirm-calendar-disconnect" disabled={calendarBusy} onPress={disconnectCalendar}>
                  {calendarBusy ? <ActivityIndicator color={colors.onSurfaceInverse} /> : <Txt style={styles.confirmDeleteTxt}>Disconnect calendar</Txt>}
                </Pressable>
                <Pressable style={styles.confirmCancelBtn} testID="cancel-calendar-disconnect" disabled={calendarBusy} onPress={() => setConfirmCalendarDisconnect(false)}>
                  <Txt style={styles.confirmCancelTxt}>Keep connected</Txt>
                </Pressable>
              </View>
            </View>
          </Modal>

          {/* Premium features */}
          <View style={styles.section}>
            <Txt style={styles.sectionTitle}>PREMIUM FEATURES</Txt>
            <Pressable style={styles.featureCard} testID="open-health-report" onPress={() => { if (!premiumReady) return; router.push(premium ? "/health-report" : "/premium"); }}>
              <View style={styles.featurePuck}><Feather name="activity" size={18} color={colors.sageDeep} /></View>
              <View style={{ flex: 1 }}>
                <Txt style={styles.featureTitle}>Monthly Wardrobe Health</Txt>
                <Txt style={styles.featureSub}>What you actually wore, what&apos;s sitting unworn, and your smartest next buy</Txt>
              </View>
              {premium
                ? <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />
                : <Feather name="lock" size={16} color={colors.onSurfaceTertiary} />}
            </Pressable>
            <Pressable style={styles.featureCard} testID="open-shopping-intelligence" onPress={() => { if (!premiumReady) return; router.push(premium ? "/(tabs)/shop" : "/premium"); }}>
              <View style={styles.featurePuck}><Feather name="shopping-bag" size={18} color={colors.goldDeep} /></View>
              <View style={{ flex: 1 }}>
                <Txt style={styles.featureTitle}>Shopping Intelligence</Txt>
                <Txt style={styles.featureSub}>Do you already own something similar? Which gaps are worth buying?</Txt>
              </View>
              {premium
                ? <Feather name="chevron-right" size={20} color={colors.onSurfaceTertiary} />
                : <Feather name="lock" size={16} color={colors.onSurfaceTertiary} />}
            </Pressable>
          </View>


          {/* Membership — one honest state at a time */}
          <View style={styles.section}>
            <Txt style={styles.sectionTitle}>MEMBERSHIP</Txt>
            {user?.complimentary_active ? (
              <View style={styles.memberCard} testID="complimentary-row">
                <Txt style={styles.memberTitle}>Complimentary Premium Access</Txt>
                <Txt style={styles.memberLine}>
                  Ends {user.complimentary_expires_at ? new Date(user.complimentary_expires_at).toLocaleDateString() : ""}
                  {typeof user.complimentary_days_left === "number"
                    ? ` · ${user.complimentary_days_left} ${user.complimentary_days_left === 1 ? "day" : "days"} remaining`
                    : ""}
                </Txt>
                <Txt style={styles.memberNote}>
                  No subscription has been started and you will not be charged automatically.
                </Txt>
                <Pressable style={styles.memberBtn} testID="see-premium-plans" onPress={() => router.push("/premium")}>
                  <Feather name="award" size={15} color={colors.onSurface} />
                  <Txt style={styles.memberBtnTxt}>See Premium plans</Txt>
                </Pressable>
              </View>
            ) : premium ? (
              <View style={styles.memberCard} testID="paid-membership-row">
                <Txt style={styles.memberTitle}>Premium Membership</Txt>
                {user?.premium_plan ? (
                  <Txt style={styles.memberLine}>Current plan: {user.premium_plan}</Txt>
                ) : null}
                {user?.premium_until ? (
                  <Txt style={styles.memberLine}>
                    Renews / expires {new Date(user.premium_until).toLocaleDateString()}
                  </Txt>
                ) : null}
                <Pressable style={styles.memberBtn} testID="manage-subscription" onPress={manageSubscription}>
                  <Feather name="external-link" size={15} color={colors.onSurface} />
                  <Txt style={styles.memberBtnTxt}>Manage / Cancel Subscription</Txt>
                </Pressable>
              </View>
            ) : (
              <View style={styles.memberCard} testID="free-membership-row">
                <Txt style={styles.memberTitle}>Free Membership</Txt>
                <Txt style={styles.memberLine}>Your whole wardrobe, plus 5 Dress Me looks a month.</Txt>
                <Pressable style={styles.memberBtn} testID="go-premium" onPress={() => router.push("/premium")}>
                  <Feather name="award" size={15} color={colors.onSurface} />
                  <Txt style={styles.memberBtnTxt}>Go Premium</Txt>
                </Pressable>
              </View>
            )}
          </View>

          {/* Account */}
          <View style={styles.section}>
            <Txt style={styles.sectionTitle}>ACCOUNT</Txt>
            <Pressable style={styles.acctRow} testID="sign-out" onPress={handleSignOut}>
              <Feather name="log-out" size={18} color={colors.error} />
              <Txt style={[styles.acctTxt, { color: colors.error }]}>Sign out</Txt>
              <Feather name="chevron-right" size={18} color={colors.onSurfaceTertiary} />
            </Pressable>
          </View>

          {/* Legal & data */}
          <View style={styles.section}>
            <Txt style={styles.sectionTitle}>PRIVACY & DATA</Txt>
            <Pressable style={styles.acctRow} testID="wardrobe-audit" onPress={() => router.push("/audit")}>
              <Feather name="search" size={18} color={colors.onSurface} />
              <Txt style={styles.acctTxt}>Wardrobe audit</Txt>
              <Feather name="chevron-right" size={18} color={colors.onSurfaceTertiary} />
            </Pressable>
            <Pressable style={styles.acctRow} testID="privacy-policy" onPress={() => router.push({ pathname: "/legal", params: { doc: "privacy" } })}>
              <Feather name="shield" size={18} color={colors.onSurface} />
              <Txt style={styles.acctTxt}>Privacy Policy</Txt>
              <Feather name="chevron-right" size={18} color={colors.onSurfaceTertiary} />
            </Pressable>
            <Pressable style={styles.acctRow} testID="terms" onPress={() => router.push({ pathname: "/legal", params: { doc: "terms" } })}>
              <Feather name="file-text" size={18} color={colors.onSurface} />
              <Txt style={styles.acctTxt}>Terms of Service</Txt>
              <Feather name="chevron-right" size={18} color={colors.onSurfaceTertiary} />
            </Pressable>
            <Pressable style={styles.acctRow} testID="delete-account" onPress={() => setConfirmDelete(true)}>
              <Feather name="trash-2" size={18} color={colors.error} />
              <Txt style={[styles.acctTxt, { color: colors.error }]}>Delete my account</Txt>
              <Feather name="chevron-right" size={18} color={colors.onSurfaceTertiary} />
            </Pressable>
          </View>

          <Modal visible={confirmDelete} transparent animationType="fade" onRequestClose={() => setConfirmDelete(false)}>
            <View style={styles.confirmBackdrop}>
              <View style={styles.confirmCard}>
                <Display weight="semibold" style={styles.confirmTitle}>Delete your account?</Display>
                <Txt style={styles.confirmBody}>
                  This permanently deletes your account and everything in it — your wardrobe, outfits, collections and profiles. This cannot be undone.
                </Txt>
                {premium && !user?.complimentary_active ? (
                  <View style={styles.subWarn} testID="delete-subscription-warning">
                    <Txt style={styles.subWarnTxt}>
                      Deleting your Aureve account does not automatically cancel your App Store subscription.
                    </Txt>
                    <Pressable style={styles.subWarnBtn} testID="delete-manage-subscription" onPress={manageSubscription}>
                      <Feather name="external-link" size={14} color={colors.onSurface} />
                      <Txt style={styles.subWarnBtnTxt}>Manage / Cancel Subscription</Txt>
                    </Pressable>
                  </View>
                ) : null}
                <Pressable style={styles.confirmDeleteBtn} testID="confirm-delete" onPress={handleDelete} disabled={deleting}>
                  {deleting ? <ActivityIndicator color={colors.onSurfaceInverse} /> : <Txt style={styles.confirmDeleteTxt}>Delete everything</Txt>}
                </Pressable>
                <Pressable style={styles.confirmCancelBtn} testID="cancel-delete" onPress={() => setConfirmDelete(false)} disabled={deleting}>
                  <Txt style={styles.confirmCancelTxt}>Keep my account</Txt>
                </Pressable>
              </View>
            </View>
          </Modal>

        </View>
      </ScrollView>

      <WardrobeSwitcher visible={showSwitcher} onClose={() => { setShowSwitcher(false); load(); }} />
    </View>
  );
}

const styles = StyleSheet.create({
  statusCover: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: colors.surface,
    zIndex: 2,
  },
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.xl, paddingBottom: spacing.lg, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  titleBlock: { marginBottom: spacing.lg },
  titleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  kicker: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium, marginBottom: spacing.xs },
  pageTitle: { fontSize: 30, letterSpacing: -0.5, color: colors.onSurface },
  pageSub: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20, marginTop: spacing.xs },
  accountCard: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  avatarLg: { width: 60, height: 60, borderRadius: 30, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
  avatarInitials: { fontSize: 22, color: colors.onSage, fontFamily: fonts.displayMedium },
  accountNameLg: { fontSize: 20 },
  accountEmail: { fontSize: 13, color: colors.onSurfaceTertiary, marginTop: 1 },
  badgePremium: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", backgroundColor: colors.sage, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12, marginTop: 6 },
  badgePremiumTxt: { fontSize: 11, color: colors.onSage, fontFamily: fonts.displayMedium },
  badgeFree: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12, marginTop: 6 },
  badgeFreeTxt: { fontSize: 11, color: colors.onSurfaceSecondary, fontFamily: fonts.displayMedium },
  avatarSm: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  switcherRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.lg, backgroundColor: colors.taupe, borderRadius: radius.lg, padding: spacing.md, borderWidth: 0.5, borderColor: colors.border },
  switcherLabel: { fontSize: 10.5, letterSpacing: 1.4, color: colors.onSurfaceTertiary, fontFamily: fonts.displayMedium },
  switcherName: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium },
  profileRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  switcherTrigger: { flexDirection: "row", alignItems: "center", gap: spacing.md, flex: 1 },
  avatar: { width: 52, height: 52, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  avatarEmoji: { fontSize: 24 },
  accountName: { fontSize: 12, color: colors.onSurfaceTertiary },
  activeRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  name: { fontSize: 24 },
  backdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.45)", justifyContent: "flex-end" },
  switchSheet: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.xl, paddingBottom: spacing["2xl"] },
  switchTitle: { fontSize: 24 },
  switchSub: { fontSize: 13, color: colors.onSurfaceTertiary, marginTop: 2, marginBottom: spacing.lg },
  profRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm },
  profMain: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.md },
  profAvatar: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  profAvatarActive: { borderWidth: 1.5, borderColor: colors.brand },
  profName: { flex: 1, fontSize: 16, color: colors.onSurface },
  addRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.lg, borderTopWidth: 0.5, borderTopColor: colors.divider, paddingTop: spacing.lg },
  addInput: { flex: 1, fontFamily: fonts.body, fontSize: 15, color: colors.onSurface, borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: spacing.sm },
  addBtn: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  body: { paddingHorizontal: spacing.xl, paddingTop: spacing.xl },
  styleProfileCta: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.lg },
  spIcon: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  spTitle: { fontSize: 15, color: colors.onSurface },
  spSub: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  beautyCta: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.lg },
  beautyIcon: { width: 40, height: 40, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  premiumActiveCta: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.lg },
  featureCard: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.cream, borderWidth: 0.5, borderColor: colors.border,
    borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.md,
  },
  featurePuck: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  featureTitle: { fontSize: 15.5, color: colors.onSurface, fontFamily: fonts.displayMedium },
  featureSub: { fontSize: 12.5, color: colors.onSurfaceSecondary, marginTop: 2, lineHeight: 17 },
  missingCard: { marginTop: spacing.xl, backgroundColor: colors.surfaceInverse, borderRadius: radius.md, padding: spacing.xl },
  missingKicker: { fontSize: 11, letterSpacing: 2, color: colors.brandTertiary, marginBottom: spacing.sm },
  missingTitle: { fontSize: 24, lineHeight: 28, color: colors.onSurfaceInverse },
  missingItem: { fontSize: 16, color: colors.onSurfaceInverse, lineHeight: 22 },
  missingReason: { fontSize: 14, color: "rgba(250,250,250,0.7)", lineHeight: 21, marginTop: spacing.sm },
  avoidRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, alignItems: "flex-start" },
  avoidTxt: { flex: 1, fontSize: 13, color: colors.warning, lineHeight: 19 },
  missingBtn: { backgroundColor: colors.surface, height: 48, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", marginTop: spacing.lg },
  missingBtnTxt: { color: colors.onSurface, fontSize: 15 },
  missingRedo: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.lg, alignSelf: "flex-start" },
  missingRedoTxt: { color: colors.brandTertiary, fontSize: 13, textDecorationLine: "underline" },
  section: { marginTop: spacing["2xl"] },
  sectionTitle: { fontSize: 11, letterSpacing: 1.5, color: colors.onSurfaceTertiary, marginBottom: spacing.lg },
  barRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.md },
  barLabel: { fontSize: 13, color: colors.onSurface, width: 90 },
  barTrack: { flex: 1, height: 4, backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, overflow: "hidden" },
  barFill: { height: 4, backgroundColor: colors.brand },
  barVal: { fontSize: 12, color: colors.onSurfaceTertiary, width: 30, textAlign: "right" },
  catRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.md },
  catName: { fontSize: 13, color: colors.onSurface, width: 90 },
  catBarTrack: { flex: 1, height: 4, backgroundColor: colors.surfaceTertiary, borderRadius: radius.pill, overflow: "hidden" },
  catBarFill: { height: 4, backgroundColor: colors.onSurface },
  catCount: { fontSize: 12, color: colors.onSurfaceTertiary, width: 30, textAlign: "right" },
  rankRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginBottom: spacing.lg },
  rankNum: { fontSize: 14, color: colors.brand, width: 16 },
  rankImg: { width: 44, height: 56, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  rankName: { fontSize: 14, color: colors.onSurface },
  rankMeta: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 1 },
  healthCard: { flexDirection: "row", gap: spacing.md, backgroundColor: colors.brandTertiary, padding: spacing.lg, borderRadius: radius.sm, alignItems: "center" },
  healthTxt: { flex: 1, fontSize: 13, color: colors.onBrandTertiary, lineHeight: 19 },
  simCard: { width: 90 },
  simImg: { width: 90, height: 116, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  simPlaceholder: { alignItems: "center", justifyContent: "center" },
  simName: { fontSize: 12, color: colors.onSurface, marginTop: 6 },
  empty: { marginTop: spacing["2xl"], alignItems: "center" },
  acctRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.md },
  acctTxt: { flex: 1, fontSize: 15, color: colors.onSurface },
  acctSub: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 2 },
  memberCard: { backgroundColor: colors.cream, borderWidth: 0.5, borderColor: colors.goldSoft, borderRadius: radius.lg, padding: spacing.lg },
  memberTitle: { fontSize: 16, color: colors.onSurface, fontFamily: fonts.displayMedium },
  memberLine: { fontSize: 13.5, color: colors.onSurfaceSecondary, marginTop: 4 },
  memberNote: { fontSize: 12.5, color: colors.onSurfaceTertiary, marginTop: spacing.sm, lineHeight: 18 },
  memberBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginTop: spacing.md },
  memberBtnTxt: { fontSize: 14.5, color: colors.onSurface, fontFamily: fonts.displayMedium },
  subWarn: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md, gap: spacing.sm },
  subWarnTxt: { fontSize: 13, color: colors.onSurface, lineHeight: 19 },
  subWarnBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, height: 44, borderRadius: radius.md, borderWidth: 0.5, borderColor: colors.border, backgroundColor: colors.surface },
  subWarnBtnTxt: { fontSize: 13.5, color: colors.onSurface, fontFamily: fonts.displayMedium },
  confirmBackdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.5)", alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.xl },
  confirmCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.xl, width: "100%", maxWidth: 400 },
  confirmTitle: { fontSize: 20, color: colors.onSurface, marginBottom: spacing.sm },
  confirmBody: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21, marginBottom: spacing.xl },
  confirmDeleteBtn: { height: 52, borderRadius: radius.md, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" },
  confirmDeleteTxt: { color: colors.onSurfaceInverse, fontSize: 15, fontFamily: fonts.displayBold },
  confirmCancelBtn: { height: 50, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  confirmCancelTxt: { color: colors.onSurface, fontSize: 15, fontFamily: fonts.displayMedium },
  calendarError: { color: colors.error, fontSize: 13, lineHeight: 19, marginBottom: spacing.md },
  emptyTxt: { fontSize: 14, color: colors.onSurfaceTertiary, textAlign: "center" },
});
