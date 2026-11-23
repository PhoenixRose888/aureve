import React, { useState } from "react";
import { View, StyleSheet, Modal, Pressable, TextInput, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { useProfiles } from "@/src/context/ProfileContext";
import { usePremiumAccess } from "@/src/hooks/usePremiumAccess";

/** The one place to switch between wardrobes and add a family wardrobe.
 *  Premium belongs to the subscribing account — family wardrobes are managed
 *  profiles under it, never separate subscriptions. */
export default function WardrobeSwitcher({
  visible,
  onClose,
}: {
  visible: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const { accountPremium } = usePremiumAccess();
  const { profiles, active, switchTo, createProfile, deleteProfile } = useProfiles();
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const close = () => {
    setError("");
    setConfirmId(null);
    onClose();
  };

  const goPremium = () => {
    close();
    router.push("/premium");
  };

  const add = async () => {
    if (!accountPremium) return goPremium();
    const name = newName.trim();
    if (!name) {
      setError("Give the wardrobe a name first (e.g. David).");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await createProfile(name, "👤", "individual");
      setNewName("");
      close();
    } catch (e: any) {
      if (e?.status === 402) {
        setBusy(false);
        return goPremium();
      }
      setError(e?.message || "Couldn't add that wardrobe. Please try again.");
    }
    setBusy(false);
  };

  const remove = async (id: string) => {
    setBusy(true);
    setError("");
    try {
      await deleteProfile(id);
      setConfirmId(null);
    } catch (e: any) {
      setError(e?.message || "Couldn't remove that wardrobe.");
    }
    setBusy(false);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={close}>
      <Pressable style={styles.backdrop} onPress={close}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <Display weight="medium" style={styles.title}>Wardrobes</Display>
          <Txt style={styles.sub}>
            {accountPremium
              ? "Your subscription runs on your main wardrobe. Family wardrobes are managed profiles under your account — full wardrobe management, kept completely separate, and not separate Premium seats."
              : "Family wardrobes come with Premium. Premium features stay on your own main wardrobe."}
          </Txt>

          {profiles.map((p) => (
            <View key={p.id} style={styles.row}>
              <Pressable
                style={styles.rowMain}
                testID={`switch-profile-${p.id}`}
                onPress={async () => {
                  await switchTo(p.id);
                  close();
                }}
              >
                <View style={[styles.avatar, active?.id === p.id && styles.avatarActive]}>
                  <Txt style={styles.emoji}>{p.emoji || "👤"}</Txt>
                </View>
                <Txt style={styles.name}>{p.name}</Txt>
                {p.is_primary ? <Txt style={styles.primaryTag}>MAIN</Txt> : null}
                {active?.id === p.id ? <Feather name="check" size={18} color={colors.brand} /> : null}
              </Pressable>
              {profiles.length > 1 ? (
                confirmId === p.id ? (
                  <View style={styles.confirmRow}>
                    <Pressable onPress={() => remove(p.id)} testID={`confirm-delete-profile-${p.id}`} hitSlop={8}>
                      <Txt style={styles.confirmYes}>Delete</Txt>
                    </Pressable>
                    <Pressable onPress={() => setConfirmId(null)} hitSlop={8}>
                      <Txt style={styles.confirmNo}>Keep</Txt>
                    </Pressable>
                  </View>
                ) : (
                  <Pressable onPress={() => setConfirmId(p.id)} testID={`delete-profile-${p.id}`} hitSlop={8}>
                    <Feather name="trash-2" size={16} color={colors.onSurfaceTertiary} />
                  </Pressable>
                )
              ) : null}
            </View>
          ))}

          {confirmId ? (
            <Txt style={styles.warn}>Deleting a wardrobe also removes everything catalogued in it.</Txt>
          ) : null}

          <View style={styles.addRow}>
            <TextInput
              style={styles.input}
              value={newName}
              onChangeText={(t) => {
                setNewName(t);
                if (error) setError("");
              }}
              placeholder="New wardrobe name (e.g. David)"
              placeholderTextColor={colors.onSurfaceTertiary}
              editable={accountPremium && !busy}
              onSubmitEditing={add}
              returnKeyType="done"
              testID="new-profile-input"
            />
          </View>
          <Pressable style={styles.addBtn} testID="add-profile-button" onPress={add} disabled={busy}>
            {busy ? (
              <ActivityIndicator color={colors.onBrandPrimary} />
            ) : (
              <>
                <Feather name={accountPremium ? "plus" : "lock"} size={16} color={colors.onBrandPrimary} />
                <Txt style={styles.addTxt}>{accountPremium ? "Add wardrobe" : "Add wardrobe with Premium"}</Txt>
              </>
            )}
          </Pressable>

          {error ? <Txt style={styles.error} testID="switcher-error">{error}</Txt> : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(26,26,26,0.45)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.xl,
    paddingBottom: spacing["2xl"],
  },
  title: { fontSize: 24 },
  sub: { fontSize: 13, color: colors.onSurfaceTertiary, marginTop: 4, marginBottom: spacing.lg, lineHeight: 19 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm },
  rowMain: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 44 },
  avatar: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border,
  },
  avatarActive: { borderColor: colors.brand },
  emoji: { fontSize: 18 },
  name: { flex: 1, fontSize: 16, color: colors.onSurface },
  primaryTag: {
    fontSize: 9, letterSpacing: 1, color: colors.onSurfaceTertiary,
    borderWidth: 0.5, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: 6, paddingVertical: 2, overflow: "hidden",
  },
  confirmRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  confirmYes: { fontSize: 14, color: colors.error },
  confirmNo: { fontSize: 14, color: colors.onSurfaceTertiary },
  warn: { fontSize: 12, color: colors.warning, lineHeight: 17, marginTop: 4 },
  addRow: { marginTop: spacing.lg },
  input: {
    height: 48,
    borderWidth: 0.5,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    color: colors.onSurface,
    fontSize: 15,
    backgroundColor: colors.surfaceSecondary,
  },
  addBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    height: 50, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, marginTop: spacing.md,
  },
  addTxt: { color: colors.onBrandPrimary, fontSize: 15 },
  error: { color: colors.error, fontSize: 13, marginTop: spacing.md, lineHeight: 18 },
});
