"""Aura backend regression tests.

Covers: health, weather, auth, items CRUD, AI analyze-item, stylist,
shop-check, wear, insights, missing-piece, outfits.
"""
import requests
import pytest


# ---------------- Health & Weather (public) ----------------
class TestHealth:
    def test_root(self, api, base_url):
        r = api.get(f"{base_url}/")
        assert r.status_code == 200
        assert r.json().get("message") == "Aura API"

    def test_weather_ok(self, api, base_url):
        r = api.get(f"{base_url}/weather", params={"lat": 51.5074, "lon": -0.1278})
        assert r.status_code == 200
        j = r.json()
        assert "temperature" in j and "description" in j and "code" in j
        assert isinstance(j["code"], int)

    def test_weather_missing_params(self, api, base_url):
        r = api.get(f"{base_url}/weather")
        assert r.status_code == 422  # FastAPI validation


# ---------------- Auth ----------------
class TestAuth:
    def test_me_without_token(self, api, base_url):
        r = requests.get(f"{base_url}/auth/me")
        assert r.status_code == 401

    def test_me_bad_token(self, api, base_url):
        r = requests.get(f"{base_url}/auth/me", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_me_ok(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/auth/me", headers=auth_headers)
        assert r.status_code == 200
        j = r.json()
        assert j["user_id"] == "user_testaura01"
        assert j["email"] == "tester@aura.app"
        assert "_id" not in j


# ---------------- Items CRUD ----------------
@pytest.fixture(scope="class")
def created_item(base_url, auth_headers):
    payload = {
        "name": "TEST_Charcoal wool coat",
        "category": "Outerwear",
        "colour": "Charcoal",
        "fabric": "Wool",
        "season": "Winter",
        "pattern": "Solid",
        "brand": "TEST_Brand",
        "size": "M",
        "price": 220.0,
        "condition": "Excellent",
    }
    r = requests.post(f"{base_url}/items", headers=auth_headers, json=payload)
    assert r.status_code == 200, r.text
    item = r.json()
    yield item
    # cleanup
    requests.delete(f"{base_url}/items/{item['id']}", headers=auth_headers)


class TestItemsCRUD:
    def test_create_item(self, created_item):
        assert created_item["id"].startswith("item_")
        assert created_item["name"] == "TEST_Charcoal wool coat"
        assert created_item["user_id"] == "user_testaura01"
        assert created_item["wear_count"] == 0
        assert "_id" not in created_item

    def test_list_items_contains_created(self, base_url, auth_headers, created_item):
        r = requests.get(f"{base_url}/items", headers=auth_headers)
        assert r.status_code == 200
        ids = [i["id"] for i in r.json()]
        assert created_item["id"] in ids

    def test_list_items_unauth(self, base_url):
        r = requests.get(f"{base_url}/items")
        assert r.status_code == 401

    def test_get_item(self, base_url, auth_headers, created_item):
        r = requests.get(f"{base_url}/items/{created_item['id']}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_Charcoal wool coat"

    def test_get_item_404(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/items/item_doesnotexist", headers=auth_headers)
        assert r.status_code == 404

    def test_update_item_and_verify_persistence(self, base_url, auth_headers, created_item):
        r = requests.put(
            f"{base_url}/items/{created_item['id']}",
            headers=auth_headers,
            json={"colour": "Navy", "price": 180.0},
        )
        assert r.status_code == 200
        updated = r.json()
        assert updated["colour"] == "Navy"
        assert updated["price"] == 180.0
        # GET to confirm persistence
        r2 = requests.get(f"{base_url}/items/{created_item['id']}", headers=auth_headers)
        assert r2.json()["colour"] == "Navy"

    def test_update_item_empty_400(self, base_url, auth_headers, created_item):
        r = requests.put(
            f"{base_url}/items/{created_item['id']}",
            headers=auth_headers,
            json={},
        )
        assert r.status_code == 400

    def test_list_category_filter(self, base_url, auth_headers, created_item):
        r = requests.get(f"{base_url}/items", headers=auth_headers, params={"category": "Outerwear"})
        assert r.status_code == 200
        for it in r.json():
            assert it["category"] == "Outerwear"

    def test_delete_item(self, base_url, auth_headers):
        # separate create so cleanup fixture doesn't fight us
        r = requests.post(
            f"{base_url}/items",
            headers=auth_headers,
            json={"name": "TEST_delete_me", "category": "Tops"},
        )
        iid = r.json()["id"]
        d = requests.delete(f"{base_url}/items/{iid}", headers=auth_headers)
        assert d.status_code == 200
        g = requests.get(f"{base_url}/items/{iid}", headers=auth_headers)
        assert g.status_code == 404


# ---------------- AI: analyze-item ----------------
class TestAnalyzeItem:
    def test_analyze_item_unauth(self, base_url, clothing_image_b64):
        r = requests.post(f"{base_url}/analyze-item", json={"image": clothing_image_b64})
        assert r.status_code == 401

    def test_analyze_item_ok(self, base_url, auth_headers, clothing_image_b64):
        r = requests.post(
            f"{base_url}/analyze-item",
            headers=auth_headers,
            json={"image": clothing_image_b64},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        # Required keys per prompt
        for k in ("name", "category", "colour", "fabric", "pattern", "season", "condition", "estimated_value"):
            assert k in j, f"missing key: {k}"
        assert isinstance(j["name"], str) and len(j["name"]) > 1


# ---------------- AI: Stylist suggest ----------------
class TestStylist:
    def test_stylist_unauth(self, base_url):
        r = requests.post(f"{base_url}/stylist/suggest", json={"occasion": "brunch"})
        assert r.status_code == 401

    def test_stylist_suggests_only_owned(self, base_url, auth_headers):
        # Get owned item ids
        r_items = requests.get(f"{base_url}/items", headers=auth_headers)
        assert r_items.status_code == 200
        owned_ids = {i["id"] for i in r_items.json()}
        assert len(owned_ids) >= 2, "Seed data too small for stylist test"

        r = requests.post(
            f"{base_url}/stylist/suggest",
            headers=auth_headers,
            json={"occasion": "smart brunch in the city", "temperature": 18, "weather": "Partly cloudy"},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j and "resolved_items" in j
        assert isinstance(j["resolved_items"], list) and len(j["resolved_items"]) >= 1
        for slot in j["resolved_items"]:
            assert slot["item"]["id"] in owned_ids, "Stylist returned item NOT in wardrobe"
        for k in ("styling_notes", "summary"):
            assert k in j


# ---------------- AI: Shop-check ----------------
class TestShopCheck:
    def test_shop_check_unauth(self, base_url, clothing_image_b64):
        r = requests.post(f"{base_url}/shop-check", json={"image": clothing_image_b64})
        assert r.status_code == 401

    def test_shop_check_ok(self, base_url, auth_headers, clothing_image_b64):
        r = requests.post(
            f"{base_url}/shop-check",
            headers=auth_headers,
            json={"image": clothing_image_b64},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("verdict") in ("Buy", "Skip", "Maybe")
        for k in ("item_summary", "reason", "similar_items", "matches_with", "outfits_added", "fills_gap", "gap_note"):
            assert k in j, f"missing key {k}"
        assert isinstance(j["similar_items"], list)
        assert isinstance(j["matches_with"], list)


# ---------------- Outfits ----------------
@pytest.fixture(scope="class")
def outfit_item_ids(base_url, auth_headers):
    r = requests.get(f"{base_url}/items", headers=auth_headers)
    return [i["id"] for i in r.json()[:2]]


class TestOutfits:
    def test_create_outfit(self, base_url, auth_headers, outfit_item_ids):
        assert len(outfit_item_ids) >= 2
        r = requests.post(
            f"{base_url}/outfits",
            headers=auth_headers,
            json={
                "name": "TEST_Brunch look",
                "item_ids": outfit_item_ids,
                "occasion": "brunch",
                "source": "manual",
            },
        )
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["id"].startswith("outfit_")
        assert o["item_ids"] == outfit_item_ids
        assert "_id" not in o

    def test_list_outfits_hydrated(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/outfits", headers=auth_headers)
        assert r.status_code == 200
        outfits = r.json()
        assert isinstance(outfits, list) and len(outfits) >= 1
        # hydrated items array is present
        assert "items" in outfits[0]

    def test_outfits_unauth(self, base_url):
        assert requests.get(f"{base_url}/outfits").status_code == 401


# ---------------- Wear log ----------------
class TestWear:
    def test_wear_increments_wear_count(self, base_url, auth_headers):
        # pick one item, capture wear_count, log wear, verify increment
        r_items = requests.get(f"{base_url}/items", headers=auth_headers)
        item = r_items.json()[0]
        before = item.get("wear_count", 0)

        r = requests.post(
            f"{base_url}/wear",
            headers=auth_headers,
            json={
                "item_ids": [item["id"]],
                "occasion": "TEST_wear",
                "flattering": 4,
                "comfort": 5,
                "confidence": 4,
                "notes": "TEST_",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"].startswith("wear_")

        after = requests.get(f"{base_url}/items/{item['id']}", headers=auth_headers).json()
        assert after["wear_count"] == before + 1
        assert after["last_worn"] is not None

    def test_list_wear(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/wear", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- Insights ----------------
class TestInsights:
    def test_insights_unauth(self, base_url):
        assert requests.get(f"{base_url}/insights").status_code == 401

    def test_insights_shape(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/insights", headers=auth_headers)
        assert r.status_code == 200
        j = r.json()
        for k in (
            "total_items", "total_wears", "total_value", "avg_cost_per_wear",
            "outfits_logged", "avg_flattering", "avg_comfort", "avg_confidence",
            "categories", "most_worn", "least_worn",
        ):
            assert k in j, f"missing key {k}"
        assert isinstance(j["total_items"], int) and j["total_items"] >= 1
        assert isinstance(j["categories"], dict)
        assert isinstance(j["most_worn"], list)


# ---------------- AI: Missing piece ----------------
class TestMissingPiece:
    def test_missing_piece_unauth(self, base_url):
        assert requests.post(f"{base_url}/insights/missing-piece").status_code == 401

    def test_missing_piece_ok(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/insights/missing-piece",
            headers=auth_headers,
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("recommendation", "reason", "avoid"):
            assert k in j and isinstance(j[k], str) and len(j[k]) > 1
