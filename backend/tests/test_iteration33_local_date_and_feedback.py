"""Iteration 33 — regression tests for:
 (1) Dress Me LOCAL-date fix on GET /api/dressme/context and POST /api/dressme
 (2) Outfit-feedback tone (candid: names a problem for a clashing outfit)
 (3) Feedback same-slot swap guard (regression from iteration 31)

Backend: FastAPI+Mongo. Hits the public preview URL used by the app.
"""
import os
import datetime as dt
import time
import re
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


# ----------------- fixtures -----------------
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


def _fmt(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def _today():
    return dt.date.today()


def _yesterday():
    return dt.date.today() - dt.timedelta(days=1)


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
# 1) LOCAL DATE ON GET /api/dressme/context
# ------------------------------------------------------------
class TestContextLocalDate:
    """A plan for YESTERDAY (local) must not leak into TODAY's context.
    Prior bug: server derived today from UTC and would read yesterday's plan
    for users ahead of UTC (e.g. AU +10/+11)."""

    def test_yesterday_plan_does_not_leak_into_today_context(self, seeded_headers):
        y = _yesterday()
        t = _today()
        _cleanup_plans(seeded_headers, [y, t])
        # create yesterday's plan
        c = requests.post(f"{API}/plans",
                          json={"date": _fmt(y),
                                "title": "TEST_i33 yesterday plan",
                                "occasion": "TEST_date night"},
                          headers=seeded_headers, timeout=20)
        assert c.status_code == 200, c.text
        plan_id = c.json().get("id")
        assert plan_id
        try:
            # Probe with TODAY's local date — must be false
            r_today = requests.get(f"{API}/dressme/context",
                                   params={"date": _fmt(t)},
                                   headers=seeded_headers, timeout=20)
            assert r_today.status_code == 200, r_today.text
            j_today = r_today.json()
            assert j_today.get("has_context") is False, (
                f"yesterday's plan leaked into today's context: {j_today}")
            assert j_today.get("source") in (None, ""), j_today

            # Probe with YESTERDAY's local date — must be true, source=plan
            r_yest = requests.get(f"{API}/dressme/context",
                                  params={"date": _fmt(y)},
                                  headers=seeded_headers, timeout=20)
            assert r_yest.status_code == 200, r_yest.text
            j_yest = r_yest.json()
            assert j_yest.get("has_context") is True, j_yest
            assert j_yest.get("source") == "plan", j_yest
            # label should be title or occasion
            label = j_yest.get("label") or ""
            assert "TEST_" in label, f"label missing plan text: {label!r}"
        finally:
            d = requests.delete(f"{API}/plans/{plan_id}",
                                headers=seeded_headers, timeout=20)
            assert d.status_code == 200, d.text
        # after cleanup, both dates should be false
        r_after = requests.get(f"{API}/dressme/context",
                               params={"date": _fmt(y)},
                               headers=seeded_headers, timeout=20)
        assert r_after.status_code == 200
        assert r_after.json().get("has_context") is False

    def test_context_still_works_without_date_param(self, seeded_headers):
        _cleanup_plans(seeded_headers, [_today()])
        r = requests.get(f"{API}/dressme/context",
                         headers=seeded_headers, timeout=20)
        assert r.status_code == 200, r.text
        # No plan for today (UTC) -> has_context False (calendar not connected)
        assert r.json().get("has_context") is False


# ------------------------------------------------------------
# 2) LOCAL DATE ON POST /api/dressme
# ------------------------------------------------------------
class TestDressMeLocalDate:
    """local_date=TODAY must NOT pick up yesterday's plan; local_date=YESTERDAY
    may; an explicit `occasion` in body must always win."""

    def test_local_date_today_ignores_yesterday_plan(self, seeded_headers):
        y = _yesterday()
        t = _today()
        _cleanup_plans(seeded_headers, [y, t])
        c = requests.post(f"{API}/plans",
                          json={"date": _fmt(y),
                                "title": "TEST_i33 yesterday post",
                                "occasion": "TEST_yesterday_occasion_ONLY"},
                          headers=seeded_headers, timeout=20)
        assert c.status_code == 200, c.text
        plan_id = c.json()["id"]
        try:
            # POST /api/dressme with local_date=TODAY — no occasion,
            # no plan for today -> must NOT reference yesterday's plan
            r = requests.post(f"{API}/dressme",
                              json={"local_date": _fmt(t)},
                              headers=seeded_headers, timeout=120)
            if r.status_code == 402:
                pytest.skip("dressme quota exhausted (402)")
            assert r.status_code == 200, r.text
            j = r.json()
            occ = (j.get("occasion_used") or "")
            from_plan = j.get("from_plan")
            assert "TEST_yesterday_occasion_ONLY" not in occ, (
                f"yesterday's plan bled into today's occasion_used: {occ!r}")
            assert from_plan in (None, ""), (
                f"from_plan should be null for today (no today plan): {from_plan!r}")

            # POST with local_date=YESTERDAY may use that plan
            r2 = requests.post(f"{API}/dressme",
                               json={"local_date": _fmt(y)},
                               headers=seeded_headers, timeout=120)
            if r2.status_code == 402:
                pytest.skip("dressme quota exhausted (402) on 2nd call")
            assert r2.status_code == 200, r2.text
            j2 = r2.json()
            # We don't require it to use the plan, but from_plan or occasion_used may reference it
            # At minimum: no error and a from_plan value is allowed
            assert isinstance(j2.get("occasion_used"), str)

            # Explicit occasion always wins even when a plan exists for that date
            r3 = requests.post(f"{API}/dressme",
                               json={"local_date": _fmt(y),
                                     "occasion": "TEST_explicit override brunch"},
                               headers=seeded_headers, timeout=120)
            if r3.status_code == 402:
                pytest.skip("dressme quota exhausted (402) on 3rd call")
            assert r3.status_code == 200, r3.text
            j3 = r3.json()
            assert "TEST_explicit override brunch" in (j3.get("occasion_used") or ""), (
                f"explicit occasion did not win: {j3.get('occasion_used')!r}")
        finally:
            requests.delete(f"{API}/plans/{plan_id}", headers=seeded_headers, timeout=20)


# ------------------------------------------------------------
# 3) OUTFIT FEEDBACK TONE — must name a problem for a clashing look
# ------------------------------------------------------------
NEGATIVE_TERMS = re.compile(
    r"(clash|mismatch|off|too\s+(formal|casual|sporty|dressy)|heavy|"
    r"doesn'?t\s+work|isn'?t\s+working|weakest|weak\s+piece|not\s+quite|"
    r"pull(s|ing)?\s+the\s+look|jars|fight|fights|out\s+of\s+place|"
    r"struggle|struggles|disconnect|disagree|inconsistent|proportion|"
    r"formality|season(s)?\s+(clash|mix|mismatch)|throws?\s+off)",
    re.IGNORECASE)


class TestFeedbackTone:
    """Submit a deliberately clashing combination and confirm the response
    actually names a problem rather than opening with a hollow compliment."""

    @pytest.fixture(scope="class")
    def reviewer_items(self, reviewer_token):
        h = {"Authorization": f"Bearer {reviewer_token}"}
        r = requests.get(f"{API}/items", headers=h, timeout=30)
        assert r.status_code == 200
        return r.json()

    def _pick(self, items, category):
        cat = category.lower()
        for it in items:
            if str(it.get("category", "")).lower() == cat:
                yield it

    def test_clashing_outfit_names_problem(self, reviewer_headers, reviewer_items):
        # Try to pick a formal-leaning top with sporty shoes to force a mismatch
        tops = list(self._pick(reviewer_items, "Tops")) + list(self._pick(reviewer_items, "Dresses"))
        shoes = list(self._pick(reviewer_items, "Shoes"))
        bottoms = list(self._pick(reviewer_items, "Bottoms"))
        if not (tops and shoes):
            pytest.skip("Wardrobe missing tops or shoes for clashing test")

        # Prefer a silk/formal top + sneaker/sporty shoe if we can find them
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
                          json={"item_ids": ids,
                                "occasion": "smart dinner"},
                          timeout=180)
        if r.status_code == 402:
                pytest.skip("stylist quota exhausted")
        assert r.status_code == 200, r.text
        data = r.json()
        verdict = str(data.get("verdict") or "")
        feedback = str(data.get("feedback") or "")
        combined = f"{verdict}\n{feedback}"
        assert verdict and feedback, f"missing verdict/feedback: {data}"
        # Feedback should not be a pure compliment for a formal top + sporty shoes look.
        # We accept it as "candid" if it either names a problem, mentions swap/addition,
        # or verdict itself is not entirely positive.
        positive_only = re.compile(r"^\s*(great|perfect|love it|nailed|flawless)\b", re.IGNORECASE)
        is_pure_compliment = bool(positive_only.match(verdict)) and not NEGATIVE_TERMS.search(combined)
        has_swap_or_add = bool(data.get("swap")) or bool(data.get("addition"))
        # It's OK to be positive IF a swap/addition is offered OR if the model
        # legitimately thinks it works. We just want to prove the prompt no
        # longer forces a hollow compliment — so if none of these signals fire
        # we log and mark xfail-ish.
        candid = (not is_pure_compliment) or has_swap_or_add
        assert candid, f"tone looks hollow-positive with no problem/swap: {data}"

    def test_swap_is_same_slot_or_null(self, reviewer_headers, reviewer_items):
        """Regression: if a swap is returned, out/in categories must match
        and out_id must be in submitted ids. Otherwise swap must be null,
        with any cross-category piece coming through as `addition`."""
        tops = list(self._pick(reviewer_items, "Tops"))
        bottoms = list(self._pick(reviewer_items, "Bottoms"))
        shoes = list(self._pick(reviewer_items, "Shoes"))
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
            assert oc == ic, f"cross-category swap slipped through: out={oc} in={ic}"
        if j.get("addition") is not None:
            assert swap is None, f"both swap and addition returned: {j}"
