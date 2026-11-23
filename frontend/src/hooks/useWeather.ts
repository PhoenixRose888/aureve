import { useEffect, useReducer } from "react";
import * as Location from "expo-location";
import { api } from "@/src/api/client";
import { storage } from "@/src/utils/storage";

export type WeatherData = {
  temperature: number;
  feels_like: number;
  code: number;
  description: string;
  city?: string;
};
export type Weather = WeatherData | null;
export type WeatherStatus = "idle" | "loading" | "denied" | "error" | "done";

// Weather is read by Home, Dress Me, AI Stylist, Hair and the outfit builder.
// It is cached at MODULE level (not per screen) so moving between those screens
// never re-runs the location lookup or shows a dash while it reloads, and so a
// stylist message sent seconds after launch still carries today's conditions.
const CACHE_KEY = "aureve.weather.v1";
const FRESH_MS = 30 * 60 * 1000;       // reuse as-is
const USABLE_MS = 3 * 60 * 60 * 1000;  // still shown/sent while a refresh runs; older is dropped

// Sensible default so the experience never dead-ends when location is
// unavailable (web preview, denied permission, timeouts).
const DEFAULT = { latitude: 51.5074, longitude: -0.1278, city: "London" };

type Coords = { latitude: number; longitude: number; city?: string };

let cache: { weather: WeatherData; at: number } | null = null;
let coords: Coords | null = null;      // remembered for the session once resolved
let status: WeatherStatus = "idle";
let inflight: Promise<void> | null = null;
let hydrated = false;
let retries = 0;

const subscribers = new Set<() => void>();
const publish = () => subscribers.forEach((fn) => fn());

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    p,
    new Promise<T>((_, reject) => setTimeout(() => reject(new Error("timeout")), ms)),
  ]);
}

const usable = () => (cache && Date.now() - cache.at < USABLE_MS ? cache.weather : null);

async function hydrate() {
  if (hydrated) return;
  hydrated = true;
  const raw = await storage.getItem(CACHE_KEY, "");
  if (!raw || typeof raw !== "string") return;
  try {
    const parsed = JSON.parse(raw);
    if (
      typeof parsed?.at === "number" &&
      Date.now() - parsed.at < USABLE_MS &&
      typeof parsed?.weather?.temperature === "number"
    ) {
      cache = parsed;
      status = "done";
      publish();
    }
  } catch {}
}

async function ipLocation(): Promise<Coords | null> {
  try {
    const res = await withTimeout(fetch("https://ipapi.co/json/"), 4000);
    if (!res.ok) return null; // free tier rate-limits with 429
    const j: any = await res.json();
    if (typeof j?.latitude === "number" && typeof j?.longitude === "number") {
      return { latitude: j.latitude, longitude: j.longitude, city: j.city };
    }
  } catch {}
  return null;
}

async function resolveCoords(): Promise<Coords> {
  if (coords) return coords;
  // 1) Precise device location. Every step is time-boxed — an unanswered
  //    permission prompt must never leave the app without weather.
  try {
    const perm = await withTimeout(Location.getForegroundPermissionsAsync(), 6000);
    let granted = perm.granted;
    if (!granted && perm.canAskAgain) {
      granted = (await withTimeout(Location.requestForegroundPermissionsAsync(), 20000)).granted;
    }
    if (granted) {
      const loc = await withTimeout(
        Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low }),
        8000,
      );
      let city: string | undefined;
      try {
        const geo = await Location.reverseGeocodeAsync(loc.coords);
        city = geo?.[0]?.city || geo?.[0]?.region || undefined;
      } catch {}
      coords = { latitude: loc.coords.latitude, longitude: loc.coords.longitude, city };
      return coords;
    }
  } catch {}

  // 2) Approximate IP location.
  const ip = await ipLocation();
  if (ip) {
    coords = ip;
    return coords;
  }

  // 3) Last resort — deliberately NOT remembered, so the next load can still
  //    find the real location once permission or the network recovers.
  return DEFAULT;
}

async function refresh() {
  if (!usable()) {
    status = "loading";
    publish();
  }
  try {
    const where = await resolveCoords();
    const w = await api<WeatherData>(
      `/weather?lat=${where.latitude}&lon=${where.longitude}`,
      { auth: false, timeoutMs: 12000 },
    );
    if (typeof w?.temperature !== "number") throw new Error("no weather");
    cache = { weather: { ...w, city: where.city || w.city }, at: Date.now() };
    status = "done";
    retries = 0;
    storage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch {
    // Keep showing the last known conditions rather than a dash; only report an
    // error when there is genuinely nothing to show, and try again shortly —
    // the weather provider is occasionally slow for a minute at a time.
    status = usable() ? "done" : "error";
    if (!usable() && retries < 2) {
      retries += 1;
      const delay = retries * 5000;
      setTimeout(() => { if (!usable()) ensureWeather(true); }, delay);
    }
  } finally {
    publish();
  }
}

/** Shared, de-duplicated weather load. Screens call this via useWeather(). */
export async function ensureWeather(force = false) {
  await hydrate();
  if (!force && usable() && Date.now() - cache!.at < FRESH_MS) {
    if (status !== "done") {
      status = "done";
      publish();
    }
    return;
  }
  if (!inflight) inflight = refresh().finally(() => { inflight = null; });
  return inflight;
}

export function useWeather() {
  const [, bump] = useReducer((c: number) => c + 1, 0);

  useEffect(() => {
    subscribers.add(bump);
    ensureWeather();
    return () => { subscribers.delete(bump); };
  }, []);

  return { weather: usable(), status, reload: () => ensureWeather(true) };
}
