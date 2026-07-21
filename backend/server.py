from fastapi import FastAPI, APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import json
import logging
import uuid
import asyncio
import io
import base64 as _b64
from PIL import Image
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout,
    CheckoutSessionRequest,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
AI_MODEL = ("openai", "gpt-5.4")

STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY', '')

GCAL_CLIENT_ID = os.environ.get('GOOGLE_CALENDAR_CLIENT_ID', '')
GCAL_CLIENT_SECRET = os.environ.get('GOOGLE_CALENDAR_CLIENT_SECRET', '')
GCAL_REDIRECT_URI = os.environ.get('GOOGLE_CALENDAR_REDIRECT_URI', '')
GCAL_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

# Premium membership — one-time payment grants a time-boxed entitlement (whole household).
PREMIUM_PLANS = {
    "monthly": {"amount": 9.99, "days": 30, "label": "Premium Monthly"},
    "annual": {"amount": 79.99, "days": 365, "label": "Premium Annual"},
}
# Free tier: unlimited wardrobe + a taste of AI. Metered features:
FREE_LIMITS = {
    "stylist": {"period": "day", "max": 5},
    "beauty": {"period": "month", "max": 1},
}
# Everything not in FREE_LIMITS is Premium-only (packing, capsule, shop, missing, health, compatibility, dressme).

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
        "premium": is_premium(account),
    }


def is_premium(account: dict) -> bool:
    """Whole-household premium — driven by the account's premium_until timestamp."""
    pu = (account or {}).get("premium_until")
    if not pu:
        return False
    try:
        dt = datetime.fromisoformat(pu)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > now_utc()
    except Exception:
        return False


PREMIUM_MESSAGES = {
    "stylist": "You've used your 5 free AI outfits today. Go Premium for unlimited styling.",
    "beauty": "Colour analysis is 1/month on Free. Go Premium for unlimited analyses.",
    "packing": "The Packing Assistant is a Premium feature.",
    "capsule": "Capsule wardrobes are a Premium feature.",
    "shop": "Shopping Intelligence is a Premium feature.",
    "missing": "The Missing Piece analysis is a Premium feature.",
    "health": "The Wardrobe Health Report is a Premium feature.",
    "compatibility": "Wardrobe compatibility is a Premium feature.",
    "dressme": "Dress Me is a Premium feature.",
    "tryon": "Virtual Try-On is a Premium feature.",
    "household": "Household wardrobes are a Premium feature — one subscription covers everyone.",
}


async def enforce_limit(scope: dict, feature: str):
    """Gate a feature for free accounts. Metered features count usage per period;
    all others are Premium-only. Premium accounts always pass."""
    if scope.get("premium"):
        return
    cfg = FREE_LIMITS.get(feature)
    msg = PREMIUM_MESSAGES.get(feature, "This is a Premium feature.")
    if cfg is None:
        raise HTTPException(status_code=402, detail=msg)
    now = now_utc()
    key = now.strftime("%Y-%m-%d") if cfg["period"] == "day" else now.strftime("%Y-%m")
    doc = await db.usage.find_one(
        {"account_id": scope["account_id"], "feature": feature, "period": key}, {"_id": 0}
    )
    used = doc["count"] if doc else 0
    if used >= cfg["max"]:
        raise HTTPException(status_code=402, detail=msg)
    await db.usage.update_one(
        {"account_id": scope["account_id"], "feature": feature, "period": key},
        {"$inc": {"count": 1}}, upsert=True,
    )


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
    prem = is_premium(user)
    return {
        **user,
        "premium": prem,
        "premium_until": user.get("premium_until"),
        "premium_source": user.get("premium_source"),
        "trial_used": bool(user.get("trial_used")),
        "trial_eligible": (not prem) and (not user.get("trial_used")),
    }


@api_router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}


# ----------------------------- Membership / Payments -----------------------------
class CheckoutRequest(BaseModel):
    plan: str          # "monthly" | "annual"
    origin_url: str    # web origin the app is served from (for return URLs)


@api_router.get("/membership/plans")
async def membership_plans(user: dict = Depends(get_current_user)):
    prem = is_premium(user)
    return {
        "premium": prem,
        "premium_until": user.get("premium_until"),
        "premium_source": user.get("premium_source"),
        "trial_used": bool(user.get("trial_used")),
        "trial_eligible": (not prem) and (not user.get("trial_used")),
        "trial_days": 7,
        "plans": [
            {"id": k, "amount": v["amount"], "days": v["days"], "label": v["label"], "currency": "usd"}
            for k, v in PREMIUM_PLANS.items()
        ],
    }


@api_router.post("/membership/trial")
async def start_trial(account: dict = Depends(get_current_user)):
    """App-managed 7-day free trial — instant Premium, no card, once per account."""
    if account.get("trial_used"):
        raise HTTPException(status_code=400, detail="You've already used your free trial.")
    if is_premium(account):
        raise HTTPException(status_code=400, detail="You're already on Premium.")
    until = (now_utc() + timedelta(days=7)).isoformat()
    await db.users.update_one(
        {"user_id": account["user_id"]},
        {"$set": {"premium_until": until, "premium_source": "trial", "trial_used": True}},
    )
    return {"premium": True, "premium_until": until, "premium_source": "trial", "trial_used": True}


@api_router.post("/payments/checkout")
async def create_checkout(payload: CheckoutRequest, account: dict = Depends(get_current_user)):
    plan = PREMIUM_PLANS.get(payload.plan)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid plan")
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="Payments not configured")
    host = payload.origin_url.rstrip("/")
    success_url = f"{host}/premium-success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{host}/premium"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY)
    req = CheckoutSessionRequest(
        amount=float(plan["amount"]),
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"account_id": account["user_id"], "plan": payload.plan, "kind": "premium"},
    )
    try:
        session = await stripe_checkout.create_checkout_session(req)
    except Exception as e:
        logger.exception("checkout create failed")
        raise HTTPException(status_code=502, detail=f"Payment error: {e}")
    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "account_id": account["user_id"],
        "plan": payload.plan,
        "amount": plan["amount"],
        "currency": "usd",
        "payment_status": "initiated",
        "status": "open",
        "processed": False,
        "created_at": now_utc().isoformat(),
    })
    return {"url": session.url, "session_id": session.session_id}


async def _grant_premium(account_id: str, plan_key: str):
    """Idempotently extend an account's premium entitlement by the plan's period."""
    plan = PREMIUM_PLANS.get(plan_key) or PREMIUM_PLANS["monthly"]
    acct = await db.users.find_one({"user_id": account_id}, {"_id": 0})
    base = now_utc()
    cur = (acct or {}).get("premium_until")
    if cur:
        try:
            curdt = datetime.fromisoformat(cur)
            if curdt.tzinfo is None:
                curdt = curdt.replace(tzinfo=timezone.utc)
            if curdt > base:
                base = curdt
        except Exception:
            pass
    until = base + timedelta(days=plan["days"])
    await db.users.update_one({"user_id": account_id}, {"$set": {"premium_until": until.isoformat(), "premium_source": "paid"}})
    return until.isoformat()


@api_router.get("/payments/status/{session_id}")
async def payment_status_check(session_id: str, account: dict = Depends(get_current_user)):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Unknown session")
    if tx["account_id"] != account["user_id"]:
        raise HTTPException(status_code=403, detail="Not your session")
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY)
    try:
        st = await stripe_checkout.get_checkout_status(session_id)
    except Exception as e:
        logger.exception("checkout status failed")
        raise HTTPException(status_code=502, detail=f"Payment error: {e}")
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"payment_status": st.payment_status, "status": st.status}},
    )
    # Grant entitlement exactly once when paid.
    if st.payment_status == "paid" and not tx.get("processed"):
        await _grant_premium(tx["account_id"], tx["plan"])
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"processed": True, "processed_at": now_utc().isoformat()}},
        )
    acct = await db.users.find_one({"user_id": tx["account_id"]}, {"_id": 0})
    return {
        "payment_status": st.payment_status,
        "status": st.status,
        "premium": is_premium(acct),
        "premium_until": acct.get("premium_until"),
    }


class ProfileUpdate(BaseModel):
    measurements: Optional[dict] = None
    body_shape: Optional[str] = None
    skin_tone: Optional[str] = None
    undertone: Optional[str] = None
    height: Optional[str] = None
    sizes: Optional[str] = None
    fit_pref: Optional[str] = None
    sizes_top: Optional[str] = None
    sizes_bottom: Optional[str] = None
    style_prefs: Optional[list] = None
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
    count = await db.profiles.count_documents({"user_id": account["user_id"]})
    if not is_premium(account) and count >= 1:
        raise HTTPException(status_code=402, detail=PREMIUM_MESSAGES["household"])
    if count >= 6:
        raise HTTPException(status_code=400, detail="A household can have up to 6 members.")
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
    await db.body_photos.delete_one({"profile_id": profile_id})
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

    @field_validator("price", mode="before")
    @classmethod
    def _empty_price_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


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

    @field_validator("price", mode="before")
    @classmethod
    def _empty_price_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


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
    source: Optional[str] = "manual"  # manual | ai | tryon | capsule
    preview_image: Optional[str] = None  # base64 (e.g. a saved virtual try-on render)


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


def compress_b64(b64: Optional[str], max_side: int = 1024, quality: int = 72) -> Optional[str]:
    """Normalise any base64 image to a bounded JPEG so it stores/renders reliably.
    Oversized/uncompressed images (e.g. AI-generated clean photos) can render blank on device."""
    if not b64:
        return b64
    try:
        raw = _b64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        if img.mode not in ("RGB",):
            img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return _b64.b64encode(out.getvalue()).decode()
    except Exception:
        return b64


@api_router.post("/items")
async def create_item(payload: ItemCreate, user: dict = Depends(get_scope)):
    item = payload.dict()
    item["photo"] = compress_b64(item.get("photo"))
    item["worn_photo"] = compress_b64(item.get("worn_photo"))
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
    if "photo" in updates:
        updates["photo"] = compress_b64(updates["photo"])
    if "worn_photo" in updates:
        updates["worn_photo"] = compress_b64(updates["worn_photo"])
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


async def _analyze_core(image_b64: str, category_hint: Optional[str], scope_id: str) -> dict:
    chat = await ai_chat(f"analyze-{scope_id}-{uuid.uuid4().hex[:6]}", ANALYZE_SYSTEM)
    if category_hint:
        text = (
            f"The person in the photo may be wearing several garments. Focus ONLY on the "
            f"{category_hint} and catalogue that single item, ignoring everything else "
            f"they are wearing. Set the category to '{category_hint}'. Return JSON only."
        )
    else:
        text = "Catalogue this clothing item. Return JSON only."
    resp = await chat.send_message(UserMessage(text=text, file_contents=[ImageContent(image_base64=image_b64)]))
    return parse_json_block(resp) or {}


async def _clean_photo(image_b64: str) -> Optional[str]:
    """Background-removed, catalogue-style version of a garment photo (best-effort)."""
    instruction = (
        "Isolate the single main clothing item in this photo and remove the background. Return the SAME "
        "garment with its shape, colour, pattern, texture and details completely unchanged — do NOT restyle "
        "or redesign it. Place it centred on a clean, seamless, light neutral (#F1EFEA) studio background, "
        "flat product-catalogue style. Output only the image."
    )
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"clean-{uuid.uuid4().hex[:8]}",
        system_message="You are a product-photo background remover for a clothing catalogue.",
    ).with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
    _text, images = await chat.send_message_multimodal_response(
        UserMessage(text=instruction, file_contents=[ImageContent(image_b64)])
    )
    return compress_b64(images[0]["data"]) if images else None


@api_router.post("/analyze-item")
async def analyze_item(payload: AnalyzeRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    try:
        result = await _analyze_core(payload.image, payload.category_hint, user["user_id"])
    except Exception as e:
        logger.exception("analyze-item failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    if not result:
        raise HTTPException(status_code=502, detail="Could not analyze image")
    return result


class CaptureRequest(BaseModel):
    image: str
    category_hint: Optional[str] = None
    clean: bool = True


def _norm(v) -> str:
    return str(v or "").strip().lower()


def find_similar_items(analysis: dict, items: List[dict], limit: int = 3) -> List[dict]:
    """Flag pieces in the wardrobe that look like the one just captured, so users
    don't unknowingly re-add something they already own. Category must match; colour,
    style, fabric and pattern add to a confidence score."""
    cat = _norm(analysis.get("category"))
    if not cat:
        return []
    colour, style = _norm(analysis.get("colour")), _norm(analysis.get("style"))
    fabric, pattern = _norm(analysis.get("fabric")), _norm(analysis.get("pattern"))
    scored = []
    for it in items:
        if _norm(it.get("category")) != cat:
            continue
        score = 0
        if colour and _norm(it.get("colour")) == colour:
            score += 2
        if style and _norm(it.get("style")) == style:
            score += 2
        if fabric and _norm(it.get("fabric")) == fabric:
            score += 1
        if pattern and _norm(it.get("pattern")) == pattern:
            score += 1
        if score >= 3:
            scored.append((score, it))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [
        {
            "id": it["id"],
            "name": it.get("name", ""),
            "category": it.get("category", ""),
            "colour": it.get("colour", ""),
            "photo": it.get("photo"),
        }
        for _, it in scored[:limit]
    ]


@api_router.post("/capture")
async def capture_item(payload: CaptureRequest, user: dict = Depends(get_scope)):
    """One-shot capture: auto-tag the garment AND clean its background in parallel,
    so adding a piece needs near-zero manual work."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    tasks = [_analyze_core(payload.image, payload.category_hint, user["user_id"])]
    if payload.clean:
        tasks.append(_clean_photo(payload.image))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    analysis = results[0]
    if isinstance(analysis, Exception) or not analysis:
        logger.warning("capture analyze failed: %s", analysis)
        analysis = {}
    clean_img = None
    if payload.clean and len(results) > 1:
        cr = results[1]
        if isinstance(cr, Exception):
            logger.warning("capture clean failed: %s", cr)
        else:
            clean_img = cr
    duplicates = []
    if analysis:
        existing = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
        duplicates = find_similar_items(analysis, existing)
    return {"analysis": analysis, "clean_image": clean_img, "duplicates": duplicates}


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
    for key in ["height", "fit_pref", "sizes_top", "sizes_bottom", "sizes", "body_shape", "skin_tone", "undertone", "notes"]:
        if p.get(key):
            parts.append(f"{key.replace('_', ' ')}: {p[key]}")
    prefs = p.get("style_prefs")
    if prefs:
        prefs_str = ", ".join(prefs) if isinstance(prefs, list) else str(prefs)
        parts.append(f"style preferences: {prefs_str}")
    if not parts:
        return "No body profile provided — style with general best practices."
    return (
        "Body profile — " + "; ".join(parts) +
        ". Choose cuts, lengths, proportions and colours that flatter this body shape and skin tone, "
        "respect their fit preference and sizes, and lean into their stated style preferences."
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
    "You are Aureve, an expert personal stylist who thinks about balance, proportion, layering, contrast, colour "
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
    await enforce_limit(user, "stylist")
    return await _build_outfit(user, payload.occasion, payload.temperature, payload.weather, payload.notes)


STYLIST_CHAT_SYSTEM = (
    "You are Aureve, a warm, expert personal stylist chatting with the user about their own wardrobe. "
    "Reply conversationally and concisely — like a knowledgeable, encouraging friend, never robotic or list-heavy "
    "unless the user asks for options. You may ONLY reference items that exist in the user's wardrobe (by exact id). "
    "Never invent items. Consider occasion, weather, colour, proportion and what flatters them. "
    "When (and only when) you are recommending a specific complete outfit to wear, append at the very END of your "
    "message a fenced JSON block exactly like ```json{\"outfit\": {\"name\": \"<short name>\", \"item_ids\": [\"<id>\", \"<id>\"]}}``` "
    "using real ids from the wardrobe. Keep the conversational text natural and free of raw ids or JSON."
)


class StylistChatMessage(BaseModel):
    role: str
    content: str


class StylistChatRequest(BaseModel):
    messages: List[StylistChatMessage]
    temperature: Optional[float] = None
    weather: Optional[str] = None


@api_router.post("/stylist/chat")
async def stylist_chat(payload: StylistChatRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "stylist")
    all_items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    items = available_items(all_items)
    wardrobe = summarize_items_for_ai(items) if items else "No items yet."
    weather_line = ""
    if payload.temperature is not None:
        weather_line = f"Current weather: {payload.temperature}°C, {payload.weather or 'n/a'}.\n"
    convo = "\n".join(f"{m.role.upper()}: {m.content}" for m in payload.messages[-12:])
    prompt = (
        f"{profile_context(user)}\n{weather_line}"
        f"WARDROBE (use only these ids):\n{wardrobe}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        "Reply as Aureve to the user's most recent message."
    )
    chat = await ai_chat(f"stylistchat-{user['user_id']}-{uuid.uuid4().hex[:6]}", STYLIST_CHAT_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("stylist chat failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    outfit = None
    reply = resp or ""
    block = parse_json_block(resp)
    if block and isinstance(block.get("outfit"), dict):
        o = block["outfit"]
        by_id = {it["id"]: it for it in items}
        resolved = [by_id[i] for i in o.get("item_ids", []) if i in by_id]
        if resolved:
            outfit = {"name": o.get("name", "Outfit"), "item_ids": [r["id"] for r in resolved], "items": resolved}
        reply = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", resp, flags=re.DOTALL).strip()
    if not reply:
        reply = "Here's what I'd suggest from your wardrobe."
    return {"reply": reply, "outfit": outfit}


async def _build_outfit(user: dict, occasion: str, temperature: Optional[float],
                        weather: Optional[str], notes: Optional[str]):
    items = await db.items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    items = available_items(items)
    if len(items) < 2:
        raise HTTPException(status_code=400, detail="Not enough ready-to-wear items. Add more, or mark laundry as clean.")
    prefs = await learned_prefs(user["user_id"])
    wardrobe = summarize_items_for_ai(items)
    weather_line = ""
    if temperature is not None:
        weather_line = f"Temperature: {temperature}°C. Conditions: {weather or 'n/a'}."
    prompt = (
        f"Occasion: {occasion}\n{weather_line}\n"
        f"Extra notes: {notes or 'none'}\n"
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
    by_id = {it["id"]: it for it in items}
    enriched = []
    for slot in result.get("items", []):
        it = by_id.get(slot.get("item_id"))
        if it:
            enriched.append({"slot": slot.get("slot", it.get("category")), "reason": slot.get("reason", ""), "item": it})
    result["resolved_items"] = enriched
    return result


class DressMeRequest(BaseModel):
    temperature: Optional[float] = None
    weather: Optional[str] = None
    occasion: Optional[str] = None  # override; otherwise inferred from today's plan


@api_router.post("/dressme")
async def dress_me(payload: DressMeRequest, user: dict = Depends(get_scope)):
    """Flagship one-tap daily outfit — infers today's occasion from the planner
    (falls back to a normal day) and styles from the ready wardrobe + weather."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "dressme")
    today = now_utc().strftime("%Y-%m-%d")
    occasion = (payload.occasion or "").strip()
    plan_title = None
    cal_events = await _gcal_events(user["account_id"], today)
    if not occasion:
        plan = await db.plans.find_one({"user_id": user["user_id"], "date": today}, {"_id": 0})
        if plan:
            occasion = (plan.get("occasion") or plan.get("title") or "").strip()
            plan_title = plan.get("title") or plan.get("occasion")
    cal_line = _fmt_events_for_ai(cal_events) if cal_events else ""
    if not occasion:
        occasion = f"today's schedule — {cal_line}" if cal_line else "a normal day — versatile, put-together, easy to wear"
    notes = "Dress me for today — one confident, ready-to-wear look."
    if cal_line:
        notes += f" My schedule today: {cal_line}. Pick something that works across these."
    result = await _build_outfit(user, occasion, payload.temperature, payload.weather, notes)
    result["occasion_used"] = occasion
    result["from_plan"] = plan_title
    result["calendar_events"] = cal_events
    return result


# ----------------------------- AI: Virtual Try-On (Nano Banana) -----------------------------
class TryOnRequest(BaseModel):
    person_image: str            # base64 (no data-uri prefix) of the user
    item_ids: List[str] = []     # garments to render onto the person
    outfit_id: Optional[str] = None


@api_router.post("/tryon")
async def virtual_tryon(payload: TryOnRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "tryon")
    if not payload.person_image:
        raise HTTPException(status_code=400, detail="A photo of you is required.")
    item_ids = list(payload.item_ids)
    if payload.outfit_id and not item_ids:
        outfit = await db.outfits.find_one({"id": payload.outfit_id, "user_id": user["user_id"]}, {"_id": 0})
        if outfit:
            item_ids = outfit.get("item_ids", [])
    if not item_ids:
        raise HTTPException(status_code=400, detail="Pick at least one item to try on.")
    items = await db.items.find(
        {"id": {"$in": item_ids}, "user_id": user["user_id"]}, {"_id": 0}
    ).to_list(20)
    garments = [it for it in items if it.get("photo")][:5]
    if not garments:
        raise HTTPException(status_code=400, detail="Those items don't have photos to try on.")

    contents = [ImageContent(payload.person_image)]
    labels = []
    for it in garments:
        contents.append(ImageContent(it["photo"]))
        labels.append(f"- {it.get('name', 'item')} ({it.get('category', '')}, {it.get('colour', '')})")
    instruction = (
        "This is a virtual try-on. The FIRST image is a photo of a person. Each following image is one "
        "clothing item they own:\n" + "\n".join(labels) + "\n\n"
        "Generate ONE photorealistic image of the SAME person — keep their face, skin tone, hair and body "
        "shape identical — now wearing ALL of these garments together as a single coherent, well-fitted "
        "outfit. Natural pose, clean neutral studio-style background, flattering full-body framing, realistic "
        "fabric drape and lighting. Do not change the person's identity."
    )
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"tryon-{user['user_id']}-{uuid.uuid4().hex[:6]}",
        system_message="You are a photorealistic virtual try-on image generator.",
    ).with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
    try:
        _text, images = await chat.send_message_multimodal_response(
            UserMessage(text=instruction, file_contents=contents)
        )
    except Exception as e:
        logger.exception("tryon failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    if not images:
        raise HTTPException(status_code=502, detail="Couldn't generate a try-on image. Try a clearer full-body photo.")
    return {"image": images[0]["data"], "mime_type": images[0].get("mime_type", "image/png")}


class BodyPhoto(BaseModel):
    photo: str  # base64 (no data-uri prefix)


@api_router.get("/tryon/photo")
async def get_body_photo(user: dict = Depends(get_scope)):
    """The remembered full-body photo for the active profile (so try-on doesn't re-upload)."""
    doc = await db.body_photos.find_one({"profile_id": user["profile_id"]}, {"_id": 0})
    return {"photo": (doc or {}).get("photo")}


@api_router.put("/tryon/photo")
async def set_body_photo(payload: BodyPhoto, user: dict = Depends(get_scope)):
    await db.body_photos.update_one(
        {"profile_id": user["profile_id"]},
        {"$set": {"profile_id": user["profile_id"], "photo": payload.photo, "updated_at": now_utc().isoformat()}},
        upsert=True,
    )
    return {"ok": True}


@api_router.delete("/tryon/photo")
async def delete_body_photo(user: dict = Depends(get_scope)):
    await db.body_photos.delete_one({"profile_id": user["profile_id"]})
    return {"ok": True}


# ----------------------------- Google Calendar (read-only) -----------------------------
import urllib.parse as _urlparse


async def _gcal_valid_token(account_id: str) -> Optional[str]:
    """Return a valid access token for the account, refreshing if needed. None if not connected."""
    doc = await db.calendar_tokens.find_one({"account_id": account_id}, {"_id": 0})
    if not doc:
        return None
    exp = doc.get("expiry")
    still_valid = False
    if exp:
        try:
            still_valid = datetime.fromisoformat(exp) > now_utc() + timedelta(seconds=60)
        except Exception:
            still_valid = False
    if still_valid and doc.get("access_token"):
        return doc["access_token"]
    refresh = doc.get("refresh_token")
    if not refresh:
        return doc.get("access_token")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": GCAL_CLIENT_ID,
            "client_secret": GCAL_CLIENT_SECRET,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        })
    if r.status_code != 200:
        return None
    tok = r.json()
    new_exp = (now_utc() + timedelta(seconds=tok.get("expires_in", 3600))).isoformat()
    await db.calendar_tokens.update_one(
        {"account_id": account_id},
        {"$set": {"access_token": tok["access_token"], "expiry": new_exp}},
    )
    return tok["access_token"]


async def _gcal_events(account_id: str, date_str: str) -> List[dict]:
    token = await _gcal_valid_token(account_id)
    if not token:
        return []
    try:
        day = datetime.fromisoformat(date_str)
    except Exception:
        day = now_utc()
    start = day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    params = {
        "timeMin": start.isoformat(), "timeMax": end.isoformat(),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": "20",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            params=params, headers={"Authorization": f"Bearer {token}"},
        )
    if r.status_code != 200:
        return []
    out = []
    for ev in r.json().get("items", []):
        start_obj = ev.get("start", {})
        out.append({
            "summary": ev.get("summary", "Busy"),
            "start": start_obj.get("dateTime") or start_obj.get("date"),
            "all_day": "date" in start_obj and "dateTime" not in start_obj,
            "location": ev.get("location"),
        })
    return out


def _fmt_events_for_ai(events: List[dict]) -> str:
    lines = []
    for e in events:
        t = ""
        if e.get("start") and not e.get("all_day"):
            try:
                t = datetime.fromisoformat(e["start"].replace("Z", "+00:00")).strftime("%H:%M") + " "
            except Exception:
                t = ""
        loc = f" @ {e['location']}" if e.get("location") else ""
        lines.append(f"{t}{e['summary']}{loc}")
    return "; ".join(lines)


@api_router.get("/calendar/status")
async def calendar_status(account: dict = Depends(get_current_user)):
    doc = await db.calendar_tokens.find_one({"account_id": account["user_id"]}, {"_id": 0})
    return {"connected": bool(doc), "configured": bool(GCAL_CLIENT_ID)}


@api_router.get("/calendar/authorize")
async def calendar_authorize(account: dict = Depends(get_current_user)):
    if not GCAL_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Calendar is not configured.")
    state = uuid.uuid4().hex
    await db.calendar_oauth_states.update_one(
        {"state": state},
        {"$set": {"state": state, "account_id": account["user_id"], "created_at": now_utc().isoformat()}},
        upsert=True,
    )
    params = {
        "client_id": GCAL_CLIENT_ID,
        "redirect_uri": GCAL_REDIRECT_URI,
        "response_type": "code",
        "scope": GCAL_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + _urlparse.urlencode(params)
    return {"url": url}


@app.get("/api/calendar/callback")
async def calendar_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    def _page(msg: str) -> HTMLResponse:
        return HTMLResponse(
            f"<html><body style='font-family:-apple-system,sans-serif;background:#232323;color:#FAF9F6;"
            f"display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center'>"
            f"<div><h2 style='font-weight:600'>{msg}</h2>"
            f"<p style='color:#DCE5DF'>You can close this window and return to Aureve.</p></div>"
            f"<script>setTimeout(function(){{window.close()}},1500)</script></body></html>"
        )
    if error or not code or not state:
        return _page("Calendar connection cancelled")
    st = await db.calendar_oauth_states.find_one({"state": state})
    if not st:
        return _page("Link expired — please try again")
    account_id = st["account_id"]
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GCAL_CLIENT_ID,
            "client_secret": GCAL_CLIENT_SECRET,
            "redirect_uri": GCAL_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
    await db.calendar_oauth_states.delete_one({"state": state})
    if r.status_code != 200:
        logger.error("gcal token exchange failed: %s", r.text[:200])
        return _page("Couldn't connect calendar")
    tok = r.json()
    expiry = (now_utc() + timedelta(seconds=tok.get("expires_in", 3600))).isoformat()
    update = {"account_id": account_id, "access_token": tok.get("access_token"), "expiry": expiry}
    if tok.get("refresh_token"):
        update["refresh_token"] = tok["refresh_token"]
    await db.calendar_tokens.update_one({"account_id": account_id}, {"$set": update}, upsert=True)
    return _page("Calendar connected ✓")


@api_router.get("/calendar/events")
async def calendar_events(date: Optional[str] = None, account: dict = Depends(get_current_user)):
    d = date or now_utc().strftime("%Y-%m-%d")
    return {"events": await _gcal_events(account["user_id"], d)}


@api_router.delete("/calendar/disconnect")
async def calendar_disconnect(account: dict = Depends(get_current_user)):
    await db.calendar_tokens.delete_one({"account_id": account["user_id"]})
    return {"ok": True}


# ----------------------------- AI: Compatibility / Wardrobe Intelligence -----------------------------
COMPAT_SYSTEM = (
    "You are Aureve's compatibility engine. Given ONE focus item and the rest of the user's wardrobe, rate how "
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
    await enforce_limit(user, "compatibility")
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
    "You are Aureve's shopping-restraint advisor. The user is considering buying the item in the photo. "
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
    await enforce_limit(user, "shop")
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
    "You are Aureve's brutally honest wardrobe-gap analyst. Given the user's full wardrobe, identify the ONE "
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
    await enforce_limit(user, "missing")
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
    "You are Aureve's packing assistant. Build a smart CAPSULE wardrobe for a trip using ONLY the items in the "
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
    await enforce_limit(user, "packing")
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
    "You are Aureve's capsule wardrobe builder. Given a theme (a season or a purpose like Work or Weekend) and the "
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
    await enforce_limit(user, "capsule")
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
    "You are Aureve's wardrobe health analyst. You are given wardrobe stats and the raw numbers. Write an honest, "
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
    await enforce_limit(user, "health")
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
    "You are Aureve's professional colour analyst and beauty stylist. Using the person's skin tone, undertone and "
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
    await enforce_limit(user, "beauty")
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
    return {"message": "Aureve API"}


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
