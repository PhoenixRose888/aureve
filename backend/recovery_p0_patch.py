from pathlib import Path

root = Path(__file__).resolve().parents[1]
backend = root / "backend" / "server.py"
dressme = root / "frontend" / "app" / "(tabs)" / "dressme.tsx"
stylist = root / "frontend" / "app" / "(tabs)" / "stylist.tsx"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {label}")


# 1) Delete profile cleanup includes suggestion history.
replace_once(
    backend,
    '    for coll in (db.items, db.outfits, db.wear_logs, db.plans):\n        await coll.delete_many({"user_id": profile_id})\n',
    '    for coll in (db.items, db.outfits, db.wear_logs, db.plans, db.style_suggestions):\n        await coll.delete_many({"user_id": profile_id})\n',
    "profile cleanup removes suggestion history",
)

# 2) Add persistent suggestion-history helpers separate from wear logs.
old_recent = '''async def recent_looks_line(user_id: str, limit: int = 6) -> str:\n    \"\"\"Summarise the most recent outfits so the stylist doesn't rebuild them.\"\"\"\n    logs = await db.wear_logs.find({\"user_id\": user_id}, {\"_id\": 0}).sort(\"created_at\", -1).to_list(limit)\n    combos = [\",\".join(lg.get(\"item_ids\", [])) for lg in logs if lg.get(\"item_ids\")]\n    if not combos:\n        return \"\"\n    return \"RECENTLY WORN combinations (do not simply rebuild these): \" + \" | \".join(combos) + \"\\n\"\n\n\n'''
new_recent = '''async def recent_looks_line(user_id: str, limit: int = 6) -> str:\n    \"\"\"Summarise outfits the user actually logged as worn.\"\"\"\n    logs = await db.wear_logs.find({\"user_id\": user_id}, {\"_id\": 0}).sort(\"created_at\", -1).to_list(limit)\n    combos = [\",\".join(lg.get(\"item_ids\", [])) for lg in logs if lg.get(\"item_ids\")]\n    if not combos:\n        return \"\"\n    return \"RECENTLY WORN combinations (do not simply rebuild these): \" + \" | \".join(combos) + \"\\n\"\n\n\nasync def recent_suggestions(user_id: str, source: str = \"dressme\", limit: int = 12) -> List[dict]:\n    \"\"\"Persisted AI suggestion history. This is deliberately separate from wear_logs:\n    a suggested outfit must influence rotation without pretending it was actually worn.\"\"\"\n    return await db.style_suggestions.find(\n        {\"user_id\": user_id, \"source\": source}, {\"_id\": 0}\n    ).sort(\"created_at\", -1).to_list(limit)\n\n\ndef recent_suggestions_line(history: List[dict]) -> str:\n    combos = [\",\".join(x.get(\"item_ids\", [])) for x in history if x.get(\"item_ids\")]\n    if not combos:\n        return \"\"\n    counts = {}\n    for row in history:\n        for iid in row.get(\"item_ids\", []):\n            counts[iid] = counts.get(iid, 0) + 1\n    repeated = [iid for iid, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True) if n >= 2][:12]\n    extra = f\" Frequently suggested item ids to strongly deprioritise: {','.join(repeated)}.\" if repeated else \"\"\n    return (\n        \"RECENTLY SUGGESTED combinations (do not repeat these, even if they were never logged as worn): \"\n        + \" | \".join(combos) + extra + \"\\n\"\n    )\n\n\nasync def record_style_suggestion(user_id: str, source: str, occasion: str, item_ids: List[str]):\n    ids = [i for i in item_ids if i]\n    if not ids:\n        return\n    await db.style_suggestions.insert_one({\n        \"id\": new_id(\"sugg\"),\n        \"user_id\": user_id,\n        \"source\": source,\n        \"occasion\": occasion or \"\",\n        \"item_ids\": ids,\n        \"created_at\": now_utc().isoformat(),\n    })\n    # Bound storage per wardrobe/source. Keep the newest 60 only.\n    stale = await db.style_suggestions.find(\n        {\"user_id\": user_id, \"source\": source}, {\"_id\": 0, \"id\": 1}\n    ).sort(\"created_at\", -1).skip(60).to_list(500)\n    if stale:\n        await db.style_suggestions.delete_many({\"id\": {\"$in\": [x[\"id\"] for x in stale]}})\n\n\n'''
replace_once(backend, old_recent, new_recent, "persistent suggestion history helpers")

# 3) Extend _build_outfit with source, strict current-look exclusion, recent Dress Me history, diagnostics, and recording.
old_sig = '''async def _build_outfit(user: dict, occasion: str, temperature: Optional[float],\n                        weather: Optional[str], notes: Optional[str],\n                        avoid_item_ids: Optional[List[str]] = None):\n    items = await db.items.find(items_scope(user), {\"_id\": 0}).to_list(1000)\n    items = available_items(items)\n    if len(items) < 2:\n        raise HTTPException(status_code=400, detail=\"Not enough ready-to-wear items. Add more, or mark laundry as clean.\")\n    prefs = await learned_prefs(user[\"user_id\"])\n    wardrobe = summarize_items_for_ai(items)\n'''
new_sig = '''async def _build_outfit(user: dict, occasion: str, temperature: Optional[float],\n                        weather: Optional[str], notes: Optional[str],\n                        avoid_item_ids: Optional[List[str]] = None,\n                        source: str = \"stylist\"):\n    items = await db.items.find(items_scope(user), {\"_id\": 0}).to_list(1000)\n    items = available_items(items)\n    if len(items) < 2:\n        raise HTTPException(status_code=400, detail=\"Not enough ready-to-wear items. Add more, or mark laundry as clean.\")\n\n    explicit_avoid = {i for i in (avoid_item_ids or []) if i}\n    # Create Another Look is a hard instruction, not a polite hint. When the\n    # wardrobe has enough alternatives, remove the current look from the candidate\n    # pool entirely so the model cannot simply return it again.\n    if explicit_avoid:\n        alternatives = [it for it in items if it.get(\"id\") not in explicit_avoid]\n        if len(alternatives) >= 2:\n            items = alternatives\n\n    suggestion_history = await recent_suggestions(user[\"user_id\"], source=source) if source == \"dressme\" else []\n    prefs = await learned_prefs(user[\"user_id\"])\n    wardrobe = summarize_items_for_ai(items)\n'''
replace_once(backend, old_sig, new_sig, "outfit builder source and strict exclusions")

old_variety = '''    # Cross-day variety: name the pieces already worn elsewhere this week so the\n    # stylist intentionally varies looks instead of repeating the same hero items.\n    variety_line = \"\"\n    if avoid_item_ids:\n        avoid = set(avoid_item_ids)\n        used = [it for it in items if it.get(\"id\") in avoid]\n        if used:\n            names = \", \".join(f\"{it.get('name')} ({it.get('category')})\" for it in used)\n            variety_line = (\n                f\"ALREADY WORN elsewhere this week: {names}.\\n\"\n                \"Deliberately create a DIFFERENT look: vary the silhouette, colour palette, footwear and \"\n                \"accessories, and avoid reusing the same hero pieces (tops, bottoms, dresses, outerwear, shoes, bags) \"\n                \"unless there is a clear styling reason. Versatile basics may be reused only if styled noticeably \"\n                \"differently. Make genuine use of the wider wardrobe.\\n\"\n            )\n'''
new_variety = '''    variety_line = \"\"\n    if explicit_avoid:\n        variety_line = (\n            \"EXPLICIT EXCLUSION: the previous/current look must not be repeated. \"\n            f\"Excluded item ids: {','.join(sorted(explicit_avoid))}. \"\n            \"Build a materially different silhouette and hero-piece combination.\\n\"\n        )\n'''
replace_once(backend, old_variety, new_variety, "clear exclusion prompt")

replace_once(
    backend,
    '''        f\"{variety_line}\"\n        f\"{underused_line(items)}\"\n        f\"{await recent_looks_line(user['user_id'])}\"\n''',
    '''        f\"{variety_line}\"\n        f\"{recent_suggestions_line(suggestion_history)}\"\n        f\"{underused_line(items)}\"\n        f\"{await recent_looks_line(user['user_id'])}\"\n''',
    "suggestion history enters stylist prompt",
)

replace_once(
    backend,
    '''    result[\"resolved_items\"] = enriched\n    return result\n\n\nclass DressMeRequest(BaseModel):\n''',
    '''    result[\"resolved_items\"] = enriched\n    selected_ids = [x[\"item\"][\"id\"] for x in enriched if x.get(\"item\")]\n    if explicit_avoid and any(i in explicit_avoid for i in selected_ids):\n        logger.warning(\"STYLE_ROTATION source=%s exclusion_violation avoid=%s selected=%s\", source, sorted(explicit_avoid), selected_ids)\n    else:\n        logger.info(\"STYLE_ROTATION source=%s avoid=%s recent=%s selected=%s\", source, sorted(explicit_avoid), len(suggestion_history), selected_ids)\n    await record_style_suggestion(user[\"user_id\"], source, occasion, selected_ids)\n    return result\n\n\nclass DressMeRequest(BaseModel):\n''',
    "record and diagnose generated suggestions",
)

# 4) Dress Me backend receives current-look exclusion and marks suggestion source.
replace_once(
    backend,
    '''class DressMeRequest(BaseModel):\n    temperature: Optional[float] = None\n    weather: Optional[str] = None\n    occasion: Optional[str] = None  # override; otherwise inferred from today's plan\n''',
    '''class DressMeRequest(BaseModel):\n    temperature: Optional[float] = None\n    weather: Optional[str] = None\n    occasion: Optional[str] = None  # override; otherwise inferred from today's plan\n    avoid_item_ids: List[str] = []  # current on-screen look when asking for another\n''',
    "Dress Me request accepts avoid ids",
)
replace_once(
    backend,
    '''    result = await _build_outfit(user, occasion, payload.temperature, payload.weather, notes)\n''',
    '''    result = await _build_outfit(\n        user, occasion, payload.temperature, payload.weather, notes,\n        payload.avoid_item_ids, source=\"dressme\"\n    )\n''',
    "Dress Me forwards exclusions and source",
)

# 5) Frontend Dress Me preserves the current result while loading and sends its ids to /dressme.
replace_once(
    dressme,
    '''    setError(\"\");\n    setResult(null);\n    setSaved(false);\n    try {\n      const body: any = {};\n''',
    '''    setError(\"\");\n    setSaved(false);\n    try {\n      const body: any = {};\n''',
    "Dress Me keeps current look during regeneration",
)
replace_once(
    dressme,
    '''      if (weather && status === \"done\") {\n        body.temperature = weather.temperature;\n        body.weather = weather.description;\n      }\n      const r = await api<any>(\"/dressme\", { method: \"POST\", body });\n''',
    '''      if (weather && status === \"done\") {\n        body.temperature = weather.temperature;\n        body.weather = weather.description;\n      }\n      const currentItems = result?.resolved_items || [];\n      if (currentItems.length > 0) {\n        body.occasion = result?.occasion_used || undefined;\n        body.avoid_item_ids = currentItems.map((x: any) => x.item?.id).filter(Boolean);\n      }\n      const r = await api<any>(\"/dressme\", { method: \"POST\", body });\n''',
    "Dress Me sends current look exclusions",
)
replace_once(
    dressme,
    '''  }, [weather, status, router]);\n''',
    '''  }, [weather, status, router, result]);\n''',
    "Dress Me callback tracks current result",
)

# 6) Restore concise context question for materially vague AI Stylist prompts.
replace_once(
    stylist,
    '''const SUGGESTIONS = [\n  { icon: \"sun\", label: \"Help me dress for today\" },\n  { icon: \"grid\", label: \"Show me outfit ideas\" },\n  { icon: \"moon\", label: \"What should I wear tonight?\" },\n];\n\nexport default function Stylist() {\n''',
    '''const SUGGESTIONS = [\n  { icon: \"sun\", label: \"Help me dress for today\" },\n  { icon: \"grid\", label: \"Show me outfit ideas\" },\n  { icon: \"moon\", label: \"What should I wear tonight?\" },\n];\n\nfunction needsOccasionContext(text: string) {\n  const t = text.trim().toLowerCase();\n  if (!t) return false;\n  const asksWhatToWear = /(what should i wear|help me dress|dress me)/.test(t);\n  const vagueTime = /\\b(today|tonight|this morning|this afternoon|this evening|tomorrow)\\b/.test(t);\n  const specificContext = /\\b(work|office|meeting|wedding|funeral|church|date|dinner|lunch|party|club|concert|movie|movies|picnic|bbq|barbecue|school|gym|airport|flight|travel|interview|event|shopping|beach|hike|walk|brunch|birthday|formal|casual)\\b/.test(t);\n  return asksWhatToWear && vagueTime && !specificContext;\n}\n\nexport default function Stylist() {\n''',
    "AI Stylist vague occasion detector",
)
replace_once(
    stylist,
    '''    setMessages(history);\n    setInput(\"\");\n    setSending(true);\n    scrollDown();\n    try {\n''',
    '''    setMessages(history);\n    setInput(\"\");\n    scrollDown();\n\n    if (needsOccasionContext(content)) {\n      setMessages((prev) => [\n        ...prev,\n        { role: \"assistant\", content: \"What are you doing? Give me the occasion or plans and I’ll style you for that.\" },\n      ]);\n      haptics.success();\n      scrollDown();\n      return;\n    }\n\n    setSending(true);\n    try {\n''',
    "AI Stylist asks context before vague styling",
)

print("P0 recovery patch applied")
