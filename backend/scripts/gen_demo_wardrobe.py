"""One-time generator: creates ~16 catalogue-style garment flatlays with Nano
Banana and writes them (as compressed JPEG base64) into demo_wardrobe.py.

Run:  python scripts/gen_demo_wardrobe.py
"""
import asyncio
import os
import io
import base64
import json
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
API_KEY = os.getenv("EMERGENT_LLM_KEY")
MODEL = "gemini-3.1-flash-image-preview"
OUT = ROOT / "demo_wardrobe.py"
PROGRESS = ROOT / "scripts" / "_gen_progress.txt"

# name, category, colour, fabric, season, formality, tone, style, description-for-prompt
GARMENTS = [
    ("White Crew T-Shirt", "Tops", "White", "Cotton", "All", "Casual", "Neutral", "Minimal", "plain white cotton crew-neck t-shirt"),
    ("Light Blue Oxford Shirt", "Tops", "Light Blue", "Cotton", "All", "Smart Casual", "Cool", "Classic", "light blue oxford button-down shirt"),
    ("Cream Ribbed Sweater", "Tops", "Cream", "Wool", "Autumn", "Smart Casual", "Warm", "Cosy", "cream ribbed knit crew-neck sweater"),
    ("Black Silk Blouse", "Tops", "Black", "Silk", "All", "Formal", "Neutral", "Elegant", "black silk long-sleeve blouse"),
    ("Indigo Slim Jeans", "Bottoms", "Indigo", "Denim", "All", "Casual", "Cool", "Classic", "indigo blue slim-fit jeans"),
    ("Beige Chino Trousers", "Bottoms", "Beige", "Cotton", "All", "Smart Casual", "Warm", "Classic", "beige chino trousers"),
    ("Black Tailored Trousers", "Bottoms", "Black", "Wool", "All", "Formal", "Neutral", "Tailored", "black tailored dress trousers"),
    ("Olive Pleated Midi Skirt", "Bottoms", "Olive", "Polyester", "Autumn", "Smart Casual", "Warm", "Feminine", "olive green pleated midi skirt"),
    ("Little Black Dress", "Dresses", "Black", "Crepe", "All", "Formal", "Neutral", "Elegant", "elegant little black sheath dress"),
    ("Floral Wrap Dress", "Dresses", "Multicolour", "Viscose", "Summer", "Smart Casual", "Warm", "Feminine", "floral print wrap summer dress"),
    ("Camel Wool Overcoat", "Outerwear", "Camel", "Wool", "Winter", "Formal", "Warm", "Classic", "camel wool tailored overcoat"),
    ("Blue Denim Jacket", "Outerwear", "Blue", "Denim", "Spring", "Casual", "Cool", "Classic", "classic blue denim trucker jacket"),
    ("White Leather Sneakers", "Shoes", "White", "Leather", "All", "Casual", "Neutral", "Minimal", "pair of white leather low-top sneakers"),
    ("Tan Ankle Boots", "Shoes", "Tan", "Leather", "Autumn", "Smart Casual", "Warm", "Classic", "pair of tan leather ankle boots"),
    ("Black Leather Tote", "Bags", "Black", "Leather", "All", "Smart Casual", "Neutral", "Minimal", "black leather structured tote bag"),
    ("Brown Leather Belt", "Accessories", "Brown", "Leather", "All", "Smart Casual", "Warm", "Classic", "brown leather belt with a simple buckle"),
]


def compress(png_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(png_bytes))
    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((640, 640))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)
    return base64.b64encode(out.getvalue()).decode()


async def gen_one(desc: str) -> str | None:
    chat = LlmChat(api_key=API_KEY, session_id=f"demo-{desc[:8]}", system_message="You generate clean product images.")
    chat.with_model("gemini", MODEL).with_params(modalities=["image", "text"])
    prompt = (
        f"Professional e-commerce product flat-lay photograph of a single {desc}. "
        "Centered, laid flat, on a pure solid white background (#FFFFFF). "
        "Soft even studio lighting, no harsh shadows, no props, no mannequin, no people, "
        "no text or logos. Crisp, high detail, catalogue style, square framing."
    )
    for attempt in range(2):
        try:
            _text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
            if images:
                raw = base64.b64decode(images[0]["data"])
                return compress(raw)
        except Exception as e:
            print(f"  attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2)
    return None


async def main():
    results = []
    for i, g in enumerate(GARMENTS):
        name, cat, colour, fabric, season, formality, tone, style, desc = g
        print(f"[{i+1}/{len(GARMENTS)}] {name} ...")
        PROGRESS.write_text(f"{i+1}/{len(GARMENTS)} {name}")
        photo = await gen_one(desc)
        if not photo:
            print(f"  SKIPPED {name}")
            continue
        results.append({
            "name": name, "category": cat, "colour": colour, "fabric": fabric,
            "season": season, "formality": formality, "tone": tone, "style": style,
            "flatters": True, "photo": photo,
        })
        print(f"  ok ({len(photo)//1024} KB b64)")

    header = (
        "# Auto-generated demo wardrobe (Nano Banana flatlays, JPEG base64).\n"
        "# Regenerate with: python scripts/gen_demo_wardrobe.py\n"
        f"# {len(results)} items\n\n"
    )
    OUT.write_text(header + "DEMO_ITEMS = " + json.dumps(results, indent=1) + "\n")
    PROGRESS.write_text(f"DONE {len(results)}/{len(GARMENTS)}")
    print(f"WROTE {OUT} with {len(results)} items")


if __name__ == "__main__":
    asyncio.run(main())
