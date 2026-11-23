"""Iteration 41 — slim embedded items in /outfits, /plans, /collections/{id}.

Verifies (as reviewer review@aureve.app):
- GET /api/outfits: every embedded item has non-empty `photo`, no `orig_photo`,
  no leaked `thumb`, and is materially smaller than the full item photo from
  GET /api/items/{id} (which must still be full quality).
- GET /api/plans: 200, embedded items have non-empty photos, no orig_photo.
- GET /api/collections + GET /api/collections/{id}: outfits inside must have
  embedded items with non-empty photos and no orig_photo.
- Regression: GET /api/items still ships thumbs (no orig_photo leak).
"""
import os
import json
import pytest
import requests

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = os.environ.get("REVIEWER_PASSWORD", "")


@pytest.fixture(scope="module")
def reviewer_headers():
    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"reviewer login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, f"login body missing token: {r.text[:200]}"
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------- Outfits: slimming + payload size ----------------
class TestOutfitsSlim:
    def test_outfits_items_slim_and_smaller(self, reviewer_headers):
        r = requests.get(f"{BASE_URL}/outfits", headers=reviewer_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        outfits = r.json()
        assert isinstance(outfits, list) and len(outfits) > 0, "reviewer must have >= 1 outfit"
        payload_bytes = len(r.content)
        print(f"[/api/outfits payload] {payload_bytes} bytes ({payload_bytes/1024:.1f} KB) — {len(outfits)} outfit(s)")

        # Every embedded item must be slimmed
        checked_item_id = None
        embedded_photo_len = None
        for o in outfits:
            items = o.get("items") or []
            assert len(items) > 0, f"outfit {o.get('id')} has no embedded items"
            for it in items:
                assert "orig_photo" not in it, f"leaked orig_photo on item {it.get('id')}"
                assert "thumb" not in it, f"leaked thumb key on item {it.get('id')}"
                assert it.get("photo"), f"empty photo on item {it.get('id')} — placeholder risk"
                if checked_item_id is None:
                    checked_item_id = it["id"]
                    embedded_photo_len = len(it["photo"])

        # Cross-check: same item from GET /items/{id} must be full-size
        assert checked_item_id, "no item id captured"
        r2 = requests.get(f"{BASE_URL}/items/{checked_item_id}", headers=reviewer_headers, timeout=30)
        assert r2.status_code == 200, r2.text[:300]
        full = r2.json()
        assert full.get("photo"), "full item photo missing"
        full_len = len(full["photo"])
        print(f"[item {checked_item_id}] embedded photo={embedded_photo_len}B  full photo={full_len}B  "
              f"ratio={embedded_photo_len/full_len:.2f}x")
        assert embedded_photo_len < full_len, (
            f"embedded photo ({embedded_photo_len}) is not smaller than full ({full_len})"
        )
        # Materially smaller — thumbnail should be at most ~50% of full
        assert embedded_photo_len * 2 <= full_len, (
            "embedded photo is not materially smaller than full-resolution photo"
        )


# ---------------- Plans regression ----------------
class TestPlansSlim:
    def test_plans_200_and_slim(self, reviewer_headers):
        r = requests.get(f"{BASE_URL}/plans", headers=reviewer_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        plans = r.json()
        assert isinstance(plans, list)
        print(f"[/api/plans] {len(plans)} plan(s), payload={len(r.content)}B")
        for p in plans:
            for it in (p.get("items") or []):
                assert "orig_photo" not in it, "orig_photo leaked in /plans"
                assert it.get("photo"), "empty photo on /plans embedded item"


# ---------------- Collections regression ----------------
class TestCollectionsSlim:
    def test_collections_list_ok(self, reviewer_headers):
        r = requests.get(f"{BASE_URL}/collections", headers=reviewer_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        colls = r.json()
        assert isinstance(colls, list)
        print(f"[/api/collections] {len(colls)} collection(s)")

    def test_collection_detail_outfits_slim(self, reviewer_headers):
        r = requests.get(f"{BASE_URL}/collections", headers=reviewer_headers, timeout=30)
        assert r.status_code == 200
        colls = r.json()
        # Find a collection with at least 1 outfit; if none, create a throwaway
        target = next((c for c in colls if c.get("count", 0) > 0), None)
        cleanup_ids = []
        if target is None:
            # Get any reviewer outfit to link
            o = requests.get(f"{BASE_URL}/outfits", headers=reviewer_headers, timeout=30).json()
            if not o:
                pytest.skip("reviewer has no outfits to attach")
            create = requests.post(
                f"{BASE_URL}/collections",
                headers=reviewer_headers,
                json={"name": "TEST_iter41_slim"},
                timeout=30,
            )
            assert create.status_code == 200, create.text[:200]
            target = create.json()
            cleanup_ids.append(target["id"])
            patch = requests.patch(
                f"{BASE_URL}/collections/{target['id']}",
                headers=reviewer_headers,
                json={"add_outfit": o[0]["id"]},
                timeout=30,
            )
            assert patch.status_code == 200, patch.text[:200]
        try:
            detail = requests.get(
                f"{BASE_URL}/collections/{target['id']}", headers=reviewer_headers, timeout=30
            )
            assert detail.status_code == 200, detail.text[:300]
            body = detail.json()
            outfits = body.get("outfits") or []
            assert len(outfits) > 0, f"collection {target['id']} has no outfits attached"
            for o in outfits:
                for it in (o.get("items") or []):
                    assert "orig_photo" not in it, "orig_photo leaked in /collections/{id}"
                    assert it.get("photo"), "empty photo on collection outfit item"
            print(f"[/api/collections/{target['id']}] payload={len(detail.content)}B "
                  f"outfits={len(outfits)}")
        finally:
            for cid in cleanup_ids:
                requests.delete(f"{BASE_URL}/collections/{cid}", headers=reviewer_headers, timeout=15)


# ---------------- Items list regression (still ships thumbs) ----------------
class TestItemsListRegression:
    def test_items_list_no_orig_photo(self, reviewer_headers):
        r = requests.get(f"{BASE_URL}/items", headers=reviewer_headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert len(items) > 0
        # NB: /items already stripped orig_photo before this iteration; keep as regression.
        for it in items:
            assert "orig_photo" not in it, f"orig_photo leaked on /items for {it.get('id')}"

    def test_item_detail_full_resolution(self, reviewer_headers):
        items = requests.get(f"{BASE_URL}/items", headers=reviewer_headers, timeout=30).json()
        assert items
        detail = requests.get(
            f"{BASE_URL}/items/{items[0]['id']}", headers=reviewer_headers, timeout=30
        )
        assert detail.status_code == 200
        body = detail.json()
        assert body.get("photo"), "item detail must ship full photo"
        # Full-res photos should generally be > 10KB base64
        assert len(body["photo"]) > 8000, (
            f"item detail photo suspiciously small ({len(body['photo'])}B)"
        )
