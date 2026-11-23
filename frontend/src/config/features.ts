/**
 * Features still in development.
 *
 * Their screens and server code stay in the repo for future work, but while a
 * feature is listed here its screen immediately redirects home, so it cannot be
 * reached from the app, a deep link or a typed web address. The matching API
 * routes answer 404 (see UNRELEASED_FEATURES in backend/server.py).
 *
 * To ship one: set it to true here AND remove its name from the backend set.
 */
export const FEATURES = {
  packing: false,
  capsule: false,
  tryon: false,
  planner: false,
  looks: false,
} as const;

export type FeatureName = keyof typeof FEATURES;
