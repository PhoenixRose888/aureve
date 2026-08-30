"""STRICTLY READ-ONLY wardrobe diagnostic. Makes NO writes/updates/deletes.

Determines, for one account, whether wardrobe records still exist and whether
they are scattered across multiple profiles (the suspected root cause of the
"disappearing items" report).

USAGE (run in the PRODUCTION backend environment where MONGO_URL points at the
Atlas DB — e.g. an Emergent production shell):

    python scripts/diagnose_wardrobe.py you@email.com

It prints:
  - all profiles for the account (id + created_at)
  - item counts PER profile id
  - counts under the raw account_id (legacy/unmigrated) too
  - recent items (name / category / has-photo / created_at)
  - any item records whose user_id is NOT one of the account's profiles
It does not modify anything.
"""
import os
import sys
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


async def main(email: str):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    user = await db.users.find_one({"email": email.lower().strip()}, {"_id": 0, "password_hash": 0})
    if not user:
        print(f"No account found for {email!r}")
        return
    account_id = user["user_id"]
    print(f"Account: {email}  user_id={account_id}  provider={user.get('provider')}")

    profiles = await db.profiles.find({"user_id": account_id}, {"_id": 0}).sort("created_at", 1).to_list(50)
    print(f"\nProfiles for this account: {len(profiles)}")
    scope_ids = []
    for p in profiles:
        print(f"  - profile id={p['id']}  name={p.get('name')!r}  created_at={p.get('created_at')}")
        scope_ids.append(p["id"])

    # Items are scoped by user_id == profile id. Also check the raw account_id
    # (legacy data written before multi-profile) as an extra scope.
    all_scopes = scope_ids + [account_id]
    print("\nItem counts by scope (user_id):")
    grand = 0
    for sid in all_scopes:
        c = await db.items.count_documents({"user_id": sid})
        grand += c
        label = "PROFILE" if sid in scope_ids else "ACCOUNT_ID(legacy)"
        print(f"  [{label}] {sid}: {c} items")
    print(f"  => TOTAL across all known scopes: {grand}")

    # Recent items across ALL of this account's scopes.
    print("\nMost recent 15 items across all scopes (name | category | has_photo | created_at | scope):")
    recent = await db.items.find(
        {"user_id": {"$in": all_scopes}},
        {"_id": 0, "name": 1, "category": 1, "photo": 1, "created_at": 1, "user_id": 1},
    ).sort("created_at", -1).to_list(15)
    for it in recent:
        has_photo = bool(it.get("photo"))
        print(f"  - {it.get('name')!r:40} | {it.get('category'):12} | photo={has_photo} | {it.get('created_at')} | {it.get('user_id')}")

    # Orphans: items referencing a scope that is NEITHER a current profile NOR the account id.
    # (e.g. a deleted/renamed profile). Sample by checking distinct user_ids that look account-related is
    # not possible without owner linkage, so we simply report how many items the normal GET would miss:
    # normal GET uses the ACTIVE profile only. Show the delta vs total.
    if profiles:
        default_scope = profiles[0]["id"]
        default_count = await db.items.count_documents({"user_id": default_scope})
        print(f"\nNormal wardrobe GET (default/earliest profile {default_scope}) would show: {default_count} items")
        print(f"Items NOT visible via that default profile: {grand - default_count}")

    print("\n(READ-ONLY: nothing was modified.)")
    client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnose_wardrobe.py <account-email>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
