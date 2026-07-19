import { useState, useEffect, useCallback } from "react";
import * as Location from "expo-location";
import { api } from "@/src/api/client";

export type Weather = {
  temperature: number;
  feels_like: number;
  code: number;
  description: string;
  city?: string;
} | null;

export function useWeather() {
  const [weather, setWeather] = useState<Weather>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "denied" | "error" | "done">("idle");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const perm = await Location.getForegroundPermissionsAsync();
      let granted = perm.granted;
      if (!granted && perm.canAskAgain) {
        const req = await Location.requestForegroundPermissionsAsync();
        granted = req.granted;
      }
      if (!granted) {
        setStatus("denied");
        return;
      }
      const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low });
      const { latitude, longitude } = loc.coords;
      let city: string | undefined;
      try {
        const geo = await Location.reverseGeocodeAsync({ latitude, longitude });
        city = geo?.[0]?.city || geo?.[0]?.region || undefined;
      } catch {}
      const w = await api<Weather>(`/weather?lat=${latitude}&lon=${longitude}`, { auth: false });
      setWeather({ ...(w as any), city });
      setStatus("done");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { weather, status, reload: load };
}
