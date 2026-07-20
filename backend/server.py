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


async def ensure_default_profile(account_id: str, name: Optional[str]) -> dict:
    """Return the account's default profile, creating one (and migrating legacy
    data whose owner id == account id) on first access."""
    prof = await db.profiles.find_one({"user_id": account_id}, {"_id": 0}, sort=[("created_at", 1)])
    if prof:
        return prof
    prof = {
        "id": new_id("prof"),
        "user_id": account_id,
        "name": (name or "Me").split(" ")[0] or "Me",
        "emoji": "👤",
        "kind": "individual",
        "profile": {},
        "created_at": now_utc().isoformat(),
    }
    await db.profiles.insert_one({**prof})
    prof.pop("_id", None)
    # Migrate legacy documents (scoped by account id) to this default profile id.
    for coll in (db.items, db.outfits, db.wear_logs, db.plans):
        await coll.update_many(
            {"user_id": account_id, "profile_id": {"$exists": False}},
            {"$set": {"profile_id": prof["id"], "user_id": prof["id"]}},
        )
    return prof


async def get_scope(x_profile_id: Optional[str] = Header(None),
                    account: dict = Depends(get_current_user)) -> dict:
    """Resolve the active wardrobe profile. Returns a scope dict whose
    'user_id' is the PROFILE id, so existing data queries scope per-profile."""
    account_id = account["user_id"]
    prof = None
    if x_profile_id:
        prof = await db.profiles.find_one(
            {"id": x_profile_id, "user_id": account_id}, {"_id": 0}
        )
    if not prof:
        prof = await ensure_default_profile(account_id, account.get("name"))
    return {
        "user_id": prof["id"],       # data scope = profile id
        "account_id": account_id,
        "profile_id": prof["id"],
        "profile_name": prof.get("name"),
        "profile": prof.get("profile") or {},
    }


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


class ProfileUpdate(BaseModel):
    measurements: Optional[dict] = None
    body_shape: Optional[str] = None
    skin_tone: Optional[str] = None
    undertone: Optional[str] = None
    height: Optional[str] = None
    sizes: Optional[str] = None
    notes: Optional[str] = None


class ProfileCreate(BaseModel):
    name: str
    emoji: Optional[str] = "👤"
    kind: Optional[str] = "individual"  # individual | child | shared


class ProfileRename(BaseModel):
    name: Optional[str] = None
    emoji: Optional[str] = None
    kind: Optional[str] = None


@api_router.get("/profiles")
async def list_profiles(account: dict = Depends(get_current_user)):
    profs = await db.profiles.find({"user_id": account["user_id"]}, {"_id": 0}).sort("created_at", 1).to_list(50)
    if not profs:
        prof = await ensure_default_profile(account["user_id"], account.get("name"))
        profs = [prof]
    return profs


@api_router.post("/profiles")
async def create_profile(payload: ProfileCreate, account: dict = Depends(get_current_user)):
    await ensure_default_profile(account["user_id"], account.get("name"))
    prof = {
        "id": new_id("prof"),
        "user_id": account["user_id"],
        "name": payload.name,
        "emoji": payload.emoji or "👤",
        "kind": payload.kind or "individual",
        "profile": {},
        "created_at": now_utc().isoformat(),
    }
    await db.profiles.insert_one({**prof})
    prof.pop("_id", None)
    return prof


@api_router.put("/profiles/{profile_id}")
async def rename_profile(profile_id: str, payload: ProfileRename, account: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    if updates:
        await db.profiles.update_one(
            {"id": profile_id, "user_id": account["user_id"]}, {"$set": updates}
        )
    return await db.profiles.find_one({"id": profile_id, "user_id": account["user_id"]}, {"_id": 0})


@api_router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str, account: dict = Depends(get_current_user)):
    count = await db.profiles.count_documents({"user_id": account["user_id"]})
    if count <= 1:
        raise HTTPException(status_code=400, detail="You need at least one profile")
    # Remove the profile and its wardrobe data
    for coll in (db.items, db.outfits, db.wear_logs, db.plans):
        await coll.delete_many({"user_id": profile_id})
    await db.profiles.delete_one({"id": profile_id, "user_id": account["user_id"]})
    return {"ok": True}


@api_router.put("/profile")
async def update_profile(payload: ProfileUpdate, scope: dict = Depends(get_scope)):
    """Update the active profile's style attributes (measurements, skin tone…)."""
    prof = await db.profiles.find_one({"id": scope["profile_id"]}, {"_id": 0})
    style = (prof.get("profile") if prof else {}) or {}
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    style.update(updates)
    await db.profiles.update_one({"id": scope["profile_id"]}, {"$set": {"profile": style}})
    return await db.profiles.find_one({"id": scope["profile_id"]}, {"_id": 0})


# ----------------------------- Models -----------------------------
class ItemCreate(BaseModel):
    name: str
    category: str
    colour: Optional[str] = ""
    fabric: Optional[str] = ""
    season: Optional[str] = "All"
    pattern: Optional[str] = ""
    style: Optional[str] = ""
    sleeve_length: Optional[str] = ""
    formality: Optional[str] = ""
    tone: Optional[str] = ""
    fit_notes: Optional[str] = ""
    brand: Optional[str] = ""
    size: Optional[str] = ""
    price: Optional[float] = None
    condition: Optional[str] = ""
    availability: Optional[str] = "Ready"  # Ready | Dirty | Washing | Drying
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
    style: Optional[str] = None
    sleeve_length: Optional[str] = None
    formality: Optional[str] = None
    tone: Optional[str] = None
    fit_notes: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    price: Optional[float] = None
    condition: Optional[str] = None
    availability: Optional[str] = None
    photo: Optional[str] = None
    worn_photo: Optional[str] = None
    flatters: Optional[bool] = None


class AnalyzeRequest(BaseModel):
    image: str  # base64 without data uri prefix
    category_hint: Optional[str] = None  # e.g. "Tops" — focus the AI when several garments are worn


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
    mark_dirty: bool = False


class OutfitCreate(BaseModel):
    name: str
    item_ids: List[str]
    occasion: Optional[str] = ""
    notes: Optional[str] = ""
    source: Optional[str] = "manual"  # manual | ai


# ----------------------------- Wardrobe Items -----------------------------
FORMALITY_ORDER = {"Casual": 0, "Smart Casual": 1, "Business": 2, "Formal": 3}
_MAIN_CATS = {"Tops", "Bottoms", "Dresses", "Outerwear"}
_PAIR_EXCLUSIONS = {("Dresses", "Tops"), ("Dresses", "Bottoms")}


def _items_pair(a: dict, b: dict) -> bool:
    """Rule-based (instant, no AI) check of whether two owned pieces can appear
    in the same outfit — used to precompute a 'pairs with' count per item."""
    ca, cb = a.get("category"), b.get("category")
    if not ca or not cb or ca == cb:
        return False
    if (ca, cb) in _PAIR_EXCLUSIONS or (cb, ca) in _PAIR_EXCLUSIONS:
        return False
    # Formality must be within one step for the main garments.
    if ca in _MAIN_CATS and cb in _MAIN_CATS:
        fa = FORMALITY_ORDER.get(a.get("formality") or "")
        fb = FORMALITY_ORDER.get(b.get("formality") or "")
        if fa is not None and fb is not None and abs(fa - fb) > 1:
            return False
    return True


def compute_pairs_counts(items: List[dict]) -> dict:
    """For every item, how many OTHER ready-to-wear items it can be styled with."""
    ready = [it for it in items if (it.get("availability") or "Ready") == "Ready"]
    counts = {it["id"]: 0 for it in items}
    for i in range(len(ready)):
        for j in range(i + 1, len(ready)):
            if _items_pair(ready[i], ready[j]):
                counts[ready[i]["id"]] += 1
                counts[ready[j]["id"]] += 1
    return counts


def strip_image(doc: dict, keep: bool = False) -> dict:
    """For list views we keep photos (needed for grid) but this hook allows trimming."""
    return doc


@api_router.post("/items")
async def create_item(payload: ItemCreate, user: dict = Depends(get_scope)):
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
async def list_items(category: Optional[str] = None, user: dict = Depends(get_scope)):
    all_items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    counts = compute_pairs_counts(all_items)
    if category and category.lower() != "all":
        items = [it for it in all_items if it.get("category") == category]
    else:
        items = all_items
    for it in items:
        it["pairs_count"] = counts.get(it["id"], 0)
    return items


@api_router.get("/laundry")
async def laundry(user: dict = Depends(get_scope)):
    items = await db.items.find(
        {"user_id": user["user_id"], "availability": {"$in": ["Dirty", "Washing", "Drying"]}}, {"_id": 0}
    ).sort("name", 1).to_list(1000)
    return items


@api_router.get("/items/{item_id}")
async def get_item(item_id: str, user: dict = Depends(get_scope)):
    item = await db.items.find_one({"id": item_id, "user_id": user["user_id"]}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@api_router.put("/items/{item_id}")
async def update_item(item_id: str, payload: ItemUpdate, user: dict = Depends(get_scope)):
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
async def delete_item(item_id: str, user: dict = Depends(get_scope)):
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
    "formality (one of: Casual, Smart Casual, Business, Formal), "
    "tone (one of: Warm, Cool, Neutral), "
    "season (one of: All, Spring, Summer, Autumn, Winter), "
    "condition (one of: New, Excellent, Good, Worn), "
    "needs_care (short string, e.g. 'needs steaming' or 'none'), "
    "estimated_value (integer estimate of resale/retail value in USD), "
    "description (one short sentence). Return ONLY the JSON object, no prose."
)


@api_router.post("/analyze-item")
async def analyze_item(payload: AnalyzeRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    chat = await ai_chat(f"analyze-{user['user_id']}-{uuid.uuid4().hex[:6]}", ANALYZE_SYSTEM)
    if payload.category_hint:
        text = (
            f"The person in the photo may be wearing several garments. Focus ONLY on the "
            f"{payload.category_hint} and catalogue that single item, ignoring everything else "
            f"they are wearing. Set the category to '{payload.category_hint}'. Return JSON only."
        )
    else:
        text = "Catalogue this clothing item. Return JSON only."
    msg = UserMessage(
        text=text,
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
            f"season:{it.get('season','All')} | formality:{it.get('formality','')} | "
            f"tone:{it.get('tone','')} | fit:{it.get('fit_notes','')} | "
            f"flatters:{it.get('flatters')}"
        )
    return "\n".join(lines)


def available_items(items: List[dict]) -> List[dict]:
    """Items ready to wear — excludes anything in the laundry cycle."""
    return [it for it in items if (it.get("availability") or "Ready") == "Ready"]


def profile_context(user: dict) -> str:
    """Summarise the user's body profile / skin tone for the stylist prompt."""
    p = user.get("profile") or {}
    if not p:
        return "No body profile provided — style with general best practices."
    parts = []
    m = p.get("measurements") or {}
    meas = ", ".join(f"{k}: {v}" for k, v in m.items() if v)
    if meas:
        parts.append(f"measurements ({meas})")
    for key in ["height", "body_shape", "skin_tone", "undertone", "sizes", "notes"]:
        if p.get(key):
            parts.append(f"{key.replace('_', ' ')}: {p[key]}")
    if not parts:
        return "No body profile provided — style with general best practices."
    return (
        "Body profile — " + "; ".join(parts) +
        ". Choose cuts, lengths, proportions and colours that flatter this body shape and skin tone."
    )


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
    "You are Aura, an expert personal stylist who thinks about balance, proportion, layering, contrast, colour "
    "theory, texture and silhouette — not just colour matching. You build outfits using ONLY the items in the "
    "user's wardrobe (referenced by their exact id). Never invent items that are not in the list. "
    "Actively include styling accessories (belts, scarves, bags, sunglasses, jewellery) when they improve the look. "
    "Consider the occasion, temperature, weather, the user's learned preferences and which items flatter them. "
    "Return STRICT JSON with keys: "
    "items (array of objects with keys slot, item_id, reason — reason explains WHY it works, like a stylist), "
    "confidence_score (integer 0-100 rating the outfit on colour harmony, style cohesion, occasion + weather "
    "suitability, proportion/silhouette and use of existing wardrobe), "
    "score_reasons (array of 3-5 short bullet strings justifying the score), "
    "styling_notes (string), hair (string), makeup (string), confidence_tip (string), summary (string). "
    "slot values should be human labels like Top, Bottom, Dress, Outerwear, Shoes, Bag, Belt, Scarf, Sunglasses, "
    "Jewellery, Accessory. Only include item_id values that exist in the provided wardrobe. Return ONLY JSON."
)


@api_router.post("/stylist/suggest")
async def stylist_suggest(payload: SuggestRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    items = available_items(items)
    if len(items) < 2:
        raise HTTPException(status_code=400, detail="Not enough ready-to-wear items. Add more, or mark laundry as clean.")
    prefs = await learned_prefs(user["user_id"])
    wardrobe = summarize_items_for_ai(items)
    weather_line = ""
    if payload.temperature is not None:
        weather_line = f"Temperature: {payload.temperature}°C. Conditions: {payload.weather or 'n/a'}."
    prompt = (
        f"Occasion: {payload.occasion}\n{weather_line}\n"
        f"Extra notes: {payload.notes or 'none'}\n"
        f"{profile_context(user)}\n"
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


# ----------------------------- AI: Compatibility / Wardrobe Intelligence -----------------------------
COMPAT_SYSTEM = (
    "You are Aura's compatibility engine. Given ONE focus item and the rest of the user's wardrobe, rate how "
    "well each OTHER item pairs with the focus item, thinking like a stylist (colour harmony, tone, formality, "
    "proportion, texture, season). Return STRICT JSON with keys: "
    "versatility_score (integer 0-100 for how versatile the focus item is across the wardrobe), "
    "summary (one sentence describing the focus item's styling role), "
    "matches (array of objects: item_id, stars (integer 1-5), reason (short stylist explanation)). "
    "Rank matches best-first and include every other wardrobe item. Only use ids that exist. Return ONLY JSON."
)


@api_router.post("/items/{item_id}/compatibility")
async def item_compatibility(item_id: str, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    focus = await db.items.find_one({"id": item_id, "user_id": user["user_id"]}, {"_id": 0})
    if not focus:
        raise HTTPException(status_code=404, detail="Item not found")
    others = await db.items.find(
        {"user_id": user["user_id"], "id": {"$ne": item_id}}, {"_id": 0}
    ).to_list(1000)
    others = available_items(others)
    if len(others) < 1:
        raise HTTPException(status_code=400, detail="Add more items to see what pairs together")
    focus_desc = (
        f"id:{focus['id']} | {focus.get('category','')} | {focus.get('name','')} | "
        f"colour:{focus.get('colour','')} | tone:{focus.get('tone','')} | "
        f"formality:{focus.get('formality','')} | fabric:{focus.get('fabric','')} | season:{focus.get('season','All')}"
    )
    wardrobe = summarize_items_for_ai(others)
    prompt = (
        f"FOCUS ITEM:\n{focus_desc}\n\nREST OF WARDROBE (rate each against the focus item):\n{wardrobe}\n\n"
        "Return JSON only."
    )
    chat = await ai_chat(f"compat-{user['user_id']}-{uuid.uuid4().hex[:6]}", COMPAT_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("compatibility failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result or "matches" not in result:
        raise HTTPException(status_code=502, detail="Could not analyze compatibility")
    by_id = {it["id"]: it for it in others}
    resolved = []
    for m in result.get("matches", []):
        it = by_id.get(m.get("item_id"))
        if it:
            resolved.append({"item": it, "stars": m.get("stars", 3), "reason": m.get("reason", "")})
    result["resolved_matches"] = resolved
    result["match_count"] = len([m for m in resolved if m["stars"] >= 3])
    result["focus"] = focus
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
async def shop_check(payload: AnalyzeRequest, user: dict = Depends(get_scope)):
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
async def create_outfit(payload: OutfitCreate, user: dict = Depends(get_scope)):
    outfit = payload.dict()
    outfit["id"] = new_id("outfit")
    outfit["user_id"] = user["user_id"]
    outfit["created_at"] = now_utc().isoformat()
    await db.outfits.insert_one({**outfit})
    outfit.pop("_id", None)
    return outfit


@api_router.get("/outfits")
async def list_outfits(user: dict = Depends(get_scope)):
    outfits = await db.outfits.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    by_id = {it["id"]: it async for it in db.items.find({"user_id": user["user_id"]}, {"_id": 0})}
    for o in outfits:
        o["items"] = [by_id[i] for i in o.get("item_ids", []) if i in by_id]
    return outfits


@api_router.delete("/outfits/{outfit_id}")
async def delete_outfit(outfit_id: str, user: dict = Depends(get_scope)):
    await db.outfits.delete_one({"id": outfit_id, "user_id": user["user_id"]})
    return {"ok": True}


# ----------------------------- Outfit Planner -----------------------------
class PlanCreate(BaseModel):
    date: str  # YYYY-MM-DD
    title: Optional[str] = ""
    occasion: Optional[str] = ""
    outfit_id: Optional[str] = None
    item_ids: List[str] = []
    notes: Optional[str] = ""


@api_router.post("/plans")
async def create_plan(payload: PlanCreate, user: dict = Depends(get_scope)):
    plan = payload.dict()
    plan["id"] = new_id("plan")
    plan["user_id"] = user["user_id"]
    plan["created_at"] = now_utc().isoformat()
    # If linked to a saved outfit, snapshot its item_ids
    if plan.get("outfit_id") and not plan.get("item_ids"):
        outfit = await db.outfits.find_one({"id": plan["outfit_id"], "user_id": user["user_id"]}, {"_id": 0})
        if outfit:
            plan["item_ids"] = outfit.get("item_ids", [])
            if not plan.get("title"):
                plan["title"] = outfit.get("name", "")
    await db.plans.insert_one({**plan})
    plan.pop("_id", None)
    return plan


@api_router.get("/plans")
async def list_plans(from_date: Optional[str] = None, to_date: Optional[str] = None,
                     user: dict = Depends(get_scope)):
    query: dict = {"user_id": user["user_id"]}
    if from_date or to_date:
        query["date"] = {}
        if from_date:
            query["date"]["$gte"] = from_date
        if to_date:
            query["date"]["$lte"] = to_date
    plans = await db.plans.find(query, {"_id": 0}).sort("date", 1).to_list(500)
    by_id = {it["id"]: it async for it in db.items.find({"user_id": user["user_id"]}, {"_id": 0})}
    for p in plans:
        p["items"] = [by_id[i] for i in p.get("item_ids", []) if i in by_id]
    return plans


@api_router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str, user: dict = Depends(get_scope)):
    await db.plans.delete_one({"id": plan_id, "user_id": user["user_id"]})
    return {"ok": True}


@api_router.post("/wear")
async def log_wear(payload: WearLog, user: dict = Depends(get_scope)):
    log = payload.dict()
    log["id"] = new_id("wear")
    log["user_id"] = user["user_id"]
    log["created_at"] = now_utc().isoformat()
    await db.wear_logs.insert_one({**log})
    # Increment wear counts (and optionally move to laundry)
    item_set = {"last_worn": now_utc().isoformat()}
    if payload.mark_dirty:
        item_set["availability"] = "Dirty"
    for iid in payload.item_ids:
        await db.items.update_one(
            {"id": iid, "user_id": user["user_id"]},
            {"$inc": {"wear_count": 1}, "$set": item_set},
        )
    log.pop("_id", None)
    return log


@api_router.get("/wear")
async def list_wear(user: dict = Depends(get_scope)):
    logs = await db.wear_logs.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    by_id = {it["id"]: it async for it in db.items.find({"user_id": user["user_id"]}, {"_id": 0})}
    for lg in logs:
        lg["items"] = [by_id[i] for i in lg.get("item_ids", []) if i in by_id]
    return logs


# ----------------------------- Insights -----------------------------
@api_router.get("/insights")
async def insights(user: dict = Depends(get_scope)):
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
async def missing_piece(user: dict = Depends(get_scope)):
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


# ----------------------------- AI: Packing Capsule -----------------------------
class PackingRequest(BaseModel):
    destination: str
    days: int = 3
    start_offset_days: int = 0  # how many days from today the trip begins
    occasions: Optional[str] = ""
    notes: Optional[str] = ""


async def geocode_place(name: str):
    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": name, "count": 1, "language": "en"},
        )
    if r.status_code != 200:
        return None
    results = r.json().get("results") or []
    if not results:
        return None
    g = results[0]
    return {
        "lat": g["latitude"],
        "lon": g["longitude"],
        "city": g.get("name"),
        "country": g.get("country", ""),
    }


async def forecast_summary(lat: float, lon: float, days: int, start_offset: int = 0):
    # Open-Meteo free forecast reaches ~16 days ahead.
    start_offset = max(0, min(start_offset, 15))
    days = max(1, min(days, 16 - start_offset))
    total = start_offset + days
    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "forecast_days": min(total, 16), "timezone": "auto",
            },
        )
    if r.status_code != 200:
        return None
    d = r.json().get("daily", {})
    highs = [h for h in (d.get("temperature_2m_max", []) or [])[start_offset:total] if h is not None]
    lows = [l for l in (d.get("temperature_2m_min", []) or [])[start_offset:total] if l is not None]
    codes = [c for c in (d.get("weather_code", []) or [])[start_offset:total] if c is not None]
    if not highs or not lows:
        return None
    conditions = list({WEATHER_CODES.get(c, "Unknown") for c in codes})
    window = "for your travel dates" if start_offset > 0 else ""
    return {
        "high": round(max(highs)),
        "low": round(min(lows)),
        "conditions": conditions,
        "text": f"Highs {round(max(highs))}°C, lows {round(min(lows))}°C {window}. Expect: {', '.join(conditions)}.".replace("  ", " "),
    }


PACKING_SYSTEM = (
    "You are Aura's packing assistant. Build a smart CAPSULE wardrobe for a trip using ONLY the items in the "
    "user's wardrobe (by exact id). Maximise outfit combinations while minimising the number of pieces so it "
    "fits in a carry-on. Match the destination weather and the occasions. "
    "Return STRICT JSON with keys: "
    "weather_note (one sentence summarising conditions to pack for), "
    "capsule_item_ids (array of the item ids to pack, keep it lean), "
    "outfits (array of objects: name, item_ids (subset of the capsule)), "
    "fits_carry_on (boolean), packing_tip (one short sentence), "
    "essentials_missing (array of short strings for gaps the wardrobe can't cover, may be empty). "
    "Only use ids present in the wardrobe. Return ONLY JSON."
)


@api_router.post("/packing/plan")
async def packing_plan(payload: PackingRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    items = available_items(items)
    if len(items) < 3:
        raise HTTPException(status_code=400, detail="Need at least 3 ready-to-wear items to build a capsule")

    geo = await geocode_place(payload.destination)
    weather = None
    if geo:
        weather = await forecast_summary(geo["lat"], geo["lon"], payload.days, payload.start_offset_days)

    wardrobe = summarize_items_for_ai(items)
    prefs = await learned_prefs(user["user_id"])
    place = f"{geo['city']}, {geo['country']}" if geo else payload.destination
    weather_line = weather["text"] if weather else "Weather forecast unavailable — pack versatile layers."
    when = f"starting in {payload.start_offset_days} days" if payload.start_offset_days else "starting today"
    prompt = (
        f"Destination: {place}\nTrip length: {payload.days} days ({when})\n"
        f"Occasions: {payload.occasions or 'general travel'}\n"
        f"Forecast: {weather_line}\n"
        f"Extra notes: {payload.notes or 'none'}\n"
        f"{profile_context(user)}\n"
        f"Learned preferences: {prefs}\n\n"
        f"WARDROBE (use only these ids):\n{wardrobe}\n\n"
        "Build a lean carry-on capsule and a set of outfits from it. Return JSON only."
    )
    chat = await ai_chat(f"packing-{user['user_id']}-{uuid.uuid4().hex[:6]}", PACKING_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("packing failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result or "capsule_item_ids" not in result:
        raise HTTPException(status_code=502, detail="Could not build a packing plan")

    by_id = {it["id"]: it for it in items}
    result["capsule_items"] = [by_id[i] for i in result.get("capsule_item_ids", []) if i in by_id]
    result["resolved_outfits"] = [
        {"name": o.get("name", "Look"), "items": [by_id[i] for i in o.get("item_ids", []) if i in by_id]}
        for o in result.get("outfits", [])
    ]
    result["destination"] = place
    result["days"] = payload.days
    return result


# ----------------------------- AI: Seasonal / Purpose Capsule -----------------------------
class CapsuleRequest(BaseModel):
    theme: str  # e.g. Autumn, Winter, Work, Travel, Weekend
    occasion: Optional[str] = ""


CAPSULE_SYSTEM = (
    "You are Aura's capsule wardrobe builder. Given a theme (a season or a purpose like Work or Weekend) and the "
    "user's wardrobe, curate a lean, cohesive capsule using ONLY the items in the wardrobe (by exact id) that "
    "maximises mix-and-match outfit combinations for that theme. "
    "Return STRICT JSON with keys: "
    "summary (one sentence describing the capsule's vibe), "
    "capsule_item_ids (array of ids, keep it lean and versatile), "
    "outfits (array of objects: name, item_ids (subset of the capsule)), "
    "capsule_tip (one short styling sentence), "
    "essentials_missing (array of short strings for gaps to complete the capsule, may be empty). "
    "Only use ids present in the wardrobe. Return ONLY JSON."
)


@api_router.post("/capsule/build")
async def capsule_build(payload: CapsuleRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    items = available_items(items)
    if len(items) < 3:
        raise HTTPException(status_code=400, detail="Need at least 3 ready-to-wear items to build a capsule")
    wardrobe = summarize_items_for_ai(items)
    prefs = await learned_prefs(user["user_id"])
    prompt = (
        f"Capsule theme: {payload.theme}\n"
        f"Purpose / occasions: {payload.occasion or 'general'}\n"
        f"{profile_context(user)}\n"
        f"Learned preferences: {prefs}\n\n"
        f"WARDROBE (use only these ids):\n{wardrobe}\n\n"
        "Build a cohesive capsule and a set of outfits from it. Return JSON only."
    )
    chat = await ai_chat(f"capsule-{user['user_id']}-{uuid.uuid4().hex[:6]}", CAPSULE_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("capsule failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result or "capsule_item_ids" not in result:
        raise HTTPException(status_code=502, detail="Could not build a capsule")
    by_id = {it["id"]: it for it in items}
    result["capsule_items"] = [by_id[i] for i in result.get("capsule_item_ids", []) if i in by_id]
    result["resolved_outfits"] = [
        {"name": o.get("name", "Look"), "items": [by_id[i] for i in o.get("item_ids", []) if i in by_id]}
        for o in result.get("outfits", [])
    ]
    result["theme"] = payload.theme
    return result


# ----------------------------- AI: Wardrobe Health Report -----------------------------
HEALTH_SYSTEM = (
    "You are Aura's wardrobe health analyst. You are given wardrobe stats and the raw numbers. Write an honest, "
    "encouraging monthly report. Return STRICT JSON with keys: "
    "headline (one punchy sentence summarising the month), "
    "wasted_summary (2-3 sentences about money tied up in unworn/rarely-worn items, using the numbers given), "
    "lesson (one actionable sentence about what to wear more or rotate), "
    "missing_piece (object: recommendation, reason, unlock_note), "
    "wins (array of 1-3 short positive observations), "
    "nudges (array of 1-3 short gentle action nudges e.g. 'Wear or donate the 3 untouched dresses'). "
    "Return ONLY JSON."
)


@api_router.post("/insights/health-report")
async def health_report(user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(2000)
    if len(items) < 3:
        raise HTTPException(status_code=400, detail="Add a few more pieces to generate your report")

    unworn = [it for it in items if (it.get("wear_count", 0) or 0) == 0]
    unworn_value = round(sum(it.get("price", 0) or 0 for it in unworn), 2)
    total_value = round(sum(it.get("price", 0) or 0 for it in items), 2)

    def cpw(it):
        wc = it.get("wear_count", 0) or 0
        return (it["price"] / wc) if it.get("price") and wc > 0 else None

    high_cpw = sorted(
        [it for it in items if cpw(it) is not None],
        key=lambda x: cpw(x), reverse=True,
    )[:3]
    high_cpw_desc = "; ".join(f"{it['name']} (${cpw(it):.2f}/wear)" for it in high_cpw) or "none yet"
    counts: dict = {}
    for it in items:
        counts[it.get("category", "Other")] = counts.get(it.get("category", "Other"), 0) + 1
    breakdown = ", ".join(f"{k}:{v}" for k, v in counts.items())

    prompt = (
        f"Total pieces: {len(items)}. Total wardrobe value: ${total_value}.\n"
        f"Unworn pieces: {len(unworn)} worth ${unworn_value}.\n"
        f"Highest cost-per-wear items: {high_cpw_desc}.\n"
        f"Category breakdown: {breakdown}.\n\n"
        "Write the monthly wardrobe health report. Be honest about wasted money and name the single "
        "purchase that would unlock the most outfits. Return JSON only."
    )
    chat = await ai_chat(f"health-{user['user_id']}-{uuid.uuid4().hex[:6]}", HEALTH_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("health-report failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result:
        raise HTTPException(status_code=502, detail="Could not generate your report")
    result["stats"] = {
        "total_items": len(items),
        "total_value": total_value,
        "unworn_count": len(unworn),
        "unworn_value": unworn_value,
    }
    return result


# ----------------------------- AI: Hair & Makeup -----------------------------
class BeautyRequest(BaseModel):
    occasion: Optional[str] = ""


BEAUTY_SYSTEM = (
    "You are Aura's professional colour analyst and beauty stylist. Using the person's skin tone, undertone and "
    "any personal notes, recommend hair and makeup that flatter THEM — grounded in colour theory (warm vs cool "
    "undertones, contrast levels), never generic. Be confident, calm and specific; explain the reasoning briefly, "
    "like a stylist, and stay inclusive of all genders and presentations. "
    "Return STRICT JSON with keys: "
    "summary (one sentence on the person's colouring and the direction), "
    "palette (array of 5-8 flattering colour names to wear near the face), "
    "makeup (object: foundation (undertone guidance), blush, lip, eye, tip — each a short string; keep it "
    "wearable and optional), "
    "hair (object: colour (flattering hair-colour directions), style (a styling suggestion for the occasion), "
    "tip (one short string)), "
    "avoid (array of 2-4 short strings — colours/finishes that fight this colouring), "
    "occasion_note (one short sentence tailoring the look to the stated occasion). "
    "Return ONLY JSON."
)


@api_router.post("/beauty/suggest")
async def beauty_suggest(payload: BeautyRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    p = user.get("profile") or {}
    skin = p.get("skin_tone")
    undertone = p.get("undertone")
    notes = p.get("notes")
    if not skin and not undertone:
        raise HTTPException(
            status_code=400,
            detail="Add your skin tone and undertone in your style profile for personalised beauty advice.",
        )
    profile_line = "; ".join(
        f"{k}: {v}" for k, v in [
            ("skin tone", skin), ("undertone", undertone), ("notes", notes),
        ] if v
    )
    prompt = (
        f"Person's colouring — {profile_line}.\n"
        f"Occasion: {payload.occasion or 'everyday'}.\n\n"
        "Recommend flattering hair and makeup for this colouring and occasion. Return JSON only."
    )
    chat = await ai_chat(f"beauty-{user['user_id']}-{uuid.uuid4().hex[:6]}", BEAUTY_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("beauty failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result:
        raise HTTPException(status_code=502, detail="Could not generate beauty recommendations")
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
