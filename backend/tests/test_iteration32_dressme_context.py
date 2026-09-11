"""
Iteration 32 — Dress Me no-context prompt regression tests.

Covers:
 - GET /api/dressme/context (auth required)
 - has_context=false when no plan and no calendar
 - has_context=true (source='plan') after creating a plan for today
 - Cleanup: delete created plan
 - Regression: dressme generation does not increment wear_count/last_worn
"""
import os
import datetime as dt
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = "AureveTest2026"
SEEDED_BEARER = "test-session-token-aura-123"


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def reviewer_token():
    r = requests.post(f"{API}/auth/login", json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"reviewer login failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, f"no token in response: {r.text}"
    return tok


@pytest.fixture
def reviewer_headers(reviewer_token):
    return {"Authorization": f"Bearer {reviewer_token}", "Content-Type": "application/json"}


@pytest.fixture
def seeded_headers():
    return {"Authorization": f"Bearer {SEEDED_BEARER}", "Content-Type": "application/json"}


def _today():
    return dt.datetime.utcnow().strftime("%Y-%m-%d")


# ---------------- Auth ----------------
class TestContextAuth:
    def test_context_requires_auth(self):
        r = requests.get(f"{API}/dressme/context", timeout=20)
        assert r.status_code in (401, 403), f"unexpected: {r.status_code} {r.text}"


# ---------------- has_context behaviour ----------------
class TestDressMeContext:
    def test_no_plan_no_calendar_returns_false(self, seeded_headers):
        """Seeded test account has no plan for today and no calendar connection."""
        # Cleanup any leftover plan for today first (best effort)
        plans = requests.get(f"{API}/plans", params={"from_date": _today(), "to_date": _today()},
                             headers=seeded_headers, timeout=20).json()
        for p in plans if isinstance(plans, list) else []:
            requests.delete(f"{API}/plans/{p['id']}", headers=seeded_headers, timeout=20)

        r = requests.get(f"{API}/dressme/context", headers=seeded_headers, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("has_context") is False, f"expected has_context False, got {j}"
        assert j.get("source") in (None, ""), f"expected null source, got {j}"

    def test_plan_for_today_returns_true_with_source_plan(self, seeded_headers):
        # Create a plan for today
        payload = {"date": _today(), "title": "TEST_context probe", "occasion": "TEST_office day"}
        c = requests.post(f"{API}/plans", json=payload, headers=seeded_headers, timeout=20)
        assert c.status_code == 200, c.text
        plan_id = c.json().get("id")
        assert plan_id, c.text
        try:
            r = requests.get(f"{API}/dressme/context", headers=seeded_headers, timeout=20)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j.get("has_context") is True, f"expected True after plan create, got {j}"
            assert j.get("source") == "plan", f"expected source plan, got {j}"
            assert "TEST_" in (j.get("label") or ""), f"expected label to contain title, got {j}"
        finally:
            d = requests.delete(f"{API}/plans/{plan_id}", headers=seeded_headers, timeout=20)
            assert d.status_code == 200, d.text
        # Post-cleanup: has_context should go back to False
        r2 = requests.get(f"{API}/dressme/context", headers=seeded_headers, timeout=20)
        assert r2.status_code == 200
        assert r2.json().get("has_context") is False


# ---------------- Reviewer account probe (used by frontend playwright) ----------------
class TestReviewerContext:
    def test_reviewer_no_plan_today(self, reviewer_headers):
        # Cleanup any plans for today under reviewer to guarantee empty state
        plans = requests.get(f"{API}/plans", params={"from_date": _today(), "to_date": _today()},
                             headers=reviewer_headers, timeout=20).json()
        for p in plans if isinstance(plans, list) else []:
            requests.delete(f"{API}/plans/{p['id']}", headers=reviewer_headers, timeout=20)
        r = requests.get(f"{API}/dressme/context", headers=reviewer_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("has_context") is False, r.text


# ---------------- Regression: dressme should not update wear_count/last_worn ----------------
class TestDressMeWearNoMutate:
    def test_generate_does_not_touch_wear_stats(self, seeded_headers):
        before = requests.get(f"{API}/items", headers=seeded_headers, timeout=20)
        assert before.status_code == 200
        b_items = before.json()
        b_snap = {i["id"]: (i.get("wear_count", 0), i.get("last_worn")) for i in b_items}

        r = requests.post(f"{API}/dressme", json={"occasion": "TEST_regression"},
                          headers=seeded_headers, timeout=90)
        assert r.status_code in (200, 402), f"unexpected: {r.status_code} {r.text}"
        # If 402 (free-cap) we can't verify further, skip
        if r.status_code == 402:
            pytest.skip("dressme quota exhausted (402); skipping mutation check")

        after = requests.get(f"{API}/items", headers=seeded_headers, timeout=20)
        assert after.status_code == 200
        a_items = after.json()
        for it in a_items:
            bid = b_snap.get(it["id"])
            if bid is None:
                continue
            assert it.get("wear_count", 0) == bid[0], f"wear_count changed for {it['id']}: {bid[0]} -> {it.get('wear_count')}"
            assert it.get("last_worn") == bid[1], f"last_worn changed for {it['id']}"
