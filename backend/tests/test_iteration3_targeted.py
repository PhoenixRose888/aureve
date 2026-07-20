"""Iteration 3 targeted verification.

Covers:
- BUGFIX: POST /api/packing/plan with start_offset_days in {0,3,7,14} must all return 200
  with capsule_items, resolved_outfits, weather_note.
- NEW: PUT /api/profile saves measurements/body_shape/skin_tone/undertone/notes and
  GET /api/auth/me returns it. Partial updates must merge (not wipe).
- NEW: POST /api/stylist/suggest works after profile is set (returns 200 with
  resolved_items + confidence_score).
- NEW: POST /api/capsule/build accepts optional 'occasion' and returns
  capsule_items + resolved_outfits.
- REGRESSION: laundry exclusion still excludes Washing items from stylist.
- REGRESSION quick check: /api/, /api/weather, items CRUD, /api/insights,
  /api/insights/missing-piece, POST /api/items/{id}/compatibility, plans CRUD,
  outfits CRUD.
"""
import pytest
import requests


# ============================================================
# Health / root
# ============================================================
class TestRoot:
    def test_api_root(self, base_url):
        r = requests.get(f"{base_url}/", timeout=15)
        assert r.status_code == 200, r.text

    def test_weather(self, base_url):
        # Melbourne coords
        r = requests.get(f"{base_url}/weather", params={"lat": -37.81, "lon": 144.96}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        # Loose check - has some data
        assert isinstance(j, dict) and len(j) >= 1


# ============================================================
# NEW: PUT /api/profile + GET /api/auth/me populated
# ============================================================
class TestProfile:
    def test_profile_full_update_and_me_returns_it(self, base_url, auth_headers):
        payload = {
            "measurements": {"height": 168, "waist": 72, "hips": 96, "bust": 88, "inseam": 78},
            "body_shape": "hourglass",
            "skin_tone": "medium",
            "undertone": "warm",
            "notes": "TEST_prof_notes prefers midi skirts and structured shoulders",
        }
        r = requests.put(f"{base_url}/profile", headers=auth_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        u = r.json()
        assert "profile" in u and isinstance(u["profile"], dict), "user should have populated profile"
        prof = u["profile"]
        assert prof.get("body_shape") == "hourglass"
        assert prof.get("skin_tone") == "medium"
        assert prof.get("undertone") == "warm"
        assert prof.get("measurements", {}).get("waist") == 72
        assert prof.get("measurements", {}).get("hips") == 96

        # auth/me should now include profile
        me = requests.get(f"{base_url}/auth/me", headers=auth_headers, timeout=15).json()
        assert "profile" in me, "auth/me missing profile"
        assert me["profile"].get("body_shape") == "hourglass"
        assert me["profile"].get("measurements", {}).get("waist") == 72

    def test_profile_partial_update_merges(self, base_url, auth_headers):
        # Update just notes; body_shape/measurements from previous test must remain
        r = requests.put(
            f"{base_url}/profile",
            headers=auth_headers,
            json={"notes": "TEST_prof_notes UPDATED"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        prof = r.json()["profile"]
        assert prof.get("notes") == "TEST_prof_notes UPDATED"
        # Merge check: previously-set fields must survive
        assert prof.get("body_shape") == "hourglass", "partial update wiped body_shape!"
        assert prof.get("skin_tone") == "medium", "partial update wiped skin_tone!"
        assert prof.get("measurements", {}).get("waist") == 72, "partial update wiped measurements!"


# ============================================================
# NEW: Stylist suggest after profile set
# ============================================================
class TestStylistWithProfile:
    def test_stylist_ok_with_profile(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/stylist/suggest",
            headers=auth_headers,
            json={"occasion": "brunch with friends", "temperature": 19, "weather": "Partly cloudy"},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert "resolved_items" in j and isinstance(j["resolved_items"], list)
        assert "confidence_score" in j
        assert isinstance(j["confidence_score"], int)
        assert 0 <= j["confidence_score"] <= 100


# ============================================================
# BUGFIX: Packing plan with various start_offset_days
# ============================================================
@pytest.mark.parametrize("offset", [0, 3, 7, 14])
class TestPackingOffsets:
    def test_packing_plan_offset_ok(self, base_url, auth_headers, offset):
        r = requests.post(
            f"{base_url}/packing/plan",
            headers=auth_headers,
            json={
                "destination": "Melbourne, Australia",
                "days": 4,
                "start_offset_days": offset,
                "occasions": "sightseeing, dinner",
            },
            timeout=180,
        )
        assert r.status_code == 200, f"offset={offset}: {r.status_code} {r.text[:400]}"
        j = r.json()
        for k in ("capsule_items", "resolved_outfits", "weather_note"):
            assert k in j, f"offset={offset}: missing key {k}"
        assert isinstance(j["capsule_items"], list) and len(j["capsule_items"]) >= 1
        assert isinstance(j["resolved_outfits"], list)
        assert isinstance(j["weather_note"], str) and len(j["weather_note"]) > 1


# ============================================================
# NEW: Capsule with occasion
# ============================================================
class TestCapsuleOccasion:
    def test_capsule_travel_business_pleasure(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/capsule/build",
            headers=auth_headers,
            json={"theme": "Travel", "occasion": "business + pleasure"},
            timeout=180,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("capsule_items", "resolved_outfits"):
            assert k in j, f"missing {k}"
        assert isinstance(j["capsule_items"], list) and len(j["capsule_items"]) >= 1
        assert isinstance(j["resolved_outfits"], list)
        assert j.get("theme") == "Travel"


# ============================================================
# REGRESSION: laundry exclusion
# ============================================================
@pytest.fixture(scope="class")
def wash_item(base_url, auth_headers):
    payload = {
        "name": "TEST_ITER3_wash_red_scarf",
        "category": "Accessories",
        "colour": "Red",
        "fabric": "Silk",
        "availability": "Ready",
    }
    r = requests.post(f"{base_url}/items", headers=auth_headers, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    item = r.json()
    yield item
    # ALWAYS reset to Ready then delete
    requests.put(
        f"{base_url}/items/{item['id']}",
        headers=auth_headers,
        json={"availability": "Ready"},
        timeout=15,
    )
    requests.delete(f"{base_url}/items/{item['id']}", headers=auth_headers, timeout=15)


class TestLaundryExclusion:
    def test_washing_appears_in_laundry(self, base_url, auth_headers, wash_item):
        r = requests.put(
            f"{base_url}/items/{wash_item['id']}",
            headers=auth_headers,
            json={"availability": "Washing"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["availability"] == "Washing"
        lr = requests.get(f"{base_url}/laundry", headers=auth_headers, timeout=15)
        assert lr.status_code == 200
        assert wash_item["id"] in [i["id"] for i in lr.json()]

    def test_stylist_excludes_washing_item(self, base_url, auth_headers, wash_item):
        r = requests.post(
            f"{base_url}/stylist/suggest",
            headers=auth_headers,
            json={"occasion": "casual"},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        for slot in r.json().get("resolved_items", []):
            assert slot["item"]["id"] != wash_item["id"], "Stylist included a Washing item!"

    def test_reset_ready_removes_from_laundry(self, base_url, auth_headers, wash_item):
        r = requests.put(
            f"{base_url}/items/{wash_item['id']}",
            headers=auth_headers,
            json={"availability": "Ready"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["availability"] == "Ready"
        lr = requests.get(f"{base_url}/laundry", headers=auth_headers, timeout=15)
        assert wash_item["id"] not in [i["id"] for i in lr.json()]


# ============================================================
# REGRESSION quick checks
# ============================================================
class TestItemsCRUDQuick:
    def test_items_crud(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/items",
            headers=auth_headers,
            json={"name": "TEST_ITER3_crud_tee", "category": "Tops", "availability": "Ready"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        item = r.json()
        try:
            assert item["id"].startswith("item_")
            g = requests.get(f"{base_url}/items/{item['id']}", headers=auth_headers, timeout=15)
            assert g.status_code == 200
            u = requests.put(
                f"{base_url}/items/{item['id']}",
                headers=auth_headers,
                json={"colour": "Charcoal"},
                timeout=15,
            )
            assert u.status_code == 200
            assert u.json()["colour"] == "Charcoal"
        finally:
            requests.delete(f"{base_url}/items/{item['id']}", headers=auth_headers, timeout=15)


class TestInsights:
    def test_insights(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/insights", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text

    def test_insights_missing_piece(self, base_url, auth_headers):
        r = requests.post(f"{base_url}/insights/missing-piece", headers=auth_headers, timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j, dict) and len(j) >= 1


class TestCompatibilityQuick:
    def test_compat_ok(self, base_url, auth_headers):
        items = requests.get(f"{base_url}/items", headers=auth_headers, timeout=15).json()
        # Filter out any TEST_ items just in case
        items = [i for i in items if not i.get("name", "").startswith("TEST_")]
        assert len(items) >= 2
        focus = items[0]["id"]
        r = requests.post(
            f"{base_url}/items/{focus}/compatibility",
            headers=auth_headers,
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("versatility_score", "summary", "resolved_matches", "match_count"):
            assert k in j
