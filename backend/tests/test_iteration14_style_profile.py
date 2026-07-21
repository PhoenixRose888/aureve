"""Iteration 14 — Style profile fields (fit_pref, sizes_top, sizes_bottom, style_prefs)
and non-regression of Dress Me on premium account.

Covers:
- PUT /api/profile persists new fields
- GET /api/profiles reflects them under active profile's `profile`
- Partial update merge behaviour (does not wipe unrelated fields)
- POST /api/dressme still returns a valid outfit after profile update
"""
import os
import pytest
import requests

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
TOKEN = "test-session-token-aura-123"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


@pytest.fixture(scope="module")
def active_profile_id(api):
    r = api.get(f"{BASE_URL}/profiles")
    assert r.status_code == 200, r.text
    profs = r.json()
    assert profs and len(profs) >= 1
    return profs[0]["id"]


@pytest.fixture(scope="module", autouse=True)
def snapshot_and_restore(api, active_profile_id):
    """Snapshot the active profile.profile before tests, restore after."""
    r = api.get(f"{BASE_URL}/profiles")
    assert r.status_code == 200
    original = next((p for p in r.json() if p["id"] == active_profile_id), {}).get("profile", {}) or {}
    yield
    # Restore — PUT with all keys that existed. Send None for keys we want to clear (skipped by server).
    # Since server merges, we can only add-back; keys created by tests may linger. Explicitly overwrite to originals.
    restore = {
        "measurements": original.get("measurements", {}),
        "body_shape": original.get("body_shape", ""),
        "skin_tone": original.get("skin_tone", ""),
        "undertone": original.get("undertone", ""),
        "fit_pref": original.get("fit_pref", ""),
        "sizes_top": original.get("sizes_top", ""),
        "sizes_bottom": original.get("sizes_bottom", ""),
        "style_prefs": original.get("style_prefs", []),
        "notes": original.get("notes", ""),
    }
    api.put(f"{BASE_URL}/profile", json=restore)


# ---------------- Profile field persistence ----------------

def test_put_profile_persists_new_style_fields(api, active_profile_id):
    payload = {
        "fit_pref": "Tailored",
        "sizes_top": "M",
        "sizes_bottom": "30",
        "style_prefs": ["Minimal", "Classic", "Smart casual"],
    }
    r = api.put(f"{BASE_URL}/profile", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    prof = data.get("profile") or {}
    assert prof.get("fit_pref") == "Tailored"
    assert prof.get("sizes_top") == "M"
    assert prof.get("sizes_bottom") == "30"
    assert prof.get("style_prefs") == ["Minimal", "Classic", "Smart casual"]


def test_get_profiles_reflects_new_fields(api, active_profile_id):
    r = api.get(f"{BASE_URL}/profiles")
    assert r.status_code == 200
    prof = next((p for p in r.json() if p["id"] == active_profile_id), None)
    assert prof is not None
    p = prof.get("profile") or {}
    assert p.get("fit_pref") == "Tailored"
    assert p.get("sizes_top") == "M"
    assert p.get("sizes_bottom") == "30"
    assert p.get("style_prefs") == ["Minimal", "Classic", "Smart casual"]


def test_partial_update_merges_and_does_not_wipe(api, active_profile_id):
    # Seed richer profile
    api.put(f"{BASE_URL}/profile", json={
        "body_shape": "Hourglass",
        "skin_tone": "Medium",
        "undertone": "Warm",
        "measurements": {"height": "170", "waist": "70"},
        "notes": "loves defined waists",
        "fit_pref": "Tailored",
        "sizes_top": "M",
        "sizes_bottom": "30",
        "style_prefs": ["Minimal", "Classic"],
    })
    # Now send a partial update touching ONLY style_prefs
    r = api.put(f"{BASE_URL}/profile", json={"style_prefs": ["Streetwear", "Edgy"]})
    assert r.status_code == 200, r.text
    p = r.json().get("profile") or {}
    # Updated field
    assert p.get("style_prefs") == ["Streetwear", "Edgy"]
    # Unrelated fields must remain intact (merge, not overwrite)
    assert p.get("body_shape") == "Hourglass"
    assert p.get("skin_tone") == "Medium"
    assert p.get("undertone") == "Warm"
    assert p.get("notes") == "loves defined waists"
    assert p.get("fit_pref") == "Tailored"
    assert p.get("sizes_top") == "M"
    assert p.get("sizes_bottom") == "30"
    m = p.get("measurements") or {}
    assert m.get("height") == "170"
    assert m.get("waist") == "70"


def test_partial_update_touching_only_fit_pref_keeps_style_prefs(api):
    # Change fit_pref only
    r = api.put(f"{BASE_URL}/profile", json={"fit_pref": "Relaxed"})
    assert r.status_code == 200
    p = r.json().get("profile") or {}
    assert p.get("fit_pref") == "Relaxed"
    # style_prefs from previous test should still be there
    assert p.get("style_prefs") == ["Streetwear", "Edgy"]


# ---------------- Dress Me non-regression ----------------

def test_dressme_still_works_with_new_profile_fields(api):
    """After enriching the profile with new style fields, dressme should still 200."""
    # Ensure account has enough ready items — check first
    items = api.get(f"{BASE_URL}/items").json()
    ready = [i for i in items if (i.get("availability") or "Ready") == "Ready"]
    if len(ready) < 2:
        pytest.skip(f"Not enough ready-to-wear items ({len(ready)}) — cannot exercise /dressme.")

    r = api.post(f"{BASE_URL}/dressme", json={"temperature": 18, "weather": "cloudy"})
    # 402 would indicate premium not granted — flag clearly
    assert r.status_code == 200, f"dressme returned {r.status_code}: {r.text[:400]}"
    body = r.json()
    assert "items" in body or "resolved_items" in body, f"missing items/resolved_items: {list(body.keys())}"
    # Should have at least 1 resolved item mapped to wardrobe
    resolved = body.get("resolved_items") or []
    assert isinstance(resolved, list)
    if resolved:
        # Item shape sanity
        first = resolved[0]
        assert "item" in first and "slot" in first
        assert first["item"].get("id")
