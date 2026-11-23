import { useEffect, useState } from "react";
import { Redirect } from "expo-router";
import { useAuth } from "@/src/context/AuthContext";
import BrandSplash from "@/src/components/BrandSplash";

export default function Index() {
  const { user, loading } = useAuth();
  const [minSplashDone, setMinSplashDone] = useState(false);

  useEffect(() => {
    // Hold the branded splash long enough for the logo to fade in and be read.
    const t = setTimeout(() => setMinSplashDone(true), 2900);
    return () => clearTimeout(t);
  }, []);

  if (loading || !minSplashDone) {
    return <BrandSplash />;
  }

  // A valid saved session opens straight to Home; otherwise the welcome screen.
  if (user) return <Redirect href="/(tabs)" />;
  return <Redirect href="/welcome" />;
}
