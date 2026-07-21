"""Iteration 7 — /api/dressme (Premium) + /api/stylist/suggest regression.

Scope (per review_request):
- FREE account → POST /api/dressme returns 402
- PREMIUM → POST /api/dressme with weather/temperature → 200 with expected shape
- Occasion override honored via occasion_used
- Plan inference (today's plan drives occasion + from_plan)
- Regression: /api/stylist/suggest still works (shared _build_outfit helper)
- Metering bypass on premium: 3 consecutive /api/dressme calls succeed

Cleanup: reset user_testaura01 to FREE, clear `usage` collection,
delete any test plans created. Aura profile prof_365ddfe52deb has ~5 ready items.
"""
import os
from datetime import datetime, timezone

import pytest
import pymongo

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
TOKEN = "test-session-token-aura-123"
ACCOUNT_ID = "user_testaura01"
PROFILE_ID = "prof_365ddfe52deb"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "X-Profile-Id": PROFILE_ID,
}

# Long timeout for AI-heavy calls (up to 180s per problem statement)
AI_TIMEOUT = 200


@pytest.fixture(scope="module")
def mongo():
    """Direct MongoDB handle to flip premium & clean usage/plans."""
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    client = pymongo.MongoClient(mongo_url)
    yield client[db_name]
    client.close()


def _grant_premium(mongo):
    mongo.users.update_one(
        {"user_id": ACCOUNT_ID},
        {"$set": {"premium_until": "2099-01-01T00:00:00+00:00"}},
    )


def _revoke_premium(mongo):
    mongo.users.update_one(
        {"user_id": ACCOUNT_ID}, {"$unset": {"premium_until": ""}}
    )


def _clear_usage(mongo):
    mongo.usage.delete_many({"account_id": ACCOUNT_ID})


def _clear_test_plans(mongo):
    # Plans are scoped by profile_id (stored as user_id)
    mongo.plans.delete_many({"user_id": PROFILE_ID})


@pytest.fixture(scope="module", autouse=True)
def _clean_environment(mongo):
    """Baseline: start FREE + no usage + no lingering test plans."""
    _revoke_premium(mongo)
    _clear_usage(mongo)
    _clear_test_plans(mongo)
    yield
    # Final cleanup mandated by review_request
    _revoke_premium(mongo)
    _clear_usage(mongo)
    _clear_test_plans(mongo)


# --------------------------- Helpers ---------------------------
def _validate_outfit_shape(data: dict):
    assert isinstance(data.get("confidence_score"), (int, float)), \
        f"confidence_score not numeric: {data.get('confidence_score')!r}"
    assert isinstance(data.get("summary"), str) and data["summary"].strip(), \
        "summary missing/empty"
    resolved = data.get("resolved_items")
    assert isinstance(resolved, list) and len(resolved) >= 1, \
        f"resolved_items empty: {resolved!r}"
    for r in resolved:
        assert r.get("slot"), f"slot missing in resolved item: {r}"
        assert isinstance(r.get("item"), dict), f"item missing/invalid: {r}"


def _all_items_are_profile_ready(data: dict, ready_ids: set):
    for r in data.get("resolved_items", []):
        iid = (r.get("item") or {}).get("id")
        assert iid in ready_ids, f"item {iid} not in READY set {ready_ids}"


def _get_ready_ids():
    import requests
    r = requests.get(f"{BASE_URL}/items", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return {
        it["id"] for it in r.json()
        if (it.get("availability") or "Clean") in ("Clean", "Ready", "ready", "clean")
    }


# --------------------------- Tests ---------------------------
import requests  # noqa: E402


# ---- 1. FREE gating on /api/dressme ----
class TestFreeGating:
    def test_dressme_free_returns_402(self, mongo):
        _revoke_premium(mongo)
        _clear_usage(mongo)
        r = requests.post(f"{BASE_URL}/dressme", headers=HEADERS, json={}, timeout=AI_TIMEOUT)
        assert r.status_code == 402, f"expected 402 free-gate, got {r.status_code}: {r.text[:300]}"
        body = r.json()
        assert "Premium" in (body.get("detail") or ""), f"detail should mention Premium: {body}"


# ---- 2. Premium happy path with weather ----
class TestDressMePremium:
    def test_dressme_with_weather_returns_outfit(self, mongo):
        _grant_premium(mongo)
        _clear_usage(mongo)
        ready = _get_ready_ids()
        assert ready, "prof_365ddfe52deb has no ready items — fixture broken"

        r = requests.post(
            f"{BASE_URL}/dressme",
            headers=HEADERS,
            json={"temperature": 17, "weather": "cloudy"},
            timeout=AI_TIMEOUT,
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:400]}"
        data = r.json()
        _validate_outfit_shape(data)
        _all_items_are_profile_ready(data, ready)
        assert data.get("occasion_used"), f"occasion_used missing/empty: {data.get('occasion_used')!r}"
        # No plan for today → from_plan should be None/empty
        assert not data.get("from_plan"), f"from_plan should be empty (no plan): {data.get('from_plan')!r}"

    def test_dressme_occasion_override(self, mongo):
        _grant_premium(mongo)
        r = requests.post(
            f"{BASE_URL}/dressme",
            headers=HEADERS,
            json={"occasion": "wedding guest"},
            timeout=AI_TIMEOUT,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:400]}"
        data = r.json()
        _validate_outfit_shape(data)
        assert data.get("occasion_used") == "wedding guest", \
            f"expected occasion_used='wedding guest', got {data.get('occasion_used')!r}"


# ---- 3. Plan inference ----
class TestPlanInference:
    def test_dressme_infers_occasion_from_today_plan(self, mongo):
        _grant_premium(mongo)
        _clear_test_plans(mongo)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Create a plan for today
        create = requests.post(
            f"{BASE_URL}/plans",
            headers=HEADERS,
            json={"date": today, "title": "Client dinner", "occasion": "client dinner"},
            timeout=30,
        )
        assert create.status_code == 200, f"plan create failed: {create.status_code} {create.text[:300]}"
        plan_id = create.json().get("id")
        assert plan_id, f"plan id missing: {create.json()}"

        try:
            r = requests.post(
                f"{BASE_URL}/dressme", headers=HEADERS, json={}, timeout=AI_TIMEOUT
            )
            assert r.status_code == 200, f"dressme failed: {r.status_code} {r.text[:400]}"
            data = r.json()
            _validate_outfit_shape(data)
            assert (data.get("occasion_used") or "").lower() == "client dinner", \
                f"expected occasion_used='client dinner', got {data.get('occasion_used')!r}"
            assert data.get("from_plan"), f"from_plan should be populated: {data.get('from_plan')!r}"
        finally:
            requests.delete(f"{BASE_URL}/plans/{plan_id}", headers=HEADERS, timeout=15)


# ---- 4. Regression: /api/stylist/suggest still works ----
class TestStylistRegression:
    def test_stylist_suggest_still_works(self, mongo):
        _grant_premium(mongo)
        r = requests.post(
            f"{BASE_URL}/stylist/suggest",
            headers=HEADERS,
            json={"occasion": "casual lunch", "temperature": 20},
            timeout=AI_TIMEOUT,
        )
        assert r.status_code == 200, f"stylist suggest failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        _validate_outfit_shape(data)


# ---- 5. Metering bypass on premium ----
class TestPremiumBypass:
    def test_three_dressme_calls_all_pass(self, mongo):
        _grant_premium(mongo)
        _clear_usage(mongo)
        statuses = []
        for i in range(3):
            r = requests.post(
                f"{BASE_URL}/dressme",
                headers=HEADERS,
                json={"temperature": 18, "weather": "sunny"},
                timeout=AI_TIMEOUT,
            )
            statuses.append(r.status_code)
        assert all(s == 200 for s in statuses), \
            f"expected all 200 for premium 3x, got {statuses}"
