import * as ImagePicker from "expo-image-picker";
import * as ImageManipulator from "expo-image-manipulator";
import { Linking } from "react-native";
import { diag } from "@/src/utils/diag";

export type PickResult = { base64: string } | { error: "denied" | "blocked" | "cancelled" | "failed" };

/** Longest edge we ever upload. Keeps recognition accurate while making the
 *  upload small enough to survive real mobile networks. */
const MAX_SIDE = 1280;
const JPEG_QUALITY = 0.7;

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
  quality: 1,
  base64: false,
  allowsEditing: false,
  allowsMultipleSelection: false,
};

/** Downscale + recompress on device so uploads are ~100-300KB instead of 2-4MB. */
async function shrink(asset: ImagePicker.ImagePickerAsset, source: string): Promise<string | null> {
  const started = Date.now();
  try {
    const longest = Math.max(asset.width || 0, asset.height || 0);
    const actions: ImageManipulator.Action[] = [];
    if (longest > MAX_SIDE) {
      actions.push(
        (asset.width || 0) >= (asset.height || 0)
          ? { resize: { width: MAX_SIDE } }
          : { resize: { height: MAX_SIDE } }
      );
    }
    const out = await ImageManipulator.manipulateAsync(asset.uri, actions, {
      compress: JPEG_QUALITY,
      format: ImageManipulator.SaveFormat.JPEG,
      base64: true,
    });
    if (!out.base64) throw new Error("no base64");
    diag("compress.done", {
      source,
      from: `${asset.width}x${asset.height}`,
      to: `${out.width}x${out.height}`,
      kb: Math.round((out.base64.length * 3) / 4 / 1024),
      ms: Date.now() - started,
    });
    return out.base64;
  } catch (e: any) {
    diag("compress.failed", { source, error: String(e?.message || e) });
    return null;
  }
}

export async function pickFromLibrary(): Promise<PickResult> {
  const perm = await ensureLibraryPermission();
  if (perm !== "granted") return { error: perm === "blocked" ? "blocked" : "denied" };
  try {
    const res = await ImagePicker.launchImageLibraryAsync(OPTS);
    if (res.canceled || !res.assets?.[0]) return { error: "cancelled" };
    diag("capture.picked", { source: "library" });
    const base64 = await shrink(res.assets[0], "library");
    return base64 ? { base64 } : { error: "failed" };
  } catch (e: any) {
    diag("capture.failed", { source: "library", error: String(e?.message || e) });
    return { error: "failed" };
  }
}

export async function pickFromCamera(): Promise<PickResult> {
  const perm = await ensureCameraPermission();
  if (perm !== "granted") return { error: perm === "blocked" ? "blocked" : "denied" };
  try {
    const res = await ImagePicker.launchCameraAsync(OPTS);
    if (res.canceled || !res.assets?.[0]) return { error: "cancelled" };
    diag("capture.picked", { source: "camera" });
    const base64 = await shrink(res.assets[0], "camera");
    return base64 ? { base64 } : { error: "failed" };
  } catch (e: any) {
    diag("capture.failed", { source: "camera", error: String(e?.message || e) });
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
    diag("capture.picked", { source: "library-multi", count: res.assets.length });
    const shrunk = await Promise.all(res.assets.map((a) => shrink(a, "library-multi")));
    const images = shrunk.filter((b): b is string => !!b);
    if (!images.length) return { error: "failed" };
    return { images };
  } catch (e: any) {
    diag("capture.failed", { source: "library-multi", error: String(e?.message || e) });
    return { error: "failed" };
  }
}

export function openSettings() {
  Linking.openSettings();
}
