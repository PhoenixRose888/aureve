"""Iteration 16 — Home/Dress Me/Outfits/Builder demo path backend regression.

Covers:
- GET /items (wardrobe count + category seeding)
- POST /dressme (premium AI outfit generation, resolved_items with photo+category)
- POST /outfits (save look), GET /outfits (resolved with items), DELETE /outfits/{id}
- POST /plans (Set as Today's Outfit), GET /plans

Uses the seeded PREMIUM account (Bearer test-session-token-aura-123 → user_testaura01).
Cleans up any TEST_-prefixed rows created by this run.
"""
import time
import base64
import io
import pytest
import requests


BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
TOKEN = "test-session-token-aura-123"
HDR = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _tiny_jpeg_b64() -> str:
    """Small valid JPEG for seeding items."""
    try:
        from PIL import Image
        img = Image.new("RGB", (160, 200), (230, 220, 210))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return base64.b64encode(b"\xff\xd8\xff\xd9").decode()


@pytest.fixture(scope="module")
def seeded_items():
    """Ensure at least one Tops/Bottoms/Shoes item exists. Return the created ids
    for cleanup so we don't pollute the account long-term."""
    created = []
    b64 = _tiny_jpeg_b64()

    def _has(cat):
        r = requests.get(f"{BASE_URL}/items", headers=HDR, params={"category": cat}, timeout=30)
        return r.status_code == 200 and len([x for x in r.json() if (x.get("availability") or "Ready") == "Ready"]) >= 1

    for cat, name in [("Tops", "TEST_i16 tee"), ("Bottoms", "TEST_i16 pants"), ("Shoes", "TEST_i16 sneakers")]:
        if _has(cat):
            continue
        payload = {
            "name": name,
            "category": cat,
            "colors": ["Neutral"],
            "photo": b64,
            "mime": "image/jpeg",
            "availability": "Ready",
        }
        r = requests.post(f"{BASE_URL}/items", headers=HDR, json=payload, timeout=30)
        assert r.status_code == 200, f"seed {cat} failed: {r.status_code} {r.text}"
        created.append(r.json()["id"])
    yield created
    # cleanup
    for iid in created:
        requests.delete(f"{BASE_URL}/items/{iid}", headers=HDR, timeout=15)


# ------------------------- 1. Health / auth ---------------------------------
class TestAuthAndCounts:
    def test_items_list_ok(self):
        r = requests.get(f"{BASE_URL}/items", headers=HDR, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # every item has required fields for Home count + wardrobe render
        for it in data[:5]:
            assert "id" in it
            assert "category" in it

    def test_outfits_list_ok(self):
        r = requests.get(f"{BASE_URL}/outfits", headers=HDR, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # each outfit has resolved 'items' with photo+category
        for o in data[:3]:
            assert "id" in o and "created_at" in o
            assert "items" in o
            for it in (o.get("items") or [])[:3]:
                assert "category" in it


# ------------------------- 2. Dress Me / AI ---------------------------------
class TestDressMe:
    def test_dressme_generates_look(self, seeded_items):
        body = {"temperature": 22, "weather": "Mild"}
        r = requests.post(f"{BASE_URL}/dressme", headers=HDR, json=body, timeout=90)
        assert r.status_code == 200, f"dressme failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert "resolved_items" in data, f"resolved_items missing: {list(data.keys())}"
        assert len(data["resolved_items"]) >= 1
        # each resolved slot has an item with photo/category
        for ri in data["resolved_items"]:
            assert "item" in ri
            assert "id" in ri["item"]
            assert "category" in ri["item"]
        # summary/explanation used by the Dress Me screen's paragraph
        assert any(k in data for k in ("summary", "explanation", "rationale", "notes"))


# ------------------------- 3. Save / Duplicate / Set-as-today ---------------
class TestOutfitsFlow:
    saved_id = None

    def test_create_outfit_save_look(self, seeded_items):
        items = requests.get(f"{BASE_URL}/items", headers=HDR, timeout=30).json()
        picks = [it["id"] for it in items[:2]]
        assert len(picks) >= 2, "need at least 2 items for outfit creation"
        payload = {
            "name": "TEST_i16 Dress Me look",
            "item_ids": picks,
            "occasion": "casual",
            "notes": "generated in test",
            "source": "ai",
        }
        r = requests.post(f"{BASE_URL}/outfits", headers=HDR, json=payload, timeout=30)
        assert r.status_code == 200, f"create outfit failed: {r.status_code} {r.text}"
        data = r.json()
        assert data["name"] == payload["name"]
        assert data["item_ids"] == picks
        assert "_id" not in data  # ObjectId must be excluded
        TestOutfitsFlow.saved_id = data["id"]

        # verify persistence via GET
        listing = requests.get(f"{BASE_URL}/outfits", headers=HDR, timeout=30).json()
        found = next((o for o in listing if o["id"] == data["id"]), None)
        assert found is not None, "outfit not persisted"
        assert len(found.get("items") or []) == 2, "items not resolved on list"

    def test_duplicate_outfit(self):
        assert TestOutfitsFlow.saved_id
        orig = next(o for o in requests.get(f"{BASE_URL}/outfits", headers=HDR).json()
                    if o["id"] == TestOutfitsFlow.saved_id)
        dup_payload = {
            "name": f"{orig['name']} copy",
            "item_ids": orig.get("item_ids", []),
            "occasion": orig.get("occasion", ""),
            "notes": orig.get("notes", ""),
            "source": "manual",
        }
        r = requests.post(f"{BASE_URL}/outfits", headers=HDR, json=dup_payload, timeout=30)
        assert r.status_code == 200
        dup = r.json()
        assert dup["id"] != TestOutfitsFlow.saved_id
        assert dup["name"].endswith(" copy")
        # cleanup
        requests.delete(f"{BASE_URL}/outfits/{dup['id']}", headers=HDR, timeout=15)

    def test_plans_set_as_today(self):
        assert TestOutfitsFlow.saved_id
        orig = next(o for o in requests.get(f"{BASE_URL}/outfits", headers=HDR).json()
                    if o["id"] == TestOutfitsFlow.saved_id)
        today = time.strftime("%Y-%m-%d")
        payload = {
            "date": today,
            "title": orig["name"],
            "outfit_id": orig["id"],
            "item_ids": orig.get("item_ids", []),
            "occasion": orig.get("occasion", ""),
        }
        r = requests.post(f"{BASE_URL}/plans", headers=HDR, json=payload, timeout=30)
        assert r.status_code == 200, f"plan create failed: {r.status_code} {r.text}"
        plan = r.json()
        assert plan["date"] == today
        assert plan["outfit_id"] == orig["id"]
        assert "_id" not in plan

        # verify via GET
        plans = requests.get(f"{BASE_URL}/plans", headers=HDR,
                             params={"from_date": today, "to_date": today}, timeout=30).json()
        assert any(p["id"] == plan["id"] for p in plans)
        # cleanup this plan
        requests.delete(f"{BASE_URL}/plans/{plan['id']}", headers=HDR, timeout=15)

    def test_delete_outfit(self):
        assert TestOutfitsFlow.saved_id
        r = requests.delete(f"{BASE_URL}/outfits/{TestOutfitsFlow.saved_id}", headers=HDR, timeout=15)
        assert r.status_code == 200
        # confirm gone
        listing = requests.get(f"{BASE_URL}/outfits", headers=HDR, timeout=30).json()
        assert not any(o["id"] == TestOutfitsFlow.saved_id for o in listing)
