import { useEffect, useState } from "react";
import { Redirect } from "expo-router";
import { useAuth } from "@/src/context/AuthContext";
import { storage } from "@/src/utils/storage";
import BrandSplash from "@/src/components/BrandSplash";

export default function Index() {
  const { user, loading } = useAuth();
  const [onboarded, setOnboarded] = useState<boolean | null>(null);
  const [launched, setLaunched] = useState<boolean | null>(null);
  const [minSplashDone, setMinSplashDone] = useState(false);

  useEffect(() => {
    storage.getItem<boolean>("aureve_onboarded", false).then((v) => setOnboarded(!!v));
    storage.getItem<boolean>("aureve_launched", false).then((v) => setLaunched(!!v));
    // Hold the branded splash long enough for the logo to fade in and be read.
    const t = setTimeout(() => setMinSplashDone(true), 2400);
    return () => clearTimeout(t);
  }, []);

  if (loading || onboarded === null || launched === null || !minSplashDone) {
    return <BrandSplash />;
  }

  // Returning users with a session open straight to Home.
  if (user) return <Redirect href="/(tabs)" />;
  // First launch only: the dedicated welcome screen.
  if (!launched) return <Redirect href="/welcome" />;
  // Launched before but no session: resume onboarding or sign in.
  return <Redirect href={onboarded ? "/login" : "/onboarding"} />;
}
