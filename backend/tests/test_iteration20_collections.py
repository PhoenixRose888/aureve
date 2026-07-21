"""Backend tests for Collections CRUD (iteration 20).

Covers:
- POST /api/collections (create)
- GET /api/collections (list, with count + cover)
- GET /api/collections/{id} (detail with outfits resolved)
- PATCH /api/collections/{id} (add_outfit, remove_outfit, rename)
- DELETE /api/collections/{id}
- DELETE /api/outfits/{id} pulls outfit from any collection's outfit_ids
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")
TOKEN = "test-session-token-aura-123"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


@pytest.fixture(scope="module")
def saved_outfits(api):
    r = api.get(f"{BASE_URL}/api/outfits", timeout=30)
    assert r.status_code == 200, f"list outfits: {r.status_code} {r.text[:200]}"
    outfits = r.json()
    assert isinstance(outfits, list)
    return outfits


# Track collection ids created during this run for cleanup
_created_ids: list = []


@pytest.fixture(scope="module", autouse=True)
def cleanup(api):
    yield
    for cid in _created_ids:
        try:
            api.delete(f"{BASE_URL}/api/collections/{cid}", timeout=15)
        except Exception:
            pass


# ---------------- Collections CRUD ----------------
class TestCollectionsCRUD:
    def test_create_collection(self, api):
        name = f"TEST_Coll_{uuid.uuid4().hex[:6]}"
        r = api.post(f"{BASE_URL}/api/collections", json={"name": name}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == name
        assert data["count"] == 0
        assert data["cover"] == []
        assert "id" in data
        _created_ids.append(data["id"])

    def test_list_collections_shape(self, api):
        # Ensure at least one exists
        if not _created_ids:
            r = api.post(f"{BASE_URL}/api/collections", json={"name": f"TEST_Shape_{uuid.uuid4().hex[:4]}"}, timeout=15)
            _created_ids.append(r.json()["id"])
        r = api.get(f"{BASE_URL}/api/collections", timeout=15)
        assert r.status_code == 200
        colls = r.json()
        assert isinstance(colls, list) and len(colls) >= 1
        c0 = colls[0]
        for k in ("id", "name", "count", "cover"):
            assert k in c0, f"missing field {k}"
        assert isinstance(c0["cover"], list)

    def test_get_detail_empty(self, api):
        cid = _created_ids[0]
        r = api.get(f"{BASE_URL}/api/collections/{cid}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == cid
        assert "outfits" in data and isinstance(data["outfits"], list)
        assert "outfit_ids" in data and isinstance(data["outfit_ids"], list)

    def test_get_detail_not_found(self, api):
        r = api.get(f"{BASE_URL}/api/collections/nonexistent-xyz", timeout=15)
        assert r.status_code == 404

    def test_patch_add_and_remove_outfit(self, api, saved_outfits):
        if not saved_outfits:
            pytest.skip("No saved outfits to add")
        cid = _created_ids[0]
        oid = saved_outfits[0]["id"]

        # add
        r = api.patch(f"{BASE_URL}/api/collections/{cid}", json={"add_outfit": oid}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert oid in data["outfit_ids"]
        assert data["count"] == 1
        assert len(data["outfits"]) == 1
        assert data["outfits"][0]["id"] == oid
        # cover should have some items if outfit had items
        assert isinstance(data.get("cover"), list)

        # add again (idempotent via $addToSet)
        r = api.patch(f"{BASE_URL}/api/collections/{cid}", json={"add_outfit": oid}, timeout=15)
        assert r.status_code == 200
        assert r.json()["count"] == 1, "add_outfit should be idempotent"

        # verify via GET
        r = api.get(f"{BASE_URL}/api/collections/{cid}", timeout=15)
        assert r.status_code == 200
        assert oid in r.json()["outfit_ids"]

        # remove
        r = api.patch(f"{BASE_URL}/api/collections/{cid}", json={"remove_outfit": oid}, timeout=15)
        assert r.status_code == 200
        assert oid not in r.json()["outfit_ids"]
        assert r.json()["count"] == 0

    def test_patch_rename(self, api):
        cid = _created_ids[0]
        new_name = f"TEST_Renamed_{uuid.uuid4().hex[:4]}"
        r = api.patch(f"{BASE_URL}/api/collections/{cid}", json={"name": new_name}, timeout=15)
        assert r.status_code == 200
        assert r.json()["name"] == new_name
        # verify via GET
        r = api.get(f"{BASE_URL}/api/collections/{cid}", timeout=15)
        assert r.json()["name"] == new_name

    def test_patch_not_found(self, api):
        r = api.patch(f"{BASE_URL}/api/collections/nonexistent-xyz", json={"name": "x"}, timeout=15)
        assert r.status_code == 404

    def test_delete_collection(self, api):
        # create + delete a fresh one
        name = f"TEST_ToDelete_{uuid.uuid4().hex[:4]}"
        r = api.post(f"{BASE_URL}/api/collections", json={"name": name}, timeout=15)
        cid = r.json()["id"]
        r = api.delete(f"{BASE_URL}/api/collections/{cid}", timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        # GET should now 404
        r = api.get(f"{BASE_URL}/api/collections/{cid}", timeout=15)
        assert r.status_code == 404


# ---------------- Outfit deletion pulls from collections ----------------
class TestOutfitDeletePullsFromCollections:
    def test_delete_outfit_removes_from_collection(self, api, saved_outfits):
        """Create outfit → add to a fresh collection → delete outfit → verify collection.outfit_ids no longer contains it."""
        # get an item to build an outfit with
        r = api.get(f"{BASE_URL}/api/items", timeout=15)
        assert r.status_code == 200
        items = r.json()
        if not items:
            pytest.skip("no items available to build an outfit")
        item_ids = [items[0]["id"]]

        # create outfit
        r = api.post(
            f"{BASE_URL}/api/outfits",
            json={"name": "TEST_OutfitForCollDel", "item_ids": item_ids},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        outfit_id = r.json()["id"]

        # create collection
        r = api.post(f"{BASE_URL}/api/collections", json={"name": f"TEST_DelPull_{uuid.uuid4().hex[:4]}"}, timeout=15)
        cid = r.json()["id"]
        _created_ids.append(cid)

        # add outfit to collection
        r = api.patch(f"{BASE_URL}/api/collections/{cid}", json={"add_outfit": outfit_id}, timeout=15)
        assert r.status_code == 200
        assert outfit_id in r.json()["outfit_ids"]

        # delete the outfit
        r = api.delete(f"{BASE_URL}/api/outfits/{outfit_id}", timeout=15)
        assert r.status_code == 200

        # verify it was pulled from the collection
        r = api.get(f"{BASE_URL}/api/collections/{cid}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert outfit_id not in data["outfit_ids"], "outfit id should be pulled from collection.outfit_ids after outfit deletion"
        assert data["count"] == 0


# ---------------- Auth ----------------
class TestCollectionsAuth:
    def test_unauthorized(self):
        r = requests.get(f"{BASE_URL}/api/collections", timeout=15)
        assert r.status_code in (401, 403)
