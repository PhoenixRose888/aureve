"""Iteration 5 — verify two NEW backend features:

1. GET /api/items now returns integer pairs_count on every item.
   - laundry items are excluded from pairing math
   - same-category items don't pair; Dresses don't pair with Tops/Bottoms
   - main-garment formality within one step; accessories/shoes/jewellery ignore formality
   - pairs_count is scoped per profile

2. POST /api/beauty/suggest — Hair & Makeup endpoint.
   - 400 when active profile lacks skin_tone & undertone
   - 200 when set, correct JSON shape (summary/palette/makeup/hair/avoid/occasion_note)
   - works with and without optional occasion
   - scoped per profile (skin tone on A must not leak to B)
"""
import requests
import pytest


AURA = "prof_365ddfe52deb"   # has ready items, skin_tone=medium undertone=warm
DAVID = "prof_a82ae0522746"  # empty wardrobe, no skin tone/undertone


def _h(auth_headers, profile_id=None):
    h = dict(auth_headers)
    if profile_id:
        h["X-Profile-Id"] = profile_id
    return h


# ==========================================================================
# 1. pairs_count on GET /api/items
# ==========================================================================
class TestPairsCount:
    def test_every_item_has_integer_pairs_count(self, base_url, auth_headers):
        r = requests.get(f"{base_url}/items", headers=_h(auth_headers, AURA), timeout=30)
        assert r.status_code == 200, r.text
        items = r.json()
        assert len(items) >= 2, "Aura needs >=2 seed items for pairing tests"
        for it in items:
            assert "pairs_count" in it, f"missing pairs_count on {it.get('id')}"
            assert isinstance(it["pairs_count"], int), (
                f"pairs_count not int on {it.get('id')}: {type(it['pairs_count'])}"
            )
            assert it["pairs_count"] >= 0

    def test_pairs_count_scoped_per_profile(self, base_url, auth_headers):
        """David has 0 items -> pairs_count list should be empty."""
        r = requests.get(f"{base_url}/items", headers=_h(auth_headers, DAVID), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json() == []

    def test_laundry_excluded_reduces_others_count_and_zero_for_washing(
        self, base_url, auth_headers
    ):
        """Mark Aura's Tops item Washing; verify (a) its own pairs_count==0
        while it's out of rotation, and (b) other items' pairs_count drops by 1."""
        H = _h(auth_headers, AURA)

        # Baseline
        base = requests.get(f"{base_url}/items", headers=H, timeout=30).json()
        assert base, "seed missing"
        counts_before = {i["id"]: i["pairs_count"] for i in base}
        tops = next((i for i in base if i.get("category") == "Tops"), None)
        assert tops is not None, "Aura seed lacks a Tops item"
        pc_top_before = counts_before[tops["id"]]
        assert pc_top_before >= 1, "Tops item should baseline-pair with something"

        try:
            # Flip to Washing
            put = requests.put(
                f"{base_url}/items/{tops['id']}",
                headers=H,
                json={"availability": "Washing"},
                timeout=30,
            )
            assert put.status_code == 200, put.text

            after = requests.get(f"{base_url}/items", headers=H, timeout=30).json()
            counts_after = {i["id"]: i["pairs_count"] for i in after}

            # (a) washing item's own pairs_count == 0
            assert counts_after[tops["id"]] == 0, (
                f"washing item should have pairs_count=0, got {counts_after[tops['id']]}"
            )

            # (b) every OTHER item that previously paired with the Tops loses exactly 1
            # (i.e. after == before - (1 if it was pairing with the washed Tops else 0))
            # We can prove <= before-1 for at least the items that had non-zero baseline
            # and >= 0 always. Simpler and stronger: sum(counts) drops by 2*pc_top_before.
            total_before = sum(counts_before.values())
            total_after = sum(counts_after.values())
            assert total_before - total_after == 2 * pc_top_before, (
                f"expected total to drop by {2 * pc_top_before}, "
                f"went {total_before} -> {total_after}"
            )
        finally:
            # (c) reset to Ready -> counts restored
            requests.put(
                f"{base_url}/items/{tops['id']}",
                headers=H,
                json={"availability": "Ready"},
                timeout=30,
            )

        restored = requests.get(f"{base_url}/items", headers=H, timeout=30).json()
        counts_restored = {i["id"]: i["pairs_count"] for i in restored}
        assert counts_restored == counts_before, (
            f"restored counts != baseline\nbefore={counts_before}\nafter ={counts_restored}"
        )

    def test_pair_rules_same_category_and_dresses(self, base_url, auth_headers):
        """Create a small owned-scope on a fresh temp profile to prove:
        - same-category items DO NOT pair
        - Dresses DO NOT pair with Tops or Bottoms
        - accessories pair across formalities
        - main-garment formality must be within one step
        """
        H_base = dict(auth_headers)
        # Create a temp profile so tests are isolated
        prof = requests.post(
            f"{base_url}/profiles",
            headers=H_base,
            json={"name": "TEST_PAIR_RULES", "emoji": "🧪"},
            timeout=30,
        )
        assert prof.status_code == 200, prof.text
        pid = prof.json()["id"]
        H = _h(auth_headers, pid)

        created_ids = []
        try:
            def mk(name, category, formality=None):
                body = {"name": name, "category": category, "availability": "Ready"}
                if formality:
                    body["formality"] = formality
                res = requests.post(f"{base_url}/items", headers=H, json=body, timeout=30)
                assert res.status_code == 200, res.text
                created_ids.append(res.json()["id"])
                return res.json()

            top_a = mk("TEST_PR_top_casual", "Tops", "Casual")
            top_b = mk("TEST_PR_top_smart", "Tops", "Smart Casual")     # same cat as top_a
            bottom_c = mk("TEST_PR_pants_business", "Bottoms", "Business")
            bottom_far = mk("TEST_PR_pants_formal", "Bottoms", "Formal")  # 3 from Casual -> shouldn't pair with top_a
            dress = mk("TEST_PR_dress_casual", "Dresses", "Casual")
            outer = mk("TEST_PR_outer_casual", "Outerwear", "Casual")
            shoes = mk("TEST_PR_shoes", "Shoes", "Formal")   # formality ignored for shoes
            bag = mk("TEST_PR_bag", "Bags")                  # no formality

            listing = requests.get(f"{base_url}/items", headers=H, timeout=30).json()
            by_id = {i["id"]: i["pairs_count"] for i in listing}

            # We'll rebuild expected via the same rules for cross-check.
            FORMALITY = {"Casual": 0, "Smart Casual": 1, "Business": 2, "Formal": 3}
            MAIN = {"Tops", "Bottoms", "Dresses", "Outerwear"}
            EXCL = {("Dresses", "Tops"), ("Dresses", "Bottoms")}
            all_items = [top_a, top_b, bottom_c, bottom_far, dress, outer, shoes, bag]

            def pair(a, b):
                ca, cb = a["category"], b["category"]
                if ca == cb:
                    return False
                if (ca, cb) in EXCL or (cb, ca) in EXCL:
                    return False
                if ca in MAIN and cb in MAIN:
                    fa = FORMALITY.get(a.get("formality") or "")
                    fb = FORMALITY.get(b.get("formality") or "")
                    if fa is not None and fb is not None and abs(fa - fb) > 1:
                        return False
                return True

            expected = {i["id"]: 0 for i in all_items}
            for x in range(len(all_items)):
                for y in range(x + 1, len(all_items)):
                    if pair(all_items[x], all_items[y]):
                        expected[all_items[x]["id"]] += 1
                        expected[all_items[y]["id"]] += 1

            assert by_id == expected, f"pair rule mismatch\nAPI:{by_id}\nExp:{expected}"

            # Explicit spot checks
            # top_a & top_b are same category -> must NOT pair; ensure top_a has no
            # +1 from top_b (implicit in equality above)
            # Dresses & Tops must NOT pair
            # Dress paired with Bottoms? no -> excluded
            # top_a(Casual) vs bottom_far(Formal): |0-3|=3 -> no pair
            # top_a(Casual) vs bottom_c(Business): |0-2|=2 -> no pair
            # top_a(Casual) vs outer(Casual): |0-0|=0 -> pair
            # shoes (Formal) vs top_a (Casual): NOT main -> ignores formality -> pair
            # bag (no formality) vs everything main -> pair (both have formality? bag None -> skipped constraint)
            assert expected[shoes["id"]] > 0, "shoes should pair with several items"
            assert expected[bag["id"]] > 0, "bag should pair with several items"

        finally:
            for iid in created_ids:
                requests.delete(f"{base_url}/items/{iid}", headers=H, timeout=15)
            requests.delete(f"{base_url}/profiles/{pid}", headers=H_base, timeout=15)


# ==========================================================================
# 2. POST /api/beauty/suggest
# ==========================================================================
class TestBeautySuggest:
    def test_beauty_unauth(self, base_url):
        r = requests.post(f"{base_url}/beauty/suggest", json={})
        assert r.status_code == 401

    def test_beauty_400_when_profile_missing_colouring(self, base_url, auth_headers):
        """David profile has NO skin_tone and NO undertone -> 400."""
        r = requests.post(
            f"{base_url}/beauty/suggest",
            headers=_h(auth_headers, DAVID),
            json={},
            timeout=30,
        )
        assert r.status_code == 400, r.text
        body = r.json()
        assert "detail" in body
        msg = body["detail"].lower()
        assert "skin tone" in msg or "undertone" in msg, f"unhelpful message: {body}"

    def test_beauty_200_with_valid_profile_no_occasion(self, base_url, auth_headers):
        """Aura has skin_tone=medium, undertone=warm -> should return full JSON."""
        r = requests.post(
            f"{base_url}/beauty/suggest",
            headers=_h(auth_headers, AURA),
            json={},
            timeout=180,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("summary", "palette", "makeup", "hair", "avoid", "occasion_note"):
            assert k in j, f"missing key {k} in beauty response: {list(j.keys())}"

        assert isinstance(j["summary"], str) and len(j["summary"]) > 1
        assert isinstance(j["palette"], list) and len(j["palette"]) >= 1
        assert all(isinstance(x, str) for x in j["palette"])
        assert isinstance(j["avoid"], list)
        assert isinstance(j["occasion_note"], str)

        mk = j["makeup"]
        assert isinstance(mk, dict)
        for sk in ("foundation", "blush", "lip", "eye", "tip"):
            assert sk in mk, f"makeup missing sub-key {sk}: {list(mk.keys())}"
            assert isinstance(mk[sk], str)

        hair = j["hair"]
        assert isinstance(hair, dict)
        for sk in ("colour", "style", "tip"):
            assert sk in hair, f"hair missing sub-key {sk}: {list(hair.keys())}"
            assert isinstance(hair[sk], str)

    def test_beauty_200_with_occasion(self, base_url, auth_headers):
        r = requests.post(
            f"{base_url}/beauty/suggest",
            headers=_h(auth_headers, AURA),
            json={"occasion": "wedding guest evening"},
            timeout=180,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        # Shape sanity
        assert "occasion_note" in j
        assert isinstance(j.get("palette"), list) and len(j["palette"]) >= 1
        assert isinstance(j.get("makeup"), dict)
        assert isinstance(j.get("hair"), dict)

    def test_beauty_scoped_per_profile_no_leak(self, base_url, auth_headers):
        """Setting skin tone on a temp profile A must NOT enable David (still 400)
        and David's later PUT must not enable a *third* profile."""
        H_base = dict(auth_headers)

        # First re-check: David still lacks colouring -> 400 (post-run cleanup guarantee)
        r0 = requests.post(
            f"{base_url}/beauty/suggest",
            headers=_h(auth_headers, DAVID),
            json={},
            timeout=30,
        )
        assert r0.status_code == 400, f"David colour leaked? {r0.status_code} {r0.text}"

        # Create a fresh third profile 'C' with no colouring
        prof = requests.post(
            f"{base_url}/profiles",
            headers=H_base,
            json={"name": "TEST_BEAUTY_C", "emoji": "🧪"},
            timeout=30,
        )
        assert prof.status_code == 200, prof.text
        pid = prof.json()["id"]

        try:
            # C has no colouring -> 400
            r1 = requests.post(
                f"{base_url}/beauty/suggest",
                headers=_h(auth_headers, pid),
                json={},
                timeout=30,
            )
            assert r1.status_code == 400, f"expected 400 for fresh C, got {r1.status_code} {r1.text}"

            # Set colouring on C
            up = requests.put(
                f"{base_url}/profile",
                headers=_h(auth_headers, pid),
                json={"skin_tone": "deep", "undertone": "cool"},
                timeout=30,
            )
            assert up.status_code == 200, up.text

            # Now C should 200 …
            r2 = requests.post(
                f"{base_url}/beauty/suggest",
                headers=_h(auth_headers, pid),
                json={},
                timeout=180,
            )
            assert r2.status_code == 200, r2.text

            # … but David MUST STILL 400 (no leak)
            r3 = requests.post(
                f"{base_url}/beauty/suggest",
                headers=_h(auth_headers, DAVID),
                json={},
                timeout=30,
            )
            assert r3.status_code == 400, (
                f"colouring leaked from C -> David: {r3.status_code} {r3.text}"
            )
        finally:
            requests.delete(f"{base_url}/profiles/{pid}", headers=H_base, timeout=15)
