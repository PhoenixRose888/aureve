import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { api, setToken, clearToken, getToken } from "@/src/api/client";

WebBrowser.maybeCompleteAuthSession();

type User = {
  user_id: string;
  email: string;
  name?: string;
  picture?: string;
  premium?: boolean;
  premium_until?: string;
  premium_source?: string;
  trial_used?: boolean;
  trial_eligible?: boolean;
} | null;

type AuthCtx = {
  user: User;
  loading: boolean;
  signingIn: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>({} as AuthCtx);
export const useAuth = () => useContext(Ctx);

const AUTH_URL = "https://auth.emergentagent.com/";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);
  const [signingIn, setSigningIn] = useState(false);

  const processSessionId = useCallback(async (sessionId: string) => {
    const data = await api<{ session_token: string; user: User }>("/auth/session", {
      method: "POST",
      auth: false,
      body: { session_token: sessionId },
    });
    await setToken(data.session_token);
    setUser(data.user);
  }, []);

  const checkExisting = useCallback(async () => {
    const token = await getToken();
    if (!token) return false;
    try {
      const me = await api<User>("/auth/me");
      setUser(me);
      return true;
    } catch {
      await clearToken();
      return false;
    }
  }, []);

  // On mount: web -> parse session_id from URL first; then check existing token.
  useEffect(() => {
    (async () => {
      try {
        if (Platform.OS === "web") {
          const hash = window.location.hash || "";
          const search = window.location.search || "";
          const match =
            hash.match(/session_id=([^&]+)/) || search.match(/session_id=([^&]+)/);
          if (match) {
            await processSessionId(decodeURIComponent(match[1]));
            window.history.replaceState(null, "", window.location.pathname);
            setLoading(false);
            return;
          }
        } else {
          const initial = await Linking.getInitialURL();
          if (initial) {
            const m = initial.match(/session_id=([^&]+)/);
            if (m) {
              await processSessionId(decodeURIComponent(m[1]));
              setLoading(false);
              return;
            }
          }
        }
        await checkExisting();
      } catch (e) {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, [processSessionId, checkExisting]);

  const login = useCallback(async () => {
    setSigningIn(true);
    try {
      if (Platform.OS === "web") {
        const redirectUrl = window.location.origin + "/";
        window.location.href = `${AUTH_URL}?redirect=${encodeURIComponent(redirectUrl)}`;
        return;
      }
      const redirectUrl = Linking.createURL("");
      const authUrl = `${AUTH_URL}?redirect=${encodeURIComponent(redirectUrl)}`;
      const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
      if (result.type === "success" && result.url) {
        const m = result.url.match(/session_id=([^&]+)/);
        if (m) {
          await processSessionId(decodeURIComponent(m[1]));
        }
      }
    } finally {
      setSigningIn(false);
    }
  }, [processSessionId]);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
    await clearToken();
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      setUser(await api<User>("/auth/me"));
    } catch {}
  }, []);

  return (
    <Ctx.Provider value={{ user, loading, signingIn, login, logout, refreshUser }}>
      {children}
    </Ctx.Provider>
  );
}
