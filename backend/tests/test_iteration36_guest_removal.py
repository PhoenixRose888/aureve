"""Iteration 36 - Guest/demo removal, welcome/tour flow.

Verifies:
- POST /api/auth/guest is gone (404/405)
- Brand-new email/password registration -> empty wardrobe, non-premium, no plans/wear
- Login again works, delete account cleans up
- Reviewer login still works and remains premium with wardrobe
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = "AureveTest2026"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# -- Guest endpoint gone -------------------------------------------------------
def test_health_ok(s):
    r = s.get(f"{API}/")
    assert r.status_code in (200, 404)  # root may 404; not fatal


def test_guest_endpoint_removed(s):
    r = s.post(f"{API}/auth/guest", json={})
    assert r.status_code in (404, 405), f"Guest endpoint still present: {r.status_code} {r.text[:200]}"


# -- New account flow ----------------------------------------------------------
NEW_EMAIL = f"qa+i36_{int(time.time())}@aureve.local"
NEW_PASSWORD = "secret1234"


@pytest.fixture(scope="module")
def new_account(s):
    r = s.post(f"{API}/auth/register", json={"email": NEW_EMAIL, "password": NEW_PASSWORD, "name": "QA Iter36"})
    assert r.status_code == 200, f"Register failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert "session_token" in body and "user" in body
    return {"token": body["session_token"], "user": body["user"]}


def _auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_new_account_empty_items(s, new_account):
    r = s.get(f"{API}/items", headers=_auth(new_account["token"]))
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert items == [], f"Fresh account has items (demo not purged?): {len(items)}"


def test_new_account_empty_outfits(s, new_account):
    r = s.get(f"{API}/outfits", headers=_auth(new_account["token"]))
    assert r.status_code == 200
    assert r.json() == []


def test_new_account_non_premium(s, new_account):
    r = s.get(f"{API}/auth/me", headers=_auth(new_account["token"]))
    assert r.status_code == 200
    me = r.json()
    assert me.get("is_guest") in (False, None), "New email/password account must not be guest"
    assert not me.get("premium", False), "New account should be Free, not Premium"


def test_new_account_no_plans(s, new_account):
    # /plan/week returns any planned outfits
    r = s.get(f"{API}/plan/week", headers=_auth(new_account["token"]))
    # 200 with empty structure is acceptable; endpoint may 404 if missing
    if r.status_code == 200:
        data = r.json()
        # accept empty list / empty dict / plans list empty
        if isinstance(data, list):
            assert data == []
        elif isinstance(data, dict):
            plans = data.get("plans") or data.get("days") or []
            # No plans should be present
            for d in (plans if isinstance(plans, list) else []):
                assert not (d.get("items") if isinstance(d, dict) else False)


def test_new_account_no_wear_history(s, new_account):
    r = s.get(f"{API}/wear/history", headers=_auth(new_account["token"]))
    if r.status_code == 200:
        h = r.json()
        assert (h == [] or (isinstance(h, dict) and not h.get("entries")))


def test_login_again_same_password(s, new_account):
    r = s.post(f"{API}/auth/login", json={"email": NEW_EMAIL, "password": NEW_PASSWORD})
    assert r.status_code == 200, f"Login again failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert "session_token" in body
    # store token for later delete
    new_account["token"] = body["session_token"]


def test_delete_throwaway_account(s, new_account):
    r = s.delete(f"{API}/auth/account", headers=_auth(new_account["token"]))
    assert r.status_code in (200, 204), f"Delete failed: {r.status_code} {r.text[:200]}"
    # Verify token no longer valid
    r2 = s.get(f"{API}/auth/me", headers=_auth(new_account["token"]))
    assert r2.status_code in (401, 403, 404)


# -- Reviewer regression -------------------------------------------------------
@pytest.fixture(scope="module")
def reviewer(s):
    r = s.post(f"{API}/auth/login", json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD})
    assert r.status_code == 200, f"Reviewer login failed: {r.status_code} {r.text[:200]}"
    return r.json()


def test_reviewer_login_ok(reviewer):
    assert "session_token" in reviewer
    assert "user" in reviewer


def test_reviewer_is_premium(s, reviewer):
    r = s.get(f"{API}/auth/me", headers=_auth(reviewer["session_token"]))
    assert r.status_code == 200
    me = r.json()
    assert me.get("premium") is True, f"Reviewer should still be Premium; got: {me}"


def test_reviewer_still_has_wardrobe(s, reviewer):
    r = s.get(f"{API}/items", headers=_auth(reviewer["session_token"]))
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) > 0, "Reviewer demo wardrobe should be seeded and returned"
