"""Restore the PREVIEW reviewer account's password hash.

While sanitising the source the seeding fallback was momentarily an empty
string, and the auto-reloading preview server re-seeded the reviewer account
with a hash of "" before the skip-guard was added. This restores it to the
documented preview test password so the account is not left passwordless.

Preview database only — production is a separate Atlas cluster and was never
touched (no deploy has happened since 14 November).
"""
import asyncio
import os
import sys

import bcrypt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

EMAIL = "review@aureve.app"


async def main():
    password = os.environ.get("RESTORE_REVIEWER_PASSWORD", "")
    if not password:
        print("Set RESTORE_REVIEWER_PASSWORD to run this.")
        sys.exit(1)

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    user = await db.users.find_one({"email": EMAIL}, {"_id": 0, "user_id": 1})
    if not user:
        print("No reviewer account in this database.")
        sys.exit(1)

    # Confirm the account really is passwordless before overwriting anything.
    before = await db.users.find_one({"email": EMAIL}, {"_id": 0, "password_hash": 1})
    blank = bcrypt.checkpw(b"", (before.get("password_hash") or "").encode())
    print(f"account {user['user_id']} currently accepts an empty password: {blank}")

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    await db.users.update_one({"email": EMAIL}, {"$set": {"password_hash": pw_hash}})
    after = await db.users.find_one({"email": EMAIL}, {"_id": 0, "password_hash": 1})
    print("empty password now accepted:", bcrypt.checkpw(b"", after["password_hash"].encode()))
    print("new password verifies:", bcrypt.checkpw(password.encode(), after["password_hash"].encode()))


asyncio.run(main())
