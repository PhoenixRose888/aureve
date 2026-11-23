"""
Iteration 53 — wardrobe_pool() (metadata-only load) + hydrate_photos()
(re-attach imagery only for pieces in the response) regression.

Every item object returned by an AI endpoint is compared BYTE-FOR-BYTE against
the DB document's photo / thumb / worn_photo, so a missing, null or crossed
image is caught (not just key presence).

A TEST_ probe item is created with photo + thumb + a DISTINCT worn_photo so the
worn_photo re-attachment path is exercised too.
"""
import os
import sys
import time
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
H = {"Authorization": f"Bearer {os.environ.get('TEST_SESSION_TOKEN', '')}", "Content-Type": "application/json"}
PROFILE = "prof_365ddfe52deb"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration9_tryon import _jpeg_person_b64  # noqa: E402

AI = 240
S: dict = {"checked": 0}


def post(path, body=None, retries=1):
    for attempt in range(retries + 1):
        r = requests.post(f"{BASE_URL}/api{path}", headers=H, json=body or {}, timeout=AI)
        if r.status_code != 502 or attempt == retries:
            return r
        time.sleep(3)


def check_item(it, where, allow_orig=False, imagery=("photo", "thumb", "worn_photo")):
    """Assert the response item carries exactly the DB imagery.

    `imagery` lists the fields this response is contracted to carry — /capture
    duplicates only ever carried `photo`, so the others must stay absent there.
    """
    assert isinstance(it, dict) and it.get("id"), f"{where}: bad item {it!r}"[:200]
    d = db.items.find_one({"id": it["id"]}, {"_id": 0, "photo": 1, "thumb": 1, "worn_photo": 1})
    assert d, f"{where}: {it['id']} not in DB"
    assert allow_orig or "orig_photo" not in it, f"{where}: orig_photo leaked for {it['id']}"
    if d.get("photo"):
        assert it.get("photo"), f"{where}: {it['id']} photo MISSING/NULL"
        assert it["photo"] == d["photo"], f"{where}: {it['id']} photo differs from DB (len {len(it['photo'])} vs {len(d['photo'])})"
    for field in ("thumb", "worn_photo"):
        if field not in imagery:
            assert not it.get(field), f"{where}: {it['id']} unexpectedly carries {field}"
        elif d.get(field):
            assert it.get(field) == d[field], f"{where}: {it['id']} {field} missing/differs"
    S["checked"] += 1


@pytest.fixture(scope="module", autouse=True)
def probe():
    src = db.items.find_one({"id": "item_830ae0fdf580"}, {"_id": 0})  # Light Blue Oxford Shirt
    worn = db.items.find_one({"id": "item_0f0000bdcfeb"}, {"_id": 0, "photo": 1})["photo"]
    S["src"] = src
    body = {k: src.get(k) for k in ("category", "colour", "pattern", "fabric", "style", "season",
                                     "formality", "tone") if src.get(k) is not None}
    body.update({"name": "TEST_probe Blue Oxford Shirt", "photo": src["photo"], "thumb": src.get("thumb"),
                 "worn_photo": worn, "availability": "Ready"})
    r = requests.post(f"{BASE_URL}/api/items", headers=H, json=body, timeout=60)
    assert r.status_code == 200, r.text[:300]
    S["probe"] = r.json()["id"]
    d = db.items.find_one({"id": S["probe"]}, {"_id": 0, "worn_photo": 1, "thumb": 1})
    if not d.get("worn_photo"):  # API may not accept worn_photo on create — set it directly on our own TEST_ item
        db.items.update_one({"id": S["probe"]}, {"$set": {"worn_photo": worn}})
    S["threads"] = []
    yield
    requests.delete(f"{BASE_URL}/api/items/{S['probe']}", headers=H, timeout=30)
    db.items.delete_one({"id": S["probe"]})
    for t in S["threads"]:
        db.stylist_threads.delete_one({"id": t})
    print(f"\nTotal item objects verified byte-for-byte: {S['checked']}")


# ---------- Dress Me / stylist outfit builder (_build_outfit) ----------
class TestDressMe:
    def test_dressme_context(self):
        r = requests.get(f"{BASE_URL}/api/dressme/context", headers=H, timeout=30)
        assert r.status_code == 200 and {"has_context", "source", "label"} <= set(r.json())

    def test_dressme_photos(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = post("/dressme", {"local_date": today, "temperature": 16, "weather": "Cloudy"})
        assert r.status_code == 200, r.text[:300]
        ri = r.json()["resolved_items"]
        assert len(ri) >= 2
        for x in ri:
            check_item(x["item"], "dressme.resolved_items[].item")
        S["look1"] = [x["item"]["id"] for x in ri]

    def test_dressme_another_look(self):
        assert S.get("look1")
        r = post("/dressme", {"temperature": 16, "weather": "Cloudy", "avoid_item_ids": S["look1"]})
        assert r.status_code == 200, r.text[:300]
        ri = r.json()["resolved_items"]
        assert len(ri) >= 2
        for x in ri:
            check_item(x["item"], "dressme(avoid).resolved_items[].item")
        ids = [x["item"]["id"] for x in ri]
        overlap = set(ids) & set(S["look1"])
        print("another-look overlap:", overlap)
        assert set(ids) != set(S["look1"]), "Create Another Look returned the identical look"

    def test_stylist_suggest(self):
        # /stylist/suggest only served the unreleased Planner — gated to 404.
        r = post("/stylist/suggest", {"occasion": "Office meeting", "temperature": 20})
        assert r.status_code == 404, r.text[:300]

    def test_mix_it_up(self):
        assert S.get("look1")
        r = post("/outfits/mix", {"item_ids": S["look1"], "occasion": "Weekend brunch"})
        assert r.status_code == 200, r.text[:300]
        ri = r.json()["resolved_items"]
        assert len(ri) >= 2
        for x in ri:
            check_item(x["item"], "outfits/mix.resolved_items[].item")


# ---------- AI Stylist chat ----------
class TestStylistChat:
    def test_chat_outfit_photos_and_thread(self):
        outfit = None
        for _ in range(2):
            r = post("/stylist/chat", {"messages": [{"role": "user", "content":
                     "I have a dinner date at a smart restaurant tonight, it's 14C. Build me a full outfit."}],
                     "temperature": 14})
            assert r.status_code == 200, r.text[:300]
            j = r.json()
            assert j.get("reply") and j.get("thread_id")
            S["threads"].append(j["thread_id"])
            outfit = j.get("outfit")
            if outfit:
                break
        assert outfit, "stylist never returned an outfit block in 2 tries"
        assert outfit["items"]
        for it in outfit["items"]:
            check_item(it, "stylist/chat.outfit.items[]")
        th = requests.get(f"{BASE_URL}/api/stylist/threads/{j['thread_id']}", headers=H, timeout=30)
        assert th.status_code == 200
        last = th.json()["messages"][-1]
        assert last["role"] == "assistant"
        assert last.get("outfit_item_ids") == outfit["item_ids"], "persisted outfit ids differ"
        lst = requests.get(f"{BASE_URL}/api/stylist/threads", headers=H, timeout=30).json()
        assert any(t["id"] == j["thread_id"] for t in lst)

    def test_chat_with_attached_item(self):
        r = post("/stylist/chat", {"messages": [{"role": "user", "content":
                 "What goes with this shirt for a casual Friday at the office?"}],
                 "item_ids": [S["probe"]]})
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        S["threads"].append(j["thread_id"])
        assert j.get("reply")
        for it in (j.get("outfit") or {}).get("items", []):
            check_item(it, "stylist/chat(attached).outfit.items[]")


# ---------- Check My Outfit ----------
class TestOutfitFeedback:
    def test_feedback_swap_photos_and_invariants(self):
        # Deliberately clashing look to provoke a swap.
        ids = ["item_139773517a46", "item_24d76899b7e9", "item_c12868e5b237"]  # silk blouse, olive skirt, sneakers
        got_swap = False
        for _ in range(3):
            r = post("/outfit/feedback", {"item_ids": ids, "occasion": "Black-tie gala", "temperature": 12})
            assert r.status_code == 200, r.text[:300]
            j = r.json()
            assert j.get("feedback") and "verdict" in j
            sw = j.get("swap")
            if sw:
                got_swap = True
                check_item(sw["out_item"], "outfit/feedback.swap.out_item")
                check_item(sw["in_item"], "outfit/feedback.swap.in_item")
                assert sw["out_id"] in ids
                assert sw["out_item"]["category"] == sw["in_item"]["category"], "cross-category swap leaked"
            if j.get("addition"):
                add = j["addition"]
                assert "out_item" not in add and "in_item" not in add, "addition carries item objects"
                print("addition:", {k: v for k, v in add.items() if isinstance(v, str)})
            if got_swap:
                break
        print("got swap:", got_swap)
        if not got_swap:
            pytest.skip("AI returned no swap in 3 tries — photo path not exercised")


# ---------- Try On ----------
class TestTryOn:
    def test_tryon_generates_image(self):
        # Try On is unreleased — route gated to 404 (see UNRELEASED_FEATURES).
        ids = ["item_024ec48bf1d6", "item_f1b6660a4d56"]  # tee + jeans
        r = post("/tryon", {"person_image": _jpeg_person_b64(), "item_ids": ids})
        assert r.status_code == 404, f"{r.status_code} {r.text[:300]}"


# ---------- Shopping / insights ----------
class TestInsights:
    def test_shopping_intelligence(self):
        r = post("/insights/shopping-intelligence")
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j.get("summary")
        recs = j["recommendations"]
        assert 3 <= len(recs) <= 4, len(recs)
        owned = {(d.get("name") or "").strip().lower() for d in db.items.find(
            {"user_id": PROFILE, "demo": {"$ne": True}}, {"name": 1})}
        bad = [p for rec in recs for p in rec.get("pairs_with", []) if p.strip().lower() not in owned]
        print("pairs_with not exact owned names:", bad)
        assert all(rec.get("pairs_with") for rec in recs)
        assert len(bad) <= 1, f"pairs_with references non-owned items: {bad}"

    def test_missing_piece(self):
        r = post("/insights/missing-piece")
        assert r.status_code == 200, r.text[:300]
        assert r.json(), "empty"
        print("missing-piece keys:", list(r.json()))

    def test_health_report_count(self):
        r = post("/insights/health-report")
        assert r.status_code == 200, r.text[:300]
        real = db.items.count_documents({"user_id": PROFILE, "demo": {"$ne": True}})
        assert r.json()["stats"]["total_items"] == real

    def test_shop_check_photos_and_duplicate_rule(self):
        r = post("/shop-check", {"image": S["src"]["photo"]})
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        for it in j.get("similar_items", []):
            check_item(it, "shop-check.similar_items[]")
        for it in j.get("matches_with", []):
            check_item(it, "shop-check.matches_with[]")
        print("similar:", [i["name"] for i in j["similar_items"]], "fills_gap:", j.get("fills_gap"))
        assert j["similar_items"], "owned garment photo produced no similar_items"
        if not j.get("fills_gap"):
            assert j.get("outfits_added") == 0
            assert j.get("already_covered")

    def test_compatibility(self):
        fid = "item_f1b6660a4d56"  # Indigo jeans
        r = post(f"/items/{fid}/compatibility")
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        check_item(j["focus"], "compatibility.focus")
        assert j["resolved_matches"]
        for m in j["resolved_matches"]:
            assert m["item"]["id"] != fid, "focus item appears in its own matches"
            check_item(m["item"], "compatibility.resolved_matches[].item")
        for k in ("match_count", "total_compatible", "shortlisted"):
            assert isinstance(j.get(k), int), k


# ---------- Capture duplicate detection (worn_photo re-attach) ----------
class TestCapture:
    def test_capture_duplicate_has_all_imagery(self):
        r = post("/capture", {"image": S["src"]["photo"], "clean": False})
        assert r.status_code == 200, r.text[:300]
        a = r.json()["analysis"]
        upd = {k: a[k] for k in ("category", "colour", "style", "fabric", "pattern") if a.get(k)}
        upd["name"] = f"TEST_probe {a.get('name', '')}"
        assert requests.put(f"{BASE_URL}/api/items/{S['probe']}", headers=H, json=upd, timeout=30).status_code == 200
        r = post("/capture", {"image": S["src"]["photo"], "clean": False})
        assert r.status_code == 200, r.text[:300]
        dups = r.json()["duplicates"]
        assert any(d["id"] == S["probe"] for d in dups), f"probe not flagged: {[d['id'] for d in dups]}"
        for d in dups:
            assert d.get("photo"), f"duplicate {d['id']} null photo"
            check_item(d, "capture.duplicates[]", imagery=("photo",))


# ---------- Packing / Capsule (unreleased: routes must stay gated) ----------
class TestPlanners:
    def test_packing(self):
        r = post("/packing/plan", {"destination": "Paris", "days": 3, "occasions": "museum, dinner"})
        assert r.status_code == 404, r.text[:300]

    def test_capsule(self):
        r = post("/capsule/build", {"theme": "Work"})
        assert r.status_code == 404, r.text[:300]


# ---------- Unchanged display paths ----------
class TestUnchanged:
    def test_display_endpoints_keep_photos(self):
        items = requests.get(f"{BASE_URL}/api/items", headers=H, timeout=60).json()
        # Grid intentionally serves the THUMBNAIL as `photo` (pre-existing behaviour).
        for it in items:
            d = db.items.find_one({"id": it["id"]}, {"_id": 0, "photo": 1, "thumb": 1})
            if d and d.get("photo"):
                assert it.get("photo") in (d.get("thumb"), d["photo"]), f"GET /items {it['id']} photo wrong"
            assert "orig_photo" not in it
        one = requests.get(f"{BASE_URL}/api/items/{S['probe']}", headers=H, timeout=30).json()
        check_item(one, "GET /items/{id}", allow_orig=True)  # detail view returns full doc (unchanged)
        for path in (f"/wear/pending?date={datetime.now(timezone.utc).strftime('%Y-%m-%d')}", "/outfits", "/collections", "/wear", "/laundry"):
            r = requests.get(f"{BASE_URL}/api{path}", headers=H, timeout=60)
            assert r.status_code == 200, f"{path} {r.status_code}"
            if path in ("/outfits", "/wear"):
                emb = [it for row in r.json() for it in row.get("items", [])]
                print(f"{path}: rows={len(r.json())} embedded items={len(emb)}")
                assert all(it.get("photo") for it in emb), f"{path}: embedded item without photo"
        cap = requests.get(f"{BASE_URL}/api/items/capacity", headers=H, timeout=30)
        assert cap.status_code == 200
