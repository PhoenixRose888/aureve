"""
Iteration 54 — weather fix verification + broad pre-release regression.
Weather: /api/weather validation & latency, stylist with/without weather (no city ask,
no invented weather), Dress Me with/without weather, Packing fallback.
Regression: auth lifecycle + complimentary premium, item CRUD, capacity / free cap 402,
saved outfits vs worn history, shop-check duplicate, shopping intelligence.
"""
import os
import re
import time
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
H = {"Authorization": f"Bearer {os.environ.get('TEST_SESSION_TOKEN', '')}", "Content-Type": "application/json"}
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
AI = 240
TINY_JPEG = ("/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/"
             "yQALCAABAAEBAREA/8wABgAQEAX/2gAIAQEAAD8A0s8g/9k=")
CITY_ASK = re.compile(r"(your|which|what) (city|location|town)|where are you|where you('re| are) (based|located)|"
                      r"share (your|the) (city|location)|tell me (the )?(weather|where)|what('s| is) the weather (like )?(where|in your|there)", re.I)
TEMP_CLAIM = re.compile(r"-?\d+\s?(°|degrees|ºC|C\b)", re.I)
S: dict = {}


def req(method, path, headers=H, **kw):
    t0 = time.time()
    r = requests.request(method, f"{API}{path}", headers=headers, timeout=kw.pop("timeout", AI), **kw)
    dt = time.time() - t0
    print(f"{method} {path} -> {r.status_code} in {dt:.1f}s")
    return r, dt


# ---------------- Weather endpoint ----------------
class TestWeather:
    def test_valid_coords(self):
        r, dt = req("GET", "/weather?lat=51.5074&lon=-0.1278", headers={})
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j["temperature"], (int, float))
        assert isinstance(j["feels_like"], (int, float))
        assert isinstance(j["code"], int) and isinstance(j["description"], str) and j["description"]
        assert dt < 10

    @pytest.mark.parametrize("qs", ["lat=999&lon=0", "lat=0&lon=999", "lat=-91&lon=0", "lat=nan&lon=0", "lat=inf&lon=0"])
    def test_out_of_range_400(self, qs):
        r, _ = req("GET", f"/weather?{qs}", headers={})
        assert r.status_code == 400, r.text
        assert "Traceback" not in r.text

    def test_non_numeric_422(self):
        r, _ = req("GET", "/weather?lat=abc&lon=0", headers={})
        assert r.status_code == 422

    def test_repeat_latency(self):
        times = [req("GET", f"/weather?lat={40 + i}&lon={-74 + i}", headers={})[1] for i in range(3)]
        assert max(times) < 10, times


# ---------------- AI Stylist weather awareness ----------------
class TestStylistWeather:
    Q = "What should I wear today for a casual lunch with friends?"

    def test_with_weather(self):
        r, _ = req("POST", "/stylist/chat", json={"messages": [{"role": "user", "content": self.Q}],
                                                    "temperature": 4, "weather": "Light rain"})
        assert r.status_code == 200, r.text
        reply = r.json()["reply"]
        print("WITH WEATHER:", reply[:600])
        S.setdefault("threads", []).append(r.json().get("thread_id"))
        assert not CITY_ASK.search(reply), reply
        assert re.search(r"rain|cold|chill|cool|4\s?°|wet|umbrella|layer|warm", reply, re.I), reply

    def test_without_weather(self):
        r, _ = req("POST", "/stylist/chat", json={"messages": [{"role": "user", "content": self.Q}]})
        assert r.status_code == 200, r.text
        j = r.json()
        reply = j["reply"]
        print("NO WEATHER:", reply[:600])
        S.setdefault("threads", []).append(j.get("thread_id"))
        assert len(reply) > 40
        assert not CITY_ASK.search(reply), reply
        assert not TEMP_CLAIM.search(reply), reply

    def test_vague_question_without_weather(self):
        r, _ = req("POST", "/stylist/chat", json={"messages": [{"role": "user", "content": "What should I wear today?"}]})
        assert r.status_code == 200, r.text
        reply = r.json()["reply"]
        print("VAGUE:", reply[:400])
        S.setdefault("threads", []).append(r.json().get("thread_id"))
        assert not CITY_ASK.search(reply), reply
        assert not TEMP_CLAIM.search(reply), reply


# ---------------- Dress Me with/without weather ----------------
class TestDressMe:
    @pytest.mark.parametrize("body", [{"temperature": 3, "weather": "Overcast"}, {}])
    def test_dressme(self, body):
        r, dt = req("POST", "/dressme", json={**body, "occasion": "Casual"})
        assert r.status_code == 200, r.text
        j = r.json()
        items = [ri.get("item") or {} for ri in (j.get("resolved_items") or [])]
        assert items, list(j.keys())
        assert all(it.get("photo") for it in items)
        print("dressme keys", list(j.keys()), "dt", round(dt, 1))


# ---------------- Packing (unreleased: route must stay gated) ----------------
class TestPacking:
    @pytest.mark.parametrize("dest", ["Paris", "Zzzzqqq"])
    def test_packing(self, dest):
        r, _ = req("POST", "/packing/plan", json={"destination": dest, "days": 3, "occasions": "sightseeing"})
        assert r.status_code == 404, r.text[:300]


# ---------------- Auth lifecycle + complimentary premium + free cap ----------------
class TestAccount:
    def test_register_login_me_trial_cap_logout_delete(self):
        email = f"qa+{int(time.time())}{uuid.uuid4().hex[:4]}@aureve.local"
        r, _ = req("POST", "/auth/register", headers={}, json={"email": email, "password": "secret123", "name": "TEST_QA"})
        assert r.status_code == 200, r.text
        tok = r.json()["session_token"]
        uid = r.json()["user"]["user_id"]
        hh = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        try:
            u = db.users.find_one({"user_id": uid})
            assert u.get("premium_source") == "complimentary" and u.get("complimentary_expires_at")
            exp = datetime.fromisoformat(u["premium_until"])
            days = (exp - datetime.now(timezone.utc)).total_seconds() / 86400
            assert 6.9 < days <= 7.01, days
            # duplicate register
            r2, _ = req("POST", "/auth/register", headers={}, json={"email": email, "password": "secret123"})
            assert r2.status_code == 409
            # wrong pw / login
            assert req("POST", "/auth/login", headers={}, json={"email": email, "password": "wrongpw"})[0].status_code in (400, 401)
            r3, _ = req("POST", "/auth/login", headers={}, json={"email": email, "password": "secret123"})
            assert r3.status_code == 200
            tok2 = r3.json()["session_token"]
            me, _ = req("GET", "/auth/me", headers=hh)
            assert me.status_code == 200 and me.json()["email"] == email
            print("ME membership keys:", {k: v for k, v in me.json().items() if "prem" in k or "compl" in k or "trial" in k})
            cap, _ = req("GET", "/items/capacity", headers=hh)
            assert cap.json()["premium"] is True and cap.json()["cap"] is None
            # Make this TEST user free and fill to 100
            db.users.update_one({"user_id": uid}, {"$unset": {"premium_until": ""}})
            prof = req("GET", "/profiles", headers=hh)[0].json()
            pid = prof[0]["id"] if isinstance(prof, list) else None
            db.items.insert_many([{"id": f"TEST_cap_{uid}_{i}", "user_id": pid, "name": f"TEST_cap {i}",
                                   "category": "Tops", "created_at": datetime.now(timezone.utc).isoformat()} for i in range(100)])
            cap, _ = req("GET", "/items/capacity", headers=hh)
            print("FREE capacity:", cap.json())
            assert cap.json()["full"] is True and cap.json()["cap"] == 100 and cap.json()["remaining"] == 0
            r4, _ = req("POST", "/items", headers=hh, json={"name": "TEST_over", "category": "Tops", "photo": TINY_JPEG})
            assert r4.status_code == 402, r4.text
            # logout invalidates session
            hh2 = {"Authorization": f"Bearer {tok2}"}
            assert req("POST", "/auth/logout", headers=hh2)[0].status_code == 200
            assert req("GET", "/auth/me", headers=hh2)[0].status_code == 401
        finally:
            d, _ = req("DELETE", "/auth/account", headers=hh)
            assert d.status_code == 200, d.text
            assert req("GET", "/auth/me", headers=hh)[0].status_code == 401
            assert db.items.count_documents({"id": {"$regex": f"^TEST_cap_{uid}_"}}) == 0
            assert db.users.count_documents({"user_id": uid}) == 0


# ---------------- Wardrobe CRUD ----------------
class TestItems:
    def test_crud(self):
        r, _ = req("POST", "/items", json={"name": "TEST_reg tee", "category": "Tops", "colour": "Navy", "photo": TINY_JPEG})
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        try:
            g, _ = req("GET", f"/items/{iid}")
            assert g.status_code == 200 and g.json()["photo"]
            u, _ = req("PUT", f"/items/{iid}", json={"name": "TEST_reg tee edited", "category": "Tops", "colour": "Red"})
            assert u.status_code == 200
            g2 = req("GET", f"/items/{iid}")[0].json()
            assert g2["name"] == "TEST_reg tee edited" and g2["colour"] == "Red" and g2["photo"]
            full, dt1 = req("GET", "/items")
            summ, dt2 = req("GET", "/items?summary=1")
            cat, _ = req("GET", "/items?category=Tops")
            assert full.status_code == summ.status_code == cat.status_code == 200
            assert any(i["id"] == iid for i in full.json())
            assert all(i.get("photo") for i in full.json()), "items missing photo in full list"
            assert all(i["category"] == "Tops" for i in cat.json())
            print("items full", len(full.json()), f"{dt1:.1f}s", "summary", len(summ.json()), f"{dt2:.1f}s")
        finally:
            assert req("DELETE", f"/items/{iid}")[0].status_code == 200
            assert req("GET", f"/items/{iid}")[0].status_code == 404


# ---------------- Saved vs Worn ----------------
class TestSavedWorn:
    def test_saved_and_worn_distinct(self):
        items = req("GET", "/items?summary=1")[0].json()
        ids = [i["id"] for i in items[:2]]
        before = {i: db.items.find_one({"id": i}, {"wear_count": 1, "last_worn": 1, "_id": 0}) for i in ids}
        o, _ = req("POST", "/outfits", json={"name": "TEST_saved look", "item_ids": ids, "source": "ai"})
        assert o.status_code == 200
        oid = o.json()["id"]
        wid = None
        try:
            lst = req("GET", "/outfits")[0].json()
            mine = [x for x in lst if x["id"] == oid]
            assert mine and mine[0]["items"] and all(it.get("photo") for it in mine[0]["items"])
            worn = req("GET", "/wear")[0].json()
            assert not any(w.get("outfit_id") == oid for w in (worn if isinstance(worn, list) else worn.get("logs", [])))
            # Mix it up must not mark worn
            m, _ = req("POST", "/outfits/mix", json={"outfit_id": oid, "item_ids": ids})
            print("mix", m.status_code)
            assert m.status_code == 200, m.text
            after = {i: db.items.find_one({"id": i}, {"wear_count": 1, "last_worn": 1, "_id": 0}) for i in ids}
            assert after == before, (before, after)
            # Log a wear
            w, _ = req("POST", "/wear", json={"outfit_id": oid, "name": "TEST_saved look", "item_ids": ids})
            assert w.status_code == 200
            wid = w.json()["id"]
            worn = req("GET", "/wear")[0].json()
            logs = worn if isinstance(worn, list) else worn.get("logs", [])
            mine = [x for x in logs if x["id"] == wid]
            assert mine and mine[0]["created_at"][:10] == datetime.now(timezone.utc).date().isoformat()
            assert any(x["id"] == oid for x in req("GET", "/outfits")[0].json())
        finally:
            req("DELETE", f"/outfits/{oid}")
            if wid:
                db.wear_logs.delete_one({"id": wid})
                for i, b in before.items():
                    db.items.update_one({"id": i}, {"$set": {k: (b or {}).get(k) for k in ("wear_count", "last_worn")}})


# ---------------- Shopping ----------------
class TestShopping:
    def test_shopping_intelligence(self):
        r, _ = req("POST", "/insights/shopping-intelligence", json={})
        assert r.status_code == 200, r.text
        assert r.json()["recommendations"]

    def test_shop_check_duplicate(self):
        tops = req("GET", "/items?category=Tops")[0].json()
        it = next(t for t in tops if t.get("photo") and not t["name"].startswith("TEST_"))
        print("probe item:", it["name"])
        photo = req("GET", f"/items/{it['id']}")[0].json()["photo"].split(",", 1)[-1]
        r, _ = req("POST", "/shop-check", json={"image": photo})
        assert r.status_code == 200, r.text
        j = r.json()
        print("shop-check:", j.get("verdict"), j.get("outfits_added"), j.get("already_covered"), [s["name"] for s in j["similar_items"]])
        assert all(s.get("photo") for s in j["similar_items"] + j["matches_with"])
        if j["similar_items"] and not j.get("fills_gap"):
            assert j["outfits_added"] == 0 and "already" in j["already_covered"]


# ---------------- Bulk add: /capture -> /items ----------------
class TestCaptureBulk:
    def test_capture_then_add(self):
        tops = req("GET", "/items?category=Bottoms")[0].json()
        src = next(t for t in tops if not t["name"].startswith("TEST_"))
        photo = req("GET", f"/items/{src['id']}")[0].json()["photo"]
        created = []
        try:
            for n in range(2):
                c, dt = req("POST", "/capture", json={"image": photo.split(",", 1)[-1]})
                assert c.status_code == 200, c.text
                j = c.json()
                print("capture keys:", list(j.keys())[:12], f"{dt:.1f}s", "dupes:", [d.get("name") for d in (j.get("duplicates") or j.get("possible_duplicates") or [])][:3])
                for d in (j.get("duplicates") or j.get("possible_duplicates") or []):
                    assert d.get("photo"), "duplicate without photo"
                fields = j.get("item") or j.get("analysis") or j
                r, _ = req("POST", "/items", json={"name": f"TEST_bulk {n} {fields.get('name', 'piece')}", "category": fields.get("category") or "Bottoms", "photo": photo})
                assert r.status_code == 200, r.text
                created.append(r.json()["id"])
            assert all(any(i["id"] == cid for i in req("GET", "/items?summary=1")[0].json()) for cid in created)
        finally:
            for cid in created:
                req("DELETE", f"/items/{cid}")
