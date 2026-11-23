"""Iteration 40 backend tests.

Two launch fixes to cover:
1. POST /api/dressme deterministic necessity classification via necessity_for():
   - Tops/Bottoms/Dresses/Shoes always -> "core"
   - Bags/Jewellery/Accessories never "core" (only recommended/optional)
   - Outerwear "core" only when temperature <= 15 or weather mentions
     rain/drizzle/shower/snow/storm/wind, otherwise recommended/optional.
2. GET /api/calendar/authorize + /api/calendar/config in preview:
   - preview holds a valid ~35 char secret so authorize returns 200 with a
     Google URL and config reports client_secret_length == 35.
"""

import os
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = os.environ.get("REVIEWER_PASSWORD", "")

CLOTHING_CORE = {"Tops", "Bottoms", "Dresses", "Shoes"}
EXTRAS_ONLY = {"Bags", "Jewellery", "Accessories"}
BAD_WEATHER_RE = ("rain", "drizzle", "shower", "snow", "storm", "wind")


@pytest.fixture(scope="module")
def reviewer_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("session_token") or r.json().get("token")
    assert token, f"no token in {r.json()}"
    return token


@pytest.fixture(scope="module")
def auth_headers(reviewer_token):
    return {"Authorization": f"Bearer {reviewer_token}"}


# ---------- necessity classification -----------------------------------------

def _call_dressme(auth_headers, temperature, weather, occasion):
    r = requests.post(
        f"{BASE_URL}/api/dressme",
        headers=auth_headers,
        json={"temperature": temperature, "weather": weather, "occasion": occasion},
        timeout=120,
    )
    assert r.status_code == 200, f"dressme failed: {r.status_code} {r.text}"
    data = r.json()
    assert "resolved_items" in data and isinstance(data["resolved_items"], list)
    assert len(data["resolved_items"]) >= 1
    return data


def _assert_baseline_rules(resolved):
    """Rules that MUST hold on every response regardless of weather."""
    for entry in resolved:
        item = entry.get("item") or {}
        cat = item.get("category")
        nec = entry.get("necessity")
        assert nec in {"core", "recommended", "optional"}, f"bad necessity {nec} for {cat}"
        if cat in CLOTHING_CORE:
            assert nec == "core", (
                f"Category {cat} must be core, got {nec} (item {item.get('id')})"
            )
        if cat in EXTRAS_ONLY:
            assert nec != "core", (
                f"Category {cat} must NEVER be core, got core (item {item.get('id')})"
            )


def test_dressme_clear_warm_outerwear_not_core(auth_headers):
    """26C + clear sky: any outerwear returned must NOT be core."""
    data = _call_dressme(
        auth_headers,
        temperature=26,
        weather="Clear sky",
        occasion="brunch with friends",
    )
    _assert_baseline_rules(data["resolved_items"])
    outer = [e for e in data["resolved_items"] if (e.get("item") or {}).get("category") == "Outerwear"]
    for e in outer:
        assert e["necessity"] != "core", (
            f"Outerwear should not be core at 26C clear, got {e['necessity']}"
        )


def test_dressme_cold_rain_outerwear_core_if_present(auth_headers):
    """9C + light rain: outerwear (if selected) must be core."""
    data = _call_dressme(
        auth_headers,
        temperature=9,
        weather="Light rain",
        occasion="running errands in town",
    )
    _assert_baseline_rules(data["resolved_items"])
    outer = [e for e in data["resolved_items"] if (e.get("item") or {}).get("category") == "Outerwear"]
    # Not required for outerwear to be present, but if it is, it must be core.
    for e in outer:
        assert e["necessity"] == "core", (
            f"Outerwear at 9C light rain must be core, got {e['necessity']}"
        )


def test_dressme_windy_forces_outerwear_core(auth_headers):
    """Weather mentioning wind is enough — even at mild temperature."""
    data = _call_dressme(
        auth_headers,
        temperature=18,
        weather="Windy",
        occasion="a walk in the park",
    )
    _assert_baseline_rules(data["resolved_items"])
    outer = [e for e in data["resolved_items"] if (e.get("item") or {}).get("category") == "Outerwear"]
    for e in outer:
        assert e["necessity"] == "core", (
            f"Outerwear when windy must be core, got {e['necessity']}"
        )


def test_dressme_mild_dry_outerwear_extras_only(auth_headers):
    """20C dry: outerwear (if included) must be recommended/optional."""
    data = _call_dressme(
        auth_headers,
        temperature=20,
        weather="Sunny",
        occasion="coffee catch-up",
    )
    _assert_baseline_rules(data["resolved_items"])
    outer = [e for e in data["resolved_items"] if (e.get("item") or {}).get("category") == "Outerwear"]
    for e in outer:
        assert e["necessity"] in {"recommended", "optional"}, (
            f"Outerwear on mild dry day should not be core, got {e['necessity']}"
        )


# ---------- calendar preview guard -------------------------------------------

def test_calendar_config_preview_has_valid_secret(auth_headers):
    r = requests.get(f"{BASE_URL}/api/calendar/config", headers=auth_headers, timeout=15)
    assert r.status_code == 200, f"config failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("client_secret_present") is True
    # Preview holds the correct 35-char Google secret
    assert data.get("client_secret_length") == 35, (
        f"preview secret length expected 35, got {data.get('client_secret_length')}"
    )


def test_calendar_authorize_preview_returns_google_url(auth_headers):
    r = requests.get(f"{BASE_URL}/api/calendar/authorize", headers=auth_headers, timeout=15)
    assert r.status_code == 200, f"authorize failed: {r.status_code} {r.text}"
    data = r.json()
    url = data.get("url", "")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?"), (
        f"unexpected auth url: {url}"
    )
    assert "client_id=" in url and "state=" in url and "redirect_uri=" in url
