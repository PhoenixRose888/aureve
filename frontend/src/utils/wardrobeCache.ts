/**
 * Tiny in-memory wardrobe cache so navigating away and back doesn't refetch the
 * whole catalogue. Any screen that changes an item calls markWardrobeDirty().
 */
let cached: any[] | null = null;
let fetchedAt = 0;
let dirty = false;

const MAX_AGE_MS = 60_000;

export const getCachedItems = () => cached;

export const setCachedItems = (items: any[]) => {
  cached = items;
  fetchedAt = Date.now();
  dirty = false;
};

export const markWardrobeDirty = () => {
  dirty = true;
};

/** Fresh enough to render without hitting the network again. */
export const wardrobeIsFresh = () =>
  !!cached && !dirty && Date.now() - fetchedAt < MAX_AGE_MS;

export const clearWardrobeCache = () => {
  cached = null;
  fetchedAt = 0;
  dirty = false;
};
