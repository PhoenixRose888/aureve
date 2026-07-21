"""Iteration 10 — /api/capture (analyze + Gemini background-remove) and Google Calendar endpoints.

Tests:
  - /api/capture with clean=true (real JPEG) — 200, analysis populated, non-empty clean_image
  - /api/capture with clean=false — 200, analysis populated, clean_image is None
  - Backward-compat: /api/analyze-item still returns analysis directly (with category_hint)
  - /api/calendar/status (not connected) — connected:false, configured:true
  - /api/calendar/authorize — {url} contains accounts.google.com + scope + redirect_uri
  - /api/calendar/events — {events:[]}
  - /api/calendar/disconnect — {ok:true}
  - /api/calendar/callback?error=access_denied — HTTP 200 HTML
  - /api/dressme (as premium) — 200 and returns calendar_events (empty)
  - Regression: /api/items returns pairs_count; membership endpoints healthy
"""
import base64
import io
import os
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
TEST_TOKEN = "test-session-token-aura-123"
HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}", "Content-Type": "application/json"}
USER_ID = "user_testaura01"

# Mongo (for premium toggle + cleanup)
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
_mongo = MongoClient(MONGO_URL)
_db = _mongo[DB_NAME]


def _make_jpeg_b64() -> str:
    from PIL import Image, ImageDraw, ImageFilter
    import random
    random.seed(7)
    w, h = 320, 400
    img = Image.new("RGB", (w, h), (240, 235, 225))
    d = ImageDraw.Draw(img)
    for y in range(h):
        shade = 230 - int(20 * y / h)
        d.line([(0, y), (w, y)], fill=(shade, shade - 5, shade - 10))
    d.polygon([(80, 120), (240, 120), (250, 380), (70, 380)], fill=(245, 245, 245), outline=(180, 180, 180))
    d.polygon([(80, 120), (40, 180), (60, 210), (95, 155)], fill=(238, 238, 238))
    d.polygon([(240, 120), (280, 180), (260, 210), (225, 155)], fill=(238, 238, 238))
    d.arc([130, 105, 190, 155], 0, 180, fill=(120, 120, 120), width=3)
    for _ in range(3000):
        x = random.randint(70, 250); y = random.randint(120, 380)
        c = 235 + random.randint(-15, 15)
        d.point((x, y), fill=(c, c, c))
    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="module")
def jpeg_b64():
    return _make_jpeg_b64()


@pytest.fixture(scope="module", autouse=True)
def cleanup_after_module():
    """Ensure clean starting + final state for user_testaura01."""
    # Pre-clean
    _db.users.update_one(
        {"user_id": USER_ID},
        {"$unset": {"premium_until": "", "premium_source": "", "trial_used": ""}},
    )
    _db.usage.delete_many({"user_id": USER_ID})
    _db.calendar_tokens.delete_many({"account_id": USER_ID})
    _db.calendar_oauth_states.delete_many({"account_id": USER_ID})
    yield
    # Post-clean (final)
    _db.users.update_one(
        {"user_id": USER_ID},
        {"$unset": {"premium_until": "", "premium_source": "", "trial_used": ""}},
    )
    _db.usage.delete_many({"user_id": USER_ID})
    _db.calendar_tokens.delete_many({"account_id": USER_ID})
    _db.calendar_oauth_states.delete_many({"account_id": USER_ID})


# ---------------- /api/capture ----------------
class TestCapture:
    def test_capture_clean_true(self, jpeg_b64):
        """clean=true → analysis + non-empty base64 clean_image (Gemini call up to 90s)."""
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/capture",
            headers=HEADERS,
            json={"image": jpeg_b64, "category_hint": "Tops", "clean": True},
            timeout=180,
        )
        elapsed = time.time() - t0
        print(f"[capture clean=true] status={r.status_code} elapsed={elapsed:.1f}s")
        assert r.status_code == 200, f"body={r.text[:300]}"
        body = r.json()
        assert "analysis" in body and "clean_image" in body
        a = body["analysis"]
        assert isinstance(a, dict) and a, "analysis is empty"
        # At least these fields per contract
        assert a.get("name"), f"missing name in analysis keys={list(a.keys())}"
        assert a.get("category"), f"missing category, got {a.get('category')}"
        assert a.get("colour"), f"missing colour, got keys={list(a.keys())}"
        # clean_image should be non-empty base64 (do NOT print full)
        ci = body["clean_image"]
        assert isinstance(ci, str) and len(ci) > 100, f"clean_image too short/absent (len={len(ci) if isinstance(ci,str) else 'N/A'})"
        print(f"[capture clean=true] name={a.get('name')!r} category={a.get('category')!r} "
              f"colour={a.get('colour')!r} clean_image_len={len(ci)} first10={ci[:10]!r}")

    def test_capture_clean_false(self, jpeg_b64):
        """clean=false → analysis present, clean_image is None."""
        r = requests.post(
            f"{BASE_URL}/capture",
            headers=HEADERS,
            json={"image": jpeg_b64, "clean": False},
            timeout=120,
        )
        print(f"[capture clean=false] status={r.status_code}")
        assert r.status_code == 200, f"body={r.text[:300]}"
        body = r.json()
        assert body.get("clean_image") is None, f"expected None, got {type(body.get('clean_image'))}"
        a = body.get("analysis") or {}
        assert a.get("name") and a.get("category"), f"analysis incomplete: keys={list(a.keys())}"


# ---------------- Backward compat: /api/analyze-item ----------------
class TestAnalyzeItemCompat:
    def test_analyze_item_returns_analysis_directly(self, jpeg_b64):
        r = requests.post(
            f"{BASE_URL}/analyze-item",
            headers=HEADERS,
            json={"image": jpeg_b64, "category_hint": "Tops"},
            timeout=120,
        )
        print(f"[analyze-item] status={r.status_code}")
        assert r.status_code == 200, f"body={r.text[:300]}"
        body = r.json()
        # Should be the analysis dict directly (no "analysis" wrapper, no clean_image)
        assert isinstance(body, dict)
        assert "clean_image" not in body, "analyze-item should not include clean_image"
        assert body.get("name"), f"missing name in body keys={list(body.keys())}"
        cat = (body.get("category") or "").lower()
        assert "top" in cat or cat == "tops", f"category {cat!r} should reflect hint Tops"


# ---------------- Calendar (not connected) ----------------
class TestCalendarNotConnected:
    def test_status(self):
        r = requests.get(f"{BASE_URL}/calendar/status", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("connected") is False, body
        assert body.get("configured") is True, "GCAL client not configured on server"

    def test_authorize_returns_google_url(self):
        r = requests.get(f"{BASE_URL}/calendar/authorize", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        url = r.json().get("url", "")
        assert url.startswith("https://accounts.google.com/"), f"bad url start: {url[:60]}"
        assert "calendar.readonly" in url, "scope calendar.readonly missing"
        assert "redirect_uri=" in url, "redirect_uri missing"
        assert "wardrobe-ai-311.preview.emergentagent.com" in url or "%2Fcallback" in url

    def test_events_empty_when_not_connected(self):
        r = requests.get(f"{BASE_URL}/calendar/events", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json() == {"events": []}, r.json()

    def test_disconnect_ok(self):
        r = requests.delete(f"{BASE_URL}/calendar/disconnect", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}, r.json()

    def test_callback_access_denied_returns_html_200(self):
        # Public endpoint — no auth
        r = requests.get(
            f"{BASE_URL}/calendar/callback",
            params={"error": "access_denied"},
            timeout=15,
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code} body={r.text[:200]}"
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct.lower(), f"expected html, got {ct}"
        assert "<html" in r.text.lower()


# ---------------- /api/dressme with calendar_events ----------------
class TestDressMeCalendarEvents:
    def test_dressme_includes_calendar_events(self):
        # Grant premium
        _db.users.update_one(
            {"user_id": USER_ID},
            {"$set": {"premium_until": "2099-01-01T00:00:00+00:00", "premium_source": "test"}},
            upsert=True,
        )
        try:
            r = requests.post(
                f"{BASE_URL}/dressme",
                headers=HEADERS,
                json={"temperature": 20, "weather": "clear"},
                timeout=180,
            )
            print(f"[dressme] status={r.status_code}")
            assert r.status_code == 200, f"body={r.text[:300]}"
            body = r.json()
            assert "calendar_events" in body, f"missing calendar_events; keys={list(body.keys())}"
            assert isinstance(body["calendar_events"], list), type(body["calendar_events"])
            # Not connected -> empty
            assert body["calendar_events"] == [], body["calendar_events"]
        finally:
            _db.users.update_one(
                {"user_id": USER_ID},
                {"$unset": {"premium_until": "", "premium_source": ""}},
            )
            _db.usage.delete_many({"user_id": USER_ID})


# ---------------- Regression ----------------
class TestRegression:
    def test_items_has_pairs_count(self):
        r = requests.get(f"{BASE_URL}/items", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list), f"expected list, got {type(body)}"
        # If the seeded profile has items, each must have pairs_count (int)
        if body:
            it = body[0]
            assert "pairs_count" in it, f"missing pairs_count; keys={list(it.keys())}"
            assert isinstance(it["pairs_count"], int), type(it["pairs_count"])

    def test_membership_plans(self):
        r = requests.get(f"{BASE_URL}/membership/plans", headers=HEADERS, timeout=15)
        assert r.status_code == 200, r.text
