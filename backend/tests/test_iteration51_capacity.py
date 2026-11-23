"""
Iteration 51 — GET /api/items/capacity + server-side cap re-regression.

Scope (NEW this iteration):
  • GET /api/items/capacity:
      - Non-premium, 97 items  → {count:97, cap:100, remaining:3, full:false, premium:false}
      - Non-premium, 100 items → {count:100, cap:100, remaining:0, full:true,  premium:false}
      - Revenuecat premium     → {cap:null, remaining:null, full:false, premium:true}
      - Complimentary active   → cap:null, remaining:null, full:false, premium:true
      - Not shadowed by GET /api/items/{item_id} (string 'capacity' must not be
        treated as an item id)
  • POST /api/items still 402s at exactly 100 items (count stays 100).
  • Deleting an item from a full non-premium wardrobe:
      - capacity flips to full:false, remaining:1
      - a subsequent POST /api/items succeeds (count=100 again)
  • Premium + complimentary accounts can exceed 100 on POST /api/items.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient


# ---------- env ----------
def _load_env_file(path):
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_load_env_file("/app/frontend/.env")
_load_env_file("/app/backend/.env")

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or ""
).rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"
mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


# ---------- helpers ----------
def _tiny_jpeg_b64() -> str:
    return (
        "/9j/4AAQSkZJRgABAQEAAAAAAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
        "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
        "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA"
        "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
        "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
        "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
        "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA"
        "AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx"
        "BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK"
        "U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3"
        "uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iii"
        "gD//2Q=="
    )


def _bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _strip_premium(user_id: str):
    db.users.update_one(
        {"user_id": user_id},
        {"$unset": {
            "premium_until": "",
            "premium_source": "",
            "complimentary_started_at": "",
            "complimentary_expires_at": "",
            "complimentary_used": "",
            "trial_used": "",
        }},
    )


def _seed_fillers(profile_id: str, count: int, tag: str):
    docs = []
    for i in range(count):
        docs.append({
            "id": f"item_i51_{tag}_{i}",
            "user_id": profile_id,
            "profile_id": profile_id,
            "name": f"TEST filler {i}",
            "category": "Tops",
            "photo": "",
            "worn_photo": "",
            "created_at": "2026-01-01T00:00:00+00:00",
            "wear_count": 0,
            "last_worn": None,
        })
    if docs:
        db.items.insert_many(docs)


# ---------- fixtures ----------
@pytest.fixture
def throwaway_account():
    email = f"qa+iter51_{uuid.uuid4().hex[:10]}@aureve.local"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "secret123", "name": "QA Iter51"},
        timeout=30,
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    bearer = data["session_token"]
    user_id = data["user"]["user_id"]
    profs = requests.get(f"{BASE_URL}/api/profiles", headers=_bearer(bearer), timeout=15).json()
    profile_id = profs[0]["id"]
    yield bearer, user_id, profile_id, email
    try:
        requests.delete(f"{BASE_URL}/api/auth/account", headers=_bearer(bearer), timeout=15)
    except Exception:
        pass
    try:
        db.items.delete_many({"user_id": profile_id})
    except Exception:
        pass


# ========== (A) capacity endpoint ==========
class TestCapacityEndpoint:
    def test_free_97_items_returns_remaining_3(self, throwaway_account):
        bearer, user_id, profile_id, _ = throwaway_account
        _strip_premium(user_id)
        _seed_fillers(profile_id, 97, f"free97_{user_id[-6:]}")
        try:
            r = requests.get(f"{BASE_URL}/api/items/capacity", headers=_bearer(bearer), timeout=15)
            assert r.status_code == 200, r.text
            cap = r.json()
            assert cap == {"count": 97, "cap": 100, "remaining": 3, "full": False, "premium": False}, cap
        finally:
            db.items.delete_many({"user_id": profile_id})

    def test_free_exactly_100_returns_full_true(self, throwaway_account):
        bearer, user_id, profile_id, _ = throwaway_account
        _strip_premium(user_id)
        _seed_fillers(profile_id, 100, f"free100_{user_id[-6:]}")
        try:
            r = requests.get(f"{BASE_URL}/api/items/capacity", headers=_bearer(bearer), timeout=15)
            assert r.status_code == 200
            cap = r.json()
            assert cap == {"count": 100, "cap": 100, "remaining": 0, "full": True, "premium": False}, cap
        finally:
            db.items.delete_many({"user_id": profile_id})

    def test_revenuecat_premium_capacity_is_null(self, throwaway_account):
        bearer, user_id, profile_id, _ = throwaway_account
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {"premium_until": "2099-01-01T00:00:00+00:00",
                      "premium_source": "revenuecat",
                      "revenuecat_entitlement": "Aureve"}},
        )
        _seed_fillers(profile_id, 100, f"rcprem_{user_id[-6:]}")
        try:
            r = requests.get(f"{BASE_URL}/api/items/capacity", headers=_bearer(bearer), timeout=15)
            assert r.status_code == 200
            cap = r.json()
            assert cap["premium"] is True
            assert cap["cap"] is None
            assert cap["remaining"] is None
            assert cap["full"] is False
            assert cap["count"] == 100
        finally:
            db.items.delete_many({"user_id": profile_id})

    def test_complimentary_active_capacity_is_null(self, throwaway_account):
        bearer, user_id, profile_id, _ = throwaway_account
        # /auth/register already set complimentary; just make sure it's active
        future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {"premium_until": future,
                      "premium_source": "complimentary",
                      "complimentary_expires_at": future,
                      "complimentary_used": True,
                      "trial_used": True}},
        )
        _seed_fillers(profile_id, 100, f"comp_{user_id[-6:]}")
        try:
            r = requests.get(f"{BASE_URL}/api/items/capacity", headers=_bearer(bearer), timeout=15)
            assert r.status_code == 200
            cap = r.json()
            assert cap["premium"] is True, cap
            assert cap["cap"] is None, cap
            assert cap["remaining"] is None, cap
            assert cap["full"] is False, cap
            assert cap["count"] == 100
        finally:
            db.items.delete_many({"user_id": profile_id})

    def test_capacity_not_shadowed_by_item_lookup(self, throwaway_account):
        """GET /api/items/capacity must be matched BEFORE GET /api/items/{item_id}
        — otherwise 'capacity' would be treated as an item id and return 404."""
        bearer, _user_id, _profile_id, _ = throwaway_account
        r = requests.get(f"{BASE_URL}/api/items/capacity", headers=_bearer(bearer), timeout=15)
        assert r.status_code == 200, (
            f"/items/capacity returned {r.status_code} — likely shadowed by /items/{{item_id}}: {r.text[:300]}"
        )
        # Expected keys exist (not an item document)
        body = r.json()
        for k in ("count", "cap", "remaining", "full", "premium"):
            assert k in body, body


# ========== (B) delete flips capacity + lets POST succeed again ==========
class TestDeleteFreesSlot:
    def test_delete_from_full_wardrobe_lets_create_succeed(self, throwaway_account):
        bearer, user_id, profile_id, _ = throwaway_account
        _strip_premium(user_id)
        _seed_fillers(profile_id, 100, f"flip_{user_id[-6:]}")
        try:
            # Full first
            r = requests.get(f"{BASE_URL}/api/items/capacity", headers=_bearer(bearer), timeout=15)
            assert r.json()["full"] is True

            # Grab a real item id to delete via the API
            r = requests.get(f"{BASE_URL}/api/items?summary=1", headers=_bearer(bearer), timeout=20)
            items = r.json()
            assert len(items) == 100
            victim = items[0]["id"]

            dr = requests.delete(f"{BASE_URL}/api/items/{victim}", headers=_bearer(bearer), timeout=15)
            assert dr.status_code == 200, f"delete failed: {dr.status_code} {dr.text}"

            # Capacity flips to remaining:1, full:false
            cap = requests.get(f"{BASE_URL}/api/items/capacity", headers=_bearer(bearer), timeout=15).json()
            assert cap["count"] == 99, cap
            assert cap["remaining"] == 1, cap
            assert cap["full"] is False, cap

            # Create succeeds — count back to 100
            created = requests.post(
                f"{BASE_URL}/api/items",
                headers=_bearer(bearer),
                json={"name": "TEST slot filler", "category": "Tops", "photo": _tiny_jpeg_b64()},
                timeout=30,
            )
            assert created.status_code == 200, f"POST should succeed after delete: {created.status_code} {created.text[:400]}"
            new_item_id = created.json().get("id")
            assert new_item_id

            cap2 = requests.get(f"{BASE_URL}/api/items/capacity", headers=_bearer(bearer), timeout=15).json()
            assert cap2["count"] == 100, cap2
            assert cap2["full"] is True, cap2
            assert cap2["remaining"] == 0, cap2

            # And another POST 402s again
            over = requests.post(
                f"{BASE_URL}/api/items",
                headers=_bearer(bearer),
                json={"name": "TEST should 402", "category": "Tops", "photo": _tiny_jpeg_b64()},
                timeout=30,
            )
            assert over.status_code == 402, f"expected 402 after refilling, got {over.status_code}: {over.text[:300]}"
        finally:
            db.items.delete_many({"user_id": profile_id})


# ========== (C) Server-side cap still blocks even if UI hid button ==========
class TestServerSideCapIntact:
    def test_post_items_402_at_100_three_times_no_orphans(self, throwaway_account):
        bearer, user_id, profile_id, _ = throwaway_account
        _strip_premium(user_id)
        _seed_fillers(profile_id, 100, f"gate_{user_id[-6:]}")
        try:
            for attempt in range(3):
                r = requests.post(
                    f"{BASE_URL}/api/items",
                    headers=_bearer(bearer),
                    json={"name": "TEST should not save", "category": "Tops", "photo": _tiny_jpeg_b64()},
                    timeout=30,
                )
                assert r.status_code == 402, f"attempt {attempt}: {r.status_code} {r.text[:300]}"
                detail = (r.json() or {}).get("detail") or ""
                assert "100 pieces" in detail, detail

            # Still exactly 100
            items = requests.get(f"{BASE_URL}/api/items?summary=1", headers=_bearer(bearer), timeout=20).json()
            assert len(items) == 100
        finally:
            db.items.delete_many({"user_id": profile_id})

    def test_revenuecat_premium_can_exceed_100(self, throwaway_account):
        bearer, user_id, profile_id, _ = throwaway_account
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {"premium_until": "2099-01-01T00:00:00+00:00",
                      "premium_source": "revenuecat",
                      "revenuecat_entitlement": "Aureve"}},
        )
        _seed_fillers(profile_id, 100, f"over_{user_id[-6:]}")
        try:
            r = requests.post(
                f"{BASE_URL}/api/items",
                headers=_bearer(bearer),
                json={"name": "TEST 101st premium", "category": "Tops", "photo": _tiny_jpeg_b64()},
                timeout=30,
            )
            assert r.status_code == 200, f"premium 101st should succeed: {r.status_code} {r.text[:400]}"
            items = requests.get(f"{BASE_URL}/api/items?summary=1", headers=_bearer(bearer), timeout=20).json()
            assert len(items) == 101, len(items)
        finally:
            db.items.delete_many({"user_id": profile_id})

    def test_complimentary_can_exceed_100(self, throwaway_account):
        bearer, user_id, profile_id, _ = throwaway_account
        future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {"premium_until": future,
                      "premium_source": "complimentary",
                      "complimentary_expires_at": future,
                      "complimentary_used": True,
                      "trial_used": True}},
        )
        _seed_fillers(profile_id, 100, f"compover_{user_id[-6:]}")
        try:
            r = requests.post(
                f"{BASE_URL}/api/items",
                headers=_bearer(bearer),
                json={"name": "TEST 101st complimentary", "category": "Tops", "photo": _tiny_jpeg_b64()},
                timeout=30,
            )
            assert r.status_code == 200, f"complimentary 101st should succeed: {r.status_code} {r.text[:400]}"
            items = requests.get(f"{BASE_URL}/api/items?summary=1", headers=_bearer(bearer), timeout=20).json()
            assert len(items) == 101
        finally:
            db.items.delete_many({"user_id": profile_id})


# ========== (D) Reviewer / testaura regression — must stay untouched ==========
class TestReviewerUntouched:
    def test_reviewer_still_premium_and_capacity_shows_null(self):
        bearer = os.environ.get("TEST_SESSION_TOKEN", "")
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(bearer), timeout=15)
        assert me.status_code == 200, me.text
        body = me.json()
        assert body.get("premium") is True, body
        cap = requests.get(f"{BASE_URL}/api/items/capacity", headers=_bearer(bearer), timeout=15).json()
        assert cap["premium"] is True
        assert cap["cap"] is None
        assert cap["remaining"] is None
        assert cap["full"] is False
