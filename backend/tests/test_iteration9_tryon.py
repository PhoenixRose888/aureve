"""
Iteration 9 — Virtual Try-On (POST /api/tryon) backend tests.

Scope:
  1) FREE account → POST /api/tryon returns HTTP 402 (Premium gating).
  2) PREMIUM account:
       - empty person_image → 400
       - item_ids all without photos → 400 ("don't have photos")
       - item_ids=[] and no outfit → 400
  3) PREMIUM happy path: temporarily set a real base64 JPEG on
     item_a9ef0317a93b (White cotton tee), POST /api/tryon with a real
     base64 person JPEG → 200 with non-empty `image` and `mime_type`.
     (Calls the real Gemini image model — may take 30-120s.)
  4) Regression: /api/dressme still 200 for premium; /api/items still
     returns pairs_count.

Cleanup (module teardown): revert item photo → None, unset premium_until,
clear usage collection for user_testaura01.
"""
import os
import io
import base64
import pytest
import requests
from PIL import Image, ImageDraw, ImageFilter
from pymongo import MongoClient

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com"
TOKEN = "test-session-token-aura-123"
USER_ID = "user_testaura01"
PROFILE_ID = "prof_365ddfe52deb"
TEE_ITEM_ID = "item_a9ef0317a93b"  # 'White cotton tee' (photo=null by default)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "X-Profile-Id": PROFILE_ID,
}

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# --------------------------- Fixtures ---------------------------
@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _unset_premium(db):
    db.users.update_one(
        {"user_id": USER_ID},
        {"$unset": {"premium_until": "", "premium_source": "", "trial_used": ""}},
    )
    db.usage.delete_many({"user_id": USER_ID})


def _set_premium(db):
    db.users.update_one(
        {"user_id": USER_ID},
        {"$set": {"premium_until": "2099-01-01T00:00:00+00:00"}},
    )


def _revert_tee_photo(db):
    db.items.update_one({"id": TEE_ITEM_ID}, {"$set": {"photo": None}})


@pytest.fixture(scope="module", autouse=True)
def _global_cleanup(mongo_db):
    # Ensure clean start
    _unset_premium(mongo_db)
    _revert_tee_photo(mongo_db)
    yield
    # Final cleanup — CRITICAL per review request
    _revert_tee_photo(mongo_db)
    _unset_premium(mongo_db)


def _jpeg_person_b64() -> str:
    """Create a plausible person-like full-body silhouette JPEG (~few KB)."""
    w, h = 384, 640
    img = Image.new("RGB", (w, h), (238, 232, 220))
    d = ImageDraw.Draw(img)
    # background gradient
    for y in range(h):
        v = 235 - int(30 * y / h)
        d.line([(0, y), (w, y)], fill=(v, v - 5, v - 10))
    # head
    d.ellipse((w // 2 - 42, 60, w // 2 + 42, 150), fill=(228, 190, 160), outline=(150, 110, 90))
    # neck
    d.rectangle((w // 2 - 15, 145, w // 2 + 15, 175), fill=(228, 190, 160))
    # torso (shirt-less silhouette so try-on can render clothing)
    d.polygon(
        [(w // 2 - 80, 175), (w // 2 + 80, 175), (w // 2 + 95, 380), (w // 2 - 95, 380)],
        fill=(228, 190, 160), outline=(150, 110, 90),
    )
    # arms
    d.polygon([(w // 2 - 80, 180), (w // 2 - 130, 340), (w // 2 - 100, 360), (w // 2 - 60, 200)],
              fill=(228, 190, 160), outline=(150, 110, 90))
    d.polygon([(w // 2 + 80, 180), (w // 2 + 130, 340), (w // 2 + 100, 360), (w // 2 + 60, 200)],
              fill=(228, 190, 160), outline=(150, 110, 90))
    # legs
    d.rectangle((w // 2 - 60, 380, w // 2 - 10, 600), fill=(60, 60, 80), outline=(20, 20, 40))
    d.rectangle((w // 2 + 10, 380, w // 2 + 60, 600), fill=(60, 60, 80), outline=(20, 20, 40))
    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _jpeg_tee_b64() -> str:
    """Create a simple white-tee JPEG to attach as item.photo."""
    w, h = 320, 400
    img = Image.new("RGB", (w, h), (240, 240, 240))
    d = ImageDraw.Draw(img)
    for y in range(h):
        v = 245 - int(20 * y / h)
        d.line([(0, y), (w, y)], fill=(v, v, v))
    # T-shirt shape
    d.polygon([(80, 120), (240, 120), (250, 380), (70, 380)],
              fill=(250, 250, 250), outline=(180, 180, 180))
    d.polygon([(80, 120), (40, 180), (60, 210), (95, 155)],
              fill=(240, 240, 240), outline=(170, 170, 170))
    d.polygon([(240, 120), (280, 180), (260, 210), (225, 155)],
              fill=(240, 240, 240), outline=(170, 170, 170))
    d.arc([130, 105, 190, 155], 0, 180, fill=(140, 140, 140), width=3)
    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="module")
def person_b64():
    return _jpeg_person_b64()


@pytest.fixture(scope="module")
def tee_b64():
    return _jpeg_tee_b64()


# ============================================================
# 1) FREE account gating → 402
# ============================================================
def test_1_free_account_tryon_returns_402(mongo_db, person_b64):
    _unset_premium(mongo_db)
    r = requests.post(
        f"{BASE_URL}/api/tryon",
        headers=HEADERS,
        json={"person_image": person_b64, "item_ids": [TEE_ITEM_ID]},
        timeout=30,
    )
    assert r.status_code == 402, f"Expected 402 for FREE, got {r.status_code}: {r.text[:200]}"


# ============================================================
# 2) PREMIUM 400-cases (validation)
# ============================================================
def test_2a_premium_empty_person_image_returns_400(mongo_db):
    _set_premium(mongo_db)
    r = requests.post(
        f"{BASE_URL}/api/tryon",
        headers=HEADERS,
        json={"person_image": "", "item_ids": [TEE_ITEM_ID]},
        timeout=30,
    )
    assert r.status_code == 400, f"Expected 400 for empty person_image, got {r.status_code}: {r.text[:200]}"
    assert "photo" in r.text.lower()


def test_2b_premium_items_without_photos_returns_400(mongo_db, person_b64):
    # Ensure tee photo is null (default state) and premium is set
    _set_premium(mongo_db)
    _revert_tee_photo(mongo_db)
    r = requests.post(
        f"{BASE_URL}/api/tryon",
        headers=HEADERS,
        json={"person_image": person_b64, "item_ids": [TEE_ITEM_ID]},
        timeout=30,
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"
    assert "photo" in r.text.lower()


def test_2c_premium_empty_item_ids_no_outfit_returns_400(mongo_db, person_b64):
    _set_premium(mongo_db)
    r = requests.post(
        f"{BASE_URL}/api/tryon",
        headers=HEADERS,
        json={"person_image": person_b64, "item_ids": []},
        timeout=30,
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text[:200]}"


# ============================================================
# 3) PREMIUM happy path — REAL Gemini call (30-120s)
# ============================================================
def test_3_premium_happy_path_returns_image(mongo_db, person_b64, tee_b64):
    _set_premium(mongo_db)
    # Temporarily set tee.photo to a real base64 JPEG
    mongo_db.items.update_one({"id": TEE_ITEM_ID}, {"$set": {"photo": tee_b64}})
    try:
        r = requests.post(
            f"{BASE_URL}/api/tryon",
            headers=HEADERS,
            json={"person_image": person_b64, "item_ids": [TEE_ITEM_ID]},
            timeout=180,
        )
        # Log status & shape only; DO NOT print base64 payload
        print(f"tryon status={r.status_code} body_len={len(r.text)}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
        j = r.json()
        assert "image" in j and isinstance(j["image"], str) and len(j["image"]) > 100, \
            f"image missing/too small (len={len(j.get('image', '') or '')})"
        assert "mime_type" in j and j["mime_type"], j.get("mime_type")
        print(
            f"tryon OK — image_len={len(j['image'])}, first10={j['image'][:10]!r}, "
            f"mime={j['mime_type']}"
        )
    finally:
        _revert_tee_photo(mongo_db)


# ============================================================
# 4) Regressions
# ============================================================
def test_4a_regression_dressme_premium_returns_200(mongo_db):
    _set_premium(mongo_db)
    r = requests.post(
        f"{BASE_URL}/api/dressme",
        headers=HEADERS,
        json={},
        timeout=120,
    )
    assert r.status_code == 200, f"/dressme expected 200, got {r.status_code}: {r.text[:200]}"


def test_4b_regression_items_returns_pairs_count(mongo_db):
    r = requests.get(f"{BASE_URL}/api/items", headers=HEADERS, timeout=30)
    assert r.status_code == 200, r.text[:200]
    items = r.json()
    assert isinstance(items, list) and len(items) > 0
    assert "pairs_count" in items[0], f"pairs_count missing: keys={list(items[0].keys())}"
    assert isinstance(items[0]["pairs_count"], int)
