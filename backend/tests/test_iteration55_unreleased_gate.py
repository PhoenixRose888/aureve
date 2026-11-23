"""Iteration 55 — unreleased features must stay unreachable.

Packing, Capsule, Try On and Planner are kept in the codebase for future work
but must not be reachable by any user. Their routes answer 404, exactly like an
unknown path, while every released endpoint keeps working.
"""
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com"
H = {"Authorization": f"Bearer {os.environ.get('TEST_SESSION_TOKEN', '')}", "Content-Type": "application/json"}
T = 30

GATED = [
    ("POST", "/tryon", {"person_image": "x", "item_ids": []}),
    ("GET", "/tryon/photo", None),
    ("PUT", "/tryon/photo", {"photo": "x"}),
    ("DELETE", "/tryon/photo", None),
    ("POST", "/plans", {"date": "2026-12-01", "outfit_id": "x"}),
    ("GET", "/plans?from_date=2026-12-01&to_date=2026-12-31", None),
    ("DELETE", "/plans/plan_whatever", None),
    ("POST", "/packing/plan", {"destination": "Paris", "days": 3}),
    ("POST", "/capsule/build", {"theme": "Work"}),
    ("POST", "/stylist/suggest", {"occasion": "Office"}),
]

RELEASED = [
    ("GET", "/items?summary=1"),
    ("GET", "/items/capacity"),
    ("GET", "/outfits"),
    ("GET", "/wear"),
    ("GET", "/auth/me"),
    ("GET", "/laundry"),
    ("GET", "/collections"),
    ("GET", "/stylist/threads"),
    ("GET", "/weather?lat=51.5&lon=-0.12"),
]


@pytest.mark.parametrize("method,path,body", GATED)
def test_unreleased_routes_return_404(method, path, body):
    r = requests.request(method, f"{BASE_URL}/api{path}", headers=H, json=body, timeout=T)
    assert r.status_code == 404, f"{method} {path} -> {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("method,path", RELEASED)
def test_released_routes_still_work(method, path):
    r = requests.request(method, f"{BASE_URL}/api{path}", headers=H, timeout=T)
    assert r.status_code == 200, f"{method} {path} -> {r.status_code} {r.text[:200]}"
