import { useAuth } from "@/src/context/AuthContext";
import { useProfiles } from "@/src/context/ProfileContext";

/**
 * Premium entitlement belongs to the subscribing account and runs on its
 * PRIMARY wardrobe. Family wardrobes are managed profiles under that account —
 * they keep full wardrobe management but are not independent Premium seats.
 */
export function usePremiumAccess() {
  const { user } = useAuth();
  const { active } = useProfiles();
  const accountPremium = !!user?.premium;
  // Profiles created before this field existed default to primary.
  const isPrimary = active?.is_primary !== false;
  return { accountPremium, isPrimary, premium: accountPremium && isPrimary };
}
