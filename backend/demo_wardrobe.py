"""Demo wardrobe seed — 16 Nano Banana garment flatlays (JPEG base64).
Data lives in demo_wardrobe.json; regenerate with scripts/gen_demo_wardrobe.py.
"""
import json
from pathlib import Path

DEMO_ITEMS = json.loads((Path(__file__).parent / "demo_wardrobe.json").read_text())
