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

// Sensible default so the experience never dead-ends when location is
// unavailable (web preview, denied permission, timeouts).
const DEFAULT = { latitude: 51.5074, longitude: -0.1278, city: "London" };

async function ipLocation(): Promise<{ latitude: number; longitude: number; city?: string } | null> {
  try {
    const res = await Promise.race([
      fetch("https://ipapi.co/json/"),
      new Promise<Response>((_, reject) => setTimeout(() => reject(new Error("timeout")), 5000)),
    ]);
    const j: any = await (res as Response).json();
    if (j && typeof j.latitude === "number" && typeof j.longitude === "number") {
      return { latitude: j.latitude, longitude: j.longitude, city: j.city };
    }
  } catch {}
  return null;
}

export function useWeather() {
  const [weather, setWeather] = useState<Weather>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "denied" | "error" | "done">("idle");

  const fetchFor = useCallback(async (latitude: number, longitude: number, city?: string) => {
    const w = await api<Weather>(`/weather?lat=${latitude}&lon=${longitude}`, { auth: false });
    setWeather({ ...(w as any), city: city || (w as any)?.city });
    setStatus("done");
  }, []);

  const load = useCallback(async () => {
    setStatus("loading");
    // 1) Try precise device location.
    try {
      const perm = await Location.getForegroundPermissionsAsync();
      let granted = perm.granted;
      if (!granted && perm.canAskAgain) {
        const req = await Location.requestForegroundPermissionsAsync();
        granted = req.granted;
      }
      if (granted) {
        const loc = (await Promise.race([
          Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low }),
          new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 8000)),
        ])) as Location.LocationObject;
        const { latitude, longitude } = loc.coords;
        let city: string | undefined;
        try {
          const geo = await Location.reverseGeocodeAsync({ latitude, longitude });
          city = geo?.[0]?.city || geo?.[0]?.region || undefined;
        } catch {}
        await fetchFor(latitude, longitude, city);
        return;
      }
    } catch {}

    // 2) Fall back to approximate IP-based location.
    const ip = await ipLocation();
    if (ip) {
      try {
        await fetchFor(ip.latitude, ip.longitude, ip.city);
        return;
      } catch {}
    }

    // 3) Last resort: a default city so weather + suggestions always show.
    try {
      await fetchFor(DEFAULT.latitude, DEFAULT.longitude, DEFAULT.city);
    } catch {
      setStatus("error");
    }
  }, [fetchFor]);

  useEffect(() => {
    load();
  }, [load]);

  return { weather, status, reload: load };
}
