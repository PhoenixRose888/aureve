from pathlib import Path
import re

path = Path(__file__).with_name("server.py")
text = path.read_text(encoding="utf-8")


def sub_once(pattern: str, replacement: str, label: str, flags: int = 0) -> None:
    global text
    text, n = re.subn(pattern, lambda _m: replacement, text, count=1, flags=flags)
    if n != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {n}; refusing unsafe patch")
    print(f"patched: {label}")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {n}; refusing unsafe patch")
    text = text.replace(old, new, 1)
    print(f"patched: {label}")


# 1) Reviewer/demo isolation.
sub_once(
    r'''    account_premium = is_premium\(account\)\n    return \{\n        "user_id": prof\["id"\],       # data scope = profile id\n        "account_id": account_id,\n        "profile_id": prof\["id"\],\n        "profile_name": prof\.get\("name"\),\n        "profile": prof\.get\("profile"\) or \{\},\n        "is_primary": is_primary,\n        "account_premium": account_premium,\n        "premium": account_premium and is_primary,\n        # Sample/practice pieces belong to Guest mode and the Apple review\n        # account only — never to a real signed-in wardrobe\.\n        "show_demo": bool\(account\.get\("is_guest"\)\) or _norm_email\(account\.get\("email"\) or ""\) == REVIEWER_EMAIL,\n    \}\n''',
    '''    account_premium = is_premium(account)

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
    '''        # Seed samples only while the reviewer wardrobe is genuinely empty.
        # Once real uploads exist, remove old demo rows instead of resurrecting
        # them on every restart/deploy.
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

# 2) Demo outfit rows must not leak into a signed-in real wardrobe.
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

# 3) Recognition may admit uncertainty.
replace_once(
    '''    "angled or folded items, items being worn, shadows and reflections. Identify the single main "
    "fashion item a human would obviously recognise and catalogue it anyway; do not refuse or "
    "default to a generic guess just because the background is messy. "
''',
    '''    "angled or folded items, items being worn, shadows and reflections. Identify the single main "
    "fashion item only when one is genuinely visible. A messy background is not a reason to fail, "
    "but random light, reflections, furniture, cushions or unidentifiable fabric are NOT clothing. "
    "If there is no clear fashion item, return name 'Item not recognised', choose the closest category "
    "only as a placeholder, and set confidence to 30 or lower so the app can ask for a retake. "
''',
    "honest recognition prompt",
)
replace_once(
    '    "estimated_value (integer estimate of resale/retail value in USD), "\n',
    '',
    "remove AI estimated monetary value",
)

sub_once(
    r'''def find_similar_items\(analysis: dict, items: List\[dict\], limit: int = 3\) -> List\[dict\]:\n.*?\n\n\n@api_router\.post\("/capture"\)''',
    '''def find_similar_items(analysis: dict, items: List[dict], limit: int = 3) -> List[dict]:
    """Return only high-confidence near-duplicates. Precision matters more than recall."""
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
        if _norm(it.get("category")) != cat or _norm(it.get("style")) != style:
            continue
        matches = sum([
            bool(colour and _norm(it.get("colour")) == colour),
            bool(fabric and _norm(it.get("fabric")) == fabric),
            bool(pattern and _norm(it.get("pattern")) == pattern),
        ])
        if matches >= 2:
            scored.append((matches, it))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "id": it["id"],
            "name": it.get("name", ""),
            "category": it.get("category", ""),
            "colour": it.get("colour", ""),
            "photo": it.get("photo"),
        }
        for _, it in scored[:limit]
    ]


@api_router.post("/capture")''',
    "high-precision duplicate detection",
    re.DOTALL,
)

# 4) General insights: no money/cost-per-wear.
sub_once(
    r'''    total_items = len\(items\)\n    total_wears = sum\(it\.get\("wear_count", 0\) for it in items\)\n.*?\n    most_worn =''',
    '''    total_items = len(items)
    total_wears = sum(it.get("wear_count", 0) for it in items)

    most_worn =''',
    "remove insight money calculations",
    re.DOTALL,
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

# 5) Wardrobe Health uses wear history/category balance only.
sub_once(
    r'''@api_router\.post\("/insights/health-report"\)\nasync def health_report\(user: dict = Depends\(get_scope\)\):\n.*?\n    return result\n''',
    r'''@api_router.post("/insights/health-report")
async def health_report(user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "health")
    items = await db.items.find(items_scope(user), {"_id": 0}).to_list(2000)
    if len(items) < 3:
        raise HTTPException(status_code=400, detail="Add a few more pieces to generate your report")

    unworn = [it for it in items if (it.get("wear_count", 0) or 0) == 0]
    low_wear = sorted(
        items,
        key=lambda it: ((it.get("wear_count", 0) or 0), it.get("last_worn") or ""),
    )[:8]
    low_wear_desc = "; ".join(
        f"{it.get('name')} ({it.get('category')}, worn {it.get('wear_count', 0) or 0}x)"
        for it in low_wear
    ) or "none yet"
    counts: dict = {}
    for it in items:
        counts[it.get("category", "Other")] = counts.get(it.get("category", "Other"), 0) + 1
    breakdown = ", ".join(f"{k}:{v}" for k, v in counts.items())

    prompt = (
        f"Total pieces: {len(items)}.\n"
        f"Pieces not yet worn: {len(unworn)}.\n"
        f"Lowest-wear pieces: {low_wear_desc}.\n"
        f"Category breakdown: {breakdown}.\n\n"
        "Write the monthly wardrobe health report using wear history and category balance only. "
        "Focus on underused pieces and practical rotation opportunities. Do not mention purchase "
        "price, wardrobe value, money or cost-per-wear. Name the single purchase that would unlock "
        "the most outfits. Return JSON only."
    )
    chat = await ai_chat(f"health-{user['user_id']}-{uuid.uuid4().hex[:6]}", HEALTH_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("health-report failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result:
        raise HTTPException(status_code=502, detail="Could not generate your report")
    result["stats"] = {
        "total_items": len(items),
        "unworn_count": len(unworn),
    }
    return result
''',
    "health report uses wear history only",
    re.DOTALL,
)

path.write_text(text, encoding="utf-8")
print("backend launch patch completed successfully")
