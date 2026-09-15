"""Iteration 31 — regression tests for POST /api/outfit/feedback

Bug: 'Check My Outfit' sometimes proposed a cross-category piece (e.g. a blazer
suggested when the outfit contained top/skirt/shoes) and the mobile client
applied it as a replacement of the SHOES slot, silently emptying the Shoes slot.

Backend guarantees under test:
1. When `swap` is present in the response, out_item.category == in_item.category
   (same-slot only, case-insensitive) AND out_id is one of the submitted
   item_ids.
2. When the AI proposes a cross-category piece, `swap` MUST be null and the
   suggestion is surfaced as `addition` = {name, category, why}.
3. Guard rails: <2 item_ids -> 400; unknown ids -> 404; response always
   contains `verdict` and `feedback`.
4. Free-account gating still returns HTTP 402.
"""

import os
import time
import pytest
import requests

BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = "AureveTest2026"
FREE_TOKEN = "test-session-token-aura-123"


# ------------------------- session fixtures ------------------------- #

@pytest.fixture(scope="module")
def reviewer_token():
    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"reviewer login failed: {r.status_code} {r.text}"
    return r.json()["session_token"]


@pytest.fixture(scope="module")
def reviewer_headers(reviewer_token):
    return {"Authorization": f"Bearer {reviewer_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def free_headers():
    return {"Authorization": f"Bearer {FREE_TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def reviewer_wardrobe(reviewer_headers):
    """Return items grouped by lowercase category."""
    r = requests.get(f"{BASE_URL}/items", headers=reviewer_headers, timeout=30)
    assert r.status_code == 200, r.text
    items = r.json()
    grouped: dict = {}
    for it in items:
        grouped.setdefault(str(it.get("category", "")).strip().lower(), []).append(it)
    return grouped


# ----------------------------- helpers ------------------------------ #

def _norm(s):
    return str(s or "").strip().lower()


def _pick_ids(grouped, cats):
    picked = []
    for c in cats:
        bucket = grouped.get(c) or []
        if not bucket:
            return None
        picked.append(bucket[0])
    return picked


# --------------------------- guard rails ---------------------------- #

class TestOutfitFeedbackGuardRails:
    def test_fewer_than_two_items_returns_400(self, reviewer_headers, reviewer_wardrobe):
        any_item = next(iter([v for bucket in reviewer_wardrobe.values() for v in bucket]))
        r = requests.post(
            f"{BASE_URL}/outfit/feedback",
            headers=reviewer_headers,
            json={"item_ids": [any_item["id"]]},
            timeout=60,
        )
        assert r.status_code == 400, r.text

    def test_empty_item_ids_returns_400(self, reviewer_headers):
        r = requests.post(
            f"{BASE_URL}/outfit/feedback",
            headers=reviewer_headers,
            json={"item_ids": []},
            timeout=60,
        )
        assert r.status_code == 400

    def test_unknown_ids_returns_404(self, reviewer_headers):
        r = requests.post(
            f"{BASE_URL}/outfit/feedback",
            headers=reviewer_headers,
            json={"item_ids": ["item_ghost_1", "item_ghost_2"]},
            timeout=60,
        )
        assert r.status_code == 404


# ----------------------- swap guarantee tests ----------------------- #

class TestOutfitFeedbackSwapCategory:
    """Call /outfit/feedback multiple times on different valid outfits and
    assert NO cross-category swap is ever returned. Any swap MUST have
    out_item.category == in_item.category (case-insensitive) AND out_id must
    be one of the submitted item_ids. If the model proposes an addition, the
    response surfaces it under `addition` and swap is null."""

    @pytest.fixture(scope="class")
    def outfit_combos(self, reviewer_wardrobe):
        combos = []
        # Combo 1: Top + Bottom + Shoes (the exact repro scenario)
        c1 = _pick_ids(reviewer_wardrobe, ["tops", "bottoms", "shoes"])
        if c1:
            combos.append(("tops+bottoms+shoes", c1))
        # Combo 2: Dress + Shoes (2 categories)
        c2 = _pick_ids(reviewer_wardrobe, ["dresses", "shoes"])
        if c2:
            combos.append(("dresses+shoes", c2))
        # Combo 3: Top + Bottom
        c3 = _pick_ids(reviewer_wardrobe, ["tops", "bottoms"])
        if c3:
            combos.append(("tops+bottoms", c3))
        # Combo 4: Top + Bottom + Outerwear + Shoes (four cats)
        c4 = _pick_ids(reviewer_wardrobe, ["tops", "bottoms", "outerwear", "shoes"])
        if c4:
            combos.append(("tops+bottoms+outerwear+shoes", c4))
        # Combo 5: pick second items so we test different pieces
        alt = []
        for c in ["tops", "bottoms", "shoes"]:
            bucket = reviewer_wardrobe.get(c) or []
            if len(bucket) >= 2:
                alt.append(bucket[1])
        if len(alt) >= 2:
            combos.append(("alt_top_bottom_shoes", alt))
        if not combos:
            pytest.skip("Reviewer wardrobe has too few items for combos.")
        return combos

    def test_no_cross_category_swap_across_combos(self, reviewer_headers, outfit_combos):
        """Call /outfit/feedback for each combo, checking category invariants."""
        results_seen = 0
        cross_cat_swaps = []
        for label, items in outfit_combos:
            ids = [it["id"] for it in items]
            r = requests.post(
                f"{BASE_URL}/outfit/feedback",
                headers=reviewer_headers,
                json={"item_ids": ids, "occasion": f"casual test {label}"},
                timeout=120,
            )
            assert r.status_code == 200, f"[{label}] {r.status_code} {r.text[:400]}"
            data = r.json()
            # verdict + feedback always present
            assert isinstance(data.get("verdict", ""), str) and data["verdict"], (
                f"[{label}] missing verdict: {data}"
            )
            assert isinstance(data.get("feedback", ""), str) and data["feedback"], (
                f"[{label}] missing feedback: {data}"
            )
            swap = data.get("swap")
            if swap is not None:
                # swap must be a dict with same-slot categories and out_id in submitted ids
                assert isinstance(swap, dict), f"[{label}] swap not dict: {swap!r}"
                assert "out_item" in swap and "in_item" in swap, f"[{label}] swap missing items: {swap}"
                out_cat = _norm(swap["out_item"].get("category"))
                in_cat = _norm(swap["in_item"].get("category"))
                if out_cat != in_cat:
                    cross_cat_swaps.append((label, out_cat, in_cat, swap))
                assert swap["out_id"] in set(ids), (
                    f"[{label}] out_id {swap['out_id']} not in submitted ids {ids}"
                )
            # If addition is present, ensure it is a dict describing a piece and
            # that swap is null (never both).
            if data.get("addition") is not None:
                assert swap is None, f"[{label}] both swap and addition returned: {data}"
                add = data["addition"]
                assert isinstance(add, dict)
                assert "name" in add and "category" in add, f"addition shape: {add}"
            results_seen += 1
            # brief pacing between AI calls
            time.sleep(0.5)

        assert not cross_cat_swaps, (
            f"Cross-category swaps returned by API (should never happen): {cross_cat_swaps}"
        )
        assert results_seen >= 2, f"Only {results_seen} combos tested; need >=2 for confidence."


# ------------------------ free-account gating ----------------------- #

class TestOutfitFeedbackGating:
    def test_free_account_may_hit_402(self, free_headers):
        """Free accounts have a monthly stylist allowance; either 200 (still
        within limit) or 402 (out of allowance). Never 500."""
        # need >=2 items on the free account
        r = requests.get(f"{BASE_URL}/items", headers=free_headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        if len(items) < 2:
            pytest.skip("Free test wardrobe has <2 items.")
        ids = [items[0]["id"], items[1]["id"]]
        r = requests.post(
            f"{BASE_URL}/outfit/feedback",
            headers=free_headers,
            json={"item_ids": ids},
            timeout=120,
        )
        assert r.status_code in (200, 402), f"unexpected: {r.status_code} {r.text[:300]}"

    def test_unauthenticated_returns_401(self):
        r = requests.post(
            f"{BASE_URL}/outfit/feedback",
            json={"item_ids": ["a", "b"]},
            timeout=30,
        )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


# ----------- items endpoint sanity (Create Outfit picker) ---------- #

class TestItemsListForBuilder:
    """The Create Outfit picker relies on GET /api/items. Make sure it works
    on the reviewer account so the picker doesn't render an empty state."""
    def test_items_returned(self, reviewer_headers):
        r = requests.get(f"{BASE_URL}/items", headers=reviewer_headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 4, f"too few items: {len(items)}"
