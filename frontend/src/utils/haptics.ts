import { Platform } from "react-native";
import * as Haptics from "expo-haptics";

// Thin wrappers so haptics never throw on web and stay consistent app-wide.
const enabled = Platform.OS !== "web";

export const tap = () => {
  if (enabled) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
};

export const success = () => {
  if (enabled) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
};

export const warn = () => {
  if (enabled) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
};
