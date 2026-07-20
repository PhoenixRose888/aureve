"""Regression tests for NEW Aura features (iteration 2).

Covers:
- analyze-item extra keys (formality, tone, style, sleeve_length)
- stylist/suggest confidence_score + score_reasons
- POST /api/items/{id}/compatibility
- laundry lifecycle (Washing -> excluded from stylist -> reset to Ready)
- POST /api/wear with mark_dirty:true sets availability to Dirty
- outfits list hydrated / delete
- plans CRUD + date range filter
- packing/plan (real geocode via Open-Meteo)
- capsule/build
- insights/health-report
"""
import requests
import pytest


# ============================================================
# analyze-item extended fields
# ============================================================
class TestAnalyzeItemExtras:
    def test_analyze_returns_extra_style_fields(self, base_url, auth_headers, clothing_image_b64):
        r = requests.post(
            f"{base_url}/analyze-item",
            headers=auth_headers,
            json={"image": clothing_image_b64},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("formality", "tone", "style", "sleeve_length"):
            assert k in j, f"missing NEW key: {k}"
            assert isinstance(j[k], str)


# ============================================================
# Stylist NEW: confidence_score + score_reasons
# ============================================================
class TestStylistConfidence:
    def test_stylist_returns_confidence_and_reasons(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/stylist/suggest",
            headers=auth_headers,
            json={"occasion": "coffee with friends", "temperature": 20, "weather": "Partly cloudy"},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert "confidence_score" in j, "missing confidence_score"
        assert isinstance(j["confidence_score"], int), f"confidence_score not int: {type(j['confidence_score'])}"
        assert 0 <= j["confidence_score"] <= 100
        assert "score_reasons" in j, "missing score_reasons"
        assert isinstance(j["score_reasons"], list) and len(j["score_reasons"]) >= 1
        assert all(isinstance(x, str) for x in j["score_reasons"])
        assert isinstance(j.get("resolved_items"), list)


# ============================================================
# Compatibility (versatility) - NEW endpoint
# ============================================================
class TestCompatibility:
    def test_compatibility_unauth(self, base_url):
        r = requests.post(f"{base_url}/items/some_id/compatibility")
        assert r.status_code == 401

    def test_compatibility_404(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/items/item_doesnotexist/compatibility",
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 404

    def test_compatibility_ok(self, base_url, auth_headers):
        items = requests.get(f"{base_url}/items", headers=auth_headers).json()
        assert len(items) >= 2, "seed data insufficient"
        focus = items[0]["id"]
        r = requests.post(
            f"{base_url}/items/{focus}/compatibility",
            headers=auth_headers,
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("versatility_score", "summary", "resolved_matches", "match_count"):
            assert k in j, f"missing key {k}"
        assert isinstance(j["versatility_score"], int)
        assert 0 <= j["versatility_score"] <= 100
        assert isinstance(j["summary"], str) and len(j["summary"]) > 1
        assert isinstance(j["resolved_matches"], list) and len(j["resolved_matches"]) >= 1
        for m in j["resolved_matches"]:
            assert "item" in m and "stars" in m and "reason" in m
            assert isinstance(m["stars"], int)
            assert 1 <= m["stars"] <= 5
            assert m["item"]["id"] != focus, "focus item should not be in matches"
        assert isinstance(j["match_count"], int)


# ============================================================
# Laundry lifecycle + stylist exclusion
# ============================================================
@pytest.fixture(scope="class")
def laundry_item(base_url, auth_headers):
    """Create a distinctive item, put it in Washing, yield, and always reset to Ready."""
    payload = {
        "name": "TEST_LAUNDRY_purple_sequin_top",
        "category": "Tops",
        "colour": "Purple",
        "fabric": "Sequin",
        "availability": "Ready",
        "price": 45.0,
    }
    r = requests.post(f"{base_url}/items", headers=auth_headers, json=payload)
    assert r.status_code == 200, r.text
    item = r.json()
    yield item
    # Cleanup: reset to Ready then delete
    requests.put(f"{base_url}/items/{item['id']}", headers=auth_headers, json={"availability": "Ready"})
    requests.delete(f"{base_url}/items/{item['id']}", headers=auth_headers)


class TestLaundry:
    def test_put_availability_washing_appears_in_laundry(self, base_url, auth_headers, laundry_item):
        r = requests.put(
            f"{base_url}/items/{laundry_item['id']}",
            headers=auth_headers,
            json={"availability": "Washing"},
        )
        assert r.status_code == 200
        assert r.json()["availability"] == "Washing"

        lr = requests.get(f"{base_url}/laundry", headers=auth_headers)
        assert lr.status_code == 200
        ids = [i["id"] for i in lr.json()]
        assert laundry_item["id"] in ids, "washing item not in /laundry"

    def test_stylist_excludes_washing_items(self, base_url, auth_headers, laundry_item):
        # Ensure it's washing
        requests.put(
            f"{base_url}/items/{laundry_item['id']}",
            headers=auth_headers,
            json={"availability": "Washing"},
        )
        r = requests.post(
            f"{base_url}/stylist/suggest",
            headers=auth_headers,
            json={"occasion": "casual weekend"},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for slot in j.get("resolved_items", []):
            assert slot["item"]["id"] != laundry_item["id"], "Stylist included a Washing item!"

    def test_reset_to_ready_removes_from_laundry(self, base_url, auth_headers, laundry_item):
        r = requests.put(
            f"{base_url}/items/{laundry_item['id']}",
            headers=auth_headers,
            json={"availability": "Ready"},
        )
        assert r.status_code == 200
        assert r.json()["availability"] == "Ready"
        lr = requests.get(f"{base_url}/laundry", headers=auth_headers)
        ids = [i["id"] for i in lr.json()]
        assert laundry_item["id"] not in ids


# ============================================================
# Wear mark_dirty flow
# ============================================================
class TestWearMarkDirty:
    def test_wear_with_mark_dirty_sets_dirty(self, base_url, auth_headers):
        # Create disposable item
        create = requests.post(
            f"{base_url}/items",
            headers=auth_headers,
            json={"name": "TEST_DIRTY_flow", "category": "Tops", "availability": "Ready"},
        )
        item = create.json()
        try:
            r = requests.post(
                f"{base_url}/wear",
                headers=auth_headers,
                json={
                    "item_ids": [item["id"]],
                    "occasion": "TEST_dirty",
                    "flattering": 3, "comfort": 3, "confidence": 3,
                    "mark_dirty": True,
                },
            )
            assert r.status_code == 200, r.text
            after = requests.get(f"{base_url}/items/{item['id']}", headers=auth_headers).json()
            assert after["availability"] == "Dirty", f"expected Dirty, got {after['availability']}"
            assert after["wear_count"] >= 1
            # And it must appear in /laundry
            lr = requests.get(f"{base_url}/laundry", headers=auth_headers)
            assert item["id"] in [i["id"] for i in lr.json()]
        finally:
            # cleanup: reset to Ready then delete
            requests.put(f"{base_url}/items/{item['id']}", headers=auth_headers, json={"availability": "Ready"})
            requests.delete(f"{base_url}/items/{item['id']}", headers=auth_headers)

    def test_wear_list_hydrated(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/wear", headers=auth_headers)
        assert r.status_code == 200
        logs = r.json()
        assert isinstance(logs, list)
        if logs:
            assert "items" in logs[0], "wear logs should be hydrated with items"


# ============================================================
# Outfits create/list/delete lifecycle
# ============================================================
class TestOutfitsLifecycle:
    def test_outfit_create_list_delete(self, base_url, auth_headers):
        items = requests.get(f"{base_url}/items", headers=auth_headers).json()
        ids = [i["id"] for i in items[:2]]
        assert len(ids) >= 2

        c = requests.post(
            f"{base_url}/outfits",
            headers=auth_headers,
            json={"name": "TEST_lifecycle_outfit", "item_ids": ids, "occasion": "test"},
        )
        assert c.status_code == 200, c.text
        o = c.json()
        assert o["id"].startswith("outfit_")

        listed = requests.get(f"{base_url}/outfits", headers=auth_headers).json()
        found = next((x for x in listed if x["id"] == o["id"]), None)
        assert found is not None
        assert "items" in found and len(found["items"]) == len(ids)

        d = requests.delete(f"{base_url}/outfits/{o['id']}", headers=auth_headers)
        assert d.status_code == 200

        listed2 = requests.get(f"{base_url}/outfits", headers=auth_headers).json()
        assert o["id"] not in [x["id"] for x in listed2]


# ============================================================
# Plans CRUD + range filter
# ============================================================
class TestPlans:
    def test_plans_unauth(self, base_url):
        assert requests.get(f"{base_url}/plans").status_code == 401

    def test_plan_create_range_filter_delete(self, base_url, auth_headers):
        items = requests.get(f"{base_url}/items", headers=auth_headers).json()
        ids = [i["id"] for i in items[:2]]
        assert len(ids) >= 2

        in_range_date = "2026-02-15"
        out_range_date = "2026-06-15"

        p_in = requests.post(
            f"{base_url}/plans",
            headers=auth_headers,
            json={"date": in_range_date, "item_ids": ids, "title": "TEST_plan_in", "occasion": "meeting"},
        )
        assert p_in.status_code == 200, p_in.text
        plan_in = p_in.json()
        assert plan_in["id"].startswith("plan_")

        p_out = requests.post(
            f"{base_url}/plans",
            headers=auth_headers,
            json={"date": out_range_date, "item_ids": ids, "title": "TEST_plan_out", "occasion": "picnic"},
        )
        assert p_out.status_code == 200, p_out.text
        plan_out = p_out.json()

        try:
            # Range query
            r = requests.get(
                f"{base_url}/plans",
                headers=auth_headers,
                params={"from_date": "2026-02-01", "to_date": "2026-02-28"},
            )
            assert r.status_code == 200
            plans = r.json()
            got_ids = [p["id"] for p in plans]
            assert plan_in["id"] in got_ids, "in-range plan missing"
            assert plan_out["id"] not in got_ids, "out-of-range plan leaked"

            # hydrated items
            hydrated = next(p for p in plans if p["id"] == plan_in["id"])
            assert "items" in hydrated and len(hydrated["items"]) == len(ids)
        finally:
            requests.delete(f"{base_url}/plans/{plan_in['id']}", headers=auth_headers)
            requests.delete(f"{base_url}/plans/{plan_out['id']}", headers=auth_headers)

        # verify delete
        r2 = requests.get(
            f"{base_url}/plans",
            headers=auth_headers,
            params={"from_date": "2026-01-01", "to_date": "2026-12-31"},
        )
        remaining = [p["id"] for p in r2.json()]
        assert plan_in["id"] not in remaining
        assert plan_out["id"] not in remaining


# ============================================================
# Packing plan (AI + Open-Meteo)
# ============================================================
class TestPacking:
    def test_packing_plan_ok(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/packing/plan",
            headers=auth_headers,
            json={
                "destination": "Melbourne, Australia",
                "days": 4,
                "occasions": "sightseeing, dinner",
            },
            timeout=180,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("capsule_items", "resolved_outfits", "weather_note", "fits_carry_on"):
            assert k in j, f"missing key {k}"
        assert isinstance(j["capsule_items"], list) and len(j["capsule_items"]) >= 1
        assert isinstance(j["resolved_outfits"], list)
        assert isinstance(j["weather_note"], str)
        assert isinstance(j["fits_carry_on"], bool)
        # destination echoed and geocoded
        assert "Melbourne" in (j.get("destination") or "")


# ============================================================
# Capsule build (theme)
# ============================================================
class TestCapsule:
    def test_capsule_build_work(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/capsule/build",
            headers=auth_headers,
            json={"theme": "Work"},
            timeout=180,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("capsule_items", "resolved_outfits", "summary"):
            assert k in j, f"missing key {k}"
        assert isinstance(j["capsule_items"], list) and len(j["capsule_items"]) >= 1
        assert isinstance(j["resolved_outfits"], list)
        assert isinstance(j["summary"], str) and len(j["summary"]) > 1
        assert j.get("theme") == "Work"


# ============================================================
# Health report
# ============================================================
class TestHealthReport:
    def test_health_report_ok(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/insights/health-report",
            headers=auth_headers,
            timeout=180,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("headline", "wasted_summary", "missing_piece", "stats"):
            assert k in j, f"missing key {k}"
        assert isinstance(j["headline"], str) and len(j["headline"]) > 1
        assert isinstance(j["wasted_summary"], str)
        stats = j["stats"]
        for sk in ("unworn_value", "total_value", "total_items", "unworn_count"):
            assert sk in stats, f"missing stats key {sk}"
        assert isinstance(stats["total_items"], int)
        # missing_piece is an object per prompt
        mp = j["missing_piece"]
        assert isinstance(mp, (dict, str))
