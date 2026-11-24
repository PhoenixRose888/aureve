
/**
 * Presentation-only wardrobe taxonomy, shared by the Wardrobe browser and the
 * item editor. Every item keeps its stored category/subcategory — these helpers
 * only decide which chip an item appears under, and each item resolves to
 * exactly ONE subcategory. A user-chosen `subcategory` always wins.
 */
/** The six browsable top-level categories. Bags and Jewellery are no longer
 *  top level — they live inside Accessories (stored records are untouched). */
export const MAIN_CATEGORIES = [
  "Tops",
  "Bottoms",
  "Dresses",
  "Outerwear",
  "Shoes",
  "Accessories",
];

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
  // Bags/Jewellery records are presented inside Accessories.
  if (cat === "Bags" || cat === "Jewellery") return "Accessories";
  // A user-corrected subcategory means the stored category is deliberate.
  if (item.subcategory) return cat;
  const t = T(item);
  if (BODYSUIT_RE.test(t) && !/(swimsuit|swimwear|one-?piece swim)/.test(t)) return "Tops";
  if (cat !== "Tops" && cat !== "Outerwear") return cat;
  // Never let a fabric/word match drag an obvious top into Outerwear
  // (a "knit bodysuit" or "halter cami" is a top, not a cardigan).
  // \bt-?shirt keeps "sweatshirt" out of the t-shirt cue.
  if (/(bustier|corset|bralette|halter|cami|singlet|tank|tube top|crop top|\bt-?shirt|\btee\b|blouse|button-?up|button-?down|long ?sleeve top|long ?sleeve tee|jersey top|lightweight top)/.test(t)
      && !/(sweatshirt|hoodie|hooded|fleece|pullover|cardigan|\bcoat\b|blazer|\bjacket\b)/.test(t)) {
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
    // Cami = delicate/dressy construction (strap width alone decides nothing);
    // anything ambiguous and sleeveless defaults to Singlet.
    { label: "Camis", match: /(camisole|\bcami\b|slip top|silk slip|satin top|lace top|lace trim|cowl)/ },
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
    // A warmth layer, not simply "has long sleeves": sweatshirt/hoodie/fleece
    // construction, or a proper knitted pullover.
    { label: "Jumpers", match: /(jumper|sweater|sweatshirt|hoodie|hooded|pullover|fleece|cable ?knit|chunky knit|ribbed knit jumper|knitted (jumper|sweater|pullover)|\bcrewneck sweat)/ },
    { label: "Coats", match: /(coat|trench|parka|overcoat|\bmac\b|peacoat)/ },
    { label: "Jackets", match: /(jacket|bomber|biker|windbreaker|anorak|shacket|gilet|puffer)/ },
  ],
  Bottoms: [
    { label: "Skirts", match: /(skirt|skort)/ },
    { label: "Shorts", match: /(\bshorts?\b|bermuda|cut-?off)/ },
    { label: "Leggings", match: /(legging|jegging|yoga pant|\btights\b)/ },
    // Soft, relaxed, pull-on pants never belong with tailored trousers.
    { label: "Lounge Pants", match: /(lounge|track ?pant|trackie|jogger|sweat ?pant|drawstring|pyjama|pajama|\bpj\b|harem|elastic waist|pull-?on|loungewear|athletic pant)/ },
    { label: "Jeans", match: /(jean|denim)/ },
    { label: "Trousers", match: /(trouser|\bpants?\b|chino|slack|culotte|cargo|palazzo|\bwide ?leg\b|tailored|suit pant|dress pant|work pant)/ },
  ],
  Shoes: [
    // Named footwear type beats coverage/height (high-tops are sneakers), and a
    // raised heel beats the silhouette (heeled sandals and wedges are heels).
    { label: "Sneakers", match: /(sneaker|trainer|runner|running shoe|plimsoll|converse|high-?top|hi-?top|skate shoe|\bkicks\b)/ },
    { label: "Boots", match: /(\bboot\b|\bboots\b|bootie|chelsea|combat|wellington)/ },
    { label: "Heels", match: /(heel|stiletto|\bpump\b|\bpumps\b|court shoe|\bwedge\b|platform sandal)/ },
    { label: "Dress Shoes", match: /(oxford|derby|brogue|dress shoe|monk strap|formal shoe|wingtip|dress loafer)/ },
    { label: "Flats", match: /(\bflat\b|\bflats\b|ballet|loafer|moccasin|slipper|espadrille|sandal|slide|flip ?flop|thong|\bmule\b|gladiator)/ },
  ],
  Bags: [
    // Only two user-facing buckets: a handbag may have any kind of strap.
    { label: "Clutches", match: /(clutch|evening bag|wristlet|\bpouch\b)/ },
    { label: "Handbags", match: /(handbag|hand bag|\btote\b|\bpurse\b|\bhobo\b|bucket bag|shopper|top ?handle|shoulder bag|satchel|cross ?body|\bsling\b|belt bag|bum bag|baguette|mini bag|backpack|rucksack|briefcase|laptop bag|work bag|\bbag\b)/ },
  ],
  Accessories: [
    { label: "Sunglasses", match: /(sunglass|\bshades\b|eyewear|\bglasses\b)/ },
    { label: "Hats", match: /(\bhat\b|\bhats\b|\bcap\b|beanie|beret|fedora|visor|bucket hat)/ },
    { label: "Scarves", match: /(scarf|scarves|shawl|pashmina|snood|wrap\b)/ },
    { label: "Belts", match: /(\bbelt\b|\bbelts\b)/ },
    { label: "Gloves", match: /(glove|mitten)/ },
    { label: "Jewellery", match: /(necklace|pendant|\bchain\b|choker|locket|bracelet|bangle|anklet|earring|\bhoops?\b|\bring\b|\brings\b|signet|\bwatch\b|jewel)/ },
    // Every bag type lives together — no bag subtypes.
    { label: "Bags", match: /(\bbag\b|\bbags\b|handbag|\btote\b|clutch|backpack|rucksack|cross ?body|\bpurse\b|satchel|briefcase|\bhobo\b|shopper|wristlet|\bpouch\b)/ },
  ],
  // Third level under Accessories > Jewellery.
  Jewellery: [
    // Specific placement beats generic chain/pendant construction.
    { label: "Body jewellery", match: /(body (jewellery|jewelry|chain)|thigh (chain|jewellery|jewelry)|waist chain|belly chain|harness)/ },
    { label: "Anklets", match: /(anklet|ankle (chain|bracelet))/ },
    { label: "Chokers", match: /choker/ },
    { label: "Bracelets", match: /(bracelet|bangle|\bcuff\b)/ },
    { label: "Earrings", match: /(earring|ear ?stud|\bhoops?\b)/ },
    { label: "Watches", match: /(watch)/ },
    { label: "Rings", match: /(\bring\b|\brings\b|signet)/ },
    { label: "Necklaces", match: /(necklace|pendant|\bchain\b|locket)/ },
  ],
};

/** Chip order shown to the user (matching priority above is deliberately
 *  different — the most specific cue wins). Dresses stay a single category. */
export const SUB_ORDER: Record<string, string[]> = {
  Tops: ["T-Shirts", "Shirts", "Blouses", "Polos", "Singlets", "Camis", "Crops",
         "Halter", "Long Sleeve", "Vests", "Bodysuits", "Corsets"],
  Bottoms: ["Jeans", "Trousers", "Lounge Pants", "Shorts", "Skirts", "Leggings"],
  Outerwear: ["Blazers", "Jackets", "Coats", "Cardigans", "Jumpers"],
  Shoes: ["Sneakers", "Boots", "Heels", "Flats", "Dress Shoes"],
  Bags: ["Handbags", "Clutches"],
  Accessories: ["Bags", "Belts", "Hats", "Sunglasses", "Scarves", "Gloves", "Jewellery"],
  // Third level only, reached via Accessories > Jewellery.
  Jewellery: ["Necklaces", "Chokers", "Bracelets", "Rings", "Earrings", "Watches", "Anklets", "Body jewellery"],
};

/** Levels that hold another level of subcategories rather than garments. */
export const hasThirdLevel = (category: string, sub: string) =>
  category === "Accessories" && sub === "Jewellery";

/** Exactly one subcategory per item: a user correction first, then the first
 *  matching cue. Anything the cues can't place keeps an internal "Other"
 *  label, which is never offered as a chip (the category view still shows it). */
export function primarySub(item: any, category: string): string {
  const order = SUB_ORDER[category];
  if (!order) return "";
  if (item.subcategory && order.includes(item.subcategory)) return item.subcategory;
  // Stored category is the strongest signal inside Accessories.
  if (category === "Accessories") {
    if (item.category === "Bags") return "Bags";
    if (item.category === "Jewellery") return "Jewellery";
    if (SUB_ORDER.Jewellery.includes(item.subcategory)) return "Jewellery";
  }
  const t = T(item);
  for (const r of SUB_RULES[category] || []) if (r.match.test(t)) return r.label;
  return "Other";
}
