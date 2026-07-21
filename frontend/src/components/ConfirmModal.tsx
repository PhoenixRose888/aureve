import React from "react";
import { View, StyleSheet, Modal, Pressable, ActivityIndicator } from "react-native";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius, fonts } from "@/src/theme";

type Props = {
  visible: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

// Cross-platform confirm (works on web preview AND native, unlike Alert.alert
// whose callbacks don't fire on RN-Web).
export default function ConfirmModal({
  visible,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <Display weight="medium" style={styles.title}>{title}</Display>
          {message ? <Txt style={styles.message}>{message}</Txt> : null}
          <View style={styles.row}>
            <Pressable style={styles.cancel} onPress={onCancel} disabled={busy} testID="confirm-cancel">
              <Txt style={styles.cancelTxt}>{cancelLabel}</Txt>
            </Pressable>
            <Pressable
              style={[styles.confirm, destructive && styles.confirmDanger]}
              onPress={onConfirm}
              disabled={busy}
              testID="confirm-ok"
            >
              {busy ? (
                <ActivityIndicator color={colors.onSage} size="small" />
              ) : (
                <Txt style={styles.confirmTxt}>{confirmLabel}</Txt>
              )}
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", alignItems: "center", justifyContent: "center", padding: spacing.xl },
  card: { width: "100%", maxWidth: 380, backgroundColor: colors.surface, borderRadius: 20, padding: spacing.xl },
  title: { fontSize: 18, marginBottom: spacing.sm },
  message: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 21, marginBottom: spacing.lg },
  row: { flexDirection: "row", gap: spacing.md, marginTop: spacing.sm },
  cancel: { flex: 1, height: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  cancelTxt: { fontSize: 15, color: colors.onSurface, fontFamily: fonts.displayMedium },
  confirm: { flex: 1, height: 48, borderRadius: radius.md, backgroundColor: colors.sage, alignItems: "center", justifyContent: "center" },
  confirmDanger: { backgroundColor: colors.error },
  confirmTxt: { fontSize: 15, color: colors.onSage, fontFamily: fonts.displayMedium },
});
