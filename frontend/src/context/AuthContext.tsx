import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { api, setToken, clearToken, getToken } from "@/src/api/client";
import { storage } from "@/src/utils/storage";
import { initPurchases } from "@/src/services/purchases";

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
  is_guest?: boolean;
} | null;

type AuthCtx = {
  user: User;
  isGuest: boolean;
  loading: boolean;
  signingIn: boolean;
  login: () => Promise<void>;
  guestLogin: () => Promise<void>;
  loginEmail: (email: string, password: string) => Promise<void>;
  registerEmail: (email: string, password: string, name?: string) => Promise<void>;
  deleteAccount: () => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>({} as AuthCtx);
export const useAuth = () => useContext(Ctx);

const AUTH_URL = "https://auth.emergentagent.com/";
// Token stashed when a guest starts Google sign-in so the backend can migrate
// their wardrobe into the new account (survives the web redirect reload).
const GUEST_MIGRATE_KEY = "aura_guest_migrate_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);
  const [signingIn, setSigningIn] = useState(false);

  const processSessionId = useCallback(async (sessionId: string) => {
    const guestToken = await storage.secureGet<string>(GUEST_MIGRATE_KEY, "");
    const data = await api<{ session_token: string; user: User }>("/auth/session", {
      method: "POST",
      auth: false,
      body: { session_token: sessionId, guest_token: guestToken || undefined },
    });
    await setToken(data.session_token);
    if (guestToken) await storage.secureRemove(GUEST_MIGRATE_KEY);
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

  // Stash the current guest token so it can be migrated after Google sign-in.
  const stashGuestToken = useCallback(async () => {
    if (!user?.is_guest) return;
    const token = await getToken();
    if (token) await storage.secureSet(GUEST_MIGRATE_KEY, token);
  }, [user]);

  const guestLogin = useCallback(async () => {
    setSigningIn(true);
    try {
      const data = await api<{ session_token: string; user: User }>("/auth/guest", {
        method: "POST",
        auth: false,
      });
      await setToken(data.session_token);
      setUser(data.user);
    } finally {
      setSigningIn(false);
    }
  }, []);

  const login = useCallback(async () => {
    setSigningIn(true);
    try {
      await stashGuestToken();
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
  }, [processSessionId, stashGuestToken]);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
    await clearToken();
    await storage.secureRemove(GUEST_MIGRATE_KEY);
    setUser(null);
  }, []);

  const emailAuth = useCallback(async (mode: "login" | "register", email: string, password: string, name?: string) => {
    setSigningIn(true);
    try {
      let guest_token: string | undefined;
      if (user?.is_guest) {
        const t = await getToken();
        if (t) guest_token = t;
      }
      const data = await api<{ session_token: string; user: User }>(
        mode === "register" ? "/auth/register" : "/auth/login",
        { method: "POST", auth: false, body: { email, password, name, guest_token } }
      );
      await setToken(data.session_token);
      setUser(data.user);
    } finally {
      setSigningIn(false);
    }
  }, [user]);

  const loginEmail = useCallback((email: string, password: string) => emailAuth("login", email, password), [emailAuth]);
  const registerEmail = useCallback((email: string, password: string, name?: string) => emailAuth("register", email, password, name), [emailAuth]);

  // Configure RevenueCat with the signed-in user id (native only; no-op on web / Expo Go).
  useEffect(() => {
    if (user?.user_id && !user?.is_guest) {
      initPurchases(user.user_id).catch(() => {});
    }
  }, [user?.user_id, user?.is_guest]);

  const deleteAccount = useCallback(async () => {
    try {
      await api("/auth/account", { method: "DELETE" });
    } catch {}
    await clearToken();
    await storage.secureRemove(GUEST_MIGRATE_KEY);
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {    try {
      setUser(await api<User>("/auth/me"));
    } catch {}
  }, []);

  return (
    <Ctx.Provider
      value={{
        user,
        isGuest: !!user?.is_guest,
        loading,
        signingIn,
        login,
        guestLogin,
        loginEmail,
        registerEmail,
        deleteAccount,
        logout,
        refreshUser,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}
