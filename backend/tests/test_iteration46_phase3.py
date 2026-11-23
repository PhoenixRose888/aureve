"""Phase 3 backend tests — AI Stylist attach-a-piece + Monthly Wardrobe Health.

Covers:
- POST /api/stylist/chat with `item_ids` (attached wardrobe pieces)
- Vague request → {needs_context: true} (no AI spend)
- Outfit block parsing after context enrichment
- GET /api/insights new `month` block + slim thumbnails (no orig_photo)
- Wear-log driven month counts (POST /api/wear changes counts, POST /api/dressme does NOT)
- POST /api/insights/health-report returns report fields for premium
"""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
TOKEN = os.environ.get("TEST_SESSION_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def s():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


@pytest.fixture(scope="module")
def items(s):
    r = s.get(f"{BASE_URL}/api/items", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and len(data) >= 3, "Need at least 3 seeded wardrobe items"
    return data


# -------------------- stylist/chat --------------------
class TestStylistChat:
    def test_vague_request_returns_needs_context_no_ai_spend(self, s):
        r = s.post(f"{BASE_URL}/api/stylist/chat",
                   json={"messages": [{"role": "user", "content": "what should I wear tonight?"}]},
                   timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("needs_context") is True
        assert body.get("outfit") is None
        assert isinstance(body.get("reply"), str) and len(body["reply"]) > 0
        # single question — short-ish, contains '?'
        assert "?" in body["reply"]

    def test_chat_with_attached_item_ids_references_piece(self, s, items):
        # pick a garment with an interesting name to look for in reply
        target = next((it for it in items if it.get("name") and it.get("category") in ("Tops", "Outerwear", "Dresses", "Bottoms")), items[0])
        name = target["name"]
        r = s.post(
            f"{BASE_URL}/api/stylist/chat",
            json={
                "messages": [
                    {"role": "user", "content": f"What would you change about my {name}? Talk about the piece I attached."}
                ],
                "item_ids": [target["id"]],
            },
            timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("needs_context") is not True, f"attached piece should not trigger needs_context: {body}"
        reply = (body.get("reply") or "").lower()
        assert len(reply) > 20, f"reply too short: {reply}"
        # The reply should reference the attached piece by name OR by explicit category —
        # attach line in server.py includes name+category+colour, prompting model to
        # talk about it. Accept either a token from the name or the category token.
        tokens = [t for t in re.split(r"\W+", name.lower()) if len(t) > 3]
        cat = str(target.get("category") or "").lower()
        colour = str(target.get("colour") or "").lower()
        found = any(t in reply for t in tokens) or (cat and cat[:-1] in reply) or (colour and colour in reply)
        assert found, f"reply doesn't reference attached piece '{name}' ({cat}/{colour}): {reply}"

    def test_chat_ignores_unknown_item_ids_safely(self, s):
        r = s.post(
            f"{BASE_URL}/api/stylist/chat",
            json={
                "messages": [{"role": "user", "content": "I'm going to a smart dinner tonight — pick me something."}],
                "item_ids": ["not-a-real-id-xyz", "also-fake-abc"],
            },
            timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body.get("reply"), str) and len(body["reply"]) > 0

    def test_chat_full_outfit_request_resolves_real_items(self, s, items):
        # Explicit occasion → should NOT return needs_context; may include an outfit block.
        r = s.post(
            f"{BASE_URL}/api/stylist/chat",
            json={
                "messages": [
                    {"role": "user", "content": "Build me a complete outfit for a smart dinner in the city tonight, 18°C."}
                ]
            },
            timeout=120,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("needs_context") is not True
        outfit = body.get("outfit")
        # Outfit block is model-dependent — if provided, verify structure resolves to real items
        if outfit is not None:
            assert "name" in outfit and "item_ids" in outfit and "items" in outfit
            assert isinstance(outfit["item_ids"], list) and len(outfit["item_ids"]) >= 1
            wardrobe_ids = {it["id"] for it in items}
            for iid in outfit["item_ids"]:
                assert iid in wardrobe_ids, f"outfit item {iid} not in wardrobe"
            assert len(outfit["items"]) == len(outfit["item_ids"])


# -------------------- insights --------------------
class TestInsightsMonth:
    def test_insights_returns_month_block_and_slim_thumbs(self, s):
        r = s.get(f"{BASE_URL}/api/insights", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("total_items", "most_worn", "least_worn", "month"):
            assert key in data, f"missing key {key}"
        # slim thumbs — no orig_photo present on most_worn/least_worn
        for arr_key in ("most_worn", "least_worn"):
            for it in data[arr_key]:
                assert "orig_photo" not in it, f"orig_photo leaked into {arr_key}"
                # photo should be the thumb (a string), not absent
        month = data["month"]
        assert isinstance(month, dict)
        for key in ("label", "wears_logged", "pieces_worn", "top_worn", "unworn"):
            assert key in month, f"missing month.{key}"
        assert isinstance(month["wears_logged"], int)
        assert isinstance(month["pieces_worn"], int)
        assert isinstance(month["top_worn"], list)
        assert isinstance(month["unworn"], list)
        # top_worn entries must be {item, wears}
        for row in month["top_worn"]:
            assert "item" in row and "wears" in row
            assert "orig_photo" not in row["item"]
        # unworn entries must be slim item dicts
        for it in month["unworn"]:
            assert "orig_photo" not in it
            assert "id" in it

    def test_wear_updates_month_counts_dressme_does_not(self, s, items):
        # Snapshot BEFORE
        before = s.get(f"{BASE_URL}/api/insights", timeout=30).json()["month"]

        # 1) POST /api/dressme (a SUGGESTION) — must NOT change month counts
        dm = s.post(f"{BASE_URL}/api/dressme",
                    json={"occasion": "TEST_phase3_suggestion", "temperature": 18, "weather": "clear"},
                    timeout=120)
        # Note: even if dressme returns an error, month counts should still be unchanged
        after_dm = s.get(f"{BASE_URL}/api/insights", timeout=30).json()["month"]
        assert after_dm["wears_logged"] == before["wears_logged"], "dressme changed wears_logged"
        assert after_dm["pieces_worn"] == before["pieces_worn"], "dressme changed pieces_worn"
        if dm.status_code == 200:
            assert isinstance(dm.json().get("items", []), list)

        # 2) POST /api/wear — SHOULD change month counts
        picked = [items[0]["id"]]
        # try to pick 2 distinct items for a clearer pieces_worn delta
        if len(items) > 1:
            picked.append(items[1]["id"])
        w = s.post(f"{BASE_URL}/api/wear",
                   json={"item_ids": picked, "name": "TEST_phase3_wear", "occasion": "TEST_phase3"},
                   timeout=30)
        assert w.status_code == 200, w.text
        wear_body = w.json()
        assert wear_body.get("id"), wear_body

        after_wear = s.get(f"{BASE_URL}/api/insights", timeout=30).json()["month"]
        assert after_wear["wears_logged"] == before["wears_logged"] + 1, \
            f"wears_logged did not increment: before={before['wears_logged']} after={after_wear['wears_logged']}"
        # pieces_worn is unique items worn this month — must be >= before
        assert after_wear["pieces_worn"] >= before["pieces_worn"], "pieces_worn should not decrease"

        # top_worn should include at least one of the just-worn ids
        top_ids = {row["item"]["id"] for row in after_wear["top_worn"]}
        assert any(pid in top_ids for pid in picked), \
            f"top_worn missing just-worn ids. picked={picked} top_ids={top_ids}"


# -------------------- health-report (premium) --------------------
class TestHealthReport:
    def test_health_report_returns_report_fields(self, s):
        r = s.post(f"{BASE_URL}/api/insights/health-report", json={}, timeout=180)
        # test_credentials.md: user_testaura01 is granted premium_until=2099
        assert r.status_code == 200, f"health-report failed for premium account: {r.status_code} {r.text[:400]}"
        body = r.json()
        for key in ("headline", "lesson", "nudges", "wins", "missing_piece"):
            assert key in body, f"missing report field {key}"
        assert isinstance(body["nudges"], list)
        assert isinstance(body["wins"], list)
