import { Redirect } from "expo-router";

// The Dress Me tab intercepts its press (see (tabs)/_layout) and opens the
// full-screen flow. This redirect is only a safety net if focused directly.
export default function DressMeTab() {
  return <Redirect href="/dressme" />;
}
