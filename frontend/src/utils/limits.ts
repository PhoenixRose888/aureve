/** Free-tier wardrobe size. Mirrors FREE_ITEM_CAP in the backend, which is the
 *  authority: the server still rejects anything over the cap. */
export const FREE_ITEM_CAP = 100;

export const WARDROBE_FULL_TITLE = "Your Free wardrobe is full";
export const WARDROBE_FULL_BODY =
  `You've reached the ${FREE_ITEM_CAP}-piece limit on your Free account. Upgrade to Premium for unlimited wardrobe uploads.`;
export const WARDROBE_LIMIT_LABEL = "Free wardrobe limit reached";
