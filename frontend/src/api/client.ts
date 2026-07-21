import { storage } from "@/src/utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;
export const API = `${BASE}/api`;
export const TOKEN_KEY = "aura_session_token";

let activeProfileId: string | null = null;
export function setActiveProfileId(id: string | null) {
  activeProfileId = id;
}
export function getActiveProfileId() {
  return activeProfileId;
}

export async function getToken(): Promise<string | null> {
  return await storage.secureGet(TOKEN_KEY, null);
}

export async function setToken(token: string) {
  await storage.secureSet(TOKEN_KEY, token);
}

export async function clearToken() {
  await storage.secureRemove(TOKEN_KEY);
}

type Options = {
  method?: string;
  body?: any;
  auth?: boolean;
};

export async function api<T = any>(path: string, opts: Options = {}): Promise<T> {
  const { method = "GET", body, auth = true } = opts;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const token = await getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (activeProfileId) headers["X-Profile-Id"] = activeProfileId;
  }
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    // Don't wipe the stored token here — a transient 401 on one call
    // shouldn't log the user out of the whole app. Auth bootstrap
    // (/auth/me) handles genuine invalid sessions.
    const e = new Error("Unauthorized") as any;
    e.status = 401;
    throw e;
  }
  if (!res.ok) {
    let detail = "Request failed";
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {}
    const e = new Error(detail) as any;
    e.status = res.status;
    throw e;
  }
  return (await res.json()) as T;
}
