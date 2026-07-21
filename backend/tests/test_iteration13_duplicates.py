"""
Iteration 13 backend tests — duplicate detection in POST /api/capture.

Contract (per review request):
- Response now includes `duplicates` (array) alongside {analysis, clean_image}.
- Each duplicate: {id, name, category, colour, photo}.
- Matching: same category required + score>=3 where colour=+2, style=+2, fabric=+1, pattern=+1.
- Empty wardrobe → duplicates: [].
- Different category items are never returned.

Also regressions:
- /capture returns {analysis, clean_image, duplicates}.
- POST /api/items still accepts bulk-add body (empty price coerced to null).
"""
import os
import time
import requests
import pytest

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
TOKEN = "test-session-token-aura-123"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# --- helpers ---------------------------------------------------------------

CREATED_IDS: list[str] = []


def _cleanup_all():
    for iid in list(CREATED_IDS):
        try:
            requests.delete(f"{BASE_URL}/items/{iid}", headers=HEADERS, timeout=15)
        except Exception:
            pass
    CREATED_IDS.clear()


@pytest.fixture(scope="module", autouse=True)
def _teardown():
    yield
    _cleanup_all()


def _post_item(body: dict) -> dict:
    r = requests.post(f"{BASE_URL}/items", headers=HEADERS, json=body, timeout=30)
    assert r.status_code == 200, f"create item failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    CREATED_IDS.append(data["id"])
    return data


def _capture(img_b64: str, clean: bool = False) -> dict:
    r = requests.post(
        f"{BASE_URL}/capture",
        headers=HEADERS,
        json={"image": img_b64, "clean": clean},
        timeout=90,
    )
    assert r.status_code == 200, f"/capture failed: {r.status_code} {r.text[:300]}"
    return r.json()


# ---------- Module: /capture duplicate detection ----------

class TestCaptureDuplicatesContract:
    """POST /api/capture — response shape and duplicate detection.

    We drive matching with the analysis actually returned by /capture (which uses
    the real AI). We then seed a matching TEST_ item into the wardrobe and expect
    a subsequent /capture on the same image to surface it in `duplicates`.
    """

    def test_response_has_duplicates_key(self, clothing_image_b64):
        """(a) Response ALWAYS includes 'duplicates' key (contract check)."""
        res = _capture(clothing_image_b64)
        assert "analysis" in res, res
        assert "clean_image" in res, res
        assert "duplicates" in res, "response missing 'duplicates' key"
        assert isinstance(res["duplicates"], list), "'duplicates' must be a list"

    def test_seed_duplicate_and_detect(self, clothing_image_b64):
        """(b) Given a matching item exists, /capture returns 1+ duplicate
        with the required shape {id, name, category, colour, photo}."""
        # 1) Learn what the AI sees for this image.
        first = _capture(clothing_image_b64)
        a = first.get("analysis") or {}
        category = a.get("category")
        if not category:
            pytest.skip(f"AI returned no category, cannot seed a matching dupe: {a}")

        # 2) Seed a TEST_ item that matches AI-derived attributes so it must score >=3.
        seed_body = {
            "name": f"TEST_Dupe {int(time.time())}",
            "category": category,
            "colour": a.get("colour") or "cream",
            "style": a.get("style") or "casual",
            "fabric": a.get("fabric") or "cotton",
            "pattern": a.get("pattern") or "solid",
            "photo": clothing_image_b64,
        }
        seeded = _post_item(seed_body)

        # 3) Re-capture; the seeded item should be surfaced.
        second = _capture(clothing_image_b64)
        dups = second.get("duplicates") or []
        assert isinstance(dups, list)
        assert len(dups) >= 1, (
            f"expected 1+ dupe for matched seed, got 0. analysis={second.get('analysis')}"
        )
        ids = [d.get("id") for d in dups]
        assert seeded["id"] in ids, (
            f"seeded id {seeded['id']} not in duplicates {ids}"
        )
        d = next(x for x in dups if x["id"] == seeded["id"])
        # Required duplicate shape.
        for key in ("id", "name", "category", "colour", "photo"):
            assert key in d, f"duplicate missing '{key}': {d}"
        assert d["category"] == category, (
            f"duplicate category mismatch: got {d['category']} want {category}"
        )

    def test_different_category_is_not_returned(self, clothing_image_b64):
        """(c) Items of a different category are NEVER returned as duplicates."""
        first = _capture(clothing_image_b64)
        a = first.get("analysis") or {}
        cat = (a.get("category") or "Tops")
        # Pick a category guaranteed different.
        alt = "Bottoms" if cat != "Bottoms" else "Outerwear"

        seed_body = {
            "name": f"TEST_DiffCat {int(time.time())}",
            "category": alt,
            "colour": a.get("colour") or "cream",
            "style": a.get("style") or "casual",
            "fabric": a.get("fabric") or "cotton",
            "pattern": a.get("pattern") or "solid",
            "photo": clothing_image_b64,
        }
        seeded = _post_item(seed_body)

        res = _capture(clothing_image_b64)
        dups = res.get("duplicates") or []
        seeded_in = any(d.get("id") == seeded["id"] for d in dups)
        assert not seeded_in, (
            f"different-category item leaked into duplicates: {seeded['id']} "
            f"analysis_cat={a.get('category')} seed_cat={alt} dups={dups}"
        )
        # All returned dupes MUST match the analysis category.
        for d in dups:
            assert (d.get("category") or "").lower() == (a.get("category") or "").lower(), (
                f"duplicate category '{d.get('category')}' != analysis '{a.get('category')}'"
            )


class TestCaptureRegression:
    """Regression: existing /capture contract (analysis + clean_image) still holds."""

    def test_capture_still_returns_analysis_and_clean_image(self, clothing_image_b64):
        r = requests.post(
            f"{BASE_URL}/capture",
            headers=HEADERS,
            json={"image": clothing_image_b64, "clean": True},
            timeout=120,
        )
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert "analysis" in j and isinstance(j["analysis"], dict)
        assert "clean_image" in j  # may be None if pillow removal fails, but key exists
        assert "duplicates" in j and isinstance(j["duplicates"], list)


class TestItemsPriceCoercion:
    """Regression: POST /api/items accepts bulk-add body and coerces price='' → null."""

    def test_price_empty_string_coerced_to_null(self, clothing_image_b64):
        body = {
            "name": f"TEST_PriceEmpty {int(time.time())}",
            "category": "Tops",
            "colour": "grey",
            "fabric": "cotton",
            "pattern": "solid",
            "season": "All",
            "condition": "Good",
            "price": "",  # <- the historical 422 case
            "photo": clothing_image_b64,
            "style": "casual",
            "sleeve_length": "short",
            "formality": "casual",
            "tone": "neutral",
        }
        r = requests.post(f"{BASE_URL}/items", headers=HEADERS, json=body, timeout=30)
        assert r.status_code == 200, f"price='' rejected: {r.status_code} {r.text[:300]}"
        j = r.json()
        CREATED_IDS.append(j["id"])
        assert j.get("price") in (None, 0, 0.0), f"price should be null-ish, got {j.get('price')!r}"
        # Verify persistence
        g = requests.get(f"{BASE_URL}/items/{j['id']}", headers=HEADERS, timeout=15)
        assert g.status_code == 200
        assert g.json().get("price") in (None, 0, 0.0)

    def test_price_numeric_string_still_ok(self, clothing_image_b64):
        body = {
            "name": f"TEST_PriceNum {int(time.time())}",
            "category": "Tops",
            "price": "42.5",
            "photo": clothing_image_b64,
        }
        r = requests.post(f"{BASE_URL}/items", headers=HEADERS, json=body, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        CREATED_IDS.append(j["id"])
        assert abs(float(j["price"]) - 42.5) < 1e-6
