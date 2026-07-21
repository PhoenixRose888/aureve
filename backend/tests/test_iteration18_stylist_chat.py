"""Iteration 18 — POST /api/stylist/chat backend regression.

Verifies:
  (a) General question → reply with outfit:null
  (b) Outfit request → reply + non-null outfit with real wardrobe items resolved
  (c) reply text contains no raw JSON / no raw item ids
  (d) response schema: {reply: str, outfit: null | {name, item_ids, items}}
"""
import os
import re
import time

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
TOKEN = "test-session-token-aura-123"
HDR = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def wardrobe_ids():
    r = requests.get(f"{BASE_URL}/api/items", headers=HDR, timeout=30)
    assert r.status_code == 200, f"items list failed: {r.status_code} {r.text[:200]}"
    items = r.json()
    ids = [it["id"] for it in items]
    assert len(ids) >= 2, f"Need at least 2 wardrobe items; got {len(ids)}"
    return set(ids)


def _post_chat(messages, **extra):
    body = {"messages": messages}
    body.update(extra)
    return requests.post(f"{BASE_URL}/api/stylist/chat", headers=HDR, json=body, timeout=90)


def _assert_reply_clean(reply: str):
    # No fenced JSON block leaked
    assert "```" not in reply, f"reply leaked code fence: {reply!r}"
    # No obvious raw JSON braces content
    assert not re.search(r'\{\s*"outfit"', reply), f"reply leaked raw outfit JSON: {reply!r}"
    assert not re.search(r'"item_ids"', reply), f"reply leaked raw item_ids: {reply!r}"


# ---------- (a) general question → outfit null ----------
class TestGeneralQuestion:
    def test_general_question_returns_null_outfit(self, wardrobe_ids):
        r = _post_chat([
            {"role": "user", "content": "Any tips for styling my gold earrings?"}
        ])
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert set(data.keys()) >= {"reply", "outfit"}
        assert isinstance(data["reply"], str) and data["reply"].strip(), "empty reply"
        assert data["outfit"] is None, f"expected null outfit for general question; got {data['outfit']}"
        _assert_reply_clean(data["reply"])
        # reply should not leak wardrobe ids
        for wid in wardrobe_ids:
            assert wid not in data["reply"], f"raw wardrobe id leaked in reply: {wid}"


# ---------- (b) outfit request → non-null outfit with real items ----------
class TestOutfitRequest:
    def test_outfit_request_returns_resolved_outfit(self, wardrobe_ids):
        # Retry once for flaky LLM
        last = None
        for attempt in range(2):
            r = _post_chat(
                [{"role": "user", "content": "What should I wear for a casual dinner tonight? Please put together a specific outfit from my wardrobe."}],
                temperature=18.0, weather="clear evening",
            )
            assert r.status_code == 200, r.text[:400]
            data = r.json()
            last = data
            if data.get("outfit") is not None:
                break
            time.sleep(2)
        assert last["outfit"] is not None, f"stylist should propose outfit; got reply={last['reply'][:200]!r}"
        outfit = last["outfit"]
        assert "name" in outfit and isinstance(outfit["name"], str) and outfit["name"].strip()
        assert "item_ids" in outfit and isinstance(outfit["item_ids"], list) and len(outfit["item_ids"]) >= 1
        assert "items" in outfit and isinstance(outfit["items"], list) and len(outfit["items"]) == len(outfit["item_ids"])
        # every item_id must exist in the user's wardrobe
        for iid in outfit["item_ids"]:
            assert iid in wardrobe_ids, f"outfit references non-wardrobe id {iid}"
        # resolved items must carry photo + category keys the frontend needs
        for it in outfit["items"]:
            assert "id" in it and it["id"] in wardrobe_ids
            assert "category" in it, f"resolved item missing category: {it}"
            assert "photo" in it, f"resolved item missing photo key: {it}"
        _assert_reply_clean(last["reply"])
        # reply should not spam raw ids
        for iid in outfit["item_ids"]:
            assert iid not in last["reply"], f"raw item id leaked in reply text: {iid}"


# ---------- (c) schema stability with multi-turn ----------
class TestSchemaAndHistory:
    def test_multi_turn_history_accepted(self):
        r = _post_chat([
            {"role": "user", "content": "Hi Aureve, what colours suit warm-toned skin?"},
            {"role": "assistant", "content": "Warm tones love earthy sages, camels and rust."},
            {"role": "user", "content": "Thanks!"},
        ])
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert isinstance(data.get("reply"), str) and data["reply"].strip()
        assert "outfit" in data  # may be null


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
