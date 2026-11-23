"""Measured before/after for the AI wardrobe-pool optimisation (RSS based).

tracemalloc misses BSON decoding done in C, so this measures real process RSS:
one subprocess per variant, same documents, same work.

Variants:
  old / new    - the largest real wardrobe (a seeded account, small photos)
  old300/new300- 300 REAL item documents drawn from the database, which carry
                 the true photo sizes a grown wardrobe has (~45-50 KB/item)

Read-only: makes no writes.
"""
import asyncio
import json
import os
import resource
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

OLD = {"_id": 0, "orig_photo": 0}
NEW = {"_id": 0, "orig_photo": 0, "photo": 0, "thumb": 0, "worn_photo": 0}
HYDRATE = {"_id": 0, "id": 1, "photo": 1, "thumb": 1, "worn_photo": 1}

variant = sys.argv[1]
big = variant.endswith("300")
old_path = variant.startswith("old")


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    if big:
        scope, limit = {"photo": {"$ne": None}}, 300
    else:
        top = await db.items.aggregate([
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}}, {"$limit": 1},
        ]).to_list(1)
        scope, limit = {"user_id": top[0]["_id"]}, 2000

    base = rss_mb()
    if old_path:
        items = await db.items.find(scope, OLD).to_list(limit)
        payload = json.dumps(items[:6])
    else:
        items = await db.items.find(scope, NEW).to_list(limit)
        ids = [it["id"] for it in items[:6]]
        docs = await db.items.find({"id": {"$in": ids}}, HYDRATE).to_list(6)
        by_id = {d["id"]: d for d in docs}
        for it in items[:6]:
            it.update({k: v for k, v in by_id.get(it["id"], {}).items() if k != "id"})
        payload = json.dumps(items[:6])

    print(f"{variant.upper():7} pieces={len(items):4} baseline={base:6.1f} MB  "
          f"peak={rss_mb():6.1f} MB  wardrobe_cost={rss_mb() - base:6.1f} MB  "
          f"response={len(payload) / 1e6:.2f} MB")


asyncio.run(main())
