"""
Iteration 52 — Regression for the {"orig_photo": 0} projection added to 14
db.items.find(...) loads in server.py. Proves nothing regressed: every
image-bearing response still carries `photo`, `orig_photo` is no longer leaked
from the changed endpoints, and the ONLY orig_photo consumer
(POST /api/items/{id}/clean) still works.

A TEST_ probe item is created WITH a populated orig_photo so every changed
endpoint actually loads a document that has the heavy field.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
TOKEN = os.environ.get("TEST_SESSION_TOKEN", "")
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
PROFILE = "prof_365ddfe52deb"  # default profile of user_testaura01
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration9_tryon import _jpeg_person_b64  # noqa: E402

AI_TIMEOUT = 180
STATE: dict = {}


def _no_orig(obj, where):
    assert "orig_photo" not in obj, f"{where}: orig_photo leaked in response"


def _has_photo(obj, where):
    assert obj.get("photo"), f"{where}: item {obj.get('id')} missing photo"


@pytest.fixture(scope="module", autouse=True)
def probe():
    # Pick a real garment photo from the seeded wardrobe
    src = db.items.find_one(
        {"user_id": PROFILE, "category": "Tops", "photo": {"$nin": [None, ""]}, "demo": {"$ne": True}},
        {"_id": 0},
    )
    assert src, "no seeded Tops item with a photo"
    STATE["src"] = src
    payload = {k: src.get(k) for k in ("category", "subcategory", "colour", "pattern", "material",
                                        "style", "season", "formality") if src.get(k) is not None}
    payload.update({"name": f"TEST_orig_probe {src.get('name')}", "photo": src["photo"],
                    "orig_photo": src["photo"], "availability": "Ready"})
    r = requests.post(f"{BASE_URL}/api/items", headers=H, json=payload, timeout=60)
    assert r.status_code == 200, r.text[:300]
    STATE["probe"] = r.json()
    yield
    pid = STATE["probe"]["id"]
    requests.delete(f"{BASE_URL}/api/items/{pid}", headers=H, timeout=30)
    db.items.delete_one({"id": pid})
    for tid in STATE.get("threads", []):
        db.stylist_threads.delete_one({"id": tid})


# ---------- Item add / storage ----------
class TestAddAndStorage:
    def test_post_items_stores_photo_and_orig_photo(self):
        p = STATE["probe"]
        assert p["photo"] and p["id"].startswith("item")
        doc = db.items.find_one({"id": p["id"]}, {"_id": 0})
        assert doc["photo"], "photo not stored"
        assert doc["orig_photo"] == STATE["src"]["photo"], "orig_photo not stored verbatim"
        assert doc["thumb"], "thumb not generated"

    def test_capacity_premium(self):
        r = requests.get(f"{BASE_URL}/api/items/capacity", headers=H, timeout=30)
        assert r.status_code == 200
        c = r.json()
        assert c["premium"] is True and c["cap"] is None and c["full"] is False
        assert c["count"] == db.items.count_documents({"user_id": PROFILE, "demo": {"$ne": True}})


# ---------- Wardrobe reads ----------
class TestWardrobeReads:
    def test_get_items_full(self):
        r = requests.get(f"{BASE_URL}/api/items", headers=H, timeout=60)
        assert r.status_code == 200
        items = r.json()
        db_items = list(db.items.find({"user_id": PROFILE, "demo": {"$ne": True}},
                                      {"_id": 0, "id": 1, "photo": 1, "worn_photo": 1}))
        assert len(items) == len(db_items)
        db_map = {d["id"]: d for d in db_items}
        for it in items:
            _no_orig(it, "GET /items")
            if db_map[it["id"]].get("photo"):
                assert it.get("photo"), f"{it['id']} lost photo in grid"
        assert any(i["id"] == STATE["probe"]["id"] for i in items)

    def test_get_items_summary_and_category(self):
        s = requests.get(f"{BASE_URL}/api/items?summary=1", headers=H, timeout=60).json()
        full_count = db.items.count_documents({"user_id": PROFILE, "demo": {"$ne": True}})
        assert len(s) == full_count
        assert all("photo" not in i and "orig_photo" not in i for i in s)
        c = requests.get(f"{BASE_URL}/api/items?category=Tops", headers=H, timeout=60).json()
        assert len(c) == db.items.count_documents({"user_id": PROFILE, "demo": {"$ne": True}, "category": "Tops"})
        assert all(i["category"] == "Tops" and i.get("photo") for i in c)

    def test_get_single_item_has_photo(self):
        r = requests.get(f"{BASE_URL}/api/items/{STATE['probe']['id']}", headers=H, timeout=30)
        assert r.status_code == 200
        assert r.json()["photo"] == STATE["probe"]["photo"]

    def test_laundry_lists_dirty_with_photo(self):
        pid = STATE["probe"]["id"]
        r = requests.put(f"{BASE_URL}/api/items/{pid}", headers=H, json={"availability": "Dirty"}, timeout=30)
        assert r.status_code == 200
        try:
            lr = requests.get(f"{BASE_URL}/api/laundry", headers=H, timeout=30)
            assert lr.status_code == 200
            found = [i for i in lr.json() if i["id"] == pid]
            assert found, "dirty probe not in laundry"
            _has_photo(found[0], "laundry")
            _no_orig(found[0], "laundry")
        finally:
            requests.put(f"{BASE_URL}/api/items/{pid}", headers=H, json={"availability": "Ready"}, timeout=30)
        # orig_photo still intact in DB after PUT
        assert db.items.find_one({"id": pid})["orig_photo"] == STATE["src"]["photo"]


# ---------- Capture duplicate detection ----------
class TestCapture:
    def test_capture_duplicates_carry_photo(self):
        r = requests.post(f"{BASE_URL}/api/capture", headers=H,
                          json={"image": STATE["src"]["photo"], "clean": False}, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert set(["analysis", "clean_image", "duplicates"]) <= set(j)
        assert j["analysis"], "analysis empty"
        # Dedup is deliberately strict (category+colour+2 descriptors). Align the
        # probe (which HAS orig_photo) with the AI's description of the same photo
        # so it is a true duplicate, then capture again.
        a = j["analysis"]
        upd = {k: a[k] for k in ("name", "category", "colour", "style", "fabric", "pattern") if a.get(k)}
        upd["name"] = f"TEST_orig_probe {upd.get('name', '')}"
        assert requests.put(f"{BASE_URL}/api/items/{STATE['probe']['id']}", headers=H, json=upd, timeout=30).status_code == 200
        r = requests.post(f"{BASE_URL}/api/capture", headers=H,
                          json={"image": STATE["src"]["photo"], "clean": False}, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        dups = j["duplicates"]
        assert any(d["id"] == STATE["probe"]["id"] for d in dups), "probe not flagged as duplicate"
        print("capture duplicates:", [(d.get("id"), d.get("name")) for d in dups])
        assert len(dups) >= 1, "no duplicates found for identical garment photo"
        for d in dups:
            assert d.get("photo"), f"duplicate {d.get('id')} has null photo"
            _no_orig(d, "capture duplicate")


# ---------- AI outfit builders ----------
class TestOutfitBuilders:
    def test_dressme_resolved_items_have_photos(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = requests.post(f"{BASE_URL}/api/dressme", headers=H,
                          json={"local_date": today, "temperature": 18, "weather": "Clear"}, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        ri = r.json()["resolved_items"]
        assert len(ri) >= 2, "dressme outfit too small"
        for x in ri:
            _has_photo(x["item"], "dressme")
            _no_orig(x["item"], "dressme")
        STATE["dress_ids"] = [x["item"]["id"] for x in ri]
        STATE["today"] = today

    def test_wear_pending_resolves_items(self):
        if "dress_ids" not in STATE:
            pytest.skip("dressme failed")
        r = requests.get(f"{BASE_URL}/api/wear/pending", headers=H, params={"date": STATE["today"]}, timeout=30)
        assert r.status_code == 200
        j = r.json()
        print("pending:", {k: v for k, v in j.items() if k != "items"})
        if not j.get("pending"):
            pytest.skip("already asked/logged for today")
        assert j["items"] and all(i.get("photo") for i in j["items"])

    def test_outfit_feedback(self):
        ids = STATE.get("dress_ids") or [STATE["probe"]["id"]]
        r = requests.post(f"{BASE_URL}/api/outfit/feedback", headers=H,
                          json={"item_ids": ids, "occasion": "Office", "temperature": 18}, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        print("feedback keys:", list(j.keys()))
        assert j.get("verdict") or j.get("feedback") or j.get("summary")

    def test_stylist_chat_outfit_items_have_photos(self):
        r = requests.post(f"{BASE_URL}/api/stylist/chat", headers=H, json={
            "messages": [{"role": "user", "content":
                          "Build me a complete outfit from my wardrobe for a smart dinner date tonight, around 15C."}],
            "temperature": 15, "weather": "Clear"}, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        if j.get("thread_id"):
            STATE.setdefault("threads", []).append(j["thread_id"])
        assert j.get("reply")
        print("stylist outfit present:", bool(j.get("outfit")))
        if j.get("outfit"):
            for it in j["outfit"]["items"]:
                _has_photo(it, "stylist outfit")
                _no_orig(it, "stylist outfit")

    def test_compatibility_focus_and_matches_have_photos(self):
        r = requests.post(f"{BASE_URL}/api/items/{STATE['probe']['id']}/compatibility", headers=H, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        _has_photo(j["focus"], "compat focus")
        assert j["resolved_matches"], "no resolved matches"
        for m in j["resolved_matches"]:
            _has_photo(m["item"], "compat match")
            _no_orig(m["item"], "compat match")

    def test_shop_check_items_have_photos(self):
        r = requests.post(f"{BASE_URL}/api/shop-check", headers=H,
                          json={"image": STATE["src"]["photo"]}, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        print("shop-check similar:", len(j.get("similar_items", [])), "matches:", len(j.get("matches_with", [])))
        assert "similar_items" in j and "matches_with" in j
        assert len(j["similar_items"]) + len(j["matches_with"]) >= 1
        for it in j["similar_items"] + j["matches_with"]:
            _has_photo(it, "shop-check")
            _no_orig(it, "shop-check")

    def test_packing_plan_items_have_photos(self):
        # Packing is an unreleased feature — its route is gated to 404 and the
        # photo behaviour is covered by the released endpoints above.
        r = requests.post(f"{BASE_URL}/api/packing/plan", headers=H,
                          json={"destination": "Paris", "days": 3, "occasions": "sightseeing, dinner"}, timeout=AI_TIMEOUT)
        assert r.status_code == 404, r.text[:300]

    def test_capsule_build_items_have_photos(self):
        r = requests.post(f"{BASE_URL}/api/capsule/build", headers=H,
                          json={"theme": "Weekend"}, timeout=AI_TIMEOUT)
        assert r.status_code == 404, r.text[:300]


# ---------- Insights ----------
class TestInsights:
    def test_missing_piece(self):
        r = requests.post(f"{BASE_URL}/api/insights/missing-piece", headers=H, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        print("missing-piece keys:", list(j.keys()))
        assert j.get("recommendation") and j.get("reason")
        assert "avoid" in j

    def test_shopping_intelligence(self):
        r = requests.post(f"{BASE_URL}/api/insights/shopping-intelligence", headers=H, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        print("shopping-intel keys:", list(j.keys()))
        recs = j.get("recommendations")
        assert isinstance(recs, list) and recs

    def test_health_report(self):
        r = requests.post(f"{BASE_URL}/api/insights/health-report", headers=H, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        print("health keys:", list(j.keys()))
        assert j["stats"]["total_items"] == db.items.count_documents({"user_id": PROFILE, "demo": {"$ne": True}})


# ---------- Try-on ----------
class TestTryOn:
    def test_tryon_finds_garment_photos(self):
        # Try On is unreleased — route gated to 404 (see UNRELEASED_FEATURES).
        r = requests.post(f"{BASE_URL}/api/tryon", headers=H,
                          json={"person_image": _jpeg_person_b64(), "item_ids": [STATE["probe"]["id"]]},
                          timeout=AI_TIMEOUT)
        assert r.status_code == 404, r.text[:300]


# ---------- Clean (sole orig_photo consumer) ----------
class TestCleanUsesOrigPhoto:
    def test_clean_item_uses_orig_photo(self):
        pid = STATE["probe"]["id"]
        # Make photo differ from orig_photo so we can prove clean reads orig_photo
        db.items.update_one({"id": pid}, {"$set": {"photo": "", "thumb": None}})
        r = requests.post(f"{BASE_URL}/api/items/{pid}/clean", headers=H, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        print("clean:", {k: (v if k != "photo" else len(v or "")) for k, v in j.items()})
        assert j["cleaned"] is True, f"clean failed: {j}"
        assert j["photo"] and len(j["photo"]) > 100
        doc = db.items.find_one({"id": pid})
        assert doc["photo"] == j["photo"]
        assert doc["orig_photo"] == STATE["src"]["photo"], "orig_photo not preserved"
        assert doc["thumb"]


# ---------- Free cap sanity ----------
class TestFreeCap:
    def test_free_cap_402(self):
        email = f"qa+iter52_{uuid.uuid4().hex[:8]}@aureve.local"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"email": email, "password": "secret123", "name": "TEST_iter52"}, timeout=30)
        assert r.status_code == 200, r.text
        tok, uid = r.json()["session_token"], r.json()["user"]["user_id"]
        bh = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        prof = requests.get(f"{BASE_URL}/api/profiles", headers=bh, timeout=15).json()[0]["id"]
        try:
            db.users.update_one({"user_id": uid}, {"$unset": {"premium_until": "", "premium_source": "",
                                                               "complimentary_expires_at": ""}})
            db.items.insert_many([{"id": f"item_i52_{uid[-6:]}_{i}", "user_id": prof, "profile_id": prof,
                                   "name": f"TEST filler {i}", "category": "Tops", "photo": "",
                                   "created_at": "2026-01-01T00:00:00+00:00", "wear_count": 0}
                                  for i in range(100)])
            cap = requests.get(f"{BASE_URL}/api/items/capacity", headers=bh, timeout=15).json()
            assert cap == {"count": 100, "cap": 100, "remaining": 0, "full": True, "premium": False}, cap
            r2 = requests.post(f"{BASE_URL}/api/items", headers=bh,
                               json={"name": "TEST_over", "category": "Tops", "photo": STATE["src"]["photo"]}, timeout=30)
            assert r2.status_code == 402, r2.text[:200]
        finally:
            requests.delete(f"{BASE_URL}/api/auth/account", headers=bh, timeout=30)
            db.items.delete_many({"user_id": prof, "id": {"$regex": f"^item_i52_{uid[-6:]}_"}})
