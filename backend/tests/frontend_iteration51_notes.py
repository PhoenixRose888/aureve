"""
Iteration 51 — Frontend wardrobe-full UX + slot-aware bulk upload.

Uses pytest ONLY to prep accounts/items & verify counts via the API; the actual
UI driving happens with Playwright (sync api — we're outside pytest-asyncio).
This script is intentionally a plain pytest file so results land in JUnit XML.
"""
# This file is NOT run by pytest; it's a convenience Python runner for the
# iteration 51 frontend test. See the iteration_51.json report for the Playwright run.
