"""One-off: re-seed the automated-testing account `user_testaura01` with a
realistic sample wardrobe so end-to-end Dress Me can generate meaningful outfits.

Run:  cd /app/backend && python scripts/reseed_testaura.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import db, ensure_default_profile, new_id, now_utc  # noqa: E402
from demo_wardrobe import DEMO_ITEMS  # noqa: E402

ACCOUNT_ID = "user_testaura01"


async def main():
    # Ensure the user record exists.
    await db.users.update_one(
        {"user_id": ACCOUNT_ID},
        {"$setOnInsert": {
            "user_id": ACCOUNT_ID,
            "email": "testaura01@aureve.local",
            "name": "Aura Test",
            "created_at": now_utc().isoformat(),
        }},
        upsert=True,
    )

    prof = await ensure_default_profile(ACCOUNT_ID, "Aura Test")
    profile_id = prof["id"]

    # Clean re-seed: remove any previously seeded sample items for this profile.
    removed = await db.items.delete_many({"user_id": profile_id})

    now = now_utc().isoformat()
    docs = []
    for g in DEMO_ITEMS:
        docs.append({
            "id": new_id("item"),
            "user_id": profile_id,
            "name": g["name"],
            "category": g["category"],
            "colour": g.get("colour", ""),
            "fabric": g.get("fabric", ""),
            "season": g.get("season", "All"),
            "pattern": "",
            "style": g.get("style", ""),
            "sleeve_length": "",
            "formality": g.get("formality", ""),
            "tone": g.get("tone", ""),
            "fit_notes": "",
            "brand": "",
            "size": "",
            "price": None,
            "condition": "",
            "availability": "Ready",
            "photo": g["photo"],
            "worn_photo": None,
            "flatters": g.get("flatters", True),
            "wear_count": 0,
            "last_worn": None,
            "created_at": now,
            "demo": False,
        })
    if docs:
        await db.items.insert_many(docs)

    print(f"Profile {profile_id}: removed {removed.deleted_count}, seeded {len(docs)} items")
    counts = {}
    for d in docs:
        counts[d["category"]] = counts.get(d["category"], 0) + 1
    print("By category:", counts)


if __name__ == "__main__":
    asyncio.run(main())
