/** Short display labels keep stored names intact for editing, search and classification. */
export function shortItemName(name: string = ""): string {
  const shortened = name.trim().replace(/\s+(?:t-?shirts?|tee shirts?|blazers?|trousers?|blouses?|shirts?|jumpers?|sweaters?|cardigans?|jackets?|coats?|dresses|dress|skirts?|jeans|pants|shorts|leggings?|singlets?|camisoles?|tops?|necklaces?|bracelets?|earrings?|rings?|watches|watch|anklets?|chokers?)$/i, "").trim();
  return shortened || name.trim();
}

/** Replace exact known item references once, including in older chat responses. */
export function shortItemReferences(content: string, items: { name?: string }[]): string {
  const labels = new Map(items.filter((item) => item.name?.trim()).map((item) => [item.name!.toLowerCase(), shortItemName(item.name)]));
  const names = [...labels.keys()].sort((a, b) => b.length - a.length);
  if (!names.length) return content;
  const escaped = names.map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const references = new RegExp(`(^|[^\\w])(${escaped.join("|")})(?=$|[^\\w])`, "gi");
  return content.replace(references, (_, prefix: string, name: string) => prefix + labels.get(name.toLowerCase()));
}
