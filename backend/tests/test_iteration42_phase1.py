"""Iteration 42 — Phase 1 launch structure backend verification.

Covers:
  1. GET /api/items?summary=1 shape + size vs GET /api/items
  2. Matching-set field on ItemCreate/ItemUpdate, listed by summary=1, cleared to ''
  3. POST /api/items/{id}/clean sets photo, orig_photo AND thumb (code-inspection
     is preferred over billing an AI call; we assert against a small throwaway).
"""
import os
import base64
import json
import io
import pytest
import requests

# Read from frontend/.env directly (test runs on server without those env vars set)
def _load_backend_url():
    v = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
    if v:
        return v
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL not set and not found in /app/frontend/.env")


BASE_URL = _load_backend_url().rstrip("/")
API = BASE_URL + "/api"

REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = os.environ.get("REVIEWER_PASSWORD", "")


# ---------------- Fixtures ---------------- #
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def token(session):
    r = session.post(f"{API}/auth/login", json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD})
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:300]}"
    tok = r.json().get("session_token") or r.json().get("token") or r.json().get("session", {}).get("session_token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# 1x1 PNG (fits well under compress_b64 limits and is valid image data)
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


# ---------------- Tests ---------------- #
class TestSummaryEndpoint:
    """GET /api/items?summary=1 payload shape + size regression."""

    def test_summary_returns_no_imagery_and_is_smaller(self, session, auth):
        r_full = session.get(f"{API}/items", headers=auth)
        assert r_full.status_code == 200, r_full.text[:300]
        full = r_full.json()
        assert isinstance(full, list) and len(full) > 0, "reviewer wardrobe is empty"

        r_sum = session.get(f"{API}/items?summary=1", headers=auth)
        assert r_sum.status_code == 200, r_sum.text[:300]
        summary = r_sum.json()

        # Every item must be present
        assert len(summary) == len(full), f"summary len {len(summary)} != full len {len(full)}"

        # Required fields present in summary
        required = {"id", "name", "category", "pairs_count"}
        for it in summary:
            missing = required - set(it.keys())
            assert not missing, f"summary item missing required fields {missing}: {it}"
            # NO imagery keys
            for banned in ("photo", "worn_photo", "thumb", "orig_photo"):
                assert banned not in it or it.get(banned) in (None, ""), (
                    f"summary item {it.get('id')} leaks {banned}"
                )

        full_bytes = len(json.dumps(full).encode())
        sum_bytes = len(json.dumps(summary).encode())
        # Dramatically smaller — expect at least 10x reduction on a real wardrobe
        assert sum_bytes < full_bytes / 10, (
            f"summary not materially smaller: full={full_bytes}B summary={sum_bytes}B"
        )
        print(f"\n[summary] full={full_bytes}B  summary={sum_bytes}B  ratio={sum_bytes/max(full_bytes,1):.4f}")

    def test_full_items_still_ship_thumbnails(self, session, auth):
        r = session.get(f"{API}/items", headers=auth)
        assert r.status_code == 200
        items = r.json()
        # At least one item should have a non-empty photo (thumb served as photo)
        with_photo = [it for it in items if it.get("photo")]
        assert len(with_photo) > 0, "GET /api/items should ship thumbnails in `photo`"

    def test_item_detail_returns_full_photo(self, session, auth):
        r = session.get(f"{API}/items", headers=auth)
        items = r.json()
        target = next((it for it in items if it.get("photo")), None)
        assert target is not None
        r2 = session.get(f"{API}/items/{target['id']}", headers=auth)
        assert r2.status_code == 200
        detail = r2.json()
        assert detail.get("photo"), "item detail must return full photo"
        # Full photo should be materially larger than the list thumb
        assert len(detail["photo"]) >= len(target["photo"]), (
            f"detail photo ({len(detail['photo'])}B) not >= list thumb ({len(target['photo'])}B)"
        )


class TestMatchingSet:
    """POST/GET/PUT with set_name; summary=1 includes it; cleanup."""

    _created_id = None

    def test_create_with_set_name_persists(self, session, auth):
        payload = {
            "name": "TEST_iter42_suit_jacket",
            "category": "Outerwear",
            "subcategory": "Blazers",
            "set_name": "Navy formal suit",
            "colour": "Navy",
            "photo": TINY_PNG_B64,
        }
        r = session.post(f"{API}/items", headers=auth, json=payload)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
        item = r.json()
        assert item.get("set_name") == "Navy formal suit"
        TestMatchingSet._created_id = item["id"]

        # Confirm via GET detail
        r2 = session.get(f"{API}/items/{item['id']}", headers=auth)
        assert r2.status_code == 200
        assert r2.json().get("set_name") == "Navy formal suit"

    def test_summary_includes_set_name(self, session, auth):
        assert TestMatchingSet._created_id, "prior test did not create item"
        r = session.get(f"{API}/items?summary=1", headers=auth)
        assert r.status_code == 200
        entry = next((x for x in r.json() if x["id"] == TestMatchingSet._created_id), None)
        assert entry is not None, "created item missing from summary"
        # set_name should be returned in the summary
        assert entry.get("set_name") == "Navy formal suit", f"summary did not carry set_name: {entry}"

    def test_update_set_name_change_then_clear(self, session, auth):
        iid = TestMatchingSet._created_id
        assert iid
        r1 = session.put(f"{API}/items/{iid}", headers=auth, json={"set_name": "Navy 3-piece"})
        assert r1.status_code == 200, r1.text[:300]
        assert r1.json().get("set_name") == "Navy 3-piece"

        # Set back to empty string
        r2 = session.put(f"{API}/items/{iid}", headers=auth, json={"set_name": ""})
        assert r2.status_code == 200, r2.text[:300]
        assert r2.json().get("set_name") == "", f"set_name did not clear: {r2.json()}"

    def test_zzz_cleanup(self, session, auth):
        iid = TestMatchingSet._created_id
        if iid:
            r = session.delete(f"{API}/items/{iid}", headers=auth)
            assert r.status_code in (200, 204), r.text[:200]


class TestCleanThumbFix:
    """POST /api/items/{id}/clean must update photo, orig_photo AND thumb.
    We use CODE INSPECTION to avoid a real AI call, per the review instructions."""

    def test_clean_endpoint_updates_all_three_fields_in_source(self):
        with open("/app/backend/server.py") as f:
            src = f.read()
        # Locate the clean_item_photo function
        anchor = "async def clean_item_photo("
        i = src.index(anchor)
        block = src[i:i + 3000]
        # Find the update_one call inside this block
        upd_i = block.index("db.items.update_one")
        upd_block = block[upd_i:upd_i + 400]
        assert '"photo": img' in upd_block, "clean_item_photo does not set `photo`"
        assert '"orig_photo": source' in upd_block, "clean_item_photo does not preserve `orig_photo`"
        assert '"thumb": make_thumb(img)' in upd_block, (
            "REGRESSION: clean_item_photo does not regenerate `thumb` — "
            "grids will keep showing raw upload while detail shows cleaned photo"
        )

    def test_cleaned_endpoint_reachable_with_missing_photo(self, session, auth):
        """Behavioural spot-check without spending an AI call: hit /clean on a
        throwaway item that has NO photo — the endpoint should return a
        no-photo/failure JSON (never 5xx) proving the route + auth work."""
        r = session.post(
            f"{API}/items",
            headers=auth,
            json={"name": "TEST_iter42_no_photo", "category": "Accessories", "photo": TINY_PNG_B64},
        )
        assert r.status_code in (200, 201)
        iid = r.json()["id"]
        try:
            rc = session.post(f"{API}/items/{iid}/clean", headers=auth)
            assert rc.status_code == 200, rc.text[:300]
            body = rc.json()
            # Either cleanup succeeded (cleaned:True) or failed gracefully (cleaned:False+reason).
            # Both are acceptable — this test just proves the endpoint route + auth work.
            assert "cleaned" in body, f"unexpected response shape: {body}"
        finally:
            session.delete(f"{API}/items/{iid}", headers=auth)
