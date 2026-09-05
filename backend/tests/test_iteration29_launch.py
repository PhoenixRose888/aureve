"""Iteration 29 tests — TestFlight P1 fixes.

Covers:
- Worn-photo-only item creation (photo=null) succeeds; no-image 400s.
- /capture worn:true returns AI analysis with name/category/confidence.
- Reviewer reconciliation preserves user-added items across restart; canonical demo
  set stays at 16 and stale demo:true rows with non-canonical ids are pruned.
- /calendar/config diagnostic never leaks secret and returns redirect_uri.
- /calendar/authorize still returns a Google URL and stores state.
- Regressions: demo isolation (guest, real, reviewer), bulk-delete, free cap 402,
  monthly stylist/dressme metering, /insights/health-report underused_summary.
- Profiles: create empty secondary wardrobe on premium, 402 on free, premium
  account-level (both profiles report premium:true).
"""
from __future__ import annotations

import base64
import io
import os
import time
import uuid
import subprocess

import pytest
import requests
from pymongo import MongoClient

from conftest import BASE_URL, TEST_TOKEN, _make_clothing_image_b64  # type: ignore

REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = "AureveTest2026"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def reviewer_token() -> str:
    r = requests.post(f"{BASE_URL}/auth/login",
                      json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"reviewer login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def guest_token() -> str:
    r = requests.post(f"{BASE_URL}/auth/guest", timeout=20)
    assert r.status_code == 200, r.text[:200]
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def clothing_b64() -> str:
    return _make_clothing_image_b64()


# -------------------- (1) worn_photo-only item create --------------------
class TestWornPhotoOnly:
    def test_worn_photo_only_creates_item(self, clothing_b64):
        payload = {
            "name": f"TEST_worn_only_{uuid.uuid4().hex[:6]}",
            "category": "Tops",
            "worn_photo": clothing_b64,
            # photo intentionally omitted
        }
        r = requests.post(f"{BASE_URL}/items", json=payload, headers=_bearer(TEST_TOKEN), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        it = r.json()
        assert it.get("id"), it
        assert it.get("photo") in (None, ""), f"expected photo null when only worn_photo set, got {type(it.get('photo'))}"
        assert it.get("worn_photo"), "worn_photo missing on returned item"
        # verify GET persistence
        g = requests.get(f"{BASE_URL}/items", headers=_bearer(TEST_TOKEN), timeout=20)
        assert g.status_code == 200
        found = [x for x in g.json() if x.get("id") == it["id"]]
        assert found, "created item did not persist"
        # cleanup
        requests.delete(f"{BASE_URL}/items/{it['id']}", headers=_bearer(TEST_TOKEN), timeout=10)

    def test_no_image_400s(self):
        payload = {"name": "TEST_noimg", "category": "Tops"}
        r = requests.post(f"{BASE_URL}/items", json=payload, headers=_bearer(TEST_TOKEN), timeout=15)
        assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text[:200]}"
        assert "photo" in r.text.lower()


# -------------------- (2) /capture with worn:true --------------------
class TestCaptureWorn:
    def test_capture_worn_returns_analysis(self, clothing_b64):
        payload = {"image": clothing_b64, "worn": True, "clean": False}
        r = requests.post(f"{BASE_URL}/capture", json=payload, headers=_bearer(TEST_TOKEN), timeout=90)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        body = r.json()
        analysis = body.get("analysis") or {}
        assert analysis.get("name"), f"missing analysis.name in {body}"
        assert analysis.get("category"), f"missing analysis.category in {body}"
        # confidence may be number 0..1 or 0..100
        assert "confidence" in analysis, f"missing confidence in {analysis}"


# -------------------- (3) reviewer reconciliation across restart --------------------
class TestReviewerReconciliation:
    def test_user_item_survives_restart_and_stale_demo_pruned(self, reviewer_token, clothing_b64):
        # 1. baseline demo count on reviewer
        r_list = requests.get(f"{BASE_URL}/items", headers=_bearer(reviewer_token), timeout=20)
        assert r_list.status_code == 200
        before = r_list.json()
        demo_before = [x for x in before if x.get("demo") is True]
        # canonical demo ids look like revdemo-<n>
        canonical_before = [x for x in demo_before if str(x.get("id", "")).startswith("revdemo-")]
        assert len(canonical_before) == 16, f"expected 16 canonical revdemo, got {len(canonical_before)}"

        # 2. reviewer adds a NON-demo item via API
        marker = uuid.uuid4().hex[:8]
        create = requests.post(
            f"{BASE_URL}/items",
            json={"name": f"TEST_reviewer_survives_{marker}", "category": "Tops",
                  "photo": clothing_b64},
            headers=_bearer(reviewer_token), timeout=30,
        )
        assert create.status_code == 200, create.text[:200]
        user_item = create.json()
        user_item_id = user_item["id"]
        assert not user_item.get("demo"), "user-added item should not be demo:true"

        # 3. manually insert a STALE demo:true row with a non-canonical id on the same profile
        stale_id = f"stale_demo_{marker}"
        client = MongoClient(MONGO_URL)
        try:
            profiles = list(client[DB_NAME].profiles.find({}, {"id": 1, "user_id": 1, "_id": 0}))
            # find reviewer profile id: match user_item's user_id (that IS the profile_id in this schema)
            reviewer_profile_id = user_item["user_id"]
            # sanity: profile row exists
            assert any(p["id"] == reviewer_profile_id for p in profiles), \
                f"reviewer profile {reviewer_profile_id} not found among {len(profiles)} profiles"
            client[DB_NAME].items.insert_one({
                "id": stale_id,
                "user_id": reviewer_profile_id,
                "name": "STALE demo",
                "category": "Tops",
                "photo": "",
                "demo": True,
                "created_at": "2024-01-01T00:00:00+00:00",
                "wear_count": 0,
            })
            # 4. restart backend
            rc = subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                                capture_output=True, text=True, timeout=60)
            assert rc.returncode == 0, f"supervisor restart failed: {rc.stderr}"
            # wait for server to come back
            for _ in range(30):
                try:
                    if requests.get(f"{BASE_URL}/", timeout=5).status_code < 500:
                        break
                except Exception:
                    pass
                time.sleep(1)

            # 5. verify user item SURVIVES, canonical revdemo still 16, stale demo PRUNED
            r_after = requests.get(f"{BASE_URL}/items", headers=_bearer(reviewer_token), timeout=30)
            assert r_after.status_code == 200
            after = r_after.json()
            ids_after = {x["id"] for x in after}
            assert user_item_id in ids_after, "reviewer user-added item was DELETED across restart (regression!)"
            canonical_after = [x for x in after if str(x.get("id", "")).startswith("revdemo-")]
            assert len(canonical_after) == 16, \
                f"canonical revdemo count changed: {len(canonical_after)} (expected 16). Duplicates: {[x['id'] for x in canonical_after]}"
            # no duplicates: ids unique
            assert len({x["id"] for x in canonical_after}) == 16
            # stale demo pruned
            assert stale_id not in ids_after, "stale demo:true non-canonical row was NOT pruned"
        finally:
            # cleanup: delete the user item; stale should already be gone
            try:
                requests.delete(f"{BASE_URL}/items/{user_item_id}", headers=_bearer(reviewer_token), timeout=10)
            except Exception:
                pass
            client.close()


# -------------------- (4) /calendar/config diagnostic --------------------
class TestCalendarConfig:
    def test_config_returns_diagnostic_no_secret(self, reviewer_token):
        r = requests.get(f"{BASE_URL}/calendar/config", timeout=15)
        # public endpoint (no auth in code): confirm
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body.get("redirect_uri_sent_to_google", "").endswith("/api/calendar/callback"), body
        assert body.get("client_id_tail"), body
        assert body.get("client_secret_present") is True, body
        # secret must NEVER leak
        assert "client_secret" not in body or not isinstance(body.get("client_secret"), str), body
        # explicit safety: no raw secret string present
        assert "GOCSPX" not in r.text, "OAuth client secret leaked in /calendar/config response"


# -------------------- (5) /calendar/authorize still works --------------------
class TestCalendarAuthorize:
    def test_authorize_returns_google_url_and_state(self, reviewer_token):
        r = requests.get(f"{BASE_URL}/calendar/authorize", headers=_bearer(reviewer_token), timeout=20)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        url = body.get("url", "")
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?"), url[:120]
        assert "state=" in url and "redirect_uri=" in url
        # verify state doc was created with redirect_uri
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(url).query)
        state = q.get("state", [""])[0]
        assert state, "no state in URL"
        client = MongoClient(MONGO_URL)
        try:
            st = client[DB_NAME].calendar_oauth_states.find_one({"state": state})
            assert st is not None, "state doc not stored"
            assert st.get("redirect_uri", "").endswith("/api/calendar/callback")
        finally:
            client.close()


# -------------------- (6) demo isolation regression --------------------
class TestDemoIsolation:
    def test_guest_sees_demo(self, guest_token):
        r = requests.get(f"{BASE_URL}/items", headers=_bearer(guest_token), timeout=20)
        assert r.status_code == 200
        items = r.json()
        demo = [x for x in items if x.get("demo") is True]
        assert len(demo) >= 16, f"guest should see >=16 demo, got {len(demo)}"

    def test_real_account_sees_no_demo(self):
        r = requests.get(f"{BASE_URL}/items", headers=_bearer(TEST_TOKEN), timeout=20)
        assert r.status_code == 200
        items = r.json()
        demo = [x for x in items if x.get("demo") is True]
        assert len(demo) == 0, f"real account should see 0 demo, got {len(demo)}"

    def test_reviewer_sees_its_demo(self, reviewer_token):
        r = requests.get(f"{BASE_URL}/items", headers=_bearer(reviewer_token), timeout=20)
        assert r.status_code == 200
        items = r.json()
        demo = [x for x in items if x.get("demo") is True]
        assert len(demo) >= 16, f"reviewer should see >=16 demo, got {len(demo)}"


# -------------------- (7) bulk-delete regression --------------------
class TestBulkDelete:
    def test_bulk_delete_empty_400(self):
        r = requests.post(f"{BASE_URL}/items/bulk-delete", json={"item_ids": []},
                          headers=_bearer(TEST_TOKEN), timeout=15)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_bulk_delete_own_items(self, clothing_b64):
        # create 2 items then bulk-delete
        ids = []
        for i in range(2):
            r = requests.post(f"{BASE_URL}/items",
                              json={"name": f"TEST_bulk_{i}_{uuid.uuid4().hex[:4]}",
                                    "category": "Tops", "photo": clothing_b64},
                              headers=_bearer(TEST_TOKEN), timeout=30)
            assert r.status_code == 200, r.text[:200]
            ids.append(r.json()["id"])
        r = requests.post(f"{BASE_URL}/items/bulk-delete", json={"item_ids": ids},
                          headers=_bearer(TEST_TOKEN), timeout=20)
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("deleted") == 2


# -------------------- (8) /insights/health-report copy --------------------
class TestHealthReport:
    def test_underused_summary_present(self, reviewer_token):
        r = requests.post(f"{BASE_URL}/insights/health-report",
                          json={}, headers=_bearer(reviewer_token), timeout=90)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert "underused_summary" in body, list(body.keys())
        text = str(body).lower()
        assert "wasted money" not in text and "waste of money" not in text


# -------------------- (9) Profiles: premium adds empty secondary --------------------
class TestProfiles:
    def test_premium_creates_empty_secondary_profile(self, reviewer_token):
        name = f"TEST_wardrobe_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE_URL}/profiles", json={"name": name, "emoji": "🧢"},
                          headers=_bearer(reviewer_token), timeout=20)
        assert r.status_code == 200, r.text[:200]
        prof = r.json()
        pid = prof["id"]
        try:
            # items scoped to new profile should be []
            hdr = {**_bearer(reviewer_token), "X-Profile-Id": pid}
            g = requests.get(f"{BASE_URL}/items", headers=hdr, timeout=20)
            assert g.status_code == 200, g.text[:200]
            items = g.json()
            assert isinstance(items, list) and len(items) == 0, \
                f"new secondary wardrobe should be empty, got {len(items)} items"
            # premium remains account-level: /auth/me premium true for both profiles
            for probe_pid in (pid, None):
                h = {**_bearer(reviewer_token)}
                if probe_pid:
                    h["X-Profile-Id"] = probe_pid
                me = requests.get(f"{BASE_URL}/auth/me", headers=h, timeout=15)
                assert me.status_code == 200
                mb = me.json()
                is_prem = mb.get("is_premium") or mb.get("premium") or \
                          (mb.get("user") or {}).get("is_premium") or \
                          (mb.get("account") or {}).get("is_premium")
                assert is_prem, f"expected premium true, got {mb}"
        finally:
            requests.delete(f"{BASE_URL}/profiles/{pid}",
                            headers=_bearer(reviewer_token), timeout=15)

    def test_free_account_gets_402(self, guest_token):
        # guest is Free tier — creating a second profile should 402
        r = requests.post(f"{BASE_URL}/profiles",
                          json={"name": "TEST_free_second", "emoji": "👤"},
                          headers=_bearer(guest_token), timeout=15)
        assert r.status_code == 402, f"{r.status_code} {r.text[:200]}"
