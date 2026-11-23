"""
Iteration 48 — RevenueCat 'any active entitlement = Premium' fix.

Verifies:
  * POST /api/membership/entitlement (new): any active entitlement unlocks
    Premium; non-expiring entitlements get a ~50y premium_until; explicit
    future/past expires_at is honoured as-is; the endpoint only ever
    grants/extends (active:false is a no-op, earlier dates don't shrink it);
    auth is required; app_user_id is ignored (only the authenticated user
    is ever updated); gated AI features actually unlock after a grant.
  * POST /api/webhooks/revenuecat: INITIAL_PURCHASE with no expiration_at_ms
    stores a far-future premium_until (not 31 days); TEMPORARY_ENTITLEMENT_GRANT
    with no expiry stores ~31 days; EXPIRATION/CANCELLATION with past/absent
    expiry clears premium; event de-duplication by event id.
  * /api/membership/trial and existing is_premium gating still behave.
"""
import os
import uuid
import requests
import pytest
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TOKEN = os.environ.get("TEST_SESSION_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
USER_ID = "user_testaura01"


# ------------------------------------------------------------------ helpers
def _me():
    r = requests.get(f"{API}/auth/me", headers=HEADERS, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _parse(dt_s):
    if not dt_s:
        return None
    d = datetime.fromisoformat(dt_s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _set_premium_until(iso):
    """Write premium_until directly so each test starts from a known state.
    Uses the entitlement endpoint since we have no raw DB access here — we
    reach the exact ISO via a webhook (which can set an arbitrary expiry)."""
    # Use a unique event id so we don't collide with earlier runs.
    evt_id = f"testsetup_{uuid.uuid4().hex[:10]}"
    body = {
        "event": {
            "id": evt_id,
            "type": "INITIAL_PURCHASE",
            "app_user_id": USER_ID,
            "expiration_at_ms": int(_parse(iso).timestamp() * 1000) if iso else None,
        }
    }
    r = requests.post(f"{API}/webhooks/revenuecat", json=body, timeout=15)
    assert r.status_code == 200, r.text


def _clear_premium():
    evt_id = f"testclear_{uuid.uuid4().hex[:10]}"
    r = requests.post(f"{API}/webhooks/revenuecat", json={
        "event": {"id": evt_id, "type": "EXPIRATION", "app_user_id": USER_ID}
    }, timeout=15)
    assert r.status_code == 200


# Restore the account to premium at teardown.
RESTORE_UNTIL = "2099-01-01T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _restore_premium_after():
    yield
    # Always leave the test account premium so the next test / suite can run.
    _clear_premium()  # clear so the webhook GRANTS cleanly
    _set_premium_until(RESTORE_UNTIL)
    me = _me()
    assert me["premium"] is True


# ========================================================= entitlement sync
class TestEntitlementSync:
    def test_requires_auth(self):
        r = requests.post(f"{API}/membership/entitlement", json={"active": True}, timeout=10)
        assert r.status_code in (401, 403), r.text

    def test_active_no_expiry_grants_far_future(self):
        _clear_premium()
        assert _me()["premium"] is False
        payload = {
            "active": True,
            "entitlement_id": "Aureve",
            "expires_at": None,
            "product_id": None,
            "app_user_id": USER_ID,
        }
        r = requests.post(f"{API}/membership/entitlement", json=payload, headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["premium"] is True
        assert data["updated"] is True
        assert data["premium_source"] == "revenuecat"
        until = _parse(data["premium_until"])
        # ~50 years out
        assert until > datetime.now(timezone.utc) + timedelta(days=365 * 40)
        me = _me()
        assert me["premium"] is True
        assert me["premium_source"] == "revenuecat"

    def test_active_explicit_future_expiry_stored_exact(self):
        _clear_premium()
        future_iso = "2027-01-01T00:00:00+00:00"
        payload = {"active": True, "entitlement_id": "Aureve", "expires_at": future_iso}
        r = requests.post(f"{API}/membership/entitlement", json=payload, headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["premium"] is True
        assert _parse(data["premium_until"]) == _parse(future_iso)
        assert _me()["premium"] is True

    def test_active_past_expiry_stored_but_not_premium(self):
        _clear_premium()
        past_iso = "2020-01-01T00:00:00+00:00"
        payload = {"active": True, "entitlement_id": "Aureve", "expires_at": past_iso}
        r = requests.post(f"{API}/membership/entitlement", json=payload, headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Endpoint says premium:true (it granted) but the stored date is past, so
        # is_premium() returns False — do NOT pretend the user is premium.
        assert _parse(data["premium_until"]) == _parse(past_iso)
        me = _me()
        assert me["premium"] is False, "past expiry must not count as premium"

    def test_inactive_does_not_clear_existing_premium(self):
        _set_premium_until("2030-06-01T00:00:00+00:00")
        assert _me()["premium"] is True
        r = requests.post(f"{API}/membership/entitlement", json={"active": False}, headers=HEADERS, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["updated"] is False
        me = _me()
        assert me["premium"] is True
        assert _parse(me["premium_until"]) == _parse("2030-06-01T00:00:00+00:00"), \
            "inactive report must not shorten existing premium"

    def test_earlier_expiry_does_not_shorten(self):
        _set_premium_until("2030-06-01T00:00:00+00:00")
        payload = {"active": True, "entitlement_id": "Aureve", "expires_at": "2027-01-01T00:00:00+00:00"}
        r = requests.post(f"{API}/membership/entitlement", json=payload, headers=HEADERS, timeout=15)
        assert r.status_code == 200
        me = _me()
        assert _parse(me["premium_until"]) >= _parse("2030-06-01T00:00:00+00:00"), \
            "endpoint must keep the later date, not shrink to the earlier one"

    def test_ignores_mismatched_app_user_id(self):
        """Posting a different app_user_id must only ever update the AUTHENTICATED
        user — never a different account."""
        _clear_premium()
        # Snapshot the reviewer account's premium_until (second account that must
        # not be touched).
        reviewer_login = requests.post(f"{API}/auth/login", json={
            "email": "review@aureve.app", "password": os.environ.get("REVIEWER_PASSWORD", "")
        }, timeout=15)
        assert reviewer_login.status_code == 200, reviewer_login.text
        reviewer_token = reviewer_login.json()["session_token"]
        reviewer_before = requests.get(
            f"{API}/auth/me",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            timeout=15,
        ).json()
        reviewer_until_before = reviewer_before.get("premium_until")

        # Authenticate as user_testaura01 but pass a FAKE app_user_id in the body.
        r = requests.post(f"{API}/membership/entitlement", json={
            "active": True,
            "entitlement_id": "Aureve",
            "expires_at": None,
            "app_user_id": "user_someoneelse_do_not_touch",
        }, headers=HEADERS, timeout=15)
        assert r.status_code == 200

        # user_testaura01 was updated.
        assert _me()["premium"] is True

        # Reviewer account is untouched.
        reviewer_after = requests.get(
            f"{API}/auth/me",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            timeout=15,
        ).json()
        assert reviewer_after.get("premium_until") == reviewer_until_before

    def test_grant_unlocks_gated_ai_feature(self):
        """A RevenueCat-granted premium must actually unlock gated AI features.
        /tryon enforces 'tryon' which is NOT in FREE_LIMITS, so it's strictly
        Premium-only — a free call 402s before any further validation, a
        premium call clears the gate (and 400s on missing person_image). Non-402
        is the signal we care about."""
        _clear_premium()
        tryon_body = {"person_image": "", "item_ids": []}
        r_free = requests.post(f"{API}/tryon", json=tryon_body, headers=HEADERS, timeout=30)
        assert r_free.status_code == 402, (
            f"expected 402 pre-grant from /tryon (Premium-only), got "
            f"{r_free.status_code}: {r_free.text[:200]}"
        )
        # Grant via the new endpoint.
        r = requests.post(f"{API}/membership/entitlement", json={
            "active": True, "entitlement_id": "Aureve",
        }, headers=HEADERS, timeout=15)
        assert r.status_code == 200
        assert r.json()["premium"] is True
        # Now the same gated call must NOT 402 (premium cleared the gate).
        r_prem = requests.post(f"{API}/tryon", json=tryon_body, headers=HEADERS, timeout=30)
        assert r_prem.status_code != 402, (
            f"premium grant did not unlock gated AI feature: {r_prem.status_code} {r_prem.text[:200]}"
        )


# ============================================================= webhook flow
class TestRevenueCatWebhook:
    def test_initial_purchase_no_expiry_sets_far_future(self):
        _clear_premium()
        evt_id = f"TEST_iter48_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/webhooks/revenuecat", json={
            "event": {"id": evt_id, "type": "INITIAL_PURCHASE", "app_user_id": USER_ID}
        }, timeout=15)
        assert r.status_code == 200, r.text
        me = _me()
        assert me["premium"] is True
        until = _parse(me["premium_until"])
        assert until > datetime.now(timezone.utc) + timedelta(days=365 * 40), \
            f"expected far-future premium_until, got {me['premium_until']}"

    def test_temporary_entitlement_grant_no_expiry_sets_31d(self):
        _clear_premium()
        evt_id = f"TEST_iter48_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/webhooks/revenuecat", json={
            "event": {"id": evt_id, "type": "TEMPORARY_ENTITLEMENT_GRANT", "app_user_id": USER_ID}
        }, timeout=15)
        assert r.status_code == 200
        me = _me()
        assert me["premium"] is True
        until = _parse(me["premium_until"])
        delta = until - datetime.now(timezone.utc)
        assert 29 <= delta.days <= 32, f"expected ~31d premium, got {delta.days}d ({me['premium_until']})"

    def test_expiration_clears_premium(self):
        _set_premium_until("2030-06-01T00:00:00+00:00")
        assert _me()["premium"] is True
        evt_id = f"TEST_iter48_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/webhooks/revenuecat", json={
            "event": {"id": evt_id, "type": "EXPIRATION", "app_user_id": USER_ID}
        }, timeout=15)
        assert r.status_code == 200
        me = _me()
        assert me["premium"] is False
        assert me.get("premium_until") in (None, ""), f"expected null premium_until, got {me.get('premium_until')}"

    def test_cancellation_past_expiry_clears(self):
        _set_premium_until("2030-06-01T00:00:00+00:00")
        past_ms = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        evt_id = f"TEST_iter48_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/webhooks/revenuecat", json={
            "event": {"id": evt_id, "type": "CANCELLATION", "app_user_id": USER_ID,
                      "expiration_at_ms": past_ms}
        }, timeout=15)
        assert r.status_code == 200
        me = _me()
        assert me["premium"] is False
        assert me.get("premium_until") in (None, "")

    def test_event_id_dedup(self):
        _clear_premium()
        evt_id = f"TEST_iter48_dedup_{uuid.uuid4().hex[:8]}"
        body = {"event": {"id": evt_id, "type": "INITIAL_PURCHASE", "app_user_id": USER_ID}}
        r1 = requests.post(f"{API}/webhooks/revenuecat", json=body, timeout=15)
        assert r1.status_code == 200
        first_until = _me()["premium_until"]
        # Clear premium then re-post the SAME event id → must be ignored, so
        # premium stays cleared.
        _clear_premium()
        assert _me()["premium"] is False
        r2 = requests.post(f"{API}/webhooks/revenuecat", json=body, timeout=15)
        assert r2.status_code == 200
        me = _me()
        assert me["premium"] is False, \
            f"duplicate event id must be ignored, but premium re-granted to {me.get('premium_until')} (first was {first_until})"


# ============================================================ regression
class TestRegression:
    def test_auth_me_still_returns_premium(self):
        me = _me()
        assert "premium" in me
        assert isinstance(me["premium"], bool)

    def test_trial_endpoint_behaviour(self):
        """/membership/trial requires FREE_TRIAL_ENABLED or is already-used/
        premium — must not crash and must respect state."""
        r = requests.post(f"{API}/membership/trial", headers=HEADERS, timeout=15)
        assert r.status_code in (200, 400, 403), r.text
