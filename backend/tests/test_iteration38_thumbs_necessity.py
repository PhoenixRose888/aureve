"""
Iteration 38 backend tests
--------------------------

Covers the two backend deltas introduced in launch polish:

1) Thumbnail/payload discipline on GET /api/items
   - Items store a full `photo` and a ~320px `thumb`.
   - GET /api/items returns `photo = thumb`, no `orig_photo`, no `thumb` leaked.
   - GET /api/items/{id} still returns the FULL photo.

2) Dress Me `resolved_items[].necessity` (core|recommended|optional)
   - Every entry has a valid necessity.
   - Core includes an actual outfit (top+bottom OR dress/bodysuit/jumpsuit) + shoes.
   - No backpack/briefcase/laptop/work bag is styled.
"""

import base64
import io
import os
import re

import pytest
import requests
from PIL import Image


BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = os.environ.get("REVIEWER_PASSWORD", "")


# ------------------------------ helpers ------------------------------
def _large_png_b64(size: int = 1024) -> str:
    """Produce a reasonably large base64 PNG (>60KB) so a thumbnail can be smaller."""
    img = Image.new("RGB", (size, size))
    # Fill with a gradient so PNG compression doesn't shrink to nothing.
    px = img.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = ((x * 255) // size, (y * 255) // size, ((x + y) * 255) // (2 * size))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=1)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def reviewer_token(api_client):
    r = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    token = r.json().get("session_token") or r.json().get("token")
    assert token, f"no session token in login response: {r.json()}"
    return token


@pytest.fixture(scope="module")
def auth_headers(reviewer_token):
    return {"Authorization": f"Bearer {reviewer_token}", "Content-Type": "application/json"}


# ------------------------------ Thumbnail / payload tests ------------------------------
class TestThumbnails:
    def test_post_item_and_list_returns_thumb_only(self, api_client, auth_headers):
        photo_b64 = _large_png_b64(1024)
        stored_full_len = len(photo_b64)

        create_payload = {
            "name": "TEST_iter38_thumb_navy_chinos",
            "category": "Bottoms",
            "colors": ["Navy"],
            "photo": photo_b64,
        }
        cr = api_client.post(f"{BASE_URL}/api/items", json=create_payload, headers=auth_headers, timeout=60)
        assert cr.status_code == 200, f"create failed: {cr.status_code} {cr.text[:300]}"
        created = cr.json()
        item_id = created["id"]

        try:
            # ---- LIST payload discipline ----
            list_resp = api_client.get(f"{BASE_URL}/api/items", headers=auth_headers, timeout=60)
            assert list_resp.status_code == 200
            total_bytes = len(list_resp.content)
            items = list_resp.json()
            assert isinstance(items, list)
            ours = next((it for it in items if it.get("id") == item_id), None)
            assert ours is not None, "created item not in GET /api/items"

            # (b) orig_photo must be absent from list payload
            assert "orig_photo" not in ours, f"orig_photo leaked in list: keys={list(ours.keys())}"
            # (c) thumb must not be leaked as a separate field
            assert "thumb" not in ours, f"thumb leaked as separate field: keys={list(ours.keys())}"

            listed_photo = ours.get("photo")
            assert listed_photo, "no photo returned in list"
            # (a) list photo should be SMALLER than the full stored photo we sent
            assert len(listed_photo) < stored_full_len, (
                f"list photo ({len(listed_photo)}) not smaller than stored full "
                f"({stored_full_len}) — thumbnail substitution failed"
            )

            # ---- DETAIL returns FULL photo ----
            detail = api_client.get(f"{BASE_URL}/api/items/{item_id}", headers=auth_headers, timeout=60)
            assert detail.status_code == 200
            detail_item = detail.json()
            detail_photo = detail_item.get("photo")
            assert detail_photo, "detail photo missing"
            assert len(detail_photo) > len(listed_photo), (
                f"detail photo ({len(detail_photo)}) should be larger than list photo ({len(listed_photo)})"
            )

            print(f"\n[payload] GET /api/items total bytes = {total_bytes}")
            print(f"[payload] stored full photo b64 length = {stored_full_len}")
            print(f"[payload] list photo b64 length       = {len(listed_photo)}")
            print(f"[payload] detail photo b64 length     = {len(detail_photo)}")
            print(f"[payload] items in list               = {len(items)}")
        finally:
            api_client.delete(f"{BASE_URL}/api/items/{item_id}", headers=auth_headers, timeout=30)

    def test_no_orig_photo_or_thumb_leaked_anywhere_in_list(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/items", headers=auth_headers, timeout=60)
        assert r.status_code == 200
        items = r.json()
        for it in items:
            assert "orig_photo" not in it, f"orig_photo leak in {it.get('id')}"
            assert "thumb" not in it, f"thumb leak in {it.get('id')}"


# ------------------------------ Dress Me necessity ------------------------------
BAG_TABOO_RE = re.compile(r"(backpack|rucksack|briefcase|laptop bag|work bag)", re.IGNORECASE)


def _is_core_outfit(core_items):
    """core must contain shoes AND (a top+bottom OR a dress/bodysuit/jumpsuit)."""
    slots = [(x.get("slot") or "").lower() for x in core_items]
    cats = [((x.get("item") or {}).get("category") or "").lower() for x in core_items]
    names = [((x.get("item") or {}).get("name") or "").lower() for x in core_items]
    has_shoes = any("shoe" in s or c == "shoes" for s, c in zip(slots, cats))
    has_top = any("top" in s or c == "tops" for s, c in zip(slots, cats))
    has_bottom = any("bottom" in s or c == "bottoms" for s, c in zip(slots, cats))
    has_dress = any(c == "dresses" or "dress" in s for s, c in zip(slots, cats))
    has_one_piece = has_dress or any(
        re.search(r"(bodysuit|jumpsuit|playsuit|romper)", n) for n in names
    )
    return has_shoes and ((has_top and has_bottom) or has_one_piece)


class TestDressMeNecessity:
    def test_explicit_occasion_has_necessity_and_no_taboo_bag(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/dressme",
            json={"occasion": "coffee with a friend", "temperature": 20, "weather": "clear"},
            headers=auth_headers,
            timeout=90,
        )
        assert r.status_code == 200, f"dressme failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        resolved = data.get("resolved_items") or []
        assert resolved, "resolved_items missing/empty"

        valid = {"core", "recommended", "optional"}
        for slot in resolved:
            nec = slot.get("necessity")
            assert nec in valid, f"invalid necessity {nec!r} for slot {slot.get('slot')}"

        core = [x for x in resolved if x.get("necessity") == "core"]
        assert _is_core_outfit(core), (
            "core items don't form a valid outfit (top+bottom or dress/bodysuit/jumpsuit + shoes). "
            f"core slots={[x.get('slot') for x in core]} cats="
            f"{[(x.get('item') or {}).get('category') for x in core]} names="
            f"{[(x.get('item') or {}).get('name') for x in core]}"
        )

        # No backpack/briefcase/laptop/work bag styled
        for slot in resolved:
            it = slot.get("item") or {}
            name = it.get("name") or ""
            assert not BAG_TABOO_RE.search(name), f"taboo bag styled: {name}"

        print(f"\n[dressme:coffee] resolved={len(resolved)} core={len(core)} "
              f"necessities={[x.get('necessity') for x in resolved]}")

    def test_relaxed_occasion_reports_bag_jewellery_presence(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/dressme",
            json={"occasion": "relaxing at home", "temperature": 21, "weather": "clear"},
            headers=auth_headers,
            timeout=90,
        )
        assert r.status_code == 200, f"dressme relaxed failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        resolved = data.get("resolved_items") or []
        assert resolved

        valid = {"core", "recommended", "optional"}
        for slot in resolved:
            assert slot.get("necessity") in valid

        cats = [((x.get("item") or {}).get("category") or "") for x in resolved]
        has_bag = any(c == "Bags" for c in cats)
        has_jewel = any(c == "Jewellery" for c in cats)
        # We do NOT fail if the AI includes them — just report per the request.
        print(f"\n[dressme:relaxed] included_bag={has_bag} included_jewellery={has_jewel} cats={cats}")

        # Still assert no taboo bag
        for slot in resolved:
            name = ((slot.get("item") or {}).get("name")) or ""
            assert not BAG_TABOO_RE.search(name), f"taboo bag styled in relaxed look: {name}"
