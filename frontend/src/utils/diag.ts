import { Platform } from "react-native";
import { API, getToken } from "@/src/api/client";

/**
 * Lightweight stage-level diagnostics for the photo → recognition pipeline.
 *
 * Console logging alone is useless on TestFlight, so every stage is also
 * shipped (fire-and-forget) to the backend where it lands in the server log.
 * This lets a real-device failure be pinpointed to an exact stage.
 */
export function diag(stage: string, data?: Record<string, any>) {
  const payload = { stage, data: data || {}, platform: Platform.OS };
  console.log(`[AUREVE] ${stage}`, data || "");
  ship(payload);
}

async function ship(payload: { stage: string; data: Record<string, any>; platform: string }) {
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = await getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    await fetch(`${API}/diag/log`, { method: "POST", headers, body: JSON.stringify(payload) });
  } catch {
    // diagnostics must never break the flow
  }
}
