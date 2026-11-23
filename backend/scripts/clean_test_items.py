"""Remove leftover automated-test items from the preview database.

Earlier test runs left TEST_* pieces in the seeded wardrobes; they showed up as
"similar items" in Shop Check results. Read-only for everything else.
"""
import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

PATTERN = {"name": {"$regex": "^TEST_", "$options": "i"}}


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    docs = await db.items.find(PATTERN, {"_id": 0, "id": 1, "name": 1, "user_id": 1}).to_list(500)
    for d in docs:
        print(f"  {d['user_id']}  {d['id']}  {d['name'][:50]}")
    print(f"{len(docs)} leftover test items")
    if docs:
        res = await db.items.delete_many(PATTERN)
        print(f"deleted {res.deleted_count}")


asyncio.run(main())
