"""Iteration 27 — Wardrobe persistence + per-profile scoping (RCA regression).

Regression coverage for the P1/P2 bug: on relaunch the frontend used to send
the first /items request without X-Profile-Id, which resolved to the DEFAULT
profile and made items look "lost" (or replaced by another profile's items).

Backend correctness is what we can automate here:
  1. POST /items with X-Profile-Id=A → GET /items with X-Profile-Id=A returns it
     with the exact name+category.
  2. GET /items with X-Profile-Id=B does NOT return that item (no leak).
  3. Repeated GETs are stable (no dropped counts / no server-side race).
  4. Bulk-add several items keeps every (name, category) pair on GET.
  5. The reviewer account (premium) can create+switch a second profile.
"""

import os
import uuid
import time
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
BASE_URL = f"{BASE}/api"

REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = "AureveTest2026"

# Tiny valid JPEG (1x1 white) — server requires a non-empty photo on /items
TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwc"
    "KDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAj/xAAUEAEA"
    "AAAAAAAAAAAAAAAAAAAA/8QAFAEBAAAAAAAAAAAAAAAAAAAAAP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhED"
    "EQA/AL+AB//Z"
)


def H(token, pid=None):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if pid:
        h["X-Profile-Id"] = pid
    return h


# ---------- reviewer session ----------
@pytest.fixture(scope="module")
def reviewer_token():
    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"reviewer login failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, f"no session_token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def me(reviewer_token):
    r = requests.get(f"{BASE_URL}/auth/me", headers=H(reviewer_token), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("premium") is True, f"reviewer must be premium: {data}"
    return data


@pytest.fixture(scope="module")
def profiles(reviewer_token, me):
    """Return (default_pid, second_pid). Create a second profile if the account
    only has one. Track whether we created it so we can clean up."""
    r = requests.get(f"{BASE_URL}/profiles", headers=H(reviewer_token), timeout=15)
    assert r.status_code == 200
    profs = r.json()
    assert len(profs) >= 1
    default_pid = profs[0]["id"]

    created_pid = None
    if len(profs) < 2:
        rc = requests.post(
            f"{BASE_URL}/profiles",
            headers=H(reviewer_token),
            json={"name": f"TEST_MP2_{uuid.uuid4().hex[:6]}", "emoji": "🧪", "kind": "individual"},
            timeout=15,
        )
        assert rc.status_code == 200, f"create 2nd profile failed: {rc.status_code} {rc.text}"
        created_pid = rc.json()["id"]
        second_pid = created_pid
    else:
        # Prefer a non-default that has FEWEST items to avoid touching real data
        # We just pick profs[1] — tests only create/delete their own items.
        second_pid = profs[1]["id"]

    yield default_pid, second_pid

    if created_pid:
        requests.delete(f"{BASE_URL}/profiles/{created_pid}", headers=H(reviewer_token), timeout=15)


# ============================================================
# 1) Persistence — single item name/category preserved after re-GET
# ============================================================
class TestSingleItemPersistence:
    def test_named_item_persists_with_correct_fields(self, reviewer_token, profiles):
        default_pid, second_pid = profiles
        name = f"TEST_persist_purple_oversized_sunglasses_{uuid.uuid4().hex[:6]}"
        payload = {"name": name, "category": "Accessories", "colour": "Purple", "availability": "Ready", "photo": TINY_JPEG_B64}
        r = requests.post(f"{BASE_URL}/items", headers=H(reviewer_token, second_pid), json=payload, timeout=20)
        assert r.status_code == 200, r.text
        item = r.json()
        item_id = item["id"]
        assert item["name"] == name
        assert item["category"] == "Accessories"
        assert item.get("user_id") == second_pid, "item must be scoped to second profile"

        try:
            # Simulate relaunch: brand-new GET with correct header
            r2 = requests.get(f"{BASE_URL}/items", headers=H(reviewer_token, second_pid), timeout=15)
            assert r2.status_code == 200
            found = next((i for i in r2.json() if i["id"] == item_id), None)
            assert found is not None, "item disappeared from owning profile after re-GET"
            assert found["name"] == name, f"NAME MUTATED: got {found['name']!r}"
            assert found["category"] == "Accessories", f"CATEGORY MUTATED: got {found['category']!r}"

            # Cross-profile GET must NOT return this item
            r3 = requests.get(f"{BASE_URL}/items", headers=H(reviewer_token, default_pid), timeout=15)
            assert r3.status_code == 200
            assert item_id not in [i["id"] for i in r3.json()], "cross-profile LEAK"
        finally:
            requests.delete(f"{BASE_URL}/items/{item_id}", headers=H(reviewer_token, second_pid), timeout=15)


# ============================================================
# 2) Bulk add — every item persists with its own name+category
# ============================================================
class TestBulkPersistence:
    def test_bulk_added_items_preserve_names_and_categories(self, reviewer_token, profiles):
        _, second_pid = profiles
        run_id = uuid.uuid4().hex[:6]
        specs = [
            (f"TEST_bulk_navy_tee_{run_id}", "Tops"),
            (f"TEST_bulk_black_jeans_{run_id}", "Bottoms"),
            (f"TEST_bulk_white_sneakers_{run_id}", "Shoes"),
            (f"TEST_bulk_wool_coat_{run_id}", "Outerwear"),
            (f"TEST_bulk_leather_belt_{run_id}", "Accessories"),
        ]
        created = []
        try:
            for name, cat in specs:
                r = requests.post(
                    f"{BASE_URL}/items",
                    headers=H(reviewer_token, second_pid),
                    json={"name": name, "category": cat, "availability": "Ready", "photo": TINY_JPEG_B64},
                    timeout=15,
                )
                assert r.status_code == 200, r.text
                d = r.json()
                created.append(d["id"])
                assert d["name"] == name
                assert d["category"] == cat

            # Simulate relaunch
            time.sleep(0.3)
            r = requests.get(f"{BASE_URL}/items", headers=H(reviewer_token, second_pid), timeout=20)
            assert r.status_code == 200
            by_id = {i["id"]: i for i in r.json()}
            for (name, cat), iid in zip(specs, created):
                assert iid in by_id, f"item {name} missing after re-GET"
                got = by_id[iid]
                assert got["name"] == name, f"NAME MUTATED for {iid}: {got['name']!r}"
                assert got["category"] == cat, f"CATEGORY MUTATED for {iid}: {got['category']!r}"
                # RCA guard: name must NOT collapse to generic 'New tops/shoes/...'
                assert not got["name"].lower().startswith("new "), f"item name reverted to generic: {got['name']}"
        finally:
            for iid in created:
                requests.delete(f"{BASE_URL}/items/{iid}", headers=H(reviewer_token, second_pid), timeout=15)


# ============================================================
# 3) Count stability — repeated GETs return the same total
# ============================================================
class TestCountStability:
    def test_repeated_get_items_count_stable(self, reviewer_token, profiles):
        _, second_pid = profiles
        counts = []
        for _ in range(4):
            r = requests.get(f"{BASE_URL}/items", headers=H(reviewer_token, second_pid), timeout=15)
            assert r.status_code == 200
            counts.append(len(r.json()))
            time.sleep(0.15)
        assert len(set(counts)) == 1, f"item counts drifted across identical GETs: {counts}"


# ============================================================
# 4) Multi-profile switch — items stay under their owning profile
# ============================================================
class TestMultiProfileSwitchStability:
    def test_switching_headers_returns_owner_scoped_lists(self, reviewer_token, profiles):
        default_pid, second_pid = profiles
        run_id = uuid.uuid4().hex[:6]

        r1 = requests.post(
            f"{BASE_URL}/items",
            headers=H(reviewer_token, default_pid),
            json={"name": f"TEST_switch_A_{run_id}", "category": "Tops", "availability": "Ready", "photo": TINY_JPEG_B64},
            timeout=15,
        )
        assert r1.status_code == 200
        item_a = r1.json()["id"]

        r2 = requests.post(
            f"{BASE_URL}/items",
            headers=H(reviewer_token, second_pid),
            json={"name": f"TEST_switch_B_{run_id}", "category": "Bottoms", "availability": "Ready", "photo": TINY_JPEG_B64},
            timeout=15,
        )
        assert r2.status_code == 200
        item_b = r2.json()["id"]

        try:
            # Switch back and forth: each list must contain ONLY the owner's item(s)
            for _ in range(3):
                la = requests.get(f"{BASE_URL}/items", headers=H(reviewer_token, default_pid), timeout=15).json()
                lb = requests.get(f"{BASE_URL}/items", headers=H(reviewer_token, second_pid), timeout=15).json()
                ids_a = {i["id"] for i in la}
                ids_b = {i["id"] for i in lb}
                assert item_a in ids_a and item_a not in ids_b, "profile A item visible to B"
                assert item_b in ids_b and item_b not in ids_a, "profile B item visible to A"
                time.sleep(0.15)
        finally:
            requests.delete(f"{BASE_URL}/items/{item_a}", headers=H(reviewer_token, default_pid), timeout=15)
            requests.delete(f"{BASE_URL}/items/{item_b}", headers=H(reviewer_token, second_pid), timeout=15)


# ============================================================
# 5) Header-missing regression: NO header falls back to DEFAULT profile
#    (documents the exact behaviour the frontend fix now guards against)
# ============================================================
class TestNoHeaderFallbackBehaviour:
    def test_no_header_uses_default_profile_and_hides_other_profile_items(self, reviewer_token, profiles):
        default_pid, second_pid = profiles
        run_id = uuid.uuid4().hex[:6]

        r = requests.post(
            f"{BASE_URL}/items",
            headers=H(reviewer_token, second_pid),
            json={"name": f"TEST_noheader_{run_id}", "category": "Tops", "availability": "Ready", "photo": TINY_JPEG_B64},
            timeout=15,
        )
        assert r.status_code == 200
        item_id = r.json()["id"]

        try:
            # No X-Profile-Id: backend resolves to DEFAULT profile
            r_default_no_hdr = requests.get(f"{BASE_URL}/items", headers=H(reviewer_token), timeout=15).json()
            r_default_hdr = requests.get(f"{BASE_URL}/items", headers=H(reviewer_token, default_pid), timeout=15).json()

            ids_no = sorted(i["id"] for i in r_default_no_hdr)
            ids_def = sorted(i["id"] for i in r_default_hdr)
            assert ids_no == ids_def, "no-header list differs from explicit default"
            assert item_id not in ids_no, (
                "REGRESSION: item created under non-default profile leaked into no-header/default fetch"
            )
        finally:
            requests.delete(f"{BASE_URL}/items/{item_id}", headers=H(reviewer_token, second_pid), timeout=15)
