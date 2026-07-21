"""
Iteration 8 — App-managed 7-day free trial tests.

Focus: /api/membership/trial + new trial fields on /membership/plans and /auth/me.
See review_request in iteration_8 for exact expectations.
"""
import os
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com"
TOKEN = "test-session-token-aura-123"
USER_ID = "user_testaura01"
PROFILE_ID = "prof_365ddfe52deb"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "X-Profile-Id": PROFILE_ID,
}

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _reset_free(db):
    """Reset user to a clean FREE state (unset premium/trial fields, clear usage)."""
    db.users.update_one(
        {"user_id": USER_ID},
        {"$unset": {"premium_until": "", "premium_source": "", "trial_used": ""}},
    )
    db.usage.delete_many({"user_id": USER_ID})


# ---------- 1) Clean FREE account exposes correct trial fields ----------
def test_1_clean_free_state_exposes_trial_fields(mongo_db):
    _reset_free(mongo_db)

    r_plans = requests.get(f"{BASE_URL}/api/membership/plans", headers=HEADERS, timeout=30)
    assert r_plans.status_code == 200, r_plans.text
    p = r_plans.json()
    assert p.get("premium") is False, p
    assert p.get("trial_used") is False, p
    assert p.get("trial_eligible") is True, p
    assert p.get("trial_days") == 7, p

    r_me = requests.get(f"{BASE_URL}/api/auth/me", headers=HEADERS, timeout=30)
    assert r_me.status_code == 200, r_me.text
    me = r_me.json()
    assert me.get("premium") is False, me
    assert me.get("trial_used") is False, me
    assert me.get("trial_eligible") is True, me


# ---------- 2) Start trial grants premium ----------
def test_2_start_trial_grants_premium_for_7_days(mongo_db):
    _reset_free(mongo_db)

    r = requests.post(f"{BASE_URL}/api/membership/trial", headers=HEADERS, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("premium") is True, j
    assert j.get("premium_source") == "trial", j
    assert j.get("trial_used") is True, j
    assert "premium_until" in j and j["premium_until"], j

    # premium_until ~7 days out
    until = datetime.fromisoformat(j["premium_until"])
    now = datetime.now(timezone.utc)
    delta = until - now
    # allow 6d23h < delta < 7d1h
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, hours=1), delta

    # /auth/me now reflects premium+trial
    r_me = requests.get(f"{BASE_URL}/api/auth/me", headers=HEADERS, timeout=30)
    assert r_me.status_code == 200, r_me.text
    me = r_me.json()
    assert me["premium"] is True, me
    assert me["premium_source"] == "trial", me
    assert me["trial_used"] is True, me
    assert me["trial_eligible"] is False, me


# ---------- 3) Premium-only endpoints unlocked while on trial ----------
def test_3a_dressme_200_while_on_trial():
    # requires premium (already set in test_2)
    body = {"temperature": 18, "weather": "clear"}
    r = requests.post(f"{BASE_URL}/api/dressme", headers=HEADERS, json=body, timeout=200)
    assert r.status_code == 200, f"dressme failed: {r.status_code} {r.text[:400]}"


def test_3b_packing_plan_200_while_on_trial():
    body = {"destination": "Rome", "days": 3}
    r = requests.post(f"{BASE_URL}/api/packing/plan", headers=HEADERS, json=body, timeout=200)
    assert r.status_code == 200, f"packing failed: {r.status_code} {r.text[:400]}"


# ---------- 4) Second trial attempt → 400 ----------
def test_4_second_trial_attempt_rejected():
    r = requests.post(f"{BASE_URL}/api/membership/trial", headers=HEADERS, timeout=30)
    assert r.status_code == 400, r.text
    detail = (r.json().get("detail") or "").lower()
    assert "already used" in detail or "already" in detail, detail


# ---------- 5) Expired trial → premium=false, trial_used=true, no re-trial, gated ----------
def test_5_expired_trial_is_not_re_triable_and_is_gated(mongo_db):
    # Simulate expired trial: keep trial_used=true, set premium_until to past
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    mongo_db.users.update_one(
        {"user_id": USER_ID},
        {"$set": {"premium_until": past, "premium_source": "trial", "trial_used": True}},
    )
    # clear usage so metering wouldn't interfere
    mongo_db.usage.delete_many({"user_id": USER_ID})

    r_me = requests.get(f"{BASE_URL}/api/auth/me", headers=HEADERS, timeout=30)
    assert r_me.status_code == 200, r_me.text
    me = r_me.json()
    assert me["premium"] is False, me
    assert me["trial_used"] is True, me
    assert me["trial_eligible"] is False, me

    # cannot re-trial
    r_trial = requests.post(f"{BASE_URL}/api/membership/trial", headers=HEADERS, timeout=30)
    assert r_trial.status_code == 400, r_trial.text

    # dressme is Premium-only → 402
    r_dr = requests.post(
        f"{BASE_URL}/api/dressme",
        headers=HEADERS,
        json={"temperature": 18, "weather": "clear"},
        timeout=60,
    )
    assert r_dr.status_code == 402, f"expected 402 after lapse, got {r_dr.status_code}: {r_dr.text[:400]}"


# ---------- 6) Regression: items + insights still 200 for free ----------
def test_6a_items_200_for_free(mongo_db):
    _reset_free(mongo_db)
    r = requests.get(f"{BASE_URL}/api/items", headers=HEADERS, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # response may be a list of items or dict with items
    if isinstance(data, dict):
        assert "items" in data or "pairs_count" in data or isinstance(data, dict), data


def test_6b_insights_200_for_free():
    r = requests.get(f"{BASE_URL}/api/insights", headers=HEADERS, timeout=30)
    assert r.status_code == 200, r.text


# ---------- 7) Final cleanup: reset user_testaura01 to clean FREE ----------
def test_7_final_reset_user_to_clean_free(mongo_db):
    _reset_free(mongo_db)
    u = mongo_db.users.find_one({"user_id": USER_ID})
    assert u is not None
    assert "premium_until" not in u
    assert "premium_source" not in u
    assert "trial_used" not in u
    assert mongo_db.usage.count_documents({"user_id": USER_ID}) == 0
