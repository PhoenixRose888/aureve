from pathlib import Path

root = Path(__file__).resolve().parents[1]
backend = root / "backend" / "server.py"


def replace_once(old: str, new: str, label: str):
    text = backend.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}")
    backend.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {label}")

# Reviewer sees seeded demo only while that active reviewer wardrobe contains no real pieces.
replace_once(
'''    is_primary = bool(primary) and primary[0]["id"] == prof["id"]
    account_premium = is_premium(account)
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
'''    is_primary = bool(primary) and primary[0]["id"] == prof["id"]
    account_premium = is_premium(account)

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
"dynamic reviewer demo visibility")

replace_once(
'''        # Ensure representative content: a default profile with a clean demo
        # wardrobe, reconciled deterministically (see below) so repeated
        # startups/redeploys can never create duplicates.
        prof = await ensure_default_profile(user_id, "Reviewer")
        await reconcile_reviewer_wardrobe(prof["id"])
        logger.info(f"Reviewer account ready: {email}")
''',
'''        # Keep seeded samples only while the reviewer wardrobe is genuinely empty.
        # Once real uploads exist, remove old demo rows instead of resurrecting them
        # on every restart/deploy.
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
            await db.plans.delete_many({"user_id": prof["id"], "demo": True})
            logger.info("Reviewer has %s real pieces; removed %s seeded demo pieces", real_item_count, removed.deleted_count)
        logger.info(f"Reviewer account ready: {email}")
''',
"stop reviewer demo reseeding after real uploads")

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
"exclude demo outfit rows")

replace_once(
'''    plans = await db.plans.find(query, {"_id": 0}).sort("date", 1).to_list(500)
''',
'''    if not user.get("show_demo"):
        query["demo"] = {"$ne": True}
    plans = await db.plans.find(query, {"_id": 0}).sort("date", 1).to_list(500)
''',
"exclude demo plans")

replace_once(
'''@api_router.get("/wear")
async def list_wear(user: dict = Depends(get_scope)):
    logs = await db.wear_logs.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
''',
'''@api_router.get("/wear")
async def list_wear(user: dict = Depends(get_scope)):
    wear_query = {"user_id": user["user_id"]}
    if not user.get("show_demo"):
        wear_query["demo"] = {"$ne": True}
    logs = await db.wear_logs.find(wear_query, {"_id": 0}).sort("created_at", -1).to_list(500)
''',
"exclude demo wear logs")

# Remove unreliable money/value outputs from general insights.
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

    most_worn =
''',
'''    total_items = len(items)
    total_wears = sum(it.get("wear_count", 0) for it in items)

    most_worn =
''',
"remove insight money calculations")

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
"remove insight money response fields")

print("P1 recovery patch applied")
