"""
Iteration 37 backend tests:
- Item subcategory persistence (create, update, clear)
- Calendar diagnostics (config fingerprint, last_callback_error, invalid state -> Link expired page)
"""
import os
import time
import pytest
import requests

# 1x1 transparent PNG (base64) for endpoints that require a photo
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII="
)

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = "AureveTest2026"


@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(f"{API}/auth/login",
                      json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"reviewer login failed: {r.status_code} {r.text[:200]}"
    tok = r.json()["session_token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# -------------------- SUBCATEGORY PERSISTENCE --------------------
class TestSubcategoryPersistence:
    created_ids = []

    def test_create_item_with_subcategory(self, auth_headers):
        payload = {
            "name": "TEST_iter37 Bodysuit A",
            "category": "Tops",
            "subcategory": "Bodysuits",
            "colour": "Black",
            "season": "All",
            "availability": "Ready",
            "photo": TINY_PNG_B64,
        }
        r = requests.post(f"{API}/items", headers=auth_headers, json=payload, timeout=20)
        assert r.status_code == 200, f"POST /items failed: {r.status_code} {r.text[:200]}"
        item = r.json()
        assert item.get("subcategory") == "Bodysuits", f"stored subcategory wrong: {item}"
        assert item.get("category") == "Tops"
        TestSubcategoryPersistence.created_ids.append(item["id"])

    def test_get_items_returns_subcategory(self, auth_headers):
        r = requests.get(f"{API}/items", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        items = r.json()
        target = next((i for i in items if i["id"] in TestSubcategoryPersistence.created_ids), None)
        assert target is not None, "created item missing from GET /items"
        assert target.get("subcategory") == "Bodysuits"

    def test_put_updates_category_and_subcategory(self, auth_headers):
        assert TestSubcategoryPersistence.created_ids, "no seed item"
        iid = TestSubcategoryPersistence.created_ids[0]
        # Emulate the wardrobe editor changing category+subcategory
        r = requests.put(f"{API}/items/{iid}", headers=auth_headers,
                         json={"category": "Tops", "subcategory": "Singlets"}, timeout=20)
        assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text[:200]}"
        got = requests.get(f"{API}/items", headers=auth_headers, timeout=20).json()
        target = next((i for i in got if i["id"] == iid), None)
        assert target and target.get("subcategory") == "Singlets", f"subcategory not updated: {target}"
        assert target.get("category") == "Tops"

    def test_put_empty_string_clears_subcategory(self, auth_headers):
        assert TestSubcategoryPersistence.created_ids, "no seed item"
        iid = TestSubcategoryPersistence.created_ids[0]
        r = requests.put(f"{API}/items/{iid}", headers=auth_headers,
                         json={"subcategory": ""}, timeout=20)
        assert r.status_code == 200, f"PUT clear failed: {r.status_code} {r.text[:200]}"
        got = requests.get(f"{API}/items", headers=auth_headers, timeout=20).json()
        target = next((i for i in got if i["id"] == iid), None)
        assert target is not None
        # "" is the cleared/automatic sentinel — anything falsy passes here
        assert not target.get("subcategory"), f"subcategory not cleared: {target.get('subcategory')!r}"

    def test_cross_category_flow(self, auth_headers):
        # Reproduce the frontend flow: item saved as Dresses, then edited to Tops>Bodysuits
        create = requests.post(f"{API}/items", headers=auth_headers, json={
            "name": "TEST_iter37 Denim jumpsuit",
            "category": "Dresses",
            "colour": "Black",
            "availability": "Ready",
            "photo": TINY_PNG_B64,
        }, timeout=20)
        assert create.status_code == 200, create.text[:200]
        iid = create.json()["id"]
        TestSubcategoryPersistence.created_ids.append(iid)
        # Edit: switch to Tops + Bodysuits
        upd = requests.put(f"{API}/items/{iid}", headers=auth_headers,
                           json={"category": "Tops", "subcategory": "Bodysuits"}, timeout=20)
        assert upd.status_code == 200, upd.text[:200]
        got = requests.get(f"{API}/items", headers=auth_headers, timeout=20).json()
        target = next((i for i in got if i["id"] == iid), None)
        assert target and target["category"] == "Tops" and target["subcategory"] == "Bodysuits", target

    @classmethod
    def teardown_class(cls):
        # Cleanup
        r = requests.post(f"{API}/auth/login",
                          json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD}, timeout=20)
        if r.status_code != 200:
            return
        h = {"Authorization": f"Bearer {r.json()['session_token']}"}
        for iid in cls.created_ids:
            try:
                requests.delete(f"{API}/items/{iid}", headers=h, timeout=20)
            except Exception:
                pass


# -------------------- CALENDAR DIAGNOSTICS --------------------
class TestCalendarDiagnostics:
    def test_calendar_config_shape(self):
        r = requests.get(f"{API}/calendar/config", timeout=20)
        assert r.status_code == 200, f"config failed: {r.status_code} {r.text[:200]}"
        cfg = r.json()
        assert "client_secret_fingerprint" in cfg
        assert "last_callback_error" in cfg
        assert "redirect_uri_sent_to_google" in cfg
        assert "client_id" in cfg
        # last_callback_error should be null OR a dict (never crash)
        assert cfg["last_callback_error"] is None or isinstance(cfg["last_callback_error"], dict)
        # fingerprint should be short hex OR null if secret missing
        fp = cfg["client_secret_fingerprint"]
        assert fp is None or (isinstance(fp, str) and len(fp) == 10)

    def test_calendar_callback_invalid_state_no_500(self):
        # Simulate Google redirecting back with an unknown state
        r = requests.get(f"{API}/calendar/callback",
                         params={"code": "fake", "state": "does-not-exist-xyz"},
                         timeout=20, allow_redirects=False)
        assert r.status_code == 200, f"callback should render page not 500: {r.status_code}"
        assert "Link expired" in r.text, f"expected Link expired page, got: {r.text[:200]}"

    def test_calendar_callback_error_param_no_500(self):
        r = requests.get(f"{API}/calendar/callback",
                         params={"error": "access_denied"}, timeout=20)
        assert r.status_code == 200
        assert "cancelled" in r.text.lower()


# -------------------- PREMIUM COPY (backend sanity — not applicable, FE only) --------------------
# Handled by UI test.


# -------------------- REGRESSION SMOKE --------------------
class TestRegressionSmoke:
    def test_health(self):
        r = requests.get(f"{API}/", timeout=15)
        # Root can be 404 or 200 depending on prefix; just ensure server responds
        assert r.status_code in (200, 404), r.status_code

    def test_reviewer_is_premium(self, auth_headers):
        r = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text[:200]
        me = r.json()
        assert me.get("is_premium") is True or me.get("premium_until"), me

    def test_reviewer_has_items(self, auth_headers):
        r = requests.get(f"{API}/items", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
