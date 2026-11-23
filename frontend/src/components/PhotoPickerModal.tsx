import React, { useState } from "react";
import { View, Modal, Pressable, StyleSheet, ActivityIndicator } from "react-native";
import { Feather } from "@expo/vector-icons";
import { Display, Txt } from "@/src/components/Typography";
import { colors, spacing, radius } from "@/src/theme";
import { pickFromCamera, pickFromLibrary, openSettings, PickResult } from "@/src/utils/image";

type Props = {
  visible: boolean;
  onClose: () => void;
  onPicked: (base64: string) => void;
  title?: string;
};

export default function PhotoPickerModal({ visible, onClose, onPicked, title = "Add a photo" }: Props) {
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(false);

  const handle = async (source: "camera" | "library") => {
    setBusy(true);
    setBlocked(false);
    const res: PickResult = source === "camera" ? await pickFromCamera() : await pickFromLibrary();
    setBusy(false);
    if ("base64" in res) {
      onPicked(res.base64);
      onClose();
    } else if (res.error === "blocked") {
      setBlocked(true);
    } else if (res.error === "denied") {
      setBlocked(true);
    }
    // cancelled/failed -> stay open silently
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} testID="photo-picker-backdrop">
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <Display weight="medium" style={styles.title}>
            {title}
          </Display>

          {busy ? (
            <View style={styles.busy}>
              <ActivityIndicator color={colors.onSurface} />
            </View>
          ) : blocked ? (
            <View style={styles.blocked}>
              <Txt style={styles.blockedTxt}>
                Photo access is off. Enable it in Settings to add photos of your clothes.
              </Txt>
              <Pressable style={styles.primaryBtn} onPress={openSettings} testID="open-settings-button">
                <Txt style={styles.primaryTxt}>Open Settings</Txt>
              </Pressable>
            </View>
          ) : (
            <>
              <Pressable style={styles.row} onPress={() => handle("camera")} testID="pick-camera-button">
                <Feather name="camera" size={20} color={colors.onSurface} />
                <Txt style={styles.rowTxt}>Take a photo</Txt>
              </Pressable>
              <View style={styles.divider} />
              <Pressable style={styles.row} onPress={() => handle("library")} testID="pick-library-button">
                <Feather name="image" size={20} color={colors.onSurface} />
                <Txt style={styles.rowTxt}>Choose from library</Txt>
              </Pressable>
            </>
          )}

          <Pressable style={styles.cancel} onPress={onClose} testID="photo-picker-cancel">
            <Txt style={styles.cancelTxt}>Cancel</Txt>
          </Pressable>
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
  title: { fontSize: 24, marginBottom: spacing.lg },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md },
  rowTxt: { fontSize: 16, color: colors.onSurface },
  divider: { height: 0.5, backgroundColor: colors.border },
  cancel: { marginTop: spacing.lg, alignItems: "center", paddingVertical: spacing.md },
  cancelTxt: { fontSize: 15, color: colors.onSurfaceTertiary },
  busy: { paddingVertical: spacing["2xl"], alignItems: "center" },
  blocked: { paddingVertical: spacing.md, gap: spacing.lg },
  blockedTxt: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  primaryBtn: {
    backgroundColor: colors.brandPrimary,
    paddingVertical: spacing.md,
    borderRadius: radius.sm,
    alignItems: "center",
  },
  primaryTxt: { color: colors.onBrandPrimary, fontSize: 15 },
});
