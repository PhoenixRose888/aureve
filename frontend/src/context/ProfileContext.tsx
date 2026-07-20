import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api, setActiveProfileId } from "@/src/api/client";
import { storage } from "@/src/utils/storage";
import { useAuth } from "@/src/context/AuthContext";

export type Profile = {
  id: string;
  name: string;
  emoji?: string;
  kind?: string;
  profile?: any;
};

type Ctx = {
  profiles: Profile[];
  active: Profile | null;
  loading: boolean;
  switchTo: (id: string) => Promise<void>;
  createProfile: (name: string, emoji: string, kind: string) => Promise<void>;
  deleteProfile: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
};

const ProfileCtx = createContext<Ctx>({} as Ctx);
export const useProfiles = () => useContext(ProfileCtx);

const KEY = "aura_active_profile";

export function ProfileProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const applyActive = useCallback(async (id: string | null) => {
    setActiveId(id);
    setActiveProfileId(id);
    if (id) await storage.setItem(KEY, id);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api<Profile[]>("/profiles");
      setProfiles(list);
      const stored = await storage.getItem<string | null>(KEY, null);
      const chosen = list.find((p) => p.id === stored)?.id || list[0]?.id || null;
      await applyActive(chosen);
    } catch {}
    setLoading(false);
  }, [applyActive]);

  useEffect(() => {
    if (user) {
      load();
    } else {
      setProfiles([]);
      setActiveProfileId(null);
      setActiveId(null);
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const switchTo = useCallback(async (id: string) => {
    await applyActive(id);
  }, [applyActive]);

  const createProfile = useCallback(async (name: string, emoji: string, kind: string) => {
    const p = await api<Profile>("/profiles", { method: "POST", body: { name, emoji, kind } });
    await load();
    await applyActive(p.id);
  }, [load, applyActive]);

  const deleteProfile = useCallback(async (id: string) => {
    await api(`/profiles/${id}`, { method: "DELETE" });
    await load();
  }, [load]);

  const active = profiles.find((p) => p.id === activeId) || null;

  return (
    <ProfileCtx.Provider value={{ profiles, active, loading, switchTo, createProfile, deleteProfile, refresh: load }}>
      {children}
    </ProfileCtx.Provider>
  );
}
