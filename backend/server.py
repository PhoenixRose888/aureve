from fastapi import FastAPI, APIRouter, Depends, HTTPException, Header, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import json
import logging
import uuid
import httpx
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
AI_MODEL = ("openai", "gpt-5.4")

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ----------------------------- Helpers -----------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def parse_json_block(text: str) -> dict:
    """Extract a JSON object from an LLM response that may contain code fences."""
    if not text:
        return {}
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else None
    if raw is None:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        raw = brace.group(0) if brace else text
    try:
        return json.loads(raw)
    except Exception:
        logger.warning("Failed to parse JSON from LLM: %s", text[:300])
        return {}


async def ai_chat(session_id: str, system_message: str) -> LlmChat:
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_message,
    ).with_model(*AI_MODEL)
    return chat


# ----------------------------- Auth -----------------------------
async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    expires_at = session.get("expires_at")
    if isinstance(expires_at, datetime):
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now_utc():
            raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


class SessionRequest(BaseModel):
    session_token: str


@api_router.post("/auth/session")
async def create_session(payload: SessionRequest):
    """Verify a session_token with Emergent, upsert the user, store a session."""
    async with httpx.AsyncClient(timeout=20) as hc:
        resp = await hc.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": payload.session_token},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session token")
    data = resp.json()
    email = data.get("email")
    name = data.get("name")
    picture = data.get("picture")
    session_token = data.get("session_token") or payload.session_token

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture}},
        )
    else:
        user_id = new_id("user")
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "created_at": now_utc().isoformat(),
        })

    await db.user_sessions.update_one(
        {"session_token": session_token},
        {"$set": {
            "session_token": session_token,
            "user_id": user_id,
            "expires_at": now_utc() + timedelta(days=7),
            "created_at": now_utc(),
        }},
        upsert=True,
    )
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"session_token": session_token, "user": user}


@api_router.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return user


@api_router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}


# ----------------------------- Models -----------------------------
class ItemCreate(BaseModel):
    name: str
    category: str
    colour: Optional[str] = ""
    fabric: Optional[str] = ""
    season: Optional[str] = "All"
    pattern: Optional[str] = ""
    fit_notes: Optional[str] = ""
    brand: Optional[str] = ""
    size: Optional[str] = ""
    price: Optional[float] = None
    condition: Optional[str] = ""
    photo: Optional[str] = None        # base64 (hanging)
    worn_photo: Optional[str] = None   # base64 (worn)
    flatters: Optional[bool] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    colour: Optional[str] = None
    fabric: Optional[str] = None
    season: Optional[str] = None
    pattern: Optional[str] = None
    fit_notes: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    price: Optional[float] = None
    condition: Optional[str] = None
    photo: Optional[str] = None
    worn_photo: Optional[str] = None
    flatters: Optional[bool] = None


class AnalyzeRequest(BaseModel):
    image: str  # base64 without data uri prefix


class SuggestRequest(BaseModel):
    occasion: str
    temperature: Optional[float] = None
    weather: Optional[str] = None
    notes: Optional[str] = ""


class WearLog(BaseModel):
    outfit_id: Optional[str] = None
    item_ids: List[str] = []
    photo: Optional[str] = None
    occasion: Optional[str] = ""
    flattering: int = 3
    comfort: int = 3
    confidence: int = 3
    notes: Optional[str] = ""


class OutfitCreate(BaseModel):
    name: str
    item_ids: List[str]
    occasion: Optional[str] = ""
    notes: Optional[str] = ""
    source: Optional[str] = "manual"  # manual | ai


# ----------------------------- Wardrobe Items -----------------------------
def strip_image(doc: dict, keep: bool = False) -> dict:
    """For list views we keep photos (needed for grid) but this hook allows trimming."""
    return doc


@api_router.post("/items")
async def create_item(payload: ItemCreate, user: dict = Depends(get_current_user)):
    item = payload.dict()
    item["id"] = new_id("item")
    item["user_id"] = user["user_id"]
    item["wear_count"] = 0
    item["last_worn"] = None
    item["created_at"] = now_utc().isoformat()
    await db.items.insert_one({**item})
    item.pop("_id", None)
    return item


@api_router.get("/items")
async def list_items(category: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {"user_id": user["user_id"]}
    if category and category.lower() != "all":
        query["category"] = category
    items = await db.items.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@api_router.get("/items/{item_id}")
async def get_item(item_id: str, user: dict = Depends(get_current_user)):
    item = await db.items.find_one({"id": item_id, "user_id": user["user_id"]}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@api_router.put("/items/{item_id}")
async def update_item(item_id: str, payload: ItemUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates")
    res = await db.items.update_one(
        {"id": item_id, "user_id": user["user_id"]}, {"$set": updates}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    item = await db.items.find_one({"id": item_id}, {"_id": 0})
    return item


@api_router.delete("/items/{item_id}")
async def delete_item(item_id: str, user: dict = Depends(get_current_user)):
    await db.items.delete_one({"id": item_id, "user_id": user["user_id"]})
    return {"ok": True}


# ----------------------------- AI: Analyze Item -----------------------------
ANALYZE_SYSTEM = (
    "You are a fashion cataloguing assistant. Look at the clothing item photo and return a strict JSON "
    "object describing it. Keys: name (short descriptive name, e.g. 'Cream linen blazer'), "
    "category (one of: Tops, Bottoms, Dresses, Outerwear, Shoes, Bags, Accessories, Jewellery), "
    "colour (primary colour word), fabric (best guess, e.g. cotton/denim/wool/linen/leather/silk), "
    "pattern (e.g. solid, striped, floral, checked), style (e.g. blazer, trench, bomber, pencil skirt), "
    "sleeve_length (e.g. sleeveless, short, three-quarter, long, n/a), "
    "season (one of: All, Spring, Summer, Autumn, Winter), "
    "condition (one of: New, Excellent, Good, Worn), "
    "needs_care (short string, e.g. 'needs steaming' or 'none'), "
    "estimated_value (integer estimate of resale/retail value in USD), "
    "description (one short sentence). Return ONLY the JSON object, no prose."
)


@api_router.post("/analyze-item")
async def analyze_item(payload: AnalyzeRequest, user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    chat = await ai_chat(f"analyze-{user['user_id']}-{uuid.uuid4().hex[:6]}", ANALYZE_SYSTEM)
    msg = UserMessage(
        text="Catalogue this clothing item. Return JSON only.",
        file_contents=[ImageContent(image_base64=payload.image)],
    )
    try:
        resp = await chat.send_message(msg)
    except Exception as e:
        logger.exception("analyze-item failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result:
        raise HTTPException(status_code=502, detail="Could not analyze image")
    return result


# ----------------------------- AI: Stylist Suggest -----------------------------
def summarize_items_for_ai(items: List[dict]) -> str:
    lines = []
    for it in items:
        lines.append(
            f"- id:{it['id']} | {it.get('category','')} | name:{it.get('name','')} | "
            f"colour:{it.get('colour','')} | fabric:{it.get('fabric','')} | "
            f"season:{it.get('season','All')} | fit:{it.get('fit_notes','')} | "
            f"flatters:{it.get('flatters')}"
        )
    return "\n".join(lines)


async def learned_prefs(user_id: str) -> str:
    """Summarize what has worked well based on high-rated wear logs."""
    logs = await db.wear_logs.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    if not logs:
        return "No feedback yet."
    good, bad = [], []
    for lg in logs:
        score = (lg.get("flattering", 3) + lg.get("comfort", 3) + lg.get("confidence", 3)) / 3
        tag = f"{lg.get('occasion','')} (items:{','.join(lg.get('item_ids', []))})"
        (good if score >= 4 else bad if score <= 2 else []).append(tag)
    parts = []
    if good:
        parts.append("Outfits the user loved: " + "; ".join(good[:10]))
    if bad:
        parts.append("Outfits the user disliked: " + "; ".join(bad[:10]))
    return " | ".join(parts) if parts else "Mixed feedback so far."


STYLIST_SYSTEM = (
    "You are Aura, an expert personal stylist. You build outfits using ONLY the items in the user's wardrobe "
    "(referenced by their exact id). Never invent items that are not in the list. "
    "Consider the occasion, temperature, weather, the user's learned preferences and which items flatter them. "
    "Return STRICT JSON with keys: "
    "items (array of objects with keys slot, item_id, reason), "
    "styling_notes (string), hair (string), makeup (string), confidence_tip (string), summary (string). "
    "slot values should be human labels like Top, Bottom, Dress, Outerwear, Shoes, Bag, Jewellery, Accessory. "
    "Only include item_id values that exist in the provided wardrobe. Return ONLY JSON."
)


@api_router.post("/stylist/suggest")
async def stylist_suggest(payload: SuggestRequest, user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    if len(items) < 2:
        raise HTTPException(status_code=400, detail="Add at least 2 wardrobe items to get suggestions")
    prefs = await learned_prefs(user["user_id"])
    wardrobe = summarize_items_for_ai(items)
    weather_line = ""
    if payload.temperature is not None:
        weather_line = f"Temperature: {payload.temperature}°C. Conditions: {payload.weather or 'n/a'}."
    prompt = (
        f"Occasion: {payload.occasion}\n{weather_line}\n"
        f"Extra notes: {payload.notes or 'none'}\n"
        f"Learned preferences: {prefs}\n\n"
        f"WARDROBE (use only these ids):\n{wardrobe}\n\n"
        "Build one cohesive, weather-appropriate outfit. Return JSON only."
    )
    chat = await ai_chat(f"stylist-{user['user_id']}-{uuid.uuid4().hex[:6]}", STYLIST_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("stylist failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result or "items" not in result:
        raise HTTPException(status_code=502, detail="Could not build an outfit")
    # Attach full item objects for valid ids
    by_id = {it["id"]: it for it in items}
    enriched = []
    for slot in result.get("items", []):
        it = by_id.get(slot.get("item_id"))
        if it:
            enriched.append({"slot": slot.get("slot", it.get("category")), "reason": slot.get("reason", ""), "item": it})
    result["resolved_items"] = enriched
    return result


# ----------------------------- AI: Shop Check -----------------------------
SHOP_SYSTEM = (
    "You are Aura's shopping-restraint advisor. The user is considering buying the item in the photo. "
    "You are given their existing wardrobe. Decide if they should buy it. Be honest and help them avoid "
    "duplicate purchases. Return STRICT JSON with keys: "
    "item_summary (short description of the item in the photo), "
    "verdict (one of: Buy, Skip, Maybe), "
    "reason (2-3 sentences explaining the verdict), "
    "similar_item_ids (array of ids of owned items that are very similar / near-duplicates), "
    "matches_with_ids (array of owned item ids it would pair well with), "
    "outfits_added (integer estimate of new outfits it enables), "
    "fills_gap (boolean), gap_note (short string about the wardrobe gap it does or does not fill). "
    "Only use ids that exist in the wardrobe. Return ONLY JSON."
)


@api_router.post("/shop-check")
async def shop_check(payload: AnalyzeRequest, user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    wardrobe = summarize_items_for_ai(items) if items else "The wardrobe is currently empty."
    chat = await ai_chat(f"shop-{user['user_id']}-{uuid.uuid4().hex[:6]}", SHOP_SYSTEM)
    msg = UserMessage(
        text=f"Here is my current wardrobe:\n{wardrobe}\n\nShould I buy the item in this photo? Return JSON only.",
        file_contents=[ImageContent(image_base64=payload.image)],
    )
    try:
        resp = await chat.send_message(msg)
    except Exception as e:
        logger.exception("shop-check failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result:
        raise HTTPException(status_code=502, detail="Could not analyze the item")
    by_id = {it["id"]: it for it in items}
    result["similar_items"] = [by_id[i] for i in result.get("similar_item_ids", []) if i in by_id]
    result["matches_with"] = [by_id[i] for i in result.get("matches_with_ids", []) if i in by_id]
    return result


# ----------------------------- Outfits & Wear Logs -----------------------------
@api_router.post("/outfits")
async def create_outfit(payload: OutfitCreate, user: dict = Depends(get_current_user)):
    outfit = payload.dict()
    outfit["id"] = new_id("outfit")
    outfit["user_id"] = user["user_id"]
    outfit["created_at"] = now_utc().isoformat()
    await db.outfits.insert_one({**outfit})
    outfit.pop("_id", None)
    return outfit


@api_router.get("/outfits")
async def list_outfits(user: dict = Depends(get_current_user)):
    outfits = await db.outfits.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    by_id = {it["id"]: it async for it in db.items.find({"user_id": user["user_id"]}, {"_id": 0})}
    for o in outfits:
        o["items"] = [by_id[i] for i in o.get("item_ids", []) if i in by_id]
    return outfits


@api_router.post("/wear")
async def log_wear(payload: WearLog, user: dict = Depends(get_current_user)):
    log = payload.dict()
    log["id"] = new_id("wear")
    log["user_id"] = user["user_id"]
    log["created_at"] = now_utc().isoformat()
    await db.wear_logs.insert_one({**log})
    # Increment wear counts
    for iid in payload.item_ids:
        await db.items.update_one(
            {"id": iid, "user_id": user["user_id"]},
            {"$inc": {"wear_count": 1}, "$set": {"last_worn": now_utc().isoformat()}},
        )
    log.pop("_id", None)
    return log


@api_router.get("/wear")
async def list_wear(user: dict = Depends(get_current_user)):
    logs = await db.wear_logs.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return logs


# ----------------------------- Insights -----------------------------
@api_router.get("/insights")
async def insights(user: dict = Depends(get_current_user)):
    items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(2000)
    logs = await db.wear_logs.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(2000)
    total_items = len(items)
    total_wears = sum(it.get("wear_count", 0) for it in items)
    priced = [it for it in items if it.get("price")]
    total_value = sum(it.get("price", 0) for it in priced)

    def cpw(it):
        wc = it.get("wear_count", 0)
        return (it["price"] / wc) if it.get("price") and wc > 0 else None

    avg_cpw_vals = [cpw(it) for it in items if cpw(it) is not None]
    avg_cpw = round(sum(avg_cpw_vals) / len(avg_cpw_vals), 2) if avg_cpw_vals else None

    most_worn = sorted(items, key=lambda x: x.get("wear_count", 0), reverse=True)[:5]
    least_worn = sorted(items, key=lambda x: x.get("wear_count", 0))[:5]

    # category breakdown
    cats: dict = {}
    for it in items:
        cats[it.get("category", "Other")] = cats.get(it.get("category", "Other"), 0) + 1

    # avg ratings
    def avg(key):
        vals = [lg.get(key, 0) for lg in logs]
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "total_items": total_items,
        "total_wears": total_wears,
        "total_value": round(total_value, 2),
        "avg_cost_per_wear": avg_cpw,
        "outfits_logged": len(logs),
        "avg_flattering": avg("flattering"),
        "avg_comfort": avg("comfort"),
        "avg_confidence": avg("confidence"),
        "categories": cats,
        "most_worn": most_worn,
        "least_worn": least_worn,
    }


# ----------------------------- AI: The Missing Piece -----------------------------
MISSING_SYSTEM = (
    "You are Aura's brutally honest wardrobe-gap analyst. Given the user's full wardrobe, identify the ONE "
    "item that would most increase the number of workable outfits — a genuine gap, not another duplicate. "
    "Be honest: if they already own many of something, say so. Prefer versatile, foundational pieces. "
    "Return STRICT JSON with keys: "
    "recommendation (the single item to consider, e.g. 'A well-cut camel wool coat'), "
    "reason (2-3 sentences on why it unlocks the most outfits, referencing what they own), "
    "avoid (short honest warning about a category they already over-own, e.g. 'You own 8 black tops — skip more'). "
    "Return ONLY JSON."
)


@api_router.post("/insights/missing-piece")
async def missing_piece(user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(2000)
    if len(items) < 3:
        raise HTTPException(status_code=400, detail="Add a few more pieces to analyze your wardrobe gaps")
    wardrobe = summarize_items_for_ai(items)
    counts: dict = {}
    for it in items:
        counts[it.get("category", "Other")] = counts.get(it.get("category", "Other"), 0) + 1
    breakdown = ", ".join(f"{k}:{v}" for k, v in counts.items())
    prompt = (
        f"Wardrobe breakdown by count: {breakdown}\n\n"
        f"Full wardrobe:\n{wardrobe}\n\n"
        "What single piece would make this wardrobe work hardest? Return JSON only."
    )
    chat = await ai_chat(f"missing-{user['user_id']}-{uuid.uuid4().hex[:6]}", MISSING_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("missing-piece failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result:
        raise HTTPException(status_code=502, detail="Could not analyze your wardrobe")
    return result


# ----------------------------- Weather -----------------------------
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow",
    75: "Heavy snow", 80: "Rain showers", 81: "Rain showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}


@api_router.get("/weather")
async def weather(lat: float, lon: float):
    async with httpx.AsyncClient(timeout=15) as hc:
        resp = await hc.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,apparent_temperature,weather_code",
                "timezone": "auto",
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Weather unavailable")
    data = resp.json().get("current", {})
    code = data.get("weather_code", 0)
    return {
        "temperature": data.get("temperature_2m"),
        "feels_like": data.get("apparent_temperature"),
        "code": code,
        "description": WEATHER_CODES.get(code, "Unknown"),
    }


@api_router.get("/")
async def root():
    return {"message": "Aura API"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("user_id")
    await db.items.create_index("user_id")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
