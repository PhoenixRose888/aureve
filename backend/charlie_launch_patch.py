from pathlib import Path

path = Path(__file__).with_name("server.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}; refusing unsafe patch")
    text = text.replace(old, new, 1)
    print(f"patched: {label}")


# 1) Reviewer/demo isolation. Guests keep sample data. A signed-in reviewer only
# sees seeded samples while their wardrobe is genuinely empty; once real uploads
# exist, all normal items_scope() consumers exclude demo rows.
replace_once(
'''    account_premium = is_premium(account)
    return {
        "user_id": prof["id"],       # data scope = profile id
        "account_id": account_id,
        "profile_id": prof["id"],
        "profile_name": prof.get("name"),
        "profile": prof.get("profile") or {},
        "is_primary": is_primary,
        "account_premium": account_premium,
        "premium": account_premium and is_primary,
        # Sample/practice pieces belong to Guest mode and the Apple review
        # account only — never to a real signed-in wardrobe.
        "show_demo": bool(account.get("is_guest")) or _norm_email(account.get("email") or "") == REVIEWER_EMAIL,
    }
''',
'''    account_premium = is_premium(account)

    # Guest mode deliberately uses sample pieces. The App Store reviewer may
    # also use the seeded sample wardrobe, but ONLY while that wardrobe has no
    # real uploads. As soon as real pieces exist, every items_scope() consumer
    # (stylist, Dress Me, Shopping Intelligence, health, counts, pairings, etc.)
    # sees the real wardrobe only.
    is_guest = bool(account.get("is_guest"))
    is_reviewer = _norm_email(account.get("email") or "") == REVIEWER_EMAIL
    show_demo = is_guest
    if is_reviewer and not is_guest:
        real_item_count = await db.items.count_documents({
            "user_id": prof["id"],
            "demo": {"$ne": True},
        })
        show_demo = real_item_count == 0

    return {
        "user_id": prof["id"],       # data scope = profile id
        "account_id": account_id,
        "profile_id": prof["id"],
        "profile_name": prof.get("name"),
        "profile": prof.get("profile") or {},
        "is_primary": is_primary,
        "account_premium": account_premium,
        "premium": account_premium and is_primary,
        "show_demo": show_demo,
    }
''',
"dynamic reviewer demo visibility",
)

replace_once(
'''        # Ensure representative content: a default profile with a clean demo
        # wardrobe, reconciled deterministically (see below) so repeated
        # startups/redeploys can never create duplicates.
        prof = await ensure_default_profile(user_id, "Reviewer")
        await reconcile_reviewer_wardrobe(prof["id"])
        logger.info(f"Reviewer account ready: {email}")
''',
'''        # Seed representative demo content only while the reviewer wardrobe is
        # genuinely empty. Once real uploads exist, remove old seeded rows rather
        # than resurrecting them on every restart/deploy.
        prof = await ensure_default_profile(user_id, "Reviewer")
        real_item_count = await db.items.count_documents({
            "user_id": prof["id"],
            "demo": {"$ne": True},
        })
        if real_item_count == 0:
            await reconcile_reviewer_wardrobe(prof["id"])
        else:
            removed = await db.items.delete_many({"user_id": prof["id"], "demo": True})
            await db.outfits.delete_many({"user_id": prof["id"], "demo": True})
            await db.wear_logs.delete_many({"user_id": prof["id"], "demo": True})
            logger.info(
                "Reviewer has %s real pieces; removed %s seeded demo pieces",
                real_item_count,
                removed.deleted_count,
            )
        logger.info(f"Reviewer account ready: {email}")
''',
"stop reviewer demo reseeding after real uploads",
)

# 2) Don't return demo outfits to a real signed-in wardrobe. Item resolution was
# already scoped, but the outfit rows themselves could still leak through empty.
replace_once(
'''@api_router.get("/outfits")
async def list_outfits(user: dict = Depends(get_scope)):
    outfits = await db.outfits.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    by_id = {it["id"]: it async for it in db.items.find(items_scope(user), {"_id": 0})}
''',
'''@api_router.get("/outfits")
async def list_outfits(user: dict = Depends(get_scope)):
    outfit_query = {"user_id": user["user_id"]}
    if not user.get("show_demo"):
        outfit_query["demo"] = {"$ne": True}
    outfits = await db.outfits.find(outfit_query, {"_id": 0}).sort("created_at", -1).to_list(500)
    by_id = {it["id"]: it async for it in db.items.find(items_scope(user), {"_id": 0})}
''',
"exclude demo outfit rows",
)

# 3) Recognition must be allowed to say 'I don't know'. The old system prompt
# explicitly pushed the model to catalogue something anyway, which encouraged
# hats/cushions/fabric hallucinations from junk photos.
replace_once(
'''ANALYZE_SYSTEM = (
    "You are a fashion cataloguing assistant. These are REAL customer phone photos, "
    "NOT studio product shots — expect imperfect lighting, household or cluttered backgrounds, "
    "angled or folded items, items being worn, shadows and reflections. Identify the single main "
    "fashion item a human would obviously recognise and catalogue it anyway; do not refuse or "
    "default to a generic guess just because the background is messy. "
''',
'''ANALYZE_SYSTEM = (
    "You are a fashion cataloguing assistant. These are REAL customer phone photos, "
    "NOT studio product shots — expect imperfect lighting, household or cluttered backgrounds, "
    "angled or folded items, items being worn, shadows and reflections. Identify the single main "
    "fashion item only when one is genuinely visible. A messy background is not a reason to fail, "
    "but random light, reflections, furniture, cushions or unidentifiable fabric are NOT clothing. "
    "If there is no clear fashion item, return name 'Item not recognised', choose the closest category "
    "only as a placeholder, and set confidence to 30 or lower so the app can ask for a retake. "
''',
"honest recognition prompt",
)

replace_once(
'''    "needs_care (short string, e.g. 'needs steaming' or 'none'), "
    "estimated_value (integer estimate of resale/retail value in USD), "
    "description (one short sentence). Return ONLY the JSON object, no prose."
''',
'''    "needs_care (short string, e.g. 'needs steaming' or 'none'), "
    "description (one short sentence). Return ONLY the JSON object, no prose."
''',
"remove AI estimated monetary value",
)

# Tighten duplicate detection. Matching category alone plus one broad attribute
# was producing nonsense. Require an exact style match and at least two further
# matching descriptors before raising a duplicate candidate.
replace_once(
'''def find_similar_items(analysis: dict, items: List[dict], limit: int = 3) -> List[dict]:
    """Flag pieces in the wardrobe that look like the one just captured, so users
    don't unknowingly re-add something they already own. Category must match; colour,
    style, fabric and pattern add to a confidence score."""
    cat = _norm(analysis.get("category"))
    if not cat:
        return []
    colour, style = _norm(analysis.get("colour")), _norm(analysis.get("style"))
    fabric, pattern = _norm(analysis.get("fabric")), _norm(analysis.get("pattern"))
    scored = []
    for it in items:
        if _norm(it.get("category")) != cat:
            continue
        score = 0
        if colour and _norm(it.get("colour")) == colour:
            score += 2
        if style and _norm(it.get("style")) == style:
            score += 2
        if fabric and _norm(it.get("fabric")) == fabric:
            score += 1
        if pattern and _norm(it.get("pattern")) == pattern:
            score += 1
        if score >= 3:
            scored.append((score, it))
''',
'''def find_similar_items(analysis: dict, items: List[dict], limit: int = 3) -> List[dict]:
    """Return only high-confidence near-duplicates. Precision matters more than
    recall here: a false duplicate warning is worse than missing a weak match."""
    cat = _norm(analysis.get("category"))
    style = _norm(analysis.get("style"))
    confidence = int(analysis.get("confidence") or 0)
    if not cat or not style or confidence < 70:
        return []
    colour = _norm(analysis.get("colour"))
    fabric = _norm(analysis.get("fabric"))
    pattern = _norm(analysis.get("pattern"))
    scored = []
    for it in items:
        if _norm(it.get("category")) != cat:
            continue
        if _norm(it.get("style")) != style:
            continue
        descriptor_matches = 0
        if colour and _norm(it.get("colour")) == colour:
            descriptor_matches += 1
        if fabric and _norm(it.get("fabric")) == fabric:
            descriptor_matches += 1
        if pattern and _norm(it.get("pattern")) == pattern:
            descriptor_matches += 1
        if descriptor_matches >= 2:
            scored.append((descriptor_matches, it))
''',
"high-precision duplicate detection",
)

# 4) Remove money/cost-per-wear from general Insights.
replace_once(
'''    total_items = len(items)
    total_wears = sum(it.get("wear_count", 0) for it in items)
    priced = [it for it in items if it.get("price")]
    total_value = sum(it.get("price", 0) for it in priced)

    def cpw(it):
        wc = it.get("wear_count", 0)
        return (it["price"] / wc) if it.get("price") and wc > 0 else None

    avg_cpw_vals = [cpw(it) for it in items if cpw(it) is not None]
    avg_cpw = round(sum(avg_cpw_vals) / len(avg_cpw_vals), 2) if avg_cpw_vals else None

''',
'''    total_items = len(items)
    total_wears = sum(it.get("wear_count", 0) for it in items)

''',
"remove insight money calculations",
)
replace_once(
'''        "total_items": total_items,
        "total_wears": total_wears,
        "total_value": round(total_value, 2),
        "avg_cost_per_wear": avg_cpw,
        "outfits_logged": len(logs),
''',
'''        "total_items": total_items,
        "total_wears": total_wears,
        "outfits_logged": len(logs),
''',
"remove insight money response fields",
)

# 5) Wardrobe Health should be about actual wear history and rotation, not price.
replace_once(
'''    unworn = [it for it in items if (it.get("wear_count", 0) or 0) == 0]
    unworn_value = round(sum(it.get("price", 0) or 0 for it in unworn), 2)
    total_value = round(sum(it.get("price", 0) or 0 for it in items), 2)

    def cpw(it):
        wc = it.get("wear_count", 0) or 0
        return (it["price"] / wc) if it.get("price") and wc > 0 else None

    high_cpw = sorted(
        [it for it in items if cpw(it) is not None],
        key=lambda x: cpw(x), reverse=True,
    )[:3]
    high_cpw_desc = "; ".join(f"{it['name']} (${cpw(it):.2f}/wear)" for it in high_cpw) or "none yet"
    counts: dict = {}
''',
'''    unworn = [it for it in items if (it.get("wear_count", 0) or 0) == 0]
    low_wear = sorted(
        items,
        key=lambda it: ((it.get("wear_count", 0) or 0), it.get("last_worn") or ""),
    )[:8]
    low_wear_desc = "; ".join(
        f"{it.get('name')} ({it.get('category')}, worn {it.get('wear_count', 0) or 0}x)"
        for it in low_wear
    ) or "none yet"
    counts: dict = {}
''',
"health report wear-history stats",
)
replace_once(
'''    prompt = (
        f"Total pieces: {len(items)}. Total wardrobe value: ${total_value}.\n"
        f"Pieces not yet worn: {len(unworn)} worth ${unworn_value}.\n"
        f"Highest cost-per-wear items: {high_cpw_desc}.\n"
        f"Category breakdown: {breakdown}.\n\n"
        "Write the monthly wardrobe health report. Frame the numbers as underused pieces and "
        "opportunities to wear more, never as wasted money, and name the single purchase that "
        "would unlock the most outfits. Return JSON only."
    )
''',
'''    prompt = (
        f"Total pieces: {len(items)}.\n"
        f"Pieces not yet worn: {len(unworn)}.\n"
        f"Lowest-wear pieces: {low_wear_desc}.\n"
        f"Category breakdown: {breakdown}.\n\n"
        "Write the monthly wardrobe health report using wear history and category balance only. "
        "Focus on underused pieces and practical rotation opportunities. Do not mention purchase "
        "price, wardrobe value, money or cost-per-wear. Name the single purchase that would unlock "
        "the most outfits. Return JSON only."
    )
''',
"health report prompt without money",
)
replace_once(
'''    result["stats"] = {
        "total_items": len(items),
        "total_value": total_value,
        "unworn_count": len(unworn),
        "unworn_value": unworn_value,
    }
''',
'''    result["stats"] = {
        "total_items": len(items),
        "unworn_count": len(unworn),
    }
''',
"health report response without money",
)

path.write_text(text, encoding="utf-8")
print("backend launch patch completed successfully")
