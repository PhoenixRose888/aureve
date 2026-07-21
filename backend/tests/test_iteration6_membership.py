"""
Iteration 6 — Premium membership + payments + gating/metering + regression.

Covers:
  * GET /api/membership/plans
  * FREE gating (HTTP 402) on all premium-only endpoints + household 2nd profile
  * FREE metering: stylist 5/day + beauty 1/month; beauty 400 must NOT consume credit
  * PREMIUM: all gated endpoints return 200; stylist unlimited; up to 6 profiles (7th=400)
  * Payments: /payments/checkout (valid + invalid) and /payments/status
  * Regression: items+pairs_count, insights, laundry, outfits, plans, wear, analyze-item

Cleanup runs in session teardown: removes premium_until, clears usage,
deletes any test-created profiles, and resets any laundry to Ready.
"""
import os
import time
import base64
import io
import pytest
import requests

from pymongo import MongoClient

BASE_URL = os.environ.get("BASE_URL", "https://wardrobe-ai-311.preview.emergentagent.com/api")
TOKEN = "test-session-token-aura-123"
ACCOUNT_ID = "user_testaura01"
AURA_PROFILE = "prof_365ddfe52deb"
DAVID_PROFILE = "prof_a82ae0522746"
ORIGIN = "https://wardrobe-ai-311.preview.emergentagent.com"

H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
H_AURA = {**H, "X-Profile-Id": AURA_PROFILE}
H_DAVID = {**H, "X-Profile-Id": DAVID_PROFILE}

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# --------------------------- Fixtures / helpers ---------------------------
@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    db = c[DB_NAME]
    yield db
    c.close()


@pytest.fixture(scope="session", autouse=True)
def _initial_reset(mongo):
    """Ensure FREE + clean usage BEFORE the test session starts."""
    mongo.users.update_one({"user_id": ACCOUNT_ID}, {"$unset": {"premium_until": ""}})
    mongo.usage.delete_many({"account_id": ACCOUNT_ID})
    yield
    # Final cleanup at end of session
    mongo.users.update_one({"user_id": ACCOUNT_ID}, {"$unset": {"premium_until": ""}})
    mongo.usage.delete_many({"account_id": ACCOUNT_ID})
    # Remove any TEST_ profiles that this run may have left behind
    stray = list(mongo.profiles.find(
        {"user_id": ACCOUNT_ID, "id": {"$nin": [AURA_PROFILE, DAVID_PROFILE]}}, {"id": 1}
    ))
    for p in stray:
        for coll in (mongo.items, mongo.outfits, mongo.wear_logs, mongo.plans):
            coll.delete_many({"user_id": p["id"]})
        mongo.profiles.delete_one({"_id": p["_id"]})
    # Reset any laundry to Ready in the Aura wardrobe
    mongo.items.update_many(
        {"user_id": AURA_PROFILE, "availability": {"$ne": "Ready"}},
        {"$set": {"availability": "Ready"}},
    )


def _clothing_b64() -> str:
    """Small realistic-ish clothing JPEG for shop-check / analyze-item tests."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (320, 400), (230, 220, 210))
        d = ImageDraw.Draw(img)
        d.polygon([(80, 120), (240, 120), (250, 380), (70, 380)], fill=(60, 90, 160), outline=(30, 40, 90))
        d.polygon([(80, 120), (40, 180), (60, 210), (95, 155)], fill=(55, 85, 150))
        d.polygon([(240, 120), (280, 180), (260, 210), (225, 155)], fill=(55, 85, 150))
        buf = io.BytesIO(); img.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return base64.b64encode(b"\xff\xd8\xff\xd9").decode()


def set_premium(mongo, on: bool):
    if on:
        mongo.users.update_one({"user_id": ACCOUNT_ID},
                               {"$set": {"premium_until": "2099-01-01T00:00:00+00:00"}})
    else:
        mongo.users.update_one({"user_id": ACCOUNT_ID}, {"$unset": {"premium_until": ""}})


# ============================ 1. MEMBERSHIP PLANS ============================
class TestMembershipPlans:
    def test_plans_shape_and_values(self):
        r = requests.get(f"{BASE_URL}/membership/plans", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["premium"] is False
        assert d["premium_until"] is None
        plans = {p["id"]: p for p in d["plans"]}
        assert set(plans.keys()) == {"monthly", "annual"}
        assert plans["monthly"]["amount"] == 9.99 and plans["monthly"]["days"] == 30
        assert plans["annual"]["amount"] == 79.99 and plans["annual"]["days"] == 365
        for p in plans.values():
            assert p["currency"] == "usd" and p["label"]

    def test_plans_requires_auth(self):
        r = requests.get(f"{BASE_URL}/membership/plans", timeout=15)
        assert r.status_code == 401


# ============================ 2. FREE gating (402) ============================
class TestFreeGating402:
    """Every premium-only endpoint must respond 402 for a FREE account.
    enforce_limit runs BEFORE the AI call, so these fire fast (no AI cost)."""

    def setup_method(self, method):
        # Guarantee free state each time
        pass  # session fixture already unset premium_until

    def _first_item_id(self):
        r = requests.get(f"{BASE_URL}/items", headers=H_AURA, timeout=15)
        assert r.status_code == 200
        items = r.json()
        return items[0]["id"] if items else None

    def test_packing_402(self):
        r = requests.post(f"{BASE_URL}/packing/plan", headers=H_AURA,
                          json={"destination": "Paris", "days": 4, "vibe": "casual"}, timeout=30)
        assert r.status_code == 402, r.text
        assert "Premium" in r.json().get("detail", "")

    def test_capsule_402(self):
        r = requests.post(f"{BASE_URL}/capsule/build", headers=H_AURA,
                          json={"theme": "Autumn"}, timeout=30)
        assert r.status_code == 402, r.text

    def test_shop_check_402(self):
        r = requests.post(f"{BASE_URL}/shop-check", headers=H_AURA,
                          json={"image": _clothing_b64()}, timeout=30)
        assert r.status_code == 402, r.text

    def test_missing_piece_402(self):
        r = requests.post(f"{BASE_URL}/insights/missing-piece", headers=H_AURA, timeout=30)
        assert r.status_code == 402, r.text

    def test_health_report_402(self):
        r = requests.post(f"{BASE_URL}/insights/health-report", headers=H_AURA, timeout=30)
        assert r.status_code == 402, r.text

    def test_compatibility_402(self):
        item_id = self._first_item_id()
        assert item_id, "Aura seed items required for compatibility test"
        r = requests.post(f"{BASE_URL}/items/{item_id}/compatibility",
                          headers=H_AURA, timeout=30)
        assert r.status_code == 402, r.text

    def test_second_profile_402(self):
        # Aura already has >=1 profile (2 in fact); creating another must 402 on FREE
        r = requests.post(f"{BASE_URL}/profiles", headers=H,
                          json={"name": "TEST_household_free", "emoji": "🧑"}, timeout=15)
        assert r.status_code == 402, r.text
        assert "Household" in r.json().get("detail", "") or "Premium" in r.json().get("detail", "")


# ============================ 3. FREE metering ============================
class TestFreeMetering:
    def test_stylist_5_then_6th_402(self, mongo):
        # Clean stylist usage
        mongo.usage.delete_many({"account_id": ACCOUNT_ID, "feature": "stylist"})
        payload = {"occasion": "casual coffee", "notes": "quick test"}
        successes = 0
        last_status = None
        for i in range(5):
            r = requests.post(f"{BASE_URL}/stylist/suggest",
                              headers=H_AURA, json=payload, timeout=180)
            last_status = r.status_code
            if r.status_code == 200:
                successes += 1
            else:
                # Log but continue so we still hit 6th
                print(f"[stylist call {i+1}] {r.status_code}: {r.text[:200]}")
        assert successes == 5, f"Expected 5 successful stylist calls, got {successes} (last={last_status})"
        # 6th must 402
        r6 = requests.post(f"{BASE_URL}/stylist/suggest",
                           headers=H_AURA, json=payload, timeout=30)
        assert r6.status_code == 402, r6.text
        assert "Premium" in r6.json().get("detail", "")

    def test_beauty_missing_skin_400_does_not_consume(self, mongo):
        mongo.usage.delete_many({"account_id": ACCOUNT_ID, "feature": "beauty"})
        # David has no skin_tone/undertone → 400
        r = requests.post(f"{BASE_URL}/beauty/suggest", headers=H_DAVID,
                          json={}, timeout=30)
        assert r.status_code == 400, r.text
        assert "skin tone" in r.json().get("detail", "").lower()
        used = mongo.usage.find_one({"account_id": ACCOUNT_ID, "feature": "beauty"})
        assert used is None or used.get("count", 0) == 0, "Missing-skin 400 must NOT consume monthly credit"

    def test_beauty_1_then_2nd_402(self, mongo):
        mongo.usage.delete_many({"account_id": ACCOUNT_ID, "feature": "beauty"})
        # 1st on Aura (has skin_tone+undertone) → 200
        r1 = requests.post(f"{BASE_URL}/beauty/suggest", headers=H_AURA,
                           json={"occasion": "wedding"}, timeout=180)
        assert r1.status_code == 200, r1.text
        j = r1.json()
        # sanity — expected keys per iteration_5 report
        for k in ("summary", "palette", "makeup", "hair"):
            assert k in j, f"missing '{k}' in beauty response"
        # 2nd within same month → 402
        r2 = requests.post(f"{BASE_URL}/beauty/suggest", headers=H_AURA,
                           json={"occasion": "brunch"}, timeout=30)
        assert r2.status_code == 402, r2.text


# ============================ 4. PAYMENTS ============================
class TestPayments:
    session_ids: list = []

    def test_checkout_monthly_success(self, mongo):
        r = requests.post(f"{BASE_URL}/payments/checkout", headers=H,
                          json={"plan": "monthly", "origin_url": ORIGIN}, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("session_id"), "session_id missing"
        assert j.get("url", "").startswith("https://"), f"expected https url, got {j.get('url')!r}"
        assert "stripe.com" in j["url"] or "checkout" in j["url"], f"unexpected url host: {j['url']}"
        # Record in DB
        tx = mongo.payment_transactions.find_one({"session_id": j["session_id"]})
        assert tx is not None
        assert tx["account_id"] == ACCOUNT_ID
        assert tx["plan"] == "monthly"
        assert abs(tx["amount"] - 9.99) < 1e-6
        assert tx["payment_status"] in ("initiated", "unpaid", "open")
        assert tx["processed"] is False
        TestPayments.session_ids.append(j["session_id"])

    def test_checkout_annual_success(self, mongo):
        r = requests.post(f"{BASE_URL}/payments/checkout", headers=H,
                          json={"plan": "annual", "origin_url": ORIGIN}, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("session_id") and j.get("url", "").startswith("https://")
        tx = mongo.payment_transactions.find_one({"session_id": j["session_id"]})
        assert tx and abs(tx["amount"] - 79.99) < 1e-6 and tx["plan"] == "annual"
        TestPayments.session_ids.append(j["session_id"])

    def test_checkout_invalid_plan_400(self):
        r = requests.post(f"{BASE_URL}/payments/checkout", headers=H,
                          json={"plan": "lifetime", "origin_url": ORIGIN}, timeout=30)
        assert r.status_code == 400, r.text

    def test_checkout_requires_auth(self):
        r = requests.post(f"{BASE_URL}/payments/checkout",
                          json={"plan": "monthly", "origin_url": ORIGIN},
                          headers={"Content-Type": "application/json"}, timeout=15)
        assert r.status_code == 401

    def test_status_unknown_session_404(self):
        r = requests.get(f"{BASE_URL}/payments/status/does_not_exist_xyz",
                         headers=H, timeout=30)
        assert r.status_code == 404, r.text

    def test_status_returns_unpaid_and_does_not_grant(self, mongo):
        assert TestPayments.session_ids, "checkout tests must run first"
        sid = TestPayments.session_ids[0]
        r = requests.get(f"{BASE_URL}/payments/status/{sid}", headers=H, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "payment_status" in j
        # Since we didn't complete the hosted UI, it must be unpaid/open, not "paid"
        assert j["payment_status"] != "paid", f"unexpected paid status: {j}"
        # Premium must NOT have been granted
        acct = mongo.users.find_one({"user_id": ACCOUNT_ID})
        assert not acct.get("premium_until"), "premium_until must remain unset for an unpaid session"
        assert j["premium"] is False


# ============================ 5. PREMIUM (200s) ============================
class TestPremiumFeatures:
    """Grants premium via Mongo then hits every gated endpoint. Uses live AI (slow)."""

    @pytest.fixture(scope="class", autouse=True)
    def _grant_and_revoke(self, mongo):
        set_premium(mongo, True)
        yield
        set_premium(mongo, False)

    def _first_item_id(self):
        r = requests.get(f"{BASE_URL}/items", headers=H_AURA, timeout=15)
        return r.json()[0]["id"]

    def test_plans_reflects_premium(self):
        r = requests.get(f"{BASE_URL}/membership/plans", headers=H, timeout=15)
        assert r.status_code == 200
        assert r.json()["premium"] is True

    def test_packing_200(self):
        r = requests.post(f"{BASE_URL}/packing/plan", headers=H_AURA,
                          json={"destination": "Paris", "days": 4, "vibe": "casual"}, timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "capsule_item_ids" in j and isinstance(j["capsule_item_ids"], list)

    def test_capsule_200(self):
        r = requests.post(f"{BASE_URL}/capsule/build", headers=H_AURA,
                          json={"theme": "Autumn"}, timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "capsule_item_ids" in j and "summary" in j

    def test_shop_check_200(self):
        r = requests.post(f"{BASE_URL}/shop-check", headers=H_AURA,
                          json={"image": _clothing_b64()}, timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "verdict" in j and j["verdict"] in ("Buy", "Skip", "Maybe")

    def test_missing_piece_200(self):
        r = requests.post(f"{BASE_URL}/insights/missing-piece", headers=H_AURA, timeout=180)
        assert r.status_code == 200, r.text

    def test_health_report_200(self):
        r = requests.post(f"{BASE_URL}/insights/health-report", headers=H_AURA, timeout=180)
        assert r.status_code == 200, r.text

    def test_compatibility_200(self):
        item_id = self._first_item_id()
        r = requests.post(f"{BASE_URL}/items/{item_id}/compatibility",
                          headers=H_AURA, timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "versatility_score" in j and "matches" in j

    def test_stylist_unlimited(self, mongo):
        # Fill 6 successes in one day (would 402 on FREE at 6th)
        # Note: metering test already put usage=5, but premium bypasses.
        successes = 0
        for i in range(6):
            r = requests.post(f"{BASE_URL}/stylist/suggest", headers=H_AURA,
                              json={"occasion": "casual"}, timeout=180)
            if r.status_code == 200:
                successes += 1
            else:
                print(f"[premium stylist {i+1}] {r.status_code}: {r.text[:200]}")
        assert successes == 6, f"Premium stylist expected 6/6, got {successes}"

    def test_beauty_unlimited(self):
        # Two consecutive within the same month must both 200
        r1 = requests.post(f"{BASE_URL}/beauty/suggest", headers=H_AURA,
                           json={"occasion": "date night"}, timeout=180)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{BASE_URL}/beauty/suggest", headers=H_AURA,
                           json={"occasion": "office"}, timeout=180)
        assert r2.status_code == 200, r2.text


# ============================ 6. PREMIUM household cap ============================
class TestPremiumHouseholdCap:
    created: list = []

    @pytest.fixture(scope="class", autouse=True)
    def _premium_on(self, mongo):
        set_premium(mongo, True)
        yield
        set_premium(mongo, False)
        # Cleanup extras we created
        for pid in TestPremiumHouseholdCap.created:
            for coll in (mongo.items, mongo.outfits, mongo.wear_logs, mongo.plans):
                coll.delete_many({"user_id": pid})
            mongo.profiles.delete_one({"id": pid, "user_id": ACCOUNT_ID})

    def test_can_create_up_to_6_and_7th_fails(self):
        # Currently Aura + David = 2 existing → create 4 more to reach 6
        for i in range(4):
            r = requests.post(f"{BASE_URL}/profiles", headers=H,
                              json={"name": f"TEST_house_{i+1}", "emoji": "🧑"}, timeout=15)
            assert r.status_code in (200, 201), f"create #{i+1}: {r.status_code} {r.text}"
            TestPremiumHouseholdCap.created.append(r.json()["id"])
        # Verify count == 6
        r = requests.get(f"{BASE_URL}/profiles", headers=H, timeout=15)
        assert len(r.json()) == 6
        # 7th must 400
        r7 = requests.post(f"{BASE_URL}/profiles", headers=H,
                           json={"name": "TEST_house_7"}, timeout=15)
        assert r7.status_code == 400, r7.text
        assert "6" in r7.json().get("detail", "") or "up to" in r7.json().get("detail", "").lower()


# ============================ 7. REGRESSION (light) ============================
class TestRegression:
    """Quick sanity of previously-free features. No AI unless free-tier stylist/analyze."""

    def test_items_have_pairs_count(self):
        r = requests.get(f"{BASE_URL}/items", headers=H_AURA, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        for it in items:
            assert "pairs_count" in it and isinstance(it["pairs_count"], int)

    def test_items_crud_roundtrip(self):
        payload = {
            "name": "TEST_reg_shirt",
            "category": "Tops",
            "colour_primary": "navy",
            "material": "cotton",
            "pattern": "solid",
            "season": "All",
            "formality": "Casual",
            "image_base64": _clothing_b64(),
        }
        c = requests.post(f"{BASE_URL}/items", headers=H_AURA, json=payload, timeout=30)
        assert c.status_code in (200, 201), c.text
        item_id = c.json()["id"]
        try:
            g = requests.get(f"{BASE_URL}/items/{item_id}", headers=H_AURA, timeout=15)
            assert g.status_code == 200 and g.json()["name"] == "TEST_reg_shirt"
            u = requests.put(f"{BASE_URL}/items/{item_id}", headers=H_AURA,
                             json={"name": "TEST_reg_shirt_renamed"}, timeout=15)
            assert u.status_code == 200
            g2 = requests.get(f"{BASE_URL}/items/{item_id}", headers=H_AURA, timeout=15)
            assert g2.json()["name"] == "TEST_reg_shirt_renamed"
        finally:
            d = requests.delete(f"{BASE_URL}/items/{item_id}", headers=H_AURA, timeout=15)
            assert d.status_code == 200
            g3 = requests.get(f"{BASE_URL}/items/{item_id}", headers=H_AURA, timeout=15)
            assert g3.status_code == 404

    def test_insights(self):
        r = requests.get(f"{BASE_URL}/insights", headers=H_AURA, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_laundry(self):
        r = requests.get(f"{BASE_URL}/laundry", headers=H_AURA, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_outfits_crud(self):
        # Need at least one item id
        it = requests.get(f"{BASE_URL}/items", headers=H_AURA, timeout=15).json()
        assert it
        r = requests.post(f"{BASE_URL}/outfits", headers=H_AURA,
                          json={"name": "TEST_reg_outfit", "item_ids": [it[0]["id"]]}, timeout=15)
        assert r.status_code in (200, 201), r.text
        oid = r.json()["id"]
        try:
            lst = requests.get(f"{BASE_URL}/outfits", headers=H_AURA, timeout=15)
            assert lst.status_code == 200 and any(o["id"] == oid for o in lst.json())
        finally:
            d = requests.delete(f"{BASE_URL}/outfits/{oid}", headers=H_AURA, timeout=15)
            assert d.status_code == 200

    def test_plans_crud(self):
        it = requests.get(f"{BASE_URL}/items", headers=H_AURA, timeout=15).json()
        assert it
        r = requests.post(f"{BASE_URL}/plans", headers=H_AURA,
                          json={"date": "2099-12-25", "item_ids": [it[0]["id"]], "note": "TEST_reg_plan"},
                          timeout=15)
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]
        try:
            lst = requests.get(f"{BASE_URL}/plans", headers=H_AURA, timeout=15)
            assert lst.status_code == 200 and any(p["id"] == pid for p in lst.json())
        finally:
            d = requests.delete(f"{BASE_URL}/plans/{pid}", headers=H_AURA, timeout=15)
            assert d.status_code == 200

    def test_wear_log(self):
        it = requests.get(f"{BASE_URL}/items", headers=H_AURA, timeout=15).json()
        assert it
        r = requests.post(f"{BASE_URL}/wear", headers=H_AURA,
                          json={"item_ids": [it[0]["id"]], "occasion": "TEST_reg_wear"}, timeout=15)
        assert r.status_code in (200, 201), r.text

    def test_analyze_item_free(self):
        # Free-tier feature, still works (no membership gating)
        r = requests.post(f"{BASE_URL}/analyze-item", headers=H_AURA,
                          json={"image": _clothing_b64()}, timeout=180)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "category" in j

    def test_analyze_item_with_category_hint(self):
        r = requests.post(f"{BASE_URL}/analyze-item", headers=H_AURA,
                          json={"image": _clothing_b64(), "category_hint": "Tops"}, timeout=180)
        assert r.status_code == 200, r.text
        assert r.json().get("category") == "Tops"
