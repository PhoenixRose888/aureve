"""Iteration 53 — hydrate_photos under the reviewer/demo (show_demo) scope (show_demo items)."""
import os
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
STATE = {}
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def guest():
    # Reviewer account sees demo:true items (show_demo scope). NEVER delete this account.
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "review@aureve.app", "password": os.environ.get("REVIEWER_PASSWORD", "")}, timeout=60)
    assert r.status_code == 200, r.text[:200]
    tok = r.json()["session_token"]
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    STATE["threads"] = []
    yield h
    for t in STATE["threads"]:
        db.stylist_threads.delete_one({"id": t})


def test_guest_dressme_demo_items_have_photos(guest):
    r = requests.post(f"{BASE_URL}/api/dressme", headers=guest, json={"temperature": 20}, timeout=240)
    assert r.status_code == 200, r.text[:300]
    ri = r.json()["resolved_items"]
    assert len(ri) >= 2
    for x in ri:
        d = db.items.find_one({"id": x["item"]["id"]}, {"_id": 0, "photo": 1, "demo": 1})
        print(x["item"]["id"], "demo=", d.get("demo"), "photo_len=", len(x["item"].get("photo") or ""))
        if d.get("photo"):
            assert x["item"].get("photo") == d["photo"], f"{x['item']['id']} demo photo missing/differs"


def test_guest_stylist_chat(guest):
    r = requests.post(f"{BASE_URL}/api/stylist/chat", headers=guest, timeout=240, json={"messages": [
        {"role": "user", "content": "Weekend brunch with friends, 22C and sunny. Build me an outfit."}]})
    assert r.status_code == 200, r.text[:300]
    STATE["threads"].append(r.json().get("thread_id"))
    for it in (r.json().get("outfit") or {}).get("items", []):
        assert it.get("photo"), f"{it['id']} missing photo"
