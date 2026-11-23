import { Platform } from "react-native";
import * as Sharing from "expo-sharing";
import * as FileSystem from "expo-file-system/legacy";

/**
 * Share (native) or download (web) a base64 image.
 * Used to export a saved Virtual Try-On look.
 */
export async function shareImage(base64: string, mime = "image/png") {
  const ext = mime.includes("jpeg") || mime.includes("jpg") ? "jpg" : "png";

  if (Platform.OS === "web") {
    const a = document.createElement("a");
    a.href = `data:${mime};base64,${base64}`;
    a.download = `aureve-look.${ext}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    return;
  }

  const uri = `${FileSystem.cacheDirectory}aureve-look-${Date.now()}.${ext}`;
  await FileSystem.writeAsStringAsync(uri, base64, { encoding: "base64" });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: mime, dialogTitle: "Share your look" });
  }
}
