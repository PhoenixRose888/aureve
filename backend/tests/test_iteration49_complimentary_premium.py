"""Iteration 49 — Complimentary 7-day Premium on brand-new account.

Covers:
  * grant_welcome_premium on /auth/register (email) — only testable path end-to-end.
  * /auth/me returns the full complimentary_* snapshot immediately.
  * NO RESTART across new sessions and simulated reinstalls.
  * ONCE-ONLY: expiring the trial manually does NOT re-grant.
  * EXPIRY → FREE: data preserved, premium gates return 402.
  * FULL ACCESS DURING PERIOD: Premium-gated endpoints are not 402.
  * PURCHASE DURING PERIOD TAKES PRECEDENCE via /membership/entitlement.
  * EXISTING PAID SUBSCRIBER untouched (review@aureve.app).
  * EXISTING FREE/EXISTING USER untouched on login/me.
  * /membership/trial refused on complimentary account (403/400).

Uses direct Mongo touch-ups ONLY on throwaway accounts; cleans them up at the
end so review@aureve.app and user_testaura01 are left exactly as they were.
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
TEST_TOKEN = os.environ.get("TEST_SESSION_TOKEN", "")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = os.environ.get("REVIEWER_PASSWORD", "")


# ---------- helpers ----------

def _ts() -> str:
    return f"{int(time.time()*1000)}{uuid.uuid4().hex[:4]}"


def _throwaway_email() -> str:
    return f"TEST_qa+comp{_ts()}@aureve.local"


def _register(email: str, password: str = "secret123", name: str = "QA Comp"):
    r = requests.post(f"{BASE_URL}/auth/register",
                      json={"email": email, "password": password, "name": name}, timeout=20)
    return r


def _login(email: str, password: str):
    r = requests.post(f"{BASE_URL}/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    return r


def _me(token: str):
    r = requests.get(f"{BASE_URL}/auth/me",
                     headers={"Authorization": f"Bearer {token}"}, timeout=20)
    return r


def _plans(token: str):
    r = requests.get(f"{BASE_URL}/membership/plans",
                     headers={"Authorization": f"Bearer {token}"}, timeout=20)
    return r


def _delete_account(token: str):
    try:
        requests.delete(f"{BASE_URL}/auth/account",
                        headers={"Authorization": f"Bearer {token}"}, timeout=20)
    except Exception:
        pass


async def _mongo():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME], client


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------- fixtures ----------

@pytest.fixture
def fresh_account():
    """Register a brand-new throwaway account, yield (email, token, user_id).
    Deletes the account afterwards so no artefacts persist."""
    email = _throwaway_email()
    r = _register(email)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    token = data["session_token"]
    user_id = data["user"]["user_id"]
    yield email, token, user_id, data
    _delete_account(token)


# ---------- 1. NEW ACCOUNT grants complimentary ----------

class TestNewAccountGrant:
    def test_register_grants_7day_complimentary(self, fresh_account):
        email, token, user_id, reg = fresh_account
        # register payload already carries the user doc
        u = reg["user"]
        assert u.get("complimentary_used") is True
        assert u.get("trial_used") is True
        assert u.get("premium_source") == "complimentary"
        # Immediately /auth/me reflects complimentary + premium
        r = _me(token)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["premium"] is True, me
        assert me["premium_source"] == "complimentary"
        assert me["complimentary_active"] is True
        assert me["complimentary_days_left"] == 7, me
        assert me["complimentary_used"] is True
        assert me["trial_used"] is True
        assert me["premium_until"] == me["complimentary_expires_at"]
        # expiry roughly now+7d
        exp = datetime.fromisoformat(me["complimentary_expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        delta = exp - datetime.now(timezone.utc)
        assert timedelta(days=6, hours=23) < delta < timedelta(days=7, minutes=5), delta

    def test_plans_endpoint_reports_complimentary(self, fresh_account):
        _, token, _, _ = fresh_account
        r = _plans(token)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["premium"] is True
        assert p["premium_source"] == "complimentary"
        assert p["complimentary_active"] is True
        assert p["complimentary_days_left"] == 7
        assert p["trial_used"] is True
        # Legacy trial_eligible must be false (we burned trial_used).
        assert p["trial_eligible"] is False


# ---------- 2. NO RESTART ----------

class TestNoRestart:
    def test_relogin_same_timestamps(self, fresh_account):
        email, token, _, reg = fresh_account
        me1 = _me(token).json()
        # New session via /auth/login
        r = _login(email, "secret123")
        assert r.status_code == 200, r.text
        token2 = r.json()["session_token"]
        assert token2 != token
        me2 = _me(token2).json()
        # Byte-identical
        assert me1["complimentary_started_at"] == me2["complimentary_started_at"]
        assert me1["complimentary_expires_at"] == me2["complimentary_expires_at"]
        assert me1["premium_until"] == me2["premium_until"]
        # And a third hit at /auth/me (simulate reinstall / 2nd device: no local state, fresh token)
        r3 = _login(email, "secret123")
        token3 = r3.json()["session_token"]
        me3 = _me(token3).json()
        assert me1["complimentary_started_at"] == me3["complimentary_started_at"]
        assert me1["complimentary_expires_at"] == me3["complimentary_expires_at"]


# ---------- 3. ONCE ONLY ----------

class TestOnceOnly:
    def test_expired_grant_is_not_re_granted(self, fresh_account):
        email, token, user_id, _ = fresh_account

        async def _expire():
            db, client = await _mongo()
            past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"complimentary_expires_at": past, "premium_until": past}},
            )
            doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            client.close()
            return doc

        doc_before = asyncio.run(_expire())
        assert doc_before["complimentary_used"] is True
        # Fresh login after expiry
        r = _login(email, "secret123")
        assert r.status_code == 200
        token2 = r.json()["session_token"]
        me = _me(token2).json()
        assert me["premium"] is False
        assert me["complimentary_active"] is False
        # complimentary_used still true (never cleared); no new grant
        assert me["complimentary_used"] is True
        assert me["trial_used"] is True

        async def _reread():
            db, client = await _mongo()
            doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            client.close()
            return doc

        doc_after = asyncio.run(_reread())
        # premium_until stayed past (grant did not re-run)
        assert doc_after["premium_until"] == doc_before["premium_until"]
        assert doc_after["complimentary_started_at"] == doc_before["complimentary_started_at"]
        assert doc_after["complimentary_expires_at"] == doc_before["complimentary_expires_at"]


# ---------- 4. EXPIRY → FREE + 402 + data intact ----------

class TestExpiryDropsToFree:
    def test_expiry_gates_and_preserves_data(self, fresh_account):
        email, token, user_id, _ = fresh_account

        # Pre-expiry: health-report must NOT 402 (premium gate passes for complimentary user)
        pre = requests.post(
            f"{BASE_URL}/insights/health-report",
            headers={"Authorization": f"Bearer {token}"},
            json={},
            timeout=30,
        )
        assert pre.status_code != 402, f"premium-gated health-report should pass gate for complimentary user, got {pre.status_code} {pre.text}"

        # Count data snapshots BEFORE expiry (items/outfits/wear_logs)
        async def _counts():
            db, client = await _mongo()
            # Items are scoped to profile ids. Fetch the user's default profile.
            profs = await db.profiles.find({"user_id": user_id}, {"_id": 0}).to_list(10)
            pids = [p["id"] for p in profs]
            items = await db.items.count_documents({"user_id": {"$in": pids}}) if pids else 0
            outfits = await db.outfits.count_documents({"user_id": {"$in": pids}}) if pids else 0
            wear_logs = await db.wear_logs.count_documents({"user_id": {"$in": pids}}) if pids else 0
            client.close()
            return items, outfits, wear_logs

        counts_before = asyncio.run(_counts())

        async def _expire():
            db, client = await _mongo()
            past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"complimentary_expires_at": past, "premium_until": past}},
            )
            client.close()

        asyncio.run(_expire())

        me = _me(token).json()
        assert me["premium"] is False
        assert me["complimentary_active"] is False

        # Premium-gated endpoints now return 402 (use health-report + shopping-intelligence
        # which don't require additional payload fields that would 422 before the gate).
        r_health = requests.post(
            f"{BASE_URL}/insights/health-report",
            headers={"Authorization": f"Bearer {token}"},
            json={},
            timeout=20,
        )
        assert r_health.status_code == 402, f"health-report expected 402, got {r_health.status_code}"

        r_shop = requests.post(
            f"{BASE_URL}/insights/shopping-intelligence",
            headers={"Authorization": f"Bearer {token}"},
            json={},
            timeout=20,
        )
        assert r_shop.status_code == 402, f"shopping-intelligence expected 402, got {r_shop.status_code}"

        # Data intact
        counts_after = asyncio.run(_counts())
        assert counts_after == counts_before, f"data drift: {counts_before} → {counts_after}"


# ---------- 5. FULL ACCESS DURING PERIOD ----------

class TestFullAccessDuringPeriod:
    def test_gated_endpoints_not_402_for_complimentary(self, fresh_account):
        _, token, _, _ = fresh_account
        # tryon
        r = requests.post(f"{BASE_URL}/tryon",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"item_ids": []}, timeout=20)
        assert r.status_code != 402, r.text
        # health-report
        r = requests.post(f"{BASE_URL}/insights/health-report",
                          headers={"Authorization": f"Bearer {token}"},
                          json={}, timeout=30)
        assert r.status_code != 402, r.text
        # shopping-intelligence
        r = requests.post(f"{BASE_URL}/insights/shopping-intelligence",
                          headers={"Authorization": f"Bearer {token}"},
                          json={}, timeout=30)
        assert r.status_code != 402, r.text
        # stylist/chat (metered: 5/month on free — complimentary is premium so unlimited)
        r = requests.post(f"{BASE_URL}/stylist/chat",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"message": "hi"}, timeout=60)
        assert r.status_code != 402, r.text


# ---------- 6. PURCHASE DURING PERIOD TAKES PRECEDENCE ----------

class TestPurchaseOverridesComplimentary:
    def test_entitlement_overrides(self, fresh_account):
        _, token, user_id, _ = fresh_account
        me_before = _me(token).json()
        assert me_before["premium_source"] == "complimentary"

        r = requests.post(
            f"{BASE_URL}/membership/entitlement",
            headers={"Authorization": f"Bearer {token}"},
            json={"active": True, "entitlement_id": "Aureve", "expires_at": None},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["premium"] is True
        assert body["premium_source"] == "revenuecat"

        me_after = _me(token).json()
        assert me_after["premium"] is True
        assert me_after["premium_source"] == "revenuecat"
        assert me_after["complimentary_active"] is False
        # premium_until jumped ~50 years
        pu = datetime.fromisoformat(me_after["premium_until"])
        if pu.tzinfo is None:
            pu = pu.replace(tzinfo=timezone.utc)
        assert pu - datetime.now(timezone.utc) > timedelta(days=365 * 40)


# ---------- 7. EXISTING PAID SUBSCRIBER UNTOUCHED ----------

class TestReviewerUntouched:
    def test_reviewer_login_does_not_grant_complimentary(self):
        # Snapshot reviewer before login
        async def _snap():
            db, client = await _mongo()
            doc = await db.users.find_one({"email": REVIEWER_EMAIL}, {"_id": 0})
            client.close()
            return doc
        before = asyncio.run(_snap())
        assert before is not None, "reviewer account must be seeded"
        assert before.get("premium_source") in ("reviewer", "revenuecat"), before
        premium_until_before = before.get("premium_until")

        r = _login(REVIEWER_EMAIL, REVIEWER_PASSWORD)
        assert r.status_code == 200, r.text
        token = r.json()["session_token"]
        me = _me(token).json()

        # No complimentary granted; premium untouched
        assert me["premium"] is True
        assert me["premium_source"] in ("reviewer", "revenuecat")
        assert me["premium_until"] == premium_until_before
        assert me.get("complimentary_active") is False
        # Must not have complimentary fields filled in
        assert not me.get("complimentary_started_at")
        assert not me.get("complimentary_expires_at")

        after = asyncio.run(_snap())
        assert after.get("premium_source") == before.get("premium_source")
        assert after.get("premium_until") == before.get("premium_until")
        assert "complimentary_used" not in after or after.get("complimentary_used") == before.get("complimentary_used")


# ---------- 8. EXISTING FREE USER UNTOUCHED ----------

class TestExistingFreeUntouched:
    def test_login_and_me_do_not_grant(self):
        # Create a user, strip complimentary + premium entirely to simulate a pre-feature account.
        email = _throwaway_email()
        r = _register(email)
        assert r.status_code == 200
        token = r.json()["session_token"]
        user_id = r.json()["user"]["user_id"]
        try:
            async def _strip():
                db, client = await _mongo()
                await db.users.update_one(
                    {"user_id": user_id},
                    {"$unset": {
                        "complimentary_used": "",
                        "complimentary_started_at": "",
                        "complimentary_expires_at": "",
                        "trial_used": "",
                        "premium_until": "",
                        "premium_source": "",
                    }},
                )
                client.close()
            asyncio.run(_strip())

            # Re-login and hit /auth/me
            r2 = _login(email, "secret123")
            assert r2.status_code == 200
            token2 = r2.json()["session_token"]
            me = _me(token2).json()
            # NO grant should happen on login/me — grant is only at account creation.
            assert me["premium"] is False, me
            assert me.get("premium_source") in (None,), me
            assert me["complimentary_active"] is False
            assert not me.get("complimentary_used")
            assert not me.get("trial_used")
        finally:
            _delete_account(token)


# ---------- 9. OLD OPT-IN TRIAL refused ----------

class TestOldTrialRefusedForComplimentary:
    def test_trial_endpoint_refuses(self, fresh_account):
        _, token, _, _ = fresh_account
        r = requests.post(
            f"{BASE_URL}/membership/trial",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        assert r.status_code in (400, 403), r.text


# ---------- 10. Basic sanity: health + unauth ----------

class TestBasics:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/", timeout=10)
        assert r.status_code == 200

    def test_me_requires_auth(self):
        r = requests.get(f"{BASE_URL}/auth/me", timeout=10)
        assert r.status_code in (401, 403)
