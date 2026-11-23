"""Iteration 47 — DEVICE-TEST FIX PASS backend verification.

Covers the ten focused fixes:
- Shop-check `already_covered` + `outfits_added==0` when duplicate/skip.
- Stylist chat thread persistence + `thread_id` continuity (needs_context short-circuit too).
- Stylist thread listing / detail / archive endpoints and 404s.
- Continuity: an archived thread's summary is passed as context.
- _UNRESTRICTED intent: no `needs_context:true`, not turned into an occasion question.
- /insights/health-report shape and /insights month block still driven by wear logs.
"""
from __future__ import annotations

import os
import re
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://wardrobe-ai-311.preview.emergentagent.com").rstrip("/")
TOKEN = os.environ.get("TEST_SESSION_TOKEN", "")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def wardrobe(api):
    r = api.get(f"{BASE_URL}/api/items", timeout=30)
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) >= 5, f"Seeded wardrobe too small: {len(items)}"
    return items


# ---------- helper: tiny 1x1 png base64 ----------
TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+P+/HgAFhAJ/wlseK"
    "gAAAABJRU5ErkJggg=="
)


# ---------- Shop-check ----------
class TestShopCheck:
    def test_shop_check_returns_shape(self, api):
        r = api.post(f"{BASE_URL}/api/shop-check", json={"image": TINY_PNG}, timeout=90)
        assert r.status_code in (200, 502), r.text
        if r.status_code == 502:
            pytest.skip("AI shop-check upstream unavailable; skipping.")
        data = r.json()
        for k in ("verdict", "reason", "outfits_added", "similar_items", "matches_with", "fills_gap"):
            assert k in data, f"missing key {k}: {data}"

    def test_duplicate_forces_outfits_added_zero_and_already_covered(self, api):
        r = api.post(f"{BASE_URL}/api/shop-check", json={"image": TINY_PNG}, timeout=90)
        if r.status_code == 502:
            pytest.skip("AI shop-check upstream unavailable; skipping.")
        assert r.status_code == 200
        data = r.json()
        duplicate = bool(data.get("similar_items")) and not data.get("fills_gap")
        is_skip = str(data.get("verdict") or "").lower() == "skip"
        if duplicate or is_skip:
            assert data.get("outfits_added") == 0, f"outfits_added should be forced 0, got {data.get('outfits_added')}"
        if duplicate:
            assert data.get("already_covered"), "already_covered should be present for duplicates"
            assert "already" in data["already_covered"].lower() or "similar" in data["already_covered"].lower()
        else:
            # Not a duplicate — the field is only added on duplicates.
            assert "already_covered" not in data or not data.get("already_covered")


# ---------- Stylist chat + threads ----------
class TestStylistThreads:
    def test_chat_creates_thread_and_returns_thread_id(self, api):
        r = api.post(
            f"{BASE_URL}/api/stylist/chat",
            json={"messages": [{"role": "user",
                                "content": "TEST_iter47 what would you pair with my navy blazer for a work dinner?"}]},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("thread_id"), f"thread_id missing: {data}"
        assert data.get("reply"), "reply missing"
        tid = data["thread_id"]

        # GET /threads/{id} returns full messages in order (user first, then assistant)
        d = api.get(f"{BASE_URL}/api/stylist/threads/{tid}", timeout=30)
        assert d.status_code == 200, d.text
        msgs = d.json().get("messages", [])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

        # Append: same thread_id back should keep the same thread and grow it
        r2 = api.post(
            f"{BASE_URL}/api/stylist/chat",
            json={"thread_id": tid,
                  "messages": [{"role": "user", "content": "TEST_iter47 nice — what shoes would you choose?"}]},
            timeout=120,
        )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("thread_id") == tid

        d2 = api.get(f"{BASE_URL}/api/stylist/threads/{tid}", timeout=30)
        assert d2.status_code == 200
        assert len(d2.json().get("messages", [])) == 4

        # Cleanup: archive so it doesn't pollute future runs
        api.post(f"{BASE_URL}/api/stylist/threads/{tid}/archive", timeout=90)

    def test_needs_context_short_circuit_persists_turn(self, api):
        r = api.post(
            f"{BASE_URL}/api/stylist/chat",
            json={"messages": [{"role": "user", "content": "what should i wear tonight?"}]},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("needs_context") is True, f"expected needs_context true: {data}"
        assert data.get("thread_id"), "needs_context short-circuit should still persist a thread"
        tid = data["thread_id"]
        d = api.get(f"{BASE_URL}/api/stylist/threads/{tid}", timeout=30)
        assert d.status_code == 200
        msgs = d.json().get("messages", [])
        assert len(msgs) == 2
        assert msgs[1]["role"] == "assistant"
        # The occasion question contains a question mark (may not be the final char)
        assert "?" in msgs[1]["content"]

    def test_list_threads_shape(self, api):
        r = api.get(f"{BASE_URL}/api/stylist/threads", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            row = rows[0]
            # message bodies should NOT be present in the list view
            assert "messages" not in row, f"messages leaked to list view: keys={list(row.keys())}"
            for k in ("id", "title", "summary", "recommendations", "archived", "updated_at"):
                assert k in row, f"missing key {k} in list row"
            # newest first
            ts = [r.get("updated_at", "") for r in rows]
            assert ts == sorted(ts, reverse=True), "threads should be newest first"

    def test_archive_flow(self, api):
        # Create a thread first
        r = api.post(
            f"{BASE_URL}/api/stylist/chat",
            json={"messages": [{"role": "user",
                                "content": "TEST_iter47_arc what colour skirt goes with my black silk blouse?"}]},
            timeout=120,
        )
        assert r.status_code == 200
        tid = r.json()["thread_id"]

        a = api.post(f"{BASE_URL}/api/stylist/threads/{tid}/archive", timeout=120)
        assert a.status_code == 200, a.text
        body = a.json()
        assert body.get("ok") is True
        assert body.get("id") == tid
        assert body.get("title"), "title should be filled after archive"
        # summary may be filled or fallback to first-user text
        assert isinstance(body.get("recommendations"), list)

        # verify persisted
        d = api.get(f"{BASE_URL}/api/stylist/threads/{tid}", timeout=30)
        assert d.status_code == 200
        j = d.json()
        assert j.get("archived") is True
        # Messages preserved
        assert len(j.get("messages", [])) >= 2

    def test_unknown_thread_404s(self, api):
        fake = f"sthread_{uuid.uuid4().hex[:12]}"
        g = api.get(f"{BASE_URL}/api/stylist/threads/{fake}", timeout=30)
        assert g.status_code == 404
        a = api.post(f"{BASE_URL}/api/stylist/threads/{fake}/archive", timeout=30)
        assert a.status_code == 404


# ---------- Stylist continuity + unrestricted intent ----------
class TestStylistIntents:
    def test_unrestricted_intent_not_needs_context(self, api):
        r = api.post(
            f"{BASE_URL}/api/stylist/chat",
            json={"messages": [{"role": "user",
                                "content": "Give me a completely different look — it doesn't have to use anything I own."}]},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("needs_context") is not True, f"unrestricted request should NOT ask for occasion: {data}"
        reply = data.get("reply") or ""
        # Lenient: reply should describe a look, not merely ask "what's the occasion?"
        stripped = reply.strip()
        assert stripped, "empty reply for unrestricted intent"
        looks_like_only_a_question = stripped.endswith("?") and len(stripped) < 160 and "occasion" in stripped.lower()
        assert not looks_like_only_a_question, f"reply looks like an occasion question, not a look: {reply}"

    def test_earlier_thread_summary_available_after_archive(self, api):
        # 1. Have a first conversation about a specific colour recommendation.
        r1 = api.post(
            f"{BASE_URL}/api/stylist/chat",
            json={"messages": [{"role": "user",
                                "content": "What skirt colour would you recommend to pair with my Black Silk Blouse for dinner?"}]},
            timeout=120,
        )
        assert r1.status_code == 200
        tid1 = r1.json()["thread_id"]
        # 2. Archive → summarises + generates recommendations, becomes context.
        a = api.post(f"{BASE_URL}/api/stylist/threads/{tid1}/archive", timeout=120)
        assert a.status_code == 200
        # 3. Start a new thread that references "before". We check the model at
        # least attempts a substantive reply and doesn't flatly deny history.
        r2 = api.post(
            f"{BASE_URL}/api/stylist/chat",
            json={"messages": [{"role": "user",
                                "content": "What skirt colour did you recommend before?"}]},
            timeout=120,
        )
        assert r2.status_code == 200
        reply = (r2.json().get("reply") or "").lower()
        # Lenient: just make sure the model did not send a flat "no history" refusal.
        assert reply, "empty reply"
        flat_denials = ["i have no history", "i do not have access to any previous", "i can't remember our"]
        assert not any(f in reply for f in flat_denials), f"model claimed no history: {reply}"


# ---------- Insights ----------
class TestInsights:
    def test_health_report_shape(self, api):
        r = api.post(f"{BASE_URL}/api/insights/health-report", json={}, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("headline", "lesson", "nudges", "wins", "missing_piece"):
            assert k in data, f"missing key {k}: keys={list(data.keys())}"
        assert isinstance(data["nudges"], list)
        assert isinstance(data["wins"], list)
        assert isinstance(data["missing_piece"], dict)

    def test_insights_month_block_from_wear_logs_only(self, api):
        # Snapshot month block
        r1 = api.get(f"{BASE_URL}/api/insights", timeout=30)
        assert r1.status_code == 200
        m1 = r1.json().get("month") or {}
        assert "wears_logged" in m1 and "pieces_worn" in m1
        w1 = int(m1.get("wears_logged") or 0)

        # Fire a POST /api/dressme (suggestion) — MUST NOT alter wear counters
        # We deliberately do NOT actually create wear logs here.
        api.post(f"{BASE_URL}/api/dressme",
                 json={"occasion": "TEST_iter47_no_wear casual"},
                 timeout=90)
        r2 = api.get(f"{BASE_URL}/api/insights", timeout=30)
        assert r2.status_code == 200
        m2 = r2.json().get("month") or {}
        w2 = int(m2.get("wears_logged") or 0)
        assert w2 == w1, f"Dress Me suggestion changed wears_logged from {w1} to {w2}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
