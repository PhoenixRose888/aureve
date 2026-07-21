"""Iteration 12 — Bulk Multi-Add feature backend tests.

Verifies the /api/capture + /api/items contract used by the frontend bulk-add flow
(app/bulk-add.tsx). The frontend loops picked photos and for each one:
  1) POST /api/capture {image, clean: true} -> {analysis, clean_image}
  2) POST /api/items with the exact body shape sent by bulk-add.tsx (name,
     category, colour, fabric, pattern, season, condition, price[STRING], photo,
     style, sleeve_length, formality, tone)
  3) Item should appear in GET /api/items for the same profile.
"""

import base64
import io
import time
from typing import List

import pytest
import requests

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
TOKEN = "test-session-token-aura-123"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _small_clothing_jpeg_b64() -> str:
    """Small realistic-ish clothing JPEG for /capture. Keeps AI call cheap."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (256, 320), (240, 235, 225))
    d = ImageDraw.Draw(img)
    d.polygon([(64, 96), (192, 96), (200, 300), (56, 300)], fill=(230, 230, 245), outline=(140, 140, 160))
    d.polygon([(64, 96), (32, 150), (48, 175), (76, 125)], fill=(220, 220, 235), outline=(140, 140, 160))
    d.polygon([(192, 96), (224, 150), (208, 175), (180, 125)], fill=(220, 220, 235), outline=(140, 140, 160))
    d.arc([104, 82, 152, 130], 0, 180, fill=(120, 120, 120), width=3)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="module")
def clothing_b64():
    return _small_clothing_jpeg_b64()


@pytest.fixture(scope="module")
def created_ids() -> List[str]:
    return []


@pytest.fixture(scope="module", autouse=True)
def _cleanup(created_ids):
    yield
    for iid in created_ids:
        try:
            requests.delete(f"{BASE_URL}/items/{iid}", headers=HEADERS, timeout=15)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 1. /api/capture — the endpoint bulk-add calls per photo
# ---------------------------------------------------------------------------
class TestCaptureEndpoint:
    def test_capture_returns_analysis_and_clean_image(self, clothing_b64):
        """POST /api/capture {image, clean: true} — normal clothing photo."""
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/capture",
            json={"image": clothing_b64, "clean": True},
            headers=HEADERS,
            timeout=180,
        )
        dt = time.time() - t0
        print(f"/capture took {dt:.1f}s, status={r.status_code}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:400]}"
        data = r.json()
        assert "analysis" in data
        assert "clean_image" in data
        analysis = data["analysis"]
        # Analysis should be a dict; may be {} if AI fails but usually populated.
        assert isinstance(analysis, dict), f"analysis not a dict: {type(analysis)}"
        # If analysis populated, sanity-check key fields
        if analysis:
            for k in ("name", "category"):
                if k in analysis:
                    assert isinstance(analysis[k], str)
        # clean_image is either None (best-effort) or a bounded base64 JPEG string
        ci = data["clean_image"]
        if ci is not None:
            assert isinstance(ci, str)
            assert len(ci) > 500, "clean_image suspiciously short"
            assert len(ci) < 400_000, f"clean_image too large ({len(ci)} chars) — compress_b64 didn't run"
            # Should decode to real bytes
            assert base64.b64decode(ci[:400] + "==")[:2] == b"\xff\xd8", "not JPEG magic"
        # Stash for downstream test
        TestCaptureEndpoint._last_analysis = analysis
        TestCaptureEndpoint._last_clean = ci


# ---------------------------------------------------------------------------
# 2. /api/items — the fields bulk-add.tsx sends
# ---------------------------------------------------------------------------
class TestBulkAddContract:
    def test_items_accepts_bulk_add_body_shape(self, clothing_b64, created_ids):
        """Exact body shape sent by app/bulk-add.tsx — including price as STRING.
        The frontend sends `price: String(a.estimated_value)` or "" if missing.
        """
        body = {
            "name": "TEST_BulkPiece Cream tee",
            "category": "Tops",
            "colour": "cream",
            "fabric": "cotton",
            "pattern": "solid",
            "season": "All",
            "condition": "Excellent",
            "price": "42",  # NOTE: string, matches bulk-add.tsx line 62
            "photo": clothing_b64,
            "style": "t-shirt",
            "sleeve_length": "short",
            "formality": "Casual",
            "tone": "Neutral",
        }
        r = requests.post(f"{BASE_URL}/items", json=body, headers=HEADERS, timeout=60)
        assert r.status_code in (200, 201), f"POST /items failed: {r.status_code} {r.text[:400]}"
        it = r.json()
        assert it["name"] == body["name"]
        assert it["category"] == "Tops"
        assert it["colour"] == "cream"
        assert it["fabric"] == "cotton"
        assert it["pattern"] == "solid"
        assert it["season"] == "All"
        assert it["condition"] == "Excellent"
        assert it["style"] == "t-shirt"
        assert it["sleeve_length"] == "short"
        assert it["formality"] == "Casual"
        assert it["tone"] == "Neutral"
        # price string "42" should coerce to float 42.0
        assert it.get("price") == 42.0, f"price not coerced from string: {it.get('price')!r}"
        # photo stored + compressed
        assert isinstance(it.get("photo"), str) and len(it["photo"]) > 100
        assert "id" in it and it["id"].startswith("item_")
        created_ids.append(it["id"])

    def test_items_accepts_empty_string_price(self, clothing_b64, created_ids):
        """bulk-add sends price="" when a.estimated_value is falsy. Must not 422."""
        body = {
            "name": "TEST_BulkPiece NoPrice",
            "category": "Tops",
            "colour": "",
            "fabric": "",
            "pattern": "",
            "season": "All season",  # NOTE: bulk-add's default fallback string
            "condition": "",
            "price": "",  # empty string — potential Pydantic coercion issue
            "photo": clothing_b64,
            "style": "",
            "sleeve_length": "",
            "formality": "",
            "tone": "",
        }
        r = requests.post(f"{BASE_URL}/items", json=body, headers=HEADERS, timeout=60)
        # Document actual behaviour — this test asserts contract holds
        assert r.status_code in (200, 201), (
            f"Empty string price rejected — bulk-add would fail for items with no "
            f"estimated_value. Status={r.status_code} body={r.text[:400]}"
        )
        it = r.json()
        assert it["name"] == body["name"]
        # season sent as "All season" is a valid free string — server just stores it
        assert it["season"] in ("All season", "All")
        # price should be null / None when empty string
        assert it.get("price") in (None, 0, 0.0), f"unexpected price: {it.get('price')!r}"
        created_ids.append(it["id"])

    def test_items_persistence_via_get(self, created_ids):
        """Items created via bulk flow appear in GET /api/items for the same profile."""
        assert created_ids, "no created items to verify — earlier tests failed"
        r = requests.get(f"{BASE_URL}/items", headers=HEADERS, timeout=30)
        assert r.status_code == 200, r.text[:400]
        items = r.json()
        assert isinstance(items, list)
        ids = {it["id"] for it in items}
        for iid in created_ids:
            assert iid in ids, f"Bulk-added item {iid} missing from GET /api/items"
        # Spot-check first created has the expected bulk fields preserved
        target = next(it for it in items if it["id"] == created_ids[0])
        for k in ("style", "sleeve_length", "formality", "tone"):
            assert k in target, f"field {k} missing on retrieved item"
        # pairs_count computed
        assert isinstance(target.get("pairs_count"), int)

    def test_items_by_id_returns_full_record(self, created_ids):
        r = requests.get(f"{BASE_URL}/items/{created_ids[0]}", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text[:400]
        it = r.json()
        assert it["id"] == created_ids[0]
        assert "_id" not in it, "MongoDB _id leaked in response"


# ---------------------------------------------------------------------------
# 3. Full round-trip: capture output → items → list  (integration)
# ---------------------------------------------------------------------------
class TestBulkAddRoundTrip:
    def test_capture_output_can_feed_items(self, clothing_b64, created_ids):
        """Mirror exactly what bulk-add.tsx does per photo: capture -> items -> list."""
        cap = requests.post(
            f"{BASE_URL}/capture",
            json={"image": clothing_b64, "clean": True},
            headers=HEADERS,
            timeout=180,
        )
        assert cap.status_code == 200, cap.text[:400]
        cap_data = cap.json()
        a = cap_data.get("analysis") or {}
        photo = cap_data.get("clean_image") or clothing_b64
        body = {
            "name": "TEST_BulkRoundTrip " + (a.get("name") or "New piece"),
            "category": a.get("category") or "Tops",
            "colour": a.get("colour") or "",
            "fabric": a.get("fabric") or "",
            "pattern": a.get("pattern") or "",
            "season": a.get("season") or "All season",
            "condition": a.get("condition") or "",
            "price": str(a["estimated_value"]) if a.get("estimated_value") else "",
            "photo": photo,
            "style": a.get("style") or "",
            "sleeve_length": a.get("sleeve_length") or "",
            "formality": a.get("formality") or "",
            "tone": a.get("tone") or "",
        }
        r = requests.post(f"{BASE_URL}/items", json=body, headers=HEADERS, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        it = r.json()
        created_ids.append(it["id"])
        # Now verify listing
        lst = requests.get(f"{BASE_URL}/items", headers=HEADERS, timeout=30)
        assert lst.status_code == 200
        assert any(x["id"] == it["id"] for x in lst.json())
