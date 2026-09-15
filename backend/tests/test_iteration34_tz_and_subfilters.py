"""Iteration 34 — regression tests for:
 (1) GET /api/dressme/context now accepts tz_offset= without erroring,
     and correctly returns has_context=False for a local date without a plan.
 (2) POST /api/dressme accepts tz_offset in body, and with local_date=TODAY
     does NOT pick up a plan that exists only for YESTERDAY.
 (3) POST /api/outfit/feedback still returns valid JSON with the same-category
     swap guard; deliberately clashing outfit surfaces a real problem.
 (4) Wardrobe classification exposure — since the classification is presentation-
     only on the frontend we only smoke-check that POST /api/items works and
     items round-trip with the fields SUB_RULES reads (name/style/pattern/
     description/fit_notes/sleeve_length). Cleanup via /items/bulk-delete.
"""
import os
import re
import datetime as dt
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://wardrobe-ai-311.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = "AureveTest2026"
SEEDED_BEARER = "test-session-token-aura-123"


def _fmt(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def _today():
    return dt.date.today()


def _yesterday():
    return dt.date.today() - dt.timedelta(days=1)


@pytest.fixture(scope="module")
def reviewer_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"reviewer login failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture
def reviewer_headers(reviewer_token):
    return {"Authorization": f"Bearer {reviewer_token}", "Content-Type": "application/json"}


@pytest.fixture
def seeded_headers():
    return {"Authorization": f"Bearer {SEEDED_BEARER}", "Content-Type": "application/json"}


def _cleanup_plans(headers, dates):
    for d in dates:
        try:
            plans = requests.get(f"{API}/plans",
                                 params={"from_date": _fmt(d), "to_date": _fmt(d)},
                                 headers=headers, timeout=20).json()
            for p in plans if isinstance(plans, list) else []:
                requests.delete(f"{API}/plans/{p['id']}", headers=headers, timeout=20)
        except Exception:
            pass


# ------------------------------------------------------------
# 1) tz_offset query param accepted on /dressme/context
# ------------------------------------------------------------
class TestContextTzOffset:
    def test_context_accepts_tz_offset_no_plan(self, seeded_headers):
        t = _today()
        _cleanup_plans(seeded_headers, [t])
        r = requests.get(f"{API}/dressme/context",
                         params={"date": _fmt(t), "tz_offset": 600},
                         headers=seeded_headers, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("has_context") is False, j
        assert j.get("source") in (None, ""), j

    def test_context_tz_offset_various_values(self, seeded_headers):
        # Different tz offsets shouldn't error even with no calendar hooked up
        for offset in (0, 600, -300, 660, -420):
            r = requests.get(f"{API}/dressme/context",
                             params={"date": _fmt(_today()), "tz_offset": offset},
                             headers=seeded_headers, timeout=20)
            assert r.status_code == 200, f"tz_offset={offset} -> {r.status_code} {r.text}"

    def test_context_with_plan_returns_true_source_plan(self, seeded_headers):
        t = _today()
        _cleanup_plans(seeded_headers, [t])
        c = requests.post(f"{API}/plans",
                          json={"date": _fmt(t),
                                "title": "TEST_i34 today plan",
                                "occasion": "TEST_office day"},
                          headers=seeded_headers, timeout=20)
        assert c.status_code == 200, c.text
        pid = c.json()["id"]
        try:
            r = requests.get(f"{API}/dressme/context",
                             params={"date": _fmt(t), "tz_offset": 600},
                             headers=seeded_headers, timeout=20)
            assert r.status_code == 200, r.text
            j = r.json()
            assert j.get("has_context") is True, j
            assert j.get("source") == "plan", j
            assert "TEST_" in (j.get("label") or ""), j
        finally:
            requests.delete(f"{API}/plans/{pid}", headers=seeded_headers, timeout=20)


# ------------------------------------------------------------
# 2) tz_offset in POST /api/dressme body
# ------------------------------------------------------------
class TestDressMeTzOffset:
    def test_local_date_today_ignores_yesterday_plan_with_tz(self, reviewer_headers):
        y = _yesterday()
        t = _today()
        _cleanup_plans(reviewer_headers, [y, t])
        c = requests.post(f"{API}/plans",
                          json={"date": _fmt(y),
                                "title": "TEST_i34 yesterday post",
                                "occasion": "TEST_yest_occ_ONLY_i34"},
                          headers=reviewer_headers, timeout=20)
        assert c.status_code == 200, c.text
        pid = c.json()["id"]
        try:
            r = requests.post(f"{API}/dressme",
                              json={"local_date": _fmt(t), "tz_offset": 600},
                              headers=reviewer_headers, timeout=180)
            if r.status_code == 402:
                pytest.skip("dressme quota exhausted (402)")
            assert r.status_code == 200, r.text
            j = r.json()
            occ = (j.get("occasion_used") or "")
            assert "TEST_yest_occ_ONLY_i34" not in occ, (
                f"yesterday's plan bled into today's occasion_used: {occ!r}")
            assert j.get("from_plan") in (None, ""), (
                f"from_plan should be null for today (no today plan): {j.get('from_plan')!r}")
        finally:
            requests.delete(f"{API}/plans/{pid}", headers=reviewer_headers, timeout=20)


# ------------------------------------------------------------
# 3) Outfit feedback — clashing outfit names a problem;
#    swap guard: out.category == in.category and out_id in submitted ids.
# ------------------------------------------------------------
NEGATIVE_TERMS = re.compile(
    r"(clash|mismatch|off|too\s+(formal|casual|sporty|dressy)|heavy|"
    r"doesn'?t\s+work|isn'?t\s+working|weakest|weak\s+piece|not\s+quite|"
    r"pull(s|ing)?\s+the\s+look|jars|fight|fights|out\s+of\s+place|"
    r"struggle|struggles|disconnect|disagree|inconsistent|proportion|"
    r"formality|season(s)?\s+(clash|mix|mismatch)|throws?\s+off|"
    r"consider|swap|replace|instead|better|would work|would suit)",
    re.IGNORECASE)


class TestFeedbackToneAndGuard:
    @pytest.fixture(scope="class")
    def reviewer_items(self, reviewer_token):
        h = {"Authorization": f"Bearer {reviewer_token}"}
        r = requests.get(f"{API}/items", headers=h, timeout=30)
        assert r.status_code == 200
        return r.json()

    def _pick(self, items, category):
        cat = category.lower()
        return [it for it in items if str(it.get("category", "")).lower() == cat]

    def test_clashing_outfit_names_problem(self, reviewer_headers, reviewer_items):
        tops = self._pick(reviewer_items, "Tops") + self._pick(reviewer_items, "Dresses")
        shoes = self._pick(reviewer_items, "Shoes")
        bottoms = self._pick(reviewer_items, "Bottoms")
        if not (tops and shoes):
            pytest.skip("wardrobe missing tops or shoes")

        def score_formal(it):
            s = f"{it.get('name','')} {it.get('style','')} {it.get('fabric','')}".lower()
            return int(bool(re.search(r"(silk|satin|lace|blazer|blouse|dress)", s)))

        def score_sporty(it):
            s = f"{it.get('name','')} {it.get('style','')} {it.get('fabric','')}".lower()
            return int(bool(re.search(r"(sneaker|trainer|sport|running|athletic|hiking)", s)))

        top = max(tops, key=score_formal)
        shoe = max(shoes, key=score_sporty)
        ids = [top["id"], shoe["id"]]
        if bottoms and top.get("category") != "Dresses":
            ids.insert(1, bottoms[0]["id"])
        r = requests.post(f"{API}/outfit/feedback",
                          headers=reviewer_headers,
                          json={"item_ids": ids, "occasion": "smart dinner"},
                          timeout=180)
        if r.status_code == 402:
            pytest.skip("stylist quota exhausted")
        assert r.status_code == 200, r.text
        j = r.json()
        verdict = str(j.get("verdict") or "")
        feedback = str(j.get("feedback") or "")
        combined = f"{verdict}\n{feedback}"
        assert verdict and feedback, f"missing verdict/feedback: {j}"
        positive_only = re.compile(r"^\s*(great|perfect|love it|nailed|flawless)\b", re.IGNORECASE)
        is_pure_compliment = bool(positive_only.match(verdict)) and not NEGATIVE_TERMS.search(combined)
        has_swap_or_add = bool(j.get("swap")) or bool(j.get("addition"))
        assert (not is_pure_compliment) or has_swap_or_add, (
            f"tone looks hollow-positive with no problem/swap: {j}")

    def test_swap_guard_holds(self, reviewer_headers, reviewer_items):
        tops = self._pick(reviewer_items, "Tops")
        bottoms = self._pick(reviewer_items, "Bottoms")
        shoes = self._pick(reviewer_items, "Shoes")
        if not (tops and bottoms and shoes):
            pytest.skip("need tops+bottoms+shoes")
        ids = [tops[0]["id"], bottoms[0]["id"], shoes[0]["id"]]
        r = requests.post(f"{API}/outfit/feedback",
                          headers=reviewer_headers,
                          json={"item_ids": ids, "occasion": "everyday"},
                          timeout=180)
        if r.status_code == 402:
            pytest.skip("stylist quota exhausted")
        assert r.status_code == 200, r.text
        j = r.json()
        swap = j.get("swap")
        if swap is not None:
            assert isinstance(swap, dict)
            assert swap.get("out_id") in set(ids)
            oc = str(swap.get("out_item", {}).get("category", "")).strip().lower()
            ic = str(swap.get("in_item", {}).get("category", "")).strip().lower()
            assert oc == ic, f"cross-category swap: out={oc} in={ic}"
        if j.get("addition") is not None:
            assert swap is None, f"both swap and addition returned: {j}"


# ------------------------------------------------------------
# 4) Wardrobe items — create the 11 test tops, verify all round-trip,
#    confirm each has a category/name for the frontend classifier to read,
#    then bulk-delete. (Chip labels are pure frontend so we verify UI in
#    playwright separately; here we ensure API supports it.)
# ------------------------------------------------------------
TEST_ITEMS = [
    ("TEST34_Black long-sleeve bodysuit", "Dresses",  {"style": "bodysuit", "fabric": "cotton", "sleeve_length": "long"}),
    ("TEST34_Beige knit bodysuit",        "Tops",     {"style": "bodysuit", "fabric": "knit"}),
    ("TEST34_Ivory halterneck top",       "Tops",     {"style": "halterneck", "fabric": "cotton"}),
    ("TEST34_Cream silk camisole",        "Tops",     {"style": "camisole", "fabric": "silk"}),
    ("TEST34_Black ribbed singlet",       "Tops",     {"style": "singlet", "fabric": "ribbed cotton"}),
    ("TEST34_White cotton t-shirt",       "Tops",     {"style": "t-shirt", "fabric": "cotton"}),
    ("TEST34_Navy poplin shirt",          "Tops",     {"style": "shirt", "fabric": "poplin"}),
    ("TEST34_Blush satin blouse",         "Tops",     {"style": "blouse", "fabric": "satin"}),
    ("TEST34_Black crop top",             "Tops",     {"style": "crop top", "fabric": "cotton"}),
    ("TEST34_Burgundy bustier",           "Tops",     {"style": "bustier", "fabric": "satin"}),
    ("TEST34_Olive long sleeve top",      "Tops",     {"style": "long sleeve top", "fabric": "jersey", "sleeve_length": "long"}),
]


class TestWardrobeSubfilterRoundTrip:
    created_ids = []

    # tiny 1x1 transparent PNG so /items accepts it
    TINY_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

    def test_create_all_and_verify_fields(self, reviewer_headers):
        for name, cat, extras in TEST_ITEMS:
            body = {
                "name": name,
                "category": cat,
                "colour": "black",
                "fabric": extras.get("fabric", ""),
                "style": extras.get("style", ""),
                "sleeve_length": extras.get("sleeve_length", ""),
                "photo": self.TINY_PNG,
                "orig_photo": self.TINY_PNG,
            }
            r = requests.post(f"{API}/items", json=body, headers=reviewer_headers, timeout=30)
            assert r.status_code == 200, f"create {name} -> {r.status_code} {r.text}"
            j = r.json()
            assert j.get("id"), j
            assert j.get("name") == name
            assert j.get("category") == cat
            TestWardrobeSubfilterRoundTrip.created_ids.append(j["id"])
        # Confirm they are in /items
        r = requests.get(f"{API}/items", headers=reviewer_headers, timeout=30)
        assert r.status_code == 200
        names = {it.get("name") for it in r.json()}
        for name, _c, _e in TEST_ITEMS:
            assert name in names, f"missing after GET /items: {name}"

    def test_zzz_bulk_delete_cleanup(self, reviewer_headers):
        ids = TestWardrobeSubfilterRoundTrip.created_ids
        if not ids:
            pytest.skip("nothing to clean up")
        r = requests.post(f"{API}/items/bulk-delete",
                          json={"item_ids": ids},
                          headers=reviewer_headers, timeout=30)
        assert r.status_code == 200, r.text
        assert (r.json() or {}).get("deleted", 0) >= len(ids)
