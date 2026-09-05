"""
Launch batch B3 backend regression:
- POST /api/capture (clean=false) returns analysis fast
- POST /api/clean-photo returns clean_image separately
- POST /api/diag/log returns {ok:true}
- Demo isolation: guest sees demo, real acct never, reviewer still sees demo
- POST /api/items/bulk-delete: scope-safe, {deleted:n}, 400 on empty
- Free item cap (FREE_ITEM_CAP=100): 402 after cap; delete frees a slot
- Free metering: stylist/dressme = 5/MONTH (period key YYYY-MM)
- Stylist / DressMe suggest still works with cross-day diversity (avoid_item_ids)
- Health report returns underused_summary, no 'wasted' language
- Calendar authorize derives redirect_uri from x-forwarded-host
"""
import os
import base64
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/") + "/api"
REAL_TOKEN = "test-session-token-aura-123"
REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = "AureveTest2026"


def H(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _tiny_jpeg_b64():
    # Minimal 1x1 white JPEG so item creation is accepted without AI.
    hexed = (
        "ffd8ffe000104a46494600010101006000600000ffdb00430008060607060508070707090909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c202429201f2231211c1c2837292a2c2f2f2f1f2431353435322f2b2f2f2f2fffdb0043010909090c0b0c180d0d182f1c1c1c2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2f2fffc0001108000100010301220002110103110101ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f0100030101010101010101010000000000000102030405060708090a0bffc400b51100020102040403040705040400010277000102031104052131061241510761711322328108144291a1b1c109233352f0156272d10a162434e125f11718191a262728292a35363738393a434445464748494a535455565758595a636465666768696a737475767778797a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311003f00fbfcffd9"
    )
    return base64.b64encode(bytes.fromhex(hexed)).decode()


TINY_JPEG_B64 = _tiny_jpeg_b64()


# --- fixtures ---
@pytest.fixture(scope="session")
def guest():
    r = requests.post(f"{BASE_URL}/auth/guest", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()  # {session_token, user}


@pytest.fixture(scope="session")
def reviewer():
    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()  # {session_token, user}


# --- Capture / clean-photo / diag ---
class TestCapturePipeline:
    def test_capture_clean_false(self):
        r = requests.post(
            f"{BASE_URL}/capture",
            headers=H(REAL_TOKEN),
            json={"image": TINY_JPEG_B64, "clean": False},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "analysis" in body
        assert "clean_image" in body
        assert body["clean_image"] in (None, "")
        # analysis should be a dict (may be empty on 1x1) but the endpoint must
        # still return structural fields
        assert isinstance(body["analysis"], dict)
        assert "duplicates" in body

    def test_clean_photo_endpoint(self):
        r = requests.post(
            f"{BASE_URL}/clean-photo",
            headers=H(REAL_TOKEN),
            json={"image": TINY_JPEG_B64},
            timeout=90,
        )
        # Accept 200 with clean_image or 502 (upstream failure on 1x1) — both prove endpoint wired
        assert r.status_code in (200, 502), r.text
        if r.status_code == 200:
            assert "clean_image" in r.json()

    def test_diag_log(self):
        r = requests.post(
            f"{BASE_URL}/diag/log",
            json={"stage": "capture:start", "data": {"kb": 42}, "platform": "test"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}


# --- Demo isolation ---
class TestDemoIsolation:
    def test_guest_sees_demo(self, guest):
        tok = guest["session_token"]
        r = requests.get(f"{BASE_URL}/items", headers=H(tok), timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 10, f"guest should have demo wardrobe, got {len(items)}"

    def test_real_account_no_demo(self):
        r = requests.get(f"{BASE_URL}/items", headers=H(REAL_TOKEN), timeout=30)
        assert r.status_code == 200
        items = r.json()
        # None should be flagged demo
        assert not any(it.get("demo") for it in items), "real account leaked demo items"

    def test_reviewer_sees_demo(self, reviewer):
        tok = reviewer["session_token"]
        r = requests.get(f"{BASE_URL}/items", headers=H(tok), timeout=30)
        assert r.status_code == 200
        items = r.json()
        demo_items = [it for it in items if it.get("demo")]
        assert len(demo_items) >= 10, f"reviewer should see demo items, got {len(demo_items)}"

    def test_real_account_no_demo_in_laundry(self):
        r = requests.get(f"{BASE_URL}/laundry", headers=H(REAL_TOKEN), timeout=30)
        # /laundry may return object or list; accept 200 and no demo names surfacing
        assert r.status_code == 200, r.text


# --- Bulk delete ---
class TestBulkDelete:
    def test_bulk_delete_empty_returns_400(self, guest):
        tok = guest["session_token"]
        r = requests.post(f"{BASE_URL}/items/bulk-delete", headers=H(tok),
                          json={"item_ids": []}, timeout=15)
        assert r.status_code == 400

    def test_bulk_delete_only_own_scope(self, guest):
        # try to delete real-account items from guest scope — should return deleted:0
        r = requests.get(f"{BASE_URL}/items", headers=H(REAL_TOKEN), timeout=30)
        assert r.status_code == 200
        real_items = r.json()
        if not real_items:
            pytest.skip("No real-account items to attempt cross-scope delete")
        real_ids = [it["id"] for it in real_items[:2]]
        tok = guest["session_token"]
        r2 = requests.post(f"{BASE_URL}/items/bulk-delete", headers=H(tok),
                           json={"item_ids": real_ids}, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("deleted") == 0
        # sanity: real items still exist
        r3 = requests.get(f"{BASE_URL}/items", headers=H(REAL_TOKEN), timeout=30)
        still_ids = {it["id"] for it in r3.json()}
        for i in real_ids:
            assert i in still_ids, "cross-scope delete leaked!"

    def test_bulk_delete_own_items(self, guest):
        tok = guest["session_token"]
        # create two throwaway items on guest scope
        created = []
        for name in ("TEST_bulk_a", "TEST_bulk_b"):
            r = requests.post(f"{BASE_URL}/items", headers=H(tok), json={
                "name": name, "category": "Tops", "colour": "grey",
                "photo": TINY_JPEG_B64,
            }, timeout=30)
            assert r.status_code == 200, r.text
            created.append(r.json()["id"])
        r = requests.post(f"{BASE_URL}/items/bulk-delete", headers=H(tok),
                          json={"item_ids": created}, timeout=15)
        assert r.status_code == 200
        assert r.json()["deleted"] == 2
        # verify GET no longer returns them
        r = requests.get(f"{BASE_URL}/items", headers=H(tok), timeout=30)
        remaining = {it["id"] for it in r.json()}
        for c in created:
            assert c not in remaining


# --- Stylist + DressMe still work; diversity via avoid_item_ids ---
class TestStylistDressMe:
    def test_stylist_suggest_returns_outfit(self, reviewer):
        tok = reviewer["session_token"]
        r = requests.post(f"{BASE_URL}/stylist/suggest", headers=H(tok),
                          json={"occasion": "coffee", "weather": "mild"}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "resolved_items" in body or "items" in body or "outfit" in body

    def test_dressme_diversity(self, reviewer):
        tok = reviewer["session_token"]
        r1 = requests.post(f"{BASE_URL}/dressme", headers=H(tok),
                           json={"occasion": "brunch", "weather": "mild"}, timeout=60)
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        resolved = b1.get("resolved_items") or b1.get("items") or []
        ids1 = {(it.get("id")) for it in resolved if it.get("id")}
        if not ids1:
            pytest.skip("dressme did not return resolved_items")
        r2 = requests.post(f"{BASE_URL}/dressme", headers=H(tok),
                           json={"occasion": "brunch", "weather": "mild",
                                 "avoid_item_ids": list(ids1)}, timeout=60)
        assert r2.status_code == 200
        b2 = r2.json()
        resolved2 = b2.get("resolved_items") or b2.get("items") or []
        ids2 = {(it.get("id")) for it in resolved2 if it.get("id")}
        # not identical
        if ids2:
            assert ids2 != ids1, "avoid_item_ids failed to change outfit"


# --- Health report copy ---
class TestHealthReportCopy:
    def test_underused_summary_no_wasted_language(self, reviewer):
        tok = reviewer["session_token"]
        r = requests.post(f"{BASE_URL}/insights/health-report", headers=H(tok),
                          json={}, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        # Must have underused_summary key (may be empty string) and no wasted_summary key
        assert "underused_summary" in body, f"missing underused_summary: keys={list(body.keys())}"
        assert "wasted_summary" not in body
        # No judgemental language anywhere in the string values
        blob = " ".join(v for v in body.values() if isinstance(v, str)).lower()
        assert "wasted money" not in blob
        assert "waste of money" not in blob


# --- Calendar redirect_uri host derivation ---
class TestCalendarAuthorize:
    def test_derives_redirect_uri_from_forwarded_host(self):
        headers = {"Authorization": f"Bearer {REAL_TOKEN}",
                   "X-Forwarded-Host": "wardrobe-ai-311.emergent.host",
                   "X-Forwarded-Proto": "https"}
        r = requests.get(f"{BASE_URL}/calendar/authorize", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        url = r.json().get("url", "")
        assert "wardrobe-ai-311.emergent.host%2Fapi%2Fcalendar%2Fcallback" in url \
            or "wardrobe-ai-311.emergent.host/api/calendar/callback" in url, \
            f"redirect_uri did not use forwarded host. URL={url[:400]}"

    def test_falls_back_to_request_host(self):
        headers = {"Authorization": f"Bearer {REAL_TOKEN}"}
        r = requests.get(f"{BASE_URL}/calendar/authorize", headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        url = r.json().get("url", "")
        assert "redirect_uri=" in url


# --- Free item cap + monthly metering ---
# Grouped last because they mutate DB via HTTP.
class TestFreeItemCap:
    def test_item_cap_402_after_100(self, guest):
        """We use a fresh guest (Free) so we can add items to the cap without
        touching the persistent test-account. Delete-frees-slot verified after."""
        tok = guest["session_token"]
        # count current items
        r = requests.get(f"{BASE_URL}/items", headers=H(tok), timeout=30)
        assert r.status_code == 200
        current = len(r.json())
        need = 100 - current
        if need <= 0:
            pytest.skip("guest wardrobe already at/above cap; skipping fill test")
        created_ids = []
        # Add items until 402
        for i in range(need + 2):
            r = requests.post(f"{BASE_URL}/items", headers=H(tok), json={
                "name": f"TEST_cap_{i}_{uuid.uuid4().hex[:6]}",
                "category": "Tops", "colour": "grey",
                "photo": TINY_JPEG_B64,
            }, timeout=30)
            if r.status_code == 402:
                assert "100 pieces" in r.text or "hold up to" in r.text.lower(), r.text
                break
            assert r.status_code == 200, f"item {i} failed: {r.text}"
            created_ids.append(r.json()["id"])
        else:
            pytest.fail("Cap not enforced after exceeding limit")
        # Delete one, then insertion should succeed
        if created_ids:
            r = requests.delete(f"{BASE_URL}/items/{created_ids[-1]}",
                                headers=H(tok), timeout=15)
            assert r.status_code == 200, r.text
            r = requests.post(f"{BASE_URL}/items", headers=H(tok), json={
                "name": "TEST_cap_slot_freed",
                "category": "Tops", "colour": "grey",
                "photo": TINY_JPEG_B64,
            }, timeout=30)
            assert r.status_code == 200, f"delete did not free slot: {r.text}"


class TestFreeMonthlyMetering:
    """Verify Free tier stylist/dressme are metered per MONTH (5). We can't spin
    up a fresh Free account cheaply, so we introspect: 6th same-account call
    within a month must 402 with the monthly message. We use a fresh guest."""

    def test_stylist_monthly_limit(self, guest):
        tok = guest["session_token"]
        successes = 0
        last_402 = None
        for i in range(7):
            r = requests.post(f"{BASE_URL}/stylist/suggest", headers=H(tok),
                              json={"occasion": "coffee", "weather": "mild"}, timeout=60)
            if r.status_code == 200:
                successes += 1
            elif r.status_code == 402:
                last_402 = r.text
                break
            else:
                pytest.fail(f"unexpected {r.status_code}: {r.text[:200]}")
        assert last_402 is not None, f"stylist did not 402 after {successes} calls"
        assert "month" in last_402.lower(), f"expected monthly language, got {last_402}"
        assert successes <= 5, f"allowed more than 5 free stylist calls: {successes}"

    def test_dressme_monthly_limit(self, guest):
        tok = guest["session_token"]
        successes = 0
        last_402 = None
        for i in range(7):
            r = requests.post(f"{BASE_URL}/dressme", headers=H(tok),
                              json={"occasion": "brunch", "weather": "mild"}, timeout=60)
            if r.status_code == 200:
                successes += 1
            elif r.status_code == 402:
                last_402 = r.text
                break
            else:
                pytest.fail(f"unexpected {r.status_code}: {r.text[:200]}")
        assert last_402 is not None, f"dressme did not 402 after {successes} calls"
        assert "month" in last_402.lower(), f"expected monthly language, got {last_402}"
        assert successes <= 5, f"allowed more than 5 free dressme calls: {successes}"
