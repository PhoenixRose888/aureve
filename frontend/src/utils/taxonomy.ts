import { CATEGORIES } from "@/src/theme";

/**
 * Presentation-only wardrobe taxonomy, shared by the Wardrobe browser and the
 * item editor. Every item keeps its stored category/subcategory — these helpers
 * only decide which chip an item appears under, and each item resolves to
 * exactly ONE subcategory. A user-chosen `subcategory` always wins.
 */
export const FILTERS = [...CATEGORIES];

// Construction cues live across several catalogued fields, not just the name.
const T = (i: any) => {
  const sl = String(i.sleeve_length || "").toLowerCase();
  const sleeve = /long/.test(sl)
    ? "long sleeve"
    : /short/.test(sl)
    ? "short sleeve"
    : /sleeveless|none|n\/a/.test(sl)
    ? "sleeveless"
    : "";
  return `${i.name || ""} ${i.style || ""} ${i.fabric || ""} ${i.pattern || ""} ${i.description || ""} ${i.fit_notes || ""} ${sleeve}`.toLowerCase();
};

/** One-piece garments that fasten through the crotch — bodysuits, leotards and
 *  jumpsuits/playsuits — are tops, whatever they were saved as. */
const BODYSUIT_RE = /(body ?suit|bodysuit|leotard|unitard|jump ?suit|jumpsuit|playsuit|\bromper\b|boiler ?suit|dungaree|overall)/;

export function displayCategory(item: any): string {
  const cat = item.category || "";
  // A user-corrected subcategory means the stored category is deliberate.
  if (item.subcategory) return cat;
  const t = T(item);
  if (BODYSUIT_RE.test(t) && !/(swimsuit|swimwear|one-?piece swim)/.test(t)) return "Tops";
  if (cat !== "Tops" && cat !== "Outerwear") return cat;
  // Never let a fabric/word match drag an obvious top into Outerwear
  // (a "knit bodysuit" or "halter cami" is a top, not a cardigan).
  // \bt-?shirt keeps "sweatshirt" out of the t-shirt cue.
  if (/(bustier|corset|bralette|halter|cami|singlet|tank|tube top|crop top|\bt-?shirt|\btee\b|blouse|button-?up|button-?down)/.test(t)
      && !/(sweatshirt|hoodie|hooded)/.test(t)) {
    return "Tops";
  }
  if (/\b(vest|vest top|waistcoat|gilet)\b/.test(t)) return "Tops";
  if (/(hoodie|sweatshirt|jumper|sweater|cardigan|coat|trench|parka|puffer|blazer|jacket)/.test(t)) {
    return "Outerwear";
  }
  return cat;
}

export const SUB_RULES: Record<string, { label: string; match: RegExp }[]> = {
  // Most specific garment-type cue first — each item resolves to ONE label.
  Tops: [
    { label: "Bodysuits", match: BODYSUIT_RE },
    { label: "Corsets", match: /(corset|bustier|basque|boned|lace-?up (top|bodice|back)|bralette)/ },
    { label: "Halter", match: /(halter|halter-?neck|tie-?neck|neck-?tie top)/ },
    { label: "Crops", match: /(crop top|cropped top|crop tee|cropped tee|\bcropped\b|\bcrop\b|bandeau|tube top|strapless top)/ },
    { label: "Polos", match: /(\bpolo\b(?! ?neck)|polo shirt|piqu)/ },
    { label: "Vests", match: /(\bvest\b|\bvests\b|vest top|waistcoat|gilet)/ },
    { label: "Camis", match: /(camisole|\bcami\b|spaghetti|slip top|silk slip)/ },
    { label: "Singlets", match: /(singlet|\btank\b|tank top|sleeveless)/ },
    { label: "T-Shirts", match: /(\bt-?shirt|\btshirt|tee shirt|\btee\b|jersey top|crew ?neck|scoop ?neck|v-?neck tee)/ },
    { label: "Blouses", match: /(blouse|peplum|smock|tunic|wrap top|ruffle|satin|chiffon|georgette|silk top)/ },
    { label: "Shirts", match: /(\bshirts?\b|oxford|button-?up|button-?down|poplin|collared|flannel)/ },
    { label: "Long Sleeve", match: /(long ?sleeve|turtle ?neck|roll ?neck|polo ?neck|henley|knit top|rib{1,2}ed|merino|cashmere|\bknit\b)/ },
    { label: "T-Shirts", match: /short ?sleeve/ },
  ],
  Outerwear: [
    { label: "Blazers", match: /(blazer|suit jacket|tuxedo jacket)/ },
    { label: "Cardigans", match: /(cardigan|\bcardi\b)/ },
    { label: "Jumpers", match: /(jumper|sweater|sweatshirt|hoodie|hooded|pullover|\bknit\b|merino|cashmere)/ },
    { label: "Coats", match: /(coat|trench|parka|overcoat|\bmac\b|peacoat)/ },
    { label: "Jackets", match: /(jacket|bomber|biker|windbreaker|anorak|shacket|gilet|puffer)/ },
  ],
  Bottoms: [
    { label: "Skirts", match: /(skirt|skort)/ },
    { label: "Shorts", match: /(\bshorts?\b|bermuda|cut-?off)/ },
    { label: "Leggings", match: /(legging|jegging|yoga pant|\btights\b)/ },
    { label: "Jeans", match: /(jean|denim)/ },
    { label: "Pants", match: /(pant|trouser|chino|slack|culotte|cargo|jogger|track ?pant|palazzo|\bwide ?leg\b)/ },
  ],
  Shoes: [
    // Named footwear type beats coverage/height: high-tops are sneakers and
    // wedge sandals are sandals.
    { label: "Sneakers", match: /(sneaker|trainer|runner|running shoe|plimsoll|converse|high-?top|hi-?top|skate shoe|\bkicks\b)/ },
    { label: "Sandals", match: /(sandal|slide|flip ?flop|thong|espadrille|\bmule\b|gladiator)/ },
    { label: "Boots", match: /(\bboot\b|\bboots\b|bootie|chelsea|combat|wellington)/ },
    { label: "Heels", match: /(heel|stiletto|\bpump\b|\bpumps\b|court shoe|\bwedge\b)/ },
    { label: "Dress Shoes", match: /(oxford|derby|brogue|dress shoe|monk strap|formal shoe|wingtip)/ },
    { label: "Flats", match: /(\bflat\b|\bflats\b|ballet|loafer|moccasin|slipper|espadrille)/ },
  ],
  Bags: [
    // Carry style and construction, never "has a strap".
    { label: "Backpacks", match: /(backpack|back pack|rucksack|knapsack|two shoulder straps)/ },
    { label: "Briefcases", match: /(briefcase|attach|laptop bag|work bag|document|portfolio case)/ },
    { label: "Clutches", match: /(clutch|evening bag|wristlet|\bpouch\b)/ },
    { label: "Crossbody", match: /(cross ?body|\bsling bag\b|belt bag|bum bag|fanny pack|\bbaguette\b|mini bag)/ },
    { label: "Handbags", match: /(handbag|hand bag|\btote\b|\bpurse\b|\bhobo\b|bucket bag|shopper|top ?handle|shoulder bag|satchel|\bbag\b)/ },
  ],
  Accessories: [
    { label: "Sunglasses", match: /(sunglass|\bshades\b|eyewear|\bglasses\b)/ },
    { label: "Hats", match: /(\bhat\b|\bhats\b|\bcap\b|beanie|beret|fedora|visor|bucket hat)/ },
    { label: "Scarves", match: /(scarf|scarves|shawl|pashmina|snood|wrap\b)/ },
    { label: "Ties", match: /(necktie|\btie\b|\bties\b|bow ?tie|cravat)/ },
    { label: "Belts", match: /(\bbelt\b|\bbelts\b)/ },
    { label: "Gloves", match: /(glove|mitten)/ },
  ],
  Jewellery: [
    { label: "Necklaces", match: /(necklace|pendant|\bchain\b|choker|locket)/ },
    { label: "Bracelets", match: /(bracelet|bangle|\bcuff\b|anklet)/ },
    { label: "Earrings", match: /(earring|ear ?stud|\bhoops?\b)/ },
    { label: "Watches", match: /(watch)/ },
    { label: "Rings", match: /(\bring\b|\brings\b|signet)/ },
  ],
};

/** Chip order shown to the user (matching priority above is deliberately
 *  different — the most specific cue wins). Dresses stay a single category. */
export const SUB_ORDER: Record<string, string[]> = {
  Tops: ["T-Shirts", "Shirts", "Blouses", "Polos", "Singlets", "Camis", "Crops",
         "Halter", "Long Sleeve", "Vests", "Bodysuits", "Corsets"],
  Bottoms: ["Jeans", "Pants", "Shorts", "Skirts", "Leggings"],
  Outerwear: ["Blazers", "Jackets", "Coats", "Cardigans", "Jumpers"],
  Shoes: ["Sneakers", "Boots", "Heels", "Flats", "Sandals", "Dress Shoes"],
  Bags: ["Handbags", "Backpacks", "Clutches", "Briefcases", "Crossbody"],
  Accessories: ["Hats", "Sunglasses", "Scarves", "Ties", "Belts", "Gloves"],
  Jewellery: ["Necklaces", "Bracelets", "Earrings", "Rings", "Watches"],
};

/** Exactly one subcategory per item: a user correction first, then the first
 *  matching cue. Anything the cues can't place keeps an internal "Other"
 *  label, which is never offered as a chip (the category view still shows it). */
export function primarySub(item: any, category: string): string {
  const order = SUB_ORDER[category];
  if (!order) return "";
  if (item.subcategory && order.includes(item.subcategory)) return item.subcategory;
  const t = T(item);
  for (const r of SUB_RULES[category] || []) if (r.match.test(t)) return r.label;
  return "Other";
}
