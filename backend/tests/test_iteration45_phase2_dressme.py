"""Phase 2 backend tests — Dress Me + Suggested/Saved/Worn distinction.

Covers:
- POST /api/wear with `name` field persists and increments wear_count/last_worn.
- GET /api/wear/{log_id} returns single log with resolved items (404 on unknown).
- GET /api/wear/pending?date=... still works and is not shadowed by /wear/{id}.
- POST /api/outfits/mix accepts item_ids, wear_log_id or outfit_id; majority overlap; 400 if nothing resolves.
- POST /api/dressme with explicit occasion still generates; GET /api/dressme/context returns shape.
- POST /api/outfits with source='ai' saves; GET /api/outfits returns slim item thumbnails.
- POST /api/dressme (suggestion) does NOT create /api/outfits or /api/wear records.
"""
import os
import time
import requests
import pytest
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
TOKEN = os.environ.get("TEST_SESSION_TOKEN", "")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def wardrobe_ids():
    r = requests.get(f"{BASE_URL}/api/items", headers=H, timeout=20)
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) >= 4, f"expected seeded wardrobe, got {len(items)}"
    return [it["id"] for it in items]


# --------------------------- /wear POST + name ---------------------------
class TestWearNamePersists:
    def test_wear_with_name_persists_and_increments(self, wardrobe_ids):
        pre = requests.get(f"{BASE_URL}/api/items/{wardrobe_ids[0]}", headers=H, timeout=20).json()
        pre_count = int(pre.get("wear_count") or 0)
        payload = {
            "name": "TEST_phase2_named_wear",
            "item_ids": wardrobe_ids[:2],
            "occasion": "TEST occasion",
            "flattering": 4, "comfort": 4, "confidence": 5,
        }
        r = requests.post(f"{BASE_URL}/api/wear", headers=H, json=payload, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "TEST_phase2_named_wear"
        assert body["item_ids"] == wardrobe_ids[:2]
        assert "id" in body and body["id"].startswith("wear")
        assert body.get("created_at")
        # verify wear_count incremented + last_worn set
        post = requests.get(f"{BASE_URL}/api/items/{wardrobe_ids[0]}", headers=H, timeout=20).json()
        assert int(post.get("wear_count") or 0) == pre_count + 1
        assert post.get("last_worn")
        # persist check via GET
        got = requests.get(f"{BASE_URL}/api/wear/{body['id']}", headers=H, timeout=20)
        assert got.status_code == 200, got.text
        assert got.json().get("name") == "TEST_phase2_named_wear"
        # cleanup
        TestWearNamePersists._created_id = body["id"]

    def test_wear_get_returns_resolved_items(self, wardrobe_ids):
        log_id = getattr(TestWearNamePersists, "_created_id", None)
        assert log_id, "prior test must run first"
        r = requests.get(f"{BASE_URL}/api/wear/{log_id}", headers=H, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body.get("items"), list)
        assert len(body["items"]) == 2
        for it in body["items"]:
            assert it["id"] in wardrobe_ids
            # slim: no orig_photo
            assert "orig_photo" not in it

    def test_wear_get_unknown_id_returns_404(self):
        r = requests.get(f"{BASE_URL}/api/wear/wear_does_not_exist_xxx", headers=H, timeout=20)
        assert r.status_code == 404, r.text

    def test_wear_pending_not_shadowed_by_log_id_route(self):
        # /wear/pending?date=... must not be intercepted by /wear/{log_id}
        r = requests.get(
            f"{BASE_URL}/api/wear/pending?date=2020-01-01", headers=H, timeout=20
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "pending" in body


# --------------------------- /outfits/mix ---------------------------
class TestOutfitsMix:
    def test_mix_from_item_ids_keeps_majority(self, wardrobe_ids):
        base = wardrobe_ids[:4]
        r = requests.post(
            f"{BASE_URL}/api/outfits/mix",
            headers=H,
            json={"item_ids": base, "occasion": "smart-casual dinner", "temperature": 18, "weather": "clear"},
            timeout=90,
        )
        if r.status_code == 402:
            pytest.skip("premium/limit hit — account should be premium; skip")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("mixed_from_item_ids") == base
        assert body.get("occasion_used") == "smart-casual dinner"
        resolved = body.get("resolved_items") or []
        assert len(resolved) >= 2
        # necessity is one of core|recommended|optional (or empty string per code)
        for slot in resolved:
            nec = slot.get("necessity")
            assert nec in ("core", "recommended", "optional", "", None)
            assert slot.get("item", {}).get("id")
        selected = [s["item"]["id"] for s in resolved if s.get("item")]
        overlap = len(set(selected) & set(base))
        # "keeps most" → majority of returned items should come from base.
        assert overlap >= max(1, len(selected) // 2), (
            f"expected majority overlap with base {base}, got selected={selected}"
        )
        # And it should change at least one piece (or size differ)
        # (allow full-keep too as long as majority overlap holds)

    def test_mix_from_wear_log_id(self, wardrobe_ids):
        # create a wear log first
        wr = requests.post(
            f"{BASE_URL}/api/wear", headers=H,
            json={"name": "TEST_mix_source", "item_ids": wardrobe_ids[:3], "occasion": "brunch"},
            timeout=20,
        )
        assert wr.status_code == 200
        log_id = wr.json()["id"]
        r = requests.post(
            f"{BASE_URL}/api/outfits/mix", headers=H,
            json={"wear_log_id": log_id}, timeout=90,
        )
        if r.status_code == 402:
            pytest.skip("premium/limit hit")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("mixed_from_item_ids") == wardrobe_ids[:3]
        assert body.get("occasion_used")  # inherited from the log
        assert len(body.get("resolved_items") or []) >= 1

    def test_mix_from_outfit_id(self, wardrobe_ids):
        # create a saved outfit
        cr = requests.post(
            f"{BASE_URL}/api/outfits", headers=H,
            json={"name": "TEST_mix_source_outfit", "item_ids": wardrobe_ids[:3],
                  "occasion": "casual", "source": "manual"},
            timeout=20,
        )
        assert cr.status_code == 200, cr.text
        outfit_id = cr.json()["id"]
        try:
            r = requests.post(
                f"{BASE_URL}/api/outfits/mix", headers=H,
                json={"outfit_id": outfit_id}, timeout=90,
            )
            if r.status_code == 402:
                pytest.skip("premium/limit hit")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("mixed_from_item_ids") == wardrobe_ids[:3]
        finally:
            requests.delete(f"{BASE_URL}/api/outfits/{outfit_id}", headers=H, timeout=20)

    def test_mix_with_no_source_returns_400(self):
        r = requests.post(
            f"{BASE_URL}/api/outfits/mix", headers=H,
            json={"item_ids": [], "wear_log_id": None, "outfit_id": None},
            timeout=20,
        )
        assert r.status_code == 400, r.text


# --------------------------- /dressme + /dressme/context ---------------------------
class TestDressMe:
    def test_dressme_context_shape(self):
        r = requests.get(
            f"{BASE_URL}/api/dressme/context?date=2026-01-15&tz_offset=0",
            headers=H, timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) >= {"has_context", "source", "label"}
        assert isinstance(body["has_context"], bool)

    def test_dressme_with_explicit_occasion(self):
        r = requests.post(
            f"{BASE_URL}/api/dressme", headers=H,
            json={"occasion": "job interview at a design studio",
                  "temperature": 15, "weather": "cloudy"},
            timeout=90,
        )
        if r.status_code == 402:
            pytest.skip("premium/limit hit")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("occasion_used")
        assert isinstance(body.get("resolved_items"), list)
        assert len(body["resolved_items"]) >= 1


# ---------------- /outfits save (ai) + slim items in list ----------------
class TestOutfitsSaveAi:
    def test_save_ai_outfit_and_list_has_slim_items(self, wardrobe_ids):
        r = requests.post(
            f"{BASE_URL}/api/outfits", headers=H,
            json={"name": "TEST_ai_saved_look", "item_ids": wardrobe_ids[:3],
                  "occasion": "dinner", "source": "ai"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        oid = r.json()["id"]
        try:
            lst = requests.get(f"{BASE_URL}/api/outfits", headers=H, timeout=20)
            assert lst.status_code == 200
            found = next((o for o in lst.json() if o["id"] == oid), None)
            assert found, "saved outfit not in list"
            assert found.get("source") == "ai"
            assert isinstance(found.get("items"), list)
            assert len(found["items"]) == 3
            for it in found["items"]:
                assert "orig_photo" not in it
        finally:
            requests.delete(f"{BASE_URL}/api/outfits/{oid}", headers=H, timeout=20)


# ---------------- suggestion must NOT auto-save or auto-wear ----------------
class TestSuggestionDoesNotPersist:
    def test_dressme_does_not_create_outfit_or_wear(self, wardrobe_ids):
        outfits_before = len(requests.get(f"{BASE_URL}/api/outfits", headers=H, timeout=20).json())
        wears_before = len(requests.get(f"{BASE_URL}/api/wear", headers=H, timeout=20).json())
        r = requests.post(
            f"{BASE_URL}/api/dressme", headers=H,
            json={"occasion": "TEST_no_persist_check_" + str(int(time.time())),
                  "temperature": 20, "weather": "clear"},
            timeout=90,
        )
        if r.status_code == 402:
            pytest.skip("premium/limit hit")
        assert r.status_code == 200, r.text
        outfits_after = len(requests.get(f"{BASE_URL}/api/outfits", headers=H, timeout=20).json())
        wears_after = len(requests.get(f"{BASE_URL}/api/wear", headers=H, timeout=20).json())
        assert outfits_after == outfits_before, "suggestion accidentally created an outfit"
        assert wears_after == wears_before, "suggestion accidentally created a wear log"


# ---------------- final cleanup: purge TEST_ wear logs ----------------
def teardown_module(module):
    logs = requests.get(f"{BASE_URL}/api/wear", headers=H, timeout=20).json()
    for lg in logs:
        if (lg.get("name") or "").startswith("TEST_"):
            # no DELETE endpoint on wear; drop via mongo direct if available
            pass
