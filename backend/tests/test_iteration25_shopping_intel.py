"""Backend tests for iteration 25: Shopping Intelligence (Premium-only)."""
import os
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
REVIEWER_EMAIL = os.environ.get("REVIEWER_EMAIL", "review@aureve.app")
REVIEWER_PASSWORD = os.environ.get("REVIEWER_PASSWORD", "AureveTest2026")


@pytest.fixture(scope="module")
def premium_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD
    }, timeout=30)
    assert r.status_code == 200, f"Reviewer login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("session_token") or data.get("token") or data.get("access_token")
    assert tok, f"No token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def guest_token():
    r = requests.post(f"{BASE_URL}/api/auth/guest", timeout=30)
    assert r.status_code == 200, f"Guest auth failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("session_token") or data.get("token")
    assert tok, f"No token in guest response: {data}"
    return tok


# ---- /api/insights/shopping-intelligence: PREMIUM 200 ----
def test_shopping_intelligence_premium_returns_recommendations(premium_token):
    r = requests.post(
        f"{BASE_URL}/api/insights/shopping-intelligence",
        headers={"Authorization": f"Bearer {premium_token}"},
        timeout=90,
    )
    assert r.status_code == 200, f"Expected 200 got {r.status_code}: {r.text[:400]}"
    data = r.json()
    assert "recommendations" in data
    recs = data["recommendations"]
    assert isinstance(recs, list) and len(recs) >= 1
    # spot-check first recommendation shape
    first = recs[0]
    assert "piece" in first and isinstance(first["piece"], str)
    # optional fields but common
    if "pairs_with" in first:
        assert isinstance(first["pairs_with"], list)
    if "outfits_added" in first:
        assert isinstance(first["outfits_added"], (int, float))


# ---- /api/insights/shopping-intelligence: FREE (guest) 402 ----
def test_shopping_intelligence_guest_returns_402(guest_token):
    r = requests.post(
        f"{BASE_URL}/api/insights/shopping-intelligence",
        headers={"Authorization": f"Bearer {guest_token}"},
        timeout=30,
    )
    assert r.status_code == 402, f"Expected 402 got {r.status_code}: {r.text[:400]}"


# ---- Sanity: reviewer /me is premium ----
def test_reviewer_is_premium(premium_token):
    r = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {premium_token}"},
        timeout=30,
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("premium") is True, f"Reviewer not premium: {data}"


# ---- Sanity: guest is NOT premium ----
def test_guest_is_not_premium(guest_token):
    r = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {guest_token}"},
        timeout=30,
    )
    assert r.status_code == 200
    assert r.json().get("premium") is False
