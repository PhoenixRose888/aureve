"""
Iteration 50 — bulk-add gate, membership/plan label, complimentary + reviewer regression.

Covers the four review items:
  (1) FREE_ITEM_CAP (100): 101st POST /items returns 402, no orphan docs created.
  (2) Premium + complimentary accounts can POST /items past 100.
  (3) /items without photo returns 400 "A photo is required to add an item."
  (4) premium_plan label on /auth/me and /membership/plans:
      - null for complimentary / free
      - "Annual" for 'aureve_annual_v1'
      - "Monthly" for 'aureve_monthly_v1'
      - "Premium" fallback for an unknown product id
  (5) Complimentary from iteration 49 still works end to end.
  (6) Reviewer user_testaura01 remains untouched.
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

# Prefer backend-env-style keys (what pytest shell actually has), fall back to
# frontend's EXPO_PUBLIC_BACKEND_URL if present.
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
BEARER_TESTAURA = os.environ.get("TEST_SESSION_TOKEN", "")

assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


# ---------- helpers ----------
def _tiny_jpeg_b64() -> str:
    # 1x1 pixel JPEG (base64) — valid enough for the backend's compress_b64 path.
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


# ---------- fixtures ----------
@pytest.fixture
def throwaway_account():
    """Register a brand-new email account, hand back (bearer, user_id). Teardown deletes via API."""
    email = f"qa+iter50_{uuid.uuid4().hex[:10]}@aureve.local"
    password = "secret123"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": password, "name": "QA Iter50"},
        timeout=30,
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    bearer = data["session_token"]
    user_id = data["user"]["user_id"]
    yield bearer, user_id, email
    # Best-effort cleanup
    try:
        requests.delete(f"{BASE_URL}/api/auth/account", headers=_bearer(bearer), timeout=15)
    except Exception:
        pass
    # Also wipe filler items in case delete API missed anything
    try:
        db.items.delete_many({"user_id": user_id})
    except Exception:
        pass


def _strip_premium(user_id: str):
    """Make the account fully FREE (no complimentary, no premium)."""
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


# ========== (1) Free-cap gate ==========
class TestFreeItemCap:
    def test_101st_item_returns_402_and_count_stays_100(self, throwaway_account):
        bearer, user_id, _email = throwaway_account
        _strip_premium(user_id)

        # Confirm it's actually free now
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(bearer), timeout=15).json()
        assert me["premium"] is False, me

        # Fast-path: bulk-insert 100 real-ish items directly into mongo scoped to this user's default profile.
        profs = requests.get(f"{BASE_URL}/api/profiles", headers=_bearer(bearer), timeout=15).json()
        profile_id = (profs[0] if isinstance(profs, list) and profs else {}).get("id")
        assert profile_id, f"no default profile: {profs}"

        docs = []
        for i in range(100):
            docs.append({
                "id": f"item_iter50_{user_id[-6:]}_{i}",
                "user_id": profile_id,  # items_scope uses profile_id as user_id
                "profile_id": profile_id,
                "name": f"TEST filler {i}",
                "category": "Tops",
                "photo": "", "worn_photo": "",
                "created_at": "2026-01-01T00:00:00+00:00",
                "wear_count": 0, "last_worn": None,
            })
        db.items.insert_many(docs)
        try:
            # /capture should still succeed (no cap on capture)
            cap = requests.post(
                f"{BASE_URL}/api/capture",
                headers=_bearer(bearer),
                json={"image": _tiny_jpeg_b64(), "clean": False},
                timeout=120,
            )
            assert cap.status_code == 200, f"/capture should not gate: {cap.status_code} {cap.text[:300]}"

            # 101st POST /api/items must fail with 402 + the FREE cap message
            for attempt in range(3):
                r = requests.post(
                    f"{BASE_URL}/api/items",
                    headers=_bearer(bearer),
                    json={"name": "TEST should not save",
                          "category": "Tops",
                          "photo": _tiny_jpeg_b64()},
                    timeout=30,
                )
                assert r.status_code == 402, f"attempt {attempt}: expected 402, got {r.status_code}: {r.text[:300]}"
                body = r.json()
                detail = body.get("detail") or ""
                assert "100 pieces" in detail or "wardrobes hold up to" in detail, body

            # Count must still be exactly 100 — no orphan writes
            r = requests.get(f"{BASE_URL}/api/items?summary=1", headers=_bearer(bearer), timeout=20)
            assert r.status_code == 200
            items = r.json()
            assert isinstance(items, list)
            assert len(items) == 100, f"expected 100 items after failed 402s, got {len(items)}"
        finally:
            db.items.delete_many({"user_id": profile_id})

    def test_premium_bypasses_cap(self, throwaway_account):
        bearer, user_id, _ = throwaway_account
        # Grant RevenueCat premium
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "premium_until": "2099-01-01T00:00:00+00:00",
                "premium_source": "revenuecat",
                "revenuecat_entitlement": "Aureve",
            },
             "$unset": {"complimentary_expires_at": "", "complimentary_started_at": "",
                        "complimentary_used": ""}},
        )
        profs = requests.get(f"{BASE_URL}/api/profiles", headers=_bearer(bearer), timeout=15).json()
        profile_id = profs[0]["id"]
        # Pre-seed 100 items
        docs = [{"id": f"item_iter50p_{user_id[-6:]}_{i}", "user_id": profile_id,
                 "profile_id": profile_id, "name": f"TEST p {i}", "category": "Tops",
                 "photo": "", "worn_photo": "",
                 "created_at": "2026-01-01T00:00:00+00:00",
                 "wear_count": 0, "last_worn": None} for i in range(100)]
        db.items.insert_many(docs)
        try:
            r = requests.post(f"{BASE_URL}/api/items", headers=_bearer(bearer),
                              json={"name": "TEST premium 101st", "category": "Tops",
                                    "photo": _tiny_jpeg_b64()}, timeout=30)
            assert r.status_code == 200, f"premium should bypass cap: {r.status_code} {r.text[:300]}"
            created_id = r.json().get("id")
            assert created_id
            # Count must be 101
            items = requests.get(f"{BASE_URL}/api/items?summary=1",
                                 headers=_bearer(bearer), timeout=20).json()
            assert len(items) == 101
        finally:
            db.items.delete_many({"user_id": profile_id})

    def test_complimentary_bypasses_cap(self, throwaway_account):
        # A fresh account is already complimentary premium for 7 days, so it should
        # be able to save past 100 items without becoming non-premium.
        bearer, user_id, _ = throwaway_account
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(bearer), timeout=15).json()
        assert me["complimentary_active"] is True
        profs = requests.get(f"{BASE_URL}/api/profiles", headers=_bearer(bearer), timeout=15).json()
        profile_id = profs[0]["id"]
        docs = [{"id": f"item_iter50c_{user_id[-6:]}_{i}", "user_id": profile_id,
                 "profile_id": profile_id, "name": f"TEST c {i}", "category": "Tops",
                 "photo": "", "worn_photo": "",
                 "created_at": "2026-01-01T00:00:00+00:00",
                 "wear_count": 0, "last_worn": None} for i in range(100)]
        db.items.insert_many(docs)
        try:
            r = requests.post(f"{BASE_URL}/api/items", headers=_bearer(bearer),
                              json={"name": "TEST comp 101st", "category": "Tops",
                                    "photo": _tiny_jpeg_b64()}, timeout=30)
            assert r.status_code == 200, f"complimentary should bypass cap: {r.status_code} {r.text[:300]}"
        finally:
            db.items.delete_many({"user_id": profile_id})


# ========== (2) Photo required ==========
class TestItemsPhotoRequired:
    def test_no_photo_returns_400(self):
        r = requests.post(
            f"{BASE_URL}/api/items",
            headers=_bearer(BEARER_TESTAURA),
            json={"name": "TEST no photo", "category": "Tops"},
            timeout=15,
        )
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        detail = (r.json().get("detail") or "")
        assert "photo is required" in detail.lower(), detail


# ========== (3) premium_plan label ==========
class TestPremiumPlanLabel:
    @pytest.mark.parametrize("product,label", [
        ("aureve_annual_v1", "Annual"),
        ("aureve_monthly_v1", "Monthly"),
        ("aureve_lifetime_v1", "Premium"),  # unknown → generic (no "mo"/"month"/"annual"/"year"/"yr"/"1m"/"12m" substring)
    ])
    def test_revenuecat_product_maps_to_label(self, throwaway_account, product, label):
        bearer, user_id, _ = throwaway_account
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "premium_until": "2099-01-01T00:00:00+00:00",
                "premium_source": "revenuecat",
                "revenuecat_product": product,
            }},
        )
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(bearer), timeout=15).json()
        assert me.get("premium_plan") == label, me
        plans = requests.get(f"{BASE_URL}/api/membership/plans", headers=_bearer(bearer), timeout=15).json()
        assert plans.get("premium_plan") == label, plans

    def test_complimentary_premium_plan_is_null(self, throwaway_account):
        bearer, _user_id, _ = throwaway_account
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(bearer), timeout=15).json()
        # Fresh account → complimentary
        assert me["premium"] is True
        assert me["complimentary_active"] is True
        assert me.get("premium_plan") is None, me

    def test_free_premium_plan_is_null(self, throwaway_account):
        bearer, user_id, _ = throwaway_account
        _strip_premium(user_id)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(bearer), timeout=15).json()
        assert me["premium"] is False
        assert me.get("premium_plan") is None, me


# ========== (4) Complimentary from iteration 49 still intact ==========
class TestComplimentaryRegression:
    def test_fresh_register_grants_7_days(self, throwaway_account):
        bearer, _user_id, _ = throwaway_account
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(bearer), timeout=15).json()
        assert me["premium"] is True
        assert me["premium_source"] == "complimentary"
        assert me["complimentary_active"] is True
        # Should be 7 days (part-days round up, could read 7)
        assert 6 <= me["complimentary_days_left"] <= 7

    def test_re_login_does_not_restart(self):
        # New account, re-login, ensure expires_at unchanged.
        email = f"qa+iter50reg_{uuid.uuid4().hex[:8]}@aureve.local"
        password = "secret123"
        r1 = requests.post(f"{BASE_URL}/api/auth/register",
                           json={"email": email, "password": password}, timeout=30)
        assert r1.status_code == 200, r1.text
        b1 = r1.json()["session_token"]
        me1 = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(b1), timeout=15).json()
        first_exp = me1["complimentary_expires_at"]
        time.sleep(1.5)
        r2 = requests.post(f"{BASE_URL}/api/auth/login",
                           json={"email": email, "password": password}, timeout=30)
        assert r2.status_code == 200, r2.text
        b2 = r2.json()["session_token"]
        me2 = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(b2), timeout=15).json()
        assert me2["complimentary_expires_at"] == first_exp, (first_exp, me2["complimentary_expires_at"])
        # cleanup
        requests.delete(f"{BASE_URL}/api/auth/account", headers=_bearer(b2), timeout=15)


# ========== (5) Reviewer untouched ==========
class TestReviewerUntouched:
    def test_user_testaura01_still_premium(self):
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_bearer(BEARER_TESTAURA), timeout=15).json()
        assert me["user_id"] == "user_testaura01"
        assert me["premium"] is True
        assert me["premium_until"].startswith("2099-01-01")
        assert me["premium_source"] == "revenuecat"
