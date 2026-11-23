"""
Frontend seed/cleanup helper — used from playwright driver.
Seeds a taxonomy validation set on the reviewer account and returns their ids
so playwright can navigate & assert. Also has cleanup.
"""
import os
import sys
import base64
import io
import json
import requests
from PIL import Image

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")

def _tiny_png():
    img = Image.new("RGB", (16, 16), (200, 200, 200))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "review@aureve.app", "password": os.environ.get("REVIEWER_PASSWORD", "")},
                      timeout=30)
    r.raise_for_status()
    return r.json().get("session_token") or r.json().get("token")

SEEDS = [
    # BOTTOMS taxonomy
    {"name": "TEST_iter38 Navy drawstring lounge pants", "category": "Bottoms", "expect_sub": "Lounge Pants"},
    {"name": "TEST_iter38 Pink lounge pants",            "category": "Bottoms", "expect_sub": "Lounge Pants"},
    {"name": "TEST_iter38 Black track pants",            "category": "Bottoms", "expect_sub": "Lounge Pants"},
    {"name": "TEST_iter38 Black tailored trousers",      "category": "Bottoms", "expect_sub": "Trousers"},
    {"name": "TEST_iter38 Navy chinos",                  "category": "Bottoms", "expect_sub": "Trousers"},
    # SHOES taxonomy (no Sandals chip)
    {"name": "TEST_iter38 Tan wedge sandals",            "category": "Shoes",   "expect_sub": "Heels"},
    {"name": "TEST_iter38 Black heeled sandals",         "category": "Shoes",   "expect_sub": "Heels"},
    {"name": "TEST_iter38 Brown flat sandals",           "category": "Shoes",   "expect_sub": "Flats"},
    {"name": "TEST_iter38 Black slides",                 "category": "Shoes",   "expect_sub": "Flats"},
    # BAGS taxonomy (Handbags + Clutches only)
    {"name": "TEST_iter38 Small crossbody bag",          "category": "Bags",    "expect_sub": "Handbags"},
    {"name": "TEST_iter38 Black leather backpack",       "category": "Bags",    "expect_sub": "Handbags"},
    {"name": "TEST_iter38 Gold evening clutch",          "category": "Bags",    "expect_sub": "Clutches"},
    # LONG SLEEVE vs JUMPER
    {"name": "TEST_iter38 Olive long sleeve top",        "category": "Tops",    "expect_sub": "Long Sleeve",
     "extra": {"sleeve_length": "long"}},
    {"name": "TEST_iter38 Grey sweatshirt",              "category": "Outerwear", "expect_sub": "Jumpers"},
    {"name": "TEST_iter38 Black hoodie",                 "category": "Outerwear", "expect_sub": "Jumpers"},
]

def seed():
    tok = login()
    hdrs = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    photo = _tiny_png()
    ids = []
    for s in SEEDS:
        body = {"name": s["name"], "category": s["category"], "photo": photo, "colors": ["Black"]}
        body.update(s.get("extra") or {})
        r = requests.post(f"{BASE_URL}/api/items", json=body, headers=hdrs, timeout=30)
        r.raise_for_status()
        ids.append(r.json()["id"])
    print(json.dumps({"token": tok, "ids": ids, "seeds": SEEDS}))

def cleanup(ids_and_token):
    tok = ids_and_token.get("token")
    hdrs = {"Authorization": f"Bearer {tok}"}
    # Also delete any lingering TEST_iter38 items
    r = requests.get(f"{BASE_URL}/api/items", headers=hdrs, timeout=60)
    items = r.json()
    to_delete = {i["id"] for i in items if (i.get("name") or "").startswith("TEST_iter38")}
    to_delete.update(ids_and_token.get("ids") or [])
    for iid in to_delete:
        requests.delete(f"{BASE_URL}/api/items/{iid}", headers=hdrs, timeout=15)
    print(json.dumps({"deleted": len(to_delete)}))

if __name__ == "__main__":
    if sys.argv[1] == "seed": seed()
    elif sys.argv[1] == "cleanup":
        cleanup(json.loads(sys.argv[2]))
