import * as ImagePicker from "expo-image-picker";
import { Linking } from "react-native";

export type PickResult = { base64: string } | { error: "denied" | "blocked" | "cancelled" | "failed" };

async function ensureLibraryPermission(): Promise<"granted" | "denied" | "blocked"> {
  const current = await ImagePicker.getMediaLibraryPermissionsAsync();
  if (current.granted) return "granted";
  if (!current.canAskAgain) return "blocked";
  const req = await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (req.granted) return "granted";
  return req.canAskAgain ? "denied" : "blocked";
}

async function ensureCameraPermission(): Promise<"granted" | "denied" | "blocked"> {
  const current = await ImagePicker.getCameraPermissionsAsync();
  if (current.granted) return "granted";
  if (!current.canAskAgain) return "blocked";
  const req = await ImagePicker.requestCameraPermissionsAsync();
  if (req.granted) return "granted";
  return req.canAskAgain ? "denied" : "blocked";
}

const OPTS: ImagePicker.ImagePickerOptions = {
  mediaTypes: ["images"],
  quality: 0.6,
  base64: true,
  allowsEditing: false,
  allowsMultipleSelection: false,
};

export async function pickFromLibrary(): Promise<PickResult> {
  const perm = await ensureLibraryPermission();
  if (perm !== "granted") return { error: perm === "blocked" ? "blocked" : "denied" };
  try {
    const res = await ImagePicker.launchImageLibraryAsync(OPTS);
    if (res.canceled || !res.assets?.[0]?.base64) return { error: "cancelled" };
    return { base64: res.assets[0].base64 };
  } catch {
    return { error: "failed" };
  }
}

export async function pickFromCamera(): Promise<PickResult> {
  const perm = await ensureCameraPermission();
  if (perm !== "granted") return { error: perm === "blocked" ? "blocked" : "denied" };
  try {
    const res = await ImagePicker.launchCameraAsync(OPTS);
    if (res.canceled || !res.assets?.[0]?.base64) return { error: "cancelled" };
    return { base64: res.assets[0].base64 };
  } catch {
    return { error: "failed" };
  }
}

export type MultiPickResult = { images: string[] } | { error: "denied" | "blocked" | "cancelled" | "failed" };

export async function pickMultipleFromLibrary(limit = 10): Promise<MultiPickResult> {
  const perm = await ensureLibraryPermission();
  if (perm !== "granted") return { error: perm === "blocked" ? "blocked" : "denied" };
  try {
    const res = await ImagePicker.launchImageLibraryAsync({
      ...OPTS,
      allowsMultipleSelection: true,
      selectionLimit: limit,
    });
    if (res.canceled || !res.assets?.length) return { error: "cancelled" };
    const images = res.assets.map((a) => a.base64).filter((b): b is string => !!b);
    if (!images.length) return { error: "failed" };
    return { images };
  } catch {
    return { error: "failed" };
  }
}

export function openSettings() {
  Linking.openSettings();
}
