"""Iteration 21 — Guest Mode (backend).

Covers:
- POST /api/auth/guest mints a guest user + 7-day session token
- GET /api/auth/me returns is_guest=true, premium=false, trial_eligible=true
- Scoped endpoints work for guests (profiles auto-create, items CRUD, outfits CRUD)
- Guest = FREE gating (stylist metered 5/day; premium-only features 402)
- /api/auth/session still works with the seeded token; empty/invalid guest_token doesn't error
- migrate_guest_data DB behaviour (already unit-tested by main agent, we assert
  scope-level effects here where feasible without real OAuth)
"""
import os
import base64
import io
import time
import pytest
import requests

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
SEEDED_TOKEN = "test-session-token-aura-123"  # resolves to user_testaura01


# ---------------------------- helpers ----------------------------
def _tiny_jpeg_b64() -> str:
    try:
        from PIL import Image
        img = Image.new("RGB", (64, 64), (200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return base64.b64encode(b"\xff\xd8\xff\xd9").decode()


@pytest.fixture(scope="module")
def guest():
    """Fresh guest session (session_token + user)."""
    r = requests.post(f"{BASE_URL}/auth/guest", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "session_token" in data and data["session_token"].startswith("guest_")
    assert data["user"]["is_guest"] is True
    assert data["user"]["user_id"].startswith("guest_")
    yield data


@pytest.fixture(scope="module")
def guest_headers(guest):
    return {
        "Authorization": f"Bearer {guest['session_token']}",
        "Content-Type": "application/json",
    }


# ---------------------------- 1. mint guest ----------------------------
class TestGuestAuth:
    def test_create_guest_returns_session_and_user(self, guest):
        assert guest["session_token"].startswith("guest_")
        u = guest["user"]
        assert u["is_guest"] is True
        assert u["name"] == "Guest"
        assert u["email"].endswith("@guest.aureve.local")

    def test_auth_me_reflects_guest(self, guest_headers):
        r = requests.get(f"{BASE_URL}/auth/me", headers=guest_headers, timeout=15)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["is_guest"] is True
        assert me["premium"] is False
        assert me["trial_eligible"] is True
        assert me.get("trial_used") is False

    def test_no_token_is_401(self):
        r = requests.get(f"{BASE_URL}/auth/me", timeout=10)
        assert r.status_code == 401


# ---------------------------- 2. scoped data endpoints ----------------------------
class TestGuestScopedData:
    def test_profiles_autocreate_for_guest(self, guest_headers):
        r = requests.get(f"{BASE_URL}/profiles", headers=guest_headers, timeout=15)
        assert r.status_code == 200, r.text
        profs = r.json()
        assert isinstance(profs, list) and len(profs) >= 1
        # sanity: shape
        assert "id" in profs[0]
        assert profs[0].get("kind") == "individual"

    def test_guest_can_add_and_list_item(self, guest_headers):
        payload = {
            "name": "TEST_guest_item",
            "category": "top",
            "colour": "black",
            "photo": _tiny_jpeg_b64(),
        }
        r = requests.post(f"{BASE_URL}/items", headers=guest_headers, json=payload, timeout=45)
        assert r.status_code == 200, r.text
        item = r.json()
        assert "id" in item
        # verify list
        r2 = requests.get(f"{BASE_URL}/items", headers=guest_headers, timeout=15)
        assert r2.status_code == 200
        items = r2.json()
        assert any(it["id"] == item["id"] for it in items)

    def test_guest_can_create_and_list_outfit(self, guest_headers):
        # need at least one item id
        items = requests.get(f"{BASE_URL}/items", headers=guest_headers, timeout=15).json()
        if not items:
            pytest.skip("no items to build outfit")
        item_id = items[0]["id"]
        payload = {"name": "TEST_guest_outfit", "item_ids": [item_id], "occasion": "casual"}
        r = requests.post(f"{BASE_URL}/outfits", headers=guest_headers, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        outfit = r.json()
        assert outfit.get("id")
        r2 = requests.get(f"{BASE_URL}/outfits", headers=guest_headers, timeout=15)
        assert r2.status_code == 200
        assert any(o["id"] == outfit["id"] for o in r2.json())


# ---------------------------- 3. AI gating (guest == FREE) ----------------------------
class TestGuestGating:
    """Guest must behave exactly like a free signed-in account."""

    def test_stylist_metered_allowed_within_free_limit(self, guest_headers):
        # Fresh guest so usage=0. Ask for one suggestion — must NOT 402.
        payload = {"occasion": "casual", "context": "coffee run"}
        r = requests.post(
            f"{BASE_URL}/stylist/suggest", headers=guest_headers, json=payload, timeout=60
        )
        # AI may return 200 or 500 on transient LLM errors, but never 402 for the first hit.
        assert r.status_code != 402, f"stylist should be allowed on first call, got 402: {r.text}"

    @pytest.mark.parametrize(
        "endpoint,method,body",
        [
            ("/dressme", "POST", {"occasion": "casual"}),
            ("/packing/plan", "POST", {"destination": "Paris", "days": 3}),
            ("/capsule/build", "POST", {"theme": "Winter"}),
            ("/insights/health-report", "POST", {}),
            ("/insights/missing-piece", "POST", {}),
            ("/tryon", "POST", {"item_ids": ["nonexistent"], "person_image": _tiny_jpeg_b64()}),
            ("/shop-check", "POST", {"query": "black jacket", "image": _tiny_jpeg_b64()}),
        ],
    )
    def test_premium_only_features_return_402_for_guest(self, guest_headers, endpoint, method, body):
        r = requests.request(
            method, f"{BASE_URL}{endpoint}", headers=guest_headers, json=body, timeout=20
        )
        assert r.status_code == 402, f"{endpoint} expected 402 for guest, got {r.status_code}: {r.text[:200]}"
        # Response carries a helpful message
        try:
            detail = r.json().get("detail", "")
        except Exception:
            detail = ""
        assert isinstance(detail, str)

    def test_household_second_profile_402_for_guest(self, guest_headers):
        """Second profile creation is premium-gated even for guests."""
        payload = {"name": "TEST_second", "emoji": "👶", "kind": "individual"}
        r = requests.post(f"{BASE_URL}/profiles", headers=guest_headers, json=payload, timeout=15)
        # First profile already auto-created, so this is the 2nd
        assert r.status_code == 402, f"expected 402 on 2nd profile for guest, got {r.status_code}: {r.text[:200]}"


# ---------------------------- 4. /auth/session compatibility ----------------------------
class TestSessionCompat:
    def test_seeded_token_still_works_via_me(self):
        """The main agent seeds test-session-token-aura-123 → user_testaura01.
        We can't call /auth/session (requires real Emergent OAuth), but /auth/me
        with the seeded bearer must still resolve to the seeded account.
        This verifies the auth pipeline hasn't been broken by the new code path."""
        r = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {SEEDED_TOKEN}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        me = r.json()
        assert me.get("user_id") == "user_testaura01"
        assert me.get("is_guest") is False

    def test_session_invalid_token_still_401(self):
        """POST /auth/session with a bogus session token → 401 (Emergent rejects)."""
        r = requests.post(
            f"{BASE_URL}/auth/session",
            json={"session_token": "bogus-nonexistent"},
            timeout=20,
        )
        assert r.status_code == 401

    def test_session_bogus_guest_token_does_not_crash(self):
        """Even if session_token is invalid, presence of guest_token must not
        turn a 401 into a 500. Best we can validate without real OAuth."""
        r = requests.post(
            f"{BASE_URL}/auth/session",
            json={"session_token": "bogus", "guest_token": "guest_doesnotexist"},
            timeout=20,
        )
        assert r.status_code in (400, 401), f"unexpected {r.status_code}: {r.text[:200]}"

    def test_session_empty_guest_token_does_not_crash(self):
        r = requests.post(
            f"{BASE_URL}/auth/session",
            json={"session_token": "bogus", "guest_token": ""},
            timeout=20,
        )
        assert r.status_code in (400, 401)


# ---------------------------- 5. logout retires guest session ----------------------------
class TestGuestLogout:
    def test_guest_logout_invalidates_token(self):
        r = requests.post(f"{BASE_URL}/auth/guest", timeout=15)
        assert r.status_code == 200
        tok = r.json()["session_token"]
        headers = {"Authorization": f"Bearer {tok}"}
        # verify valid first
        r1 = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
        assert r1.status_code == 200
        # logout
        r2 = requests.post(f"{BASE_URL}/auth/logout", headers=headers, timeout=10)
        assert r2.status_code == 200
        # now invalid
        r3 = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=10)
        assert r3.status_code == 401
