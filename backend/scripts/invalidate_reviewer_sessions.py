"""Invalidate the store-reviewer account's active login sessions.

Session tokens live for 7 days and a password change does not expire them, so a
rotation must clear them explicitly. Narrowly scoped: deletes session rows for
the reviewer account only — no user data, no other account, nothing dropped.

In production the same thing happens automatically on the deploy that rotates
the password (see seed_reviewer_account in server.py); this script is for the
preview database, where no deploy takes place.
"""
import asyncio
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

EMAIL = os.environ.get("REVIEWER_EMAIL", "review@aureve.app").strip().lower()


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await db.users.find_one({"email": EMAIL}, {"_id": 0, "user_id": 1})
    if not user:
        print(f"No account for {EMAIL} in this database.")
        return
    uid = user["user_id"]
    before = await db.user_sessions.count_documents({"user_id": uid})
    res = await db.user_sessions.delete_many({"user_id": uid})
    after = await db.user_sessions.count_documents({"user_id": uid})
    print(f"{EMAIL} ({uid}): sessions before={before} deleted={res.deleted_count} remaining={after}")


asyncio.run(main())
