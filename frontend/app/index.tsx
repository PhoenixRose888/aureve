import { useEffect, useState } from "react";
import { Redirect } from "expo-router";
import { useAuth } from "@/src/context/AuthContext";
import { storage } from "@/src/utils/storage";
import BrandSplash from "@/src/components/BrandSplash";

export default function Index() {
  const { user, loading } = useAuth();
  const [onboarded, setOnboarded] = useState<boolean | null>(null);

  useEffect(() => {
    storage.getItem<boolean>("aureve_onboarded", false).then((v) => setOnboarded(!!v));
  }, []);

  if (loading || onboarded === null) {
    return <BrandSplash />;
  }

  if (user) return <Redirect href="/(tabs)" />;
  return <Redirect href={onboarded ? "/login" : "/onboarding"} />;
}
