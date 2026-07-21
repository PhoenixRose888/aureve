"""Iteration 11 — Backend verification for image-compression fix (blank-image bug).

Verifies:
1. POST /api/items with an oversized base64 photo → stored photo is compressed to a bounded JPEG.
2. PUT /api/items/{id} with an oversized photo → stored photo is compressed.
3. POST /api/capture returns clean_image that is either null OR bounded (< ~200KB); retry once.
4. GET /api/items → every returned item's photo is < ~250KB base64 and decodes as valid image.
5. Regression: created items round-trip name/category/colour and appear with pairs_count.

NEVER prints full base64 — lengths + first 8 chars only.
Cleans up all TEST_ items via DELETE /api/items/{id}.
"""
import base64
import io
import os
import time
from typing import Optional

import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
TOKEN = "test-session-token-aura-123"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Threshold constants (base64 char count)
BOUND_ITEM_MAX = 250_000       # GET /api/items — every photo should be under this
BOUND_STORED_MAX = 200_000     # After compress_b64 write path
BOUND_CLEAN_MAX = 200_000      # /api/capture.clean_image when present

CREATED_IDS: list = []


def _short(b64: Optional[str]) -> str:
    if not b64:
        return "None"
    return f"len={len(b64)} head={b64[:8]!r}"


def _fetch_large_unsplash_b64() -> Optional[str]:
    """Fetch a real 2400px garment JPEG from Unsplash to use as realistic large upload."""
    try:
        r = requests.get(
            "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=2400&q=95",
            timeout=20,
        )
        if r.status_code == 200 and len(r.content) > 200_000:
            return base64.b64encode(r.content).decode()
    except Exception:
        pass
    return None


def _make_realistic_large_jpeg_b64(size: int = 2000) -> str:
    """Fallback: generate a large, plausibly-photograph-like JPEG (gradient + shapes).
    Real photos have huge uniform regions → JPEG compresses them well, unlike pure noise."""
    img = Image.new("RGB", (size, size), (240, 238, 234))
    px = img.load()
    # Vertical gradient background
    for y in range(size):
        shade = 220 + (y * 30) // size
        for x in range(size):
            px[x, y] = (shade, shade - 2, shade - 5)
    # A "garment" rect with soft interior variation
    for y in range(size // 6, size * 5 // 6):
        for x in range(size // 5, size * 4 // 5):
            r = 40 + ((x + y) % 30)
            g = 60 + ((x * 2 + y) % 25)
            b = 120 + ((y * 3) % 35)
            px[x, y] = (r, g, b)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=95)
    return base64.b64encode(out.getvalue()).decode()


def _make_large_jpeg_b64(size: int = 2000) -> str:
    b = _fetch_large_unsplash_b64()
    if b:
        return b
    return _make_realistic_large_jpeg_b64(size)


def _is_valid_image_b64(b64: str) -> bool:
    try:
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        img.verify()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    yield s
    # Final cleanup: delete every TEST_ item we tracked
    for iid in list(CREATED_IDS):
        try:
            s.delete(f"{BASE_URL}/api/items/{iid}", timeout=15)
        except Exception:
            pass


@pytest.fixture(scope="module")
def large_b64():
    b = _make_large_jpeg_b64(2000)
    print(f"\n[fixture] large_b64 {_short(b)}  raw_bytes~{len(base64.b64decode(b))}")
    assert len(b) > 300_000, f"Test fixture must be >300KB base64, got {len(b)}"
    return b


# ------------------------------------------------------------------
# 1) POST /api/items with a large photo → stored bounded JPEG
# ------------------------------------------------------------------
class TestCreateItemCompression:
    def test_create_item_compresses_large_photo(self, session, large_b64):
        payload = {
            "name": "TEST_LargePhotoItem",
            "category": "Tops",
            "colour": "blue",
            "photo": large_b64,
        }
        r = session.post(f"{BASE_URL}/api/items", json=payload, timeout=60)
        assert r.status_code == 200, f"create failed: {r.status_code} {r.text[:300]}"
        item = r.json()
        assert item.get("id"), "item missing id"
        CREATED_IDS.append(item["id"])
        stored = item.get("photo")
        print(f"[create] input {_short(large_b64)} -> stored {_short(stored)}")
        assert stored, "stored photo missing"
        assert len(stored) < BOUND_STORED_MAX, f"stored photo not compressed: {len(stored)}"
        # Reduction ratio sanity
        assert len(stored) < len(large_b64) * 0.6, "compression insufficient"
        # Valid JPEG (base64 typically starts with /9j/)
        assert stored.startswith("/9j/"), f"stored not JPEG magic, head={stored[:12]!r}"
        assert _is_valid_image_b64(stored), "stored photo is not a valid decodable image"

        # Round-trip via GET
        rg = session.get(f"{BASE_URL}/api/items/{item['id']}", timeout=15)
        assert rg.status_code == 200
        gitem = rg.json()
        assert gitem["name"] == "TEST_LargePhotoItem"
        assert gitem["category"] == "Tops"
        assert gitem["colour"] == "blue"
        assert gitem.get("photo") and len(gitem["photo"]) < BOUND_STORED_MAX

    def test_create_item_compresses_worn_photo(self, session, large_b64):
        payload = {
            "name": "TEST_WornPhotoItem",
            "category": "Bottoms",
            "colour": "black",
            "photo": large_b64,
            "worn_photo": large_b64,
        }
        r = session.post(f"{BASE_URL}/api/items", json=payload, timeout=60)
        assert r.status_code == 200
        item = r.json()
        CREATED_IDS.append(item["id"])
        stored_worn = item.get("worn_photo")
        print(f"[create] worn stored {_short(stored_worn)}")
        assert stored_worn and len(stored_worn) < BOUND_STORED_MAX
        assert _is_valid_image_b64(stored_worn)


# ------------------------------------------------------------------
# 2) PUT /api/items/{id} with a large photo → stored bounded
# ------------------------------------------------------------------
class TestUpdateItemCompression:
    def test_put_item_compresses_photo(self, session, large_b64):
        # Create small first
        create = session.post(
            f"{BASE_URL}/api/items",
            json={"name": "TEST_UpdatePhotoItem", "category": "Tops", "colour": "red"},
            timeout=30,
        )
        assert create.status_code == 200
        item_id = create.json()["id"]
        CREATED_IDS.append(item_id)

        # Update with large photo
        r = session.put(
            f"{BASE_URL}/api/items/{item_id}",
            json={"photo": large_b64},
            timeout=60,
        )
        assert r.status_code == 200, f"put failed: {r.status_code} {r.text[:300]}"
        updated = r.json()
        stored = updated.get("photo")
        print(f"[update] input {_short(large_b64)} -> stored {_short(stored)}")
        assert stored and len(stored) < BOUND_STORED_MAX
        assert stored.startswith("/9j/")
        assert _is_valid_image_b64(stored)

        # Verify persistence via GET
        rg = session.get(f"{BASE_URL}/api/items/{item_id}", timeout=15)
        gs = rg.json().get("photo")
        assert gs and len(gs) < BOUND_STORED_MAX
        assert _is_valid_image_b64(gs)


# ------------------------------------------------------------------
# 3) POST /api/capture → clean_image null OR bounded JPEG
# ------------------------------------------------------------------
class TestCaptureCleanImageBounded:
    def _small_garment_jpeg(self) -> str:
        """A small, plausible garment-like image (single-colour rect with border)."""
        img = Image.new("RGB", (640, 800), (220, 220, 230))
        # Draw a rectangular "shirt" shape via pixel access
        for y in range(150, 700):
            for x in range(120, 520):
                img.putpixel((x, y), (60, 90, 140))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90)
        return base64.b64encode(out.getvalue()).decode()

    def test_capture_clean_image_bounded_with_retry(self, session):
        garment = self._small_garment_jpeg()
        bounded_seen = False
        last_result = None
        attempts = 0
        # Up to 2 attempts to observe the bounded-image case at least once
        for attempts in range(1, 3):
            t0 = time.time()
            r = session.post(
                f"{BASE_URL}/api/capture",
                json={"image": garment, "category_hint": "Tops", "clean": True},
                timeout=180,
            )
            dt = time.time() - t0
            assert r.status_code == 200, f"capture failed: {r.status_code} {r.text[:300]}"
            body = r.json()
            analysis = body.get("analysis") or {}
            clean_img = body.get("clean_image")
            print(f"[capture attempt {attempts}] {dt:.1f}s analysis_keys={list(analysis.keys())[:5]} clean={_short(clean_img)}")
            assert isinstance(analysis, dict) and analysis, "analysis missing"
            last_result = (analysis, clean_img)
            if clean_img is None:
                # Acceptable fallback, but retry once to try to see bounded case
                continue
            # Must be bounded and valid
            assert len(clean_img) < BOUND_CLEAN_MAX, f"clean_image too large: {len(clean_img)}"
            assert clean_img.startswith("/9j/"), f"clean_image not JPEG magic: {clean_img[:12]!r}"
            assert _is_valid_image_b64(clean_img), "clean_image not a valid image"
            bounded_seen = True
            break

        analysis, clean_img = last_result
        # Assert either bounded_seen OR both attempts were null-fallback (still acceptable per spec)
        if not bounded_seen:
            print("[capture] clean_image was null on both attempts — acceptable fallback per spec")
        assert bounded_seen or clean_img is None


# ------------------------------------------------------------------
# 4) GET /api/items → every photo is < BOUND_ITEM_MAX and valid
# ------------------------------------------------------------------
class TestListItemsAllBounded:
    def test_all_items_bounded_and_valid(self, session):
        r = session.get(f"{BASE_URL}/api/items", timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        oversized = []
        invalid = []
        checked = 0
        for it in items:
            p = it.get("photo")
            if not p:
                continue
            checked += 1
            if len(p) >= BOUND_ITEM_MAX:
                oversized.append((it.get("id"), it.get("name"), len(p)))
            elif not _is_valid_image_b64(p):
                invalid.append((it.get("id"), it.get("name"), len(p)))
        print(f"[list] total={len(items)} with_photo={checked} oversized={len(oversized)} invalid={len(invalid)}")
        if oversized:
            print("[oversized samples]", oversized[:5])
        if invalid:
            print("[invalid samples]", invalid[:5])
        assert oversized == [], f"oversized photos remain: {oversized[:5]}"
        assert invalid == [], f"invalid image photos remain: {invalid[:5]}"


# ------------------------------------------------------------------
# 5) Regression: round-trip name/category/colour and pairs_count
# ------------------------------------------------------------------
class TestRegressionRoundTrip:
    def test_created_item_appears_in_list_with_pairs_count(self, session):
        payload = {"name": "TEST_RegressionTop", "category": "Tops", "colour": "green"}
        r = session.post(f"{BASE_URL}/api/items", json=payload, timeout=15)
        assert r.status_code == 200
        item = r.json()
        CREATED_IDS.append(item["id"])
        assert item["name"] == "TEST_RegressionTop"
        assert item["category"] == "Tops"
        assert item["colour"] == "green"

        r2 = session.get(f"{BASE_URL}/api/items", timeout=30)
        assert r2.status_code == 200
        listed = r2.json()
        found = next((x for x in listed if x["id"] == item["id"]), None)
        assert found is not None, "created item not returned in list"
        assert "pairs_count" in found and isinstance(found["pairs_count"], int)
        print(f"[regression] item {item['id']} pairs_count={found['pairs_count']}")


# ------------------------------------------------------------------
# 6) Explicit final cleanup verification
# ------------------------------------------------------------------
class TestZZZCleanup:
    def test_delete_all_created(self, session):
        remaining = []
        for iid in list(CREATED_IDS):
            dr = session.delete(f"{BASE_URL}/api/items/{iid}", timeout=15)
            if dr.status_code != 200:
                remaining.append((iid, dr.status_code))
            else:
                CREATED_IDS.remove(iid)
        assert not remaining, f"failed to delete: {remaining}"
        print(f"[cleanup] deleted {len(CREATED_IDS) == 0}")
