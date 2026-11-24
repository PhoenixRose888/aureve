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
import secrets
import base64 as _b64
from PIL import Image
import httpx
import bcrypt
import jwt
import hmac
import hashlib
import time as _time
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

# Dedicated App Store review account — the only signed-in account allowed to
# keep the seeded demo wardrobe.
REVIEWER_EMAIL = (os.environ.get('REVIEWER_EMAIL', 'review@aureve.app') or '').strip().lower()

# Sign in with Apple — audiences must include the app bundle id AND
# host.exp.Exponent (Expo Go). Configured via backend .env.
APPLE_AUDIENCES = [a.strip() for a in os.environ.get('APPLE_AUDIENCES', '').split(',') if a.strip()]
_APPLE_JWK_CLIENT = None

# .strip() so a stray space/newline in the deployed env can't break the token
# exchange (Google returns invalid_client for a padded id/secret).
GCAL_CLIENT_ID = os.environ.get('GOOGLE_CALENDAR_CLIENT_ID', '').strip().strip('"').strip("'")
GCAL_CLIENT_SECRET = os.environ.get('GOOGLE_CALENDAR_CLIENT_SECRET', '').strip().strip('"').strip("'")
GCAL_REDIRECT_URI = os.environ.get('GOOGLE_CALENDAR_REDIRECT_URI', '').strip()
# Last callback failure (reason only, never a secret) for the read-only diagnostic.
GCAL_LAST_ERROR: dict = {}
GCAL_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

# Premium membership — one-time payment grants a time-boxed entitlement (whole household).
PREMIUM_PLANS = {
    "monthly": {"amount": 9.99, "days": 30, "label": "Premium Monthly"},
    "annual": {"amount": 79.99, "days": 365, "label": "Premium Annual"},
}
# Free tier: unlimited wardrobe + a taste of AI. Metered features:
FREE_LIMITS = {
    # Free is genuinely useful: a monthly allowance of the AI features plus a
    # 100-piece active wardrobe. Premium removes every cap.
    "stylist": {"period": "month", "max": 5},
    "beauty": {"period": "month", "max": 1},
    "dressme": {"period": "month", "max": 5},
}
# Free wardrobes hold up to this many ACTIVE pieces (deleting frees slots).
FREE_ITEM_CAP = 100
# Everything not in FREE_LIMITS is Premium-only (packing, capsule, shop, missing, health, compatibility).

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def free_trial_enabled() -> bool:
    return os.environ.get("FREE_TRIAL_ENABLED", "").lower() in ("1", "true", "yes")


# ----------------------------- Helpers -----------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# Features still in development. Their code stays in the repo, but the routes
# answer 404 — exactly like an unknown path — so nothing is reachable from a
# shipped build, a deep link or a crafted request. Remove a name from this set
# when the feature is ready to ship.
UNRELEASED_FEATURES = {"packing", "capsule", "tryon", "planner"}


def unreleased(feature: str):
    async def gate():
        if feature in UNRELEASED_FEATURES:
            raise HTTPException(status_code=404, detail="Not Found")
    return gate



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
    for coll in (db.items, db.outfits, db.wear_logs, db.plans, db.stylist_threads):
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
    # The subscription belongs to the account and its PRIMARY (first) wardrobe.
    # Family wardrobes are managed profiles: full wardrobe management, but they
    # are not independent Premium seats.
    primary = await db.profiles.find(
        {"user_id": account_id}, {"_id": 0, "id": 1}
    ).sort("created_at", 1).to_list(1)
    is_primary = bool(primary) and primary[0]["id"] == prof["id"]
    account_premium = is_premium(account)

    is_guest = bool(account.get("is_guest"))
    is_reviewer = _norm_email(account.get("email") or "") == REVIEWER_EMAIL
    show_demo = is_guest
    if is_reviewer and not is_guest:
        real_item_count = await db.items.count_documents({
            "user_id": prof["id"],
            "demo": {"$ne": True},
        })
        show_demo = real_item_count == 0

    return {
        "user_id": prof["id"],       # data scope = profile id
        "account_id": account_id,
        "profile_id": prof["id"],
        "profile_name": prof.get("name"),
        "profile": prof.get("profile") or {},
        "is_primary": is_primary,
        "account_premium": account_premium,
        "premium": account_premium and is_primary,
        "show_demo": show_demo,
    }


def items_scope(user: dict) -> dict:
    """Mongo filter for a scope's wardrobe. Real signed-in accounts never see
    auto-seeded demo pieces (the records are kept, just excluded everywhere)."""
    q = {"user_id": user["user_id"]}
    if not user.get("show_demo"):
        q["demo"] = {"$ne": True}
    return q


def is_premium(account: dict) -> bool:
    """Whole-household premium — driven by the account's premium_until timestamp.
    When TRIAL_UNLOCK_ALL is enabled, every account is treated as Premium so
    friends & family can trial all features (used for shared preview builds)."""
    if os.environ.get("TRIAL_UNLOCK_ALL", "").lower() in ("1", "true", "yes"):
        return True
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


WELCOME_TRIAL_DAYS = 7


async def grant_welcome_premium(user_id: str) -> dict:
    """Give a brand-new account 7 complimentary Premium days.

    App-managed only: it never touches RevenueCat, never creates a
    subscription, never charges and never auto-renews. The start/expiry
    timestamps are stored on the account, and ``complimentary_used`` makes it
    once-per-account — so reinstalling, signing out and back in, or using
    another device can never restart it.
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return {}
    # Already had it (or already has paid Premium) — never regrant or restart.
    if user.get("complimentary_used") or user.get("trial_used") or user.get("premium_until"):
        return user
    started = now_utc()
    expires = started + timedelta(days=WELCOME_TRIAL_DAYS)
    fields = {
        "complimentary_started_at": started.isoformat(),
        "complimentary_expires_at": expires.isoformat(),
        "complimentary_used": True,
        "trial_used": True,          # blocks the old opt-in trial as well
        "premium_until": expires.isoformat(),
        "premium_source": "complimentary",
    }
    await db.users.update_one({"user_id": user_id}, {"$set": fields})
    logger.info(f"Complimentary Premium granted to {user_id} until {expires.isoformat()}")
    return {**user, **fields}


def premium_plan_label(account: dict) -> Optional[str]:
    """Monthly / Annual, read from the RevenueCat product the member bought."""
    if (account or {}).get("premium_source") != "revenuecat":
        return None
    pid = str((account or {}).get("revenuecat_product") or "").lower()
    if any(k in pid for k in ("annual", "year", "yearly", "12m")):
        return "Annual"
    if "month" in pid:
        return "Monthly"
    return "Premium"


def complimentary_state(account: dict) -> dict:
    """Days left on the complimentary period, for the subtle in-app notice."""
    exp = (account or {}).get("complimentary_expires_at")
    if not exp:
        return {"complimentary_active": False, "complimentary_days_left": 0,
                "complimentary_expires_at": None}
    try:
        dt = datetime.fromisoformat(exp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        return {"complimentary_active": False, "complimentary_days_left": 0,
                "complimentary_expires_at": None}
    remaining = dt - now_utc()
    active = remaining.total_seconds() > 0 and (account or {}).get("premium_source") == "complimentary"
    # Part-days round up, so day one reads "7 days remaining".
    days_left = max(0, -(-int(remaining.total_seconds()) // 86400)) if remaining.total_seconds() > 0 else 0
    return {
        "complimentary_active": active,
        "complimentary_days_left": days_left if active else 0,
        "complimentary_expires_at": exp,
    }


PREMIUM_MESSAGES = {
    "stylist": "You've used your 5 free AI stylist sessions this month. Go Premium for unlimited styling.",
    "beauty": "Hair styling is 1/month on Free. Go Premium for unlimited hair recommendations.",
    "packing": "The Packing Assistant is a Premium feature.",
    "capsule": "Capsule wardrobes are a Premium feature.",
    "shop": "Shopping Intelligence is a Premium feature.",
    "missing": "Shopping Intelligence is a Premium feature.",
    "health": "The Wardrobe Health Report is a Premium feature.",
    "compatibility": "Wardrobe compatibility is a Premium feature.",
    "dressme": "You've used your 5 free Dress Me looks this month. Go Premium for unlimited.",
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
    if scope.get("account_premium") and not scope.get("is_primary"):
        msg = ("Premium features run on your main wardrobe. Switch back to it to use this — "
               "family wardrobes keep full wardrobe management.")
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
    guest_token: Optional[str] = None   # optional guest session to migrate on sign-in


async def migrate_guest_data(guest_token: str, account_id: str):
    """Move a guest session's wardrobe into the real account, then retire the
    guest. Data is scoped per-profile, so reassigning the guest's profiles to
    the new account brings all items/outfits/logs along for free."""
    guest_session = await db.user_sessions.find_one({"session_token": guest_token}, {"_id": 0})
    if not guest_session:
        return
    guest_id = guest_session["user_id"]
    if guest_id == account_id:
        return
    guest_user = await db.users.find_one({"user_id": guest_id}, {"_id": 0})
    if not guest_user or not guest_user.get("is_guest"):
        return
    # Purge the auto-seeded demo wardrobe so it never clutters a real account
    # (only the guest's own added items are kept).
    guest_profiles = await db.profiles.find({"user_id": guest_id}, {"_id": 0, "id": 1}).to_list(100)
    prof_ids = [p["id"] for p in guest_profiles]
    if prof_ids:
        await db.items.delete_many({"user_id": {"$in": prof_ids}, "demo": True})
    # Reassign the guest's profiles (and any account-scoped usage) to the account.
    await db.profiles.update_many({"user_id": guest_id}, {"$set": {"user_id": account_id}})
    await db.usage.update_many({"account_id": guest_id}, {"$set": {"account_id": account_id}})
    # Carry over any entitlement the guest earned (e.g. an active trial), but
    # never downgrade an account that already has premium.
    account = await db.users.find_one({"user_id": account_id}, {"_id": 0})
    if guest_user.get("premium_until") and not is_premium(account or {}):
        await db.users.update_one({"user_id": account_id}, {"$set": {
            "premium_until": guest_user.get("premium_until"),
            "premium_source": guest_user.get("premium_source"),
            "trial_used": bool(guest_user.get("trial_used")),
        }})
    # Retire the guest user + all its sessions.
    await db.users.delete_one({"user_id": guest_id})
    await db.user_sessions.delete_many({"user_id": guest_id})


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
        await grant_welcome_premium(user_id)

    # Migrate any guest wardrobe into this account before returning.
    if payload.guest_token:
        try:
            await migrate_guest_data(payload.guest_token, user_id)
        except Exception as e:
            logger.warning(f"Guest migration skipped: {e}")

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


class EmailAuthRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
    guest_token: Optional[str] = None  # optional guest session to migrate


def _norm_email(e: str) -> str:
    return (e or "").strip().lower()


async def _mint_session(user_id: str) -> str:
    session_token = "sess_" + secrets.token_urlsafe(32)
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
    return session_token


@api_router.post("/auth/register")
async def register_email(payload: EmailAuthRequest):
    """Create an account with email + password (bcrypt-hashed) and return a
    bearer session — an alternative to Google sign-in."""
    email = _norm_email(payload.email)
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    if len(payload.password or "") < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="An account with this email already exists. Try signing in.")
    user_id = new_id("user")
    pw_hash = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt(rounds=12)).decode()
    await db.users.insert_one({
        "user_id": user_id,
        "email": email,
        "name": (payload.name or email.split("@")[0]).strip(),
        "provider": "email",
        "password_hash": pw_hash,
        "created_at": now_utc().isoformat(),
    })
    await grant_welcome_premium(user_id)
    if payload.guest_token:
        try:
            await migrate_guest_data(payload.guest_token, user_id)
        except Exception as e:
            logger.warning(f"Guest migration skipped: {e}")
    session_token = await _mint_session(user_id)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    return {"session_token": session_token, "user": user}


@api_router.post("/auth/login")
async def login_email(payload: EmailAuthRequest):
    """Sign in with email + password."""
    email = _norm_email(payload.email)
    user = await db.users.find_one({"email": email})
    # Constant-ish work to avoid leaking whether the email exists.
    dummy = "$2b$12$" + "x" * 53
    stored = (user or {}).get("password_hash") or dummy
    ok = False
    try:
        ok = bcrypt.checkpw(payload.password.encode(), stored.encode())
    except Exception:
        ok = False
    if not user or not user.get("password_hash") or not ok:
        raise HTTPException(status_code=400, detail="Incorrect email or password.")
    session_token = await _mint_session(user["user_id"])
    safe = {k: v for k, v in user.items() if k not in ("_id", "password_hash")}
    return {"session_token": session_token, "user": safe}


class AppleAuthRequest(BaseModel):
    identity_token: str
    name: Optional[str] = None
    email: Optional[str] = None
    guest_token: Optional[str] = None  # optional guest session to migrate


def _apple_jwk_client():
    global _APPLE_JWK_CLIENT
    if _APPLE_JWK_CLIENT is None:
        _APPLE_JWK_CLIENT = jwt.PyJWKClient("https://appleid.apple.com/auth/keys")
    return _APPLE_JWK_CLIENT


@api_router.post("/auth/apple")
async def apple_auth(payload: AppleAuthRequest):
    """Verify a Sign in with Apple identity token against Apple's JWKS, upsert
    the user by their stable Apple subject id, and return a bearer session.
    This is the equivalent login option to Google required by Apple 5.1.1(v)."""
    if not APPLE_AUDIENCES:
        raise HTTPException(status_code=500, detail="Apple sign-in is not configured")
    try:
        signing_key = _apple_jwk_client().get_signing_key_from_jwt(payload.identity_token)
        claims = jwt.decode(
            payload.identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=APPLE_AUDIENCES,
            issuer="https://appleid.apple.com",
        )
    except Exception as e:
        logger.warning(f"Apple token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid Apple identity token")

    apple_sub = claims.get("sub")
    if not apple_sub:
        raise HTTPException(status_code=401, detail="Invalid Apple identity token")
    token_email = claims.get("email")

    existing = await db.users.find_one({"apple_sub": apple_sub}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
    else:
        # Name + email are returned by Apple ONLY on the first sign-in — persist
        # them now; on later logins they arrive null and must not overwrite.
        user_id = new_id("user")
        await db.users.insert_one({
            "user_id": user_id,
            "apple_sub": apple_sub,
            "email": _norm_email(payload.email) if payload.email else (token_email or f"{user_id}@privaterelay.appleid.local"),
            "name": (payload.name or "").strip() or "Aureve Member",
            "provider": "apple",
            "created_at": now_utc().isoformat(),
        })
        await grant_welcome_premium(user_id)

    if payload.guest_token:
        try:
            await migrate_guest_data(payload.guest_token, user_id)
        except Exception as e:
            logger.warning(f"Guest migration skipped: {e}")

    session_token = await _mint_session(user_id)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    return {"session_token": session_token, "user": user}


@api_router.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    prem = is_premium(user)
    return {
        **user,
        "premium": prem,
        "is_guest": bool(user.get("is_guest")),
        "premium_until": user.get("premium_until"),
        "premium_source": user.get("premium_source"),
        "trial_used": bool(user.get("trial_used")),
        "trial_eligible": free_trial_enabled() and (not prem) and (not user.get("trial_used")),
        **complimentary_state(user),
        "premium_plan": premium_plan_label(user),
    }


@api_router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}


@api_router.delete("/auth/account")
async def delete_account(account: dict = Depends(get_current_user)):
    """Permanently delete the signed-in account and ALL associated data
    (every wardrobe profile, items, outfits, plans, collections, usage,
    calendar tokens, payment records and sessions). Required by App Store /
    Play Store policy for apps that support accounts."""
    account_id = account["user_id"]
    profs = await db.profiles.find({"user_id": account_id}, {"_id": 0, "id": 1}).to_list(200)
    prof_ids = [p["id"] for p in profs]
    if prof_ids:
        for coll in (db.items, db.outfits, db.wear_logs, db.plans, db.collections, db.stylist_threads):
            await coll.delete_many({"user_id": {"$in": prof_ids}})
    await db.profiles.delete_many({"user_id": account_id})
    await db.usage.delete_many({"account_id": account_id})
    await db.calendar_tokens.delete_many({"account_id": account_id})
    await db.payment_transactions.delete_many({"account_id": account_id})
    await db.user_sessions.delete_many({"user_id": account_id})
    await db.users.delete_one({"user_id": account_id})
    return {"ok": True, "deleted": True}


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
        "trial_eligible": free_trial_enabled() and (not prem) and (not user.get("trial_used")),
        "trial_days": 7,
        **complimentary_state(user),
        "premium_plan": premium_plan_label(user),
        "plans": [
            {"id": k, "amount": v["amount"], "days": v["days"], "label": v["label"], "currency": "usd"}
            for k, v in PREMIUM_PLANS.items()
        ],
    }


@api_router.get("/account-deletion", response_class=HTMLResponse)
async def account_deletion_page():
    """Public account & data deletion instructions page (no login required).
    Required by Google Play & App Store review."""
    html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Delete your Aureve account</title>
<style>
  body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#FAF9F6;color:#232323;line-height:1.6}
  .wrap{max-width:680px;margin:0 auto;padding:48px 24px 80px}
  h1{font-size:30px;letter-spacing:-0.5px;margin:0 0 8px}
  .kicker{font-size:12px;letter-spacing:2px;color:#8A8A82;text-transform:uppercase;margin-bottom:24px}
  h2{font-size:18px;margin:32px 0 8px}
  ol,ul{padding-left:20px} li{margin:6px 0}
  .card{background:#fff;border:1px solid #ECEAE3;border-radius:14px;padding:20px 24px;margin-top:16px}
  a{color:#5F7355;font-weight:600}
  .muted{color:#6B6B63;font-size:14px}
</style></head>
<body><div class="wrap">
  <div class="kicker">Aureve &middot; Privacy &amp; Data</div>
  <h1>Delete your account &amp; data</h1>
  <p>Aureve lets you permanently delete your account and all of your data at any time. This is immediate and cannot be undone.</p>

  <div class="card">
    <h2>Delete from inside the app (fastest)</h2>
    <ol>
      <li>Open <strong>Aureve</strong> and sign in.</li>
      <li>Go to the <strong>Profile</strong> tab.</li>
      <li>Scroll to <strong>Privacy &amp; data</strong>.</li>
      <li>Tap <strong>Delete my account</strong> and confirm.</li>
    </ol>
    <p class="muted">Your account and all associated data are deleted right away.</p>
  </div>

  <div class="card">
    <h2>Delete individual data (without closing your account)</h2>
    <p>You can remove or edit your own data at any time inside Aureve, without deleting your whole account:</p>
    <ul>
      <li><strong>Clothing items &amp; photos</strong> &mdash; open an item and tap the delete (trash) icon.</li>
      <li><strong>Saved outfits</strong> &mdash; open an outfit and delete it.</li>
      <li><strong>Collections</strong> and <strong>packing plans</strong> &mdash; delete them from their screens.</li>
      <li><strong>Style profile</strong> (measurements, skin tone, sizes, preferences) &mdash; edit or clear the fields in Profile &rarr; Style profile.</li>
      <li><strong>Wardrobe profiles</strong> (household members) &mdash; delete a profile to remove it and its items.</li>
      <li><strong>Connected Google Calendar</strong> &mdash; disconnect it in Profile at any time.</li>
    </ul>
    <p class="muted">These changes take effect immediately and are permanent.</p>
  </div>

  <div class="card">
    <h2>Can&rsquo;t access the app?</h2>
    <p>Email us from your account&rsquo;s email address at
      <a href="mailto:houseoffmr@gmail.com?subject=Delete%20my%20Aureve%20data">houseoffmr@gmail.com</a>.
      We will action your request as soon as possible, and within 30 days at the latest.</p>
  </div>

  <h2>What gets deleted</h2>
  <ul>
    <li>Your account and login details</li>
    <li>Every wardrobe profile you created</li>
    <li>All clothing items and photos</li>
    <li>All saved outfits, collections, packing plans and wear history</li>
    <li>Style profile, preferences and usage records</li>
    <li>Any connected calendar tokens and payment records held by us</li>
  </ul>
  <p class="muted">Deletion is immediate and permanent &mdash; we do not keep your data or additional copies after it is deleted, and there is no retention period on our side. The only exception is transaction/receipt records held by the app stores (Apple, Google) or the payment provider under their own policies; those are outside our control and we cannot delete them on their behalf.</p>
</div></body></html>"""
    return HTMLResponse(content=html)




@api_router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy_page():
    """Aureve Privacy Policy — publicly accessible (no login). Published verbatim."""
    html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Privacy Policy for Aureve</title>
<style>
  body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#FAF9F6;color:#232323;line-height:1.65}
  .wrap{max-width:720px;margin:0 auto;padding:48px 24px 96px}
  h1{font-size:30px;letter-spacing:-0.5px;margin:0 0 4px}
  .eff{color:#6B6B63;font-size:14px;margin-bottom:24px}
  h2{font-size:20px;margin:34px 0 8px}
  h3{font-size:16px;margin:18px 0 4px}
  p{margin:10px 0}
  ul{padding-left:22px} li{margin:5px 0}
  a{color:#5F7355;font-weight:600}
</style></head>
<body><div class="wrap">
<h1>Privacy Policy for Aureve</h1>
<p class="eff">Effective date: 8 August 2026</p>

<p>Aureve (&ldquo;Aureve&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo; or &ldquo;our&rdquo;) respects your privacy and is committed to protecting the personal information you provide when using the Aureve mobile application and related services.</p>
<p>This Privacy Policy explains what information Aureve collects, why we collect it, how it is used and protected, and the choices available to you regarding your information.</p>

<h2>1. Information We Collect</h2>
<p>Depending on the features you use, Aureve may collect or process the following information:</p>

<h3>Account Information</h3>
<p>When you create or use an Aureve account, we may collect:</p>
<ul>
<li>Your name</li>
<li>Email address</li>
<li>User or account identifier</li>
<li>Account and authentication information</li>
</ul>
<p>Some features may also be available through guest access without requiring all account information.</p>

<h3>Profile and Personalisation Information</h3>
<p>You may choose to provide information used to personalise Aureve's wardrobe, styling and recommendation features. This may include information such as:</p>
<ul>
<li>Height</li>
<li>Weight</li>
<li>Clothing sizes</li>
<li>Style preferences</li>
<li>Other information you voluntarily add to your profile</li>
</ul>

<h3>Wardrobe Content and Photos</h3>
<p>Aureve allows you to add clothing, accessories and other wardrobe information. We may therefore process:</p>
<ul>
<li>Photos you upload or take using your device</li>
<li>Information about wardrobe items</li>
<li>Categories, descriptions, attributes and other information associated with those items</li>
<li>Outfit information and combinations</li>
<li>Other content you voluntarily add to your wardrobe</li>
</ul>
<p>Photos and wardrobe information are used to provide Aureve's wardrobe management, styling, outfit-planning and personalised recommendation features.</p>

<h3>Location Information</h3>
<p>With your permission, Aureve may use location information to provide location-dependent features such as local weather information and weather-appropriate outfit recommendations.</p>
<p>Where possible, Aureve only uses the level of location information necessary to provide the requested feature.</p>
<p>You can control location permission through your device settings.</p>

<h3>App Activity</h3>
<p>We may collect information about how Aureve is used, including:</p>
<ul>
<li>App interactions</li>
<li>Features used</li>
<li>In-app searches</li>
<li>Other activity necessary to operate, analyse and improve Aureve</li>
</ul>

<h3>Device, Diagnostic and Performance Information</h3>
<p>We may collect technical information including:</p>
<ul>
<li>Device or other identifiers</li>
<li>Crash logs</li>
<li>Diagnostic information</li>
<li>App performance information</li>
</ul>
<p>This information helps us maintain Aureve, diagnose technical problems, improve reliability and understand how features perform.</p>

<h3>Purchases and Subscriptions</h3>
<p>If you purchase an Aureve subscription or other paid product, information relating to the purchase may be processed, including:</p>
<ul>
<li>Purchase and subscription history</li>
<li>Subscription status</li>
<li>Transaction-related information required to provide paid features</li>
</ul>
<p>Payments made through Google Play or Apple's App Store are processed by the relevant platform and payment providers. Aureve does not need to store your full credit or debit card number to provide your subscription.</p>

<h2>2. How We Use Information</h2>
<p>Information collected through Aureve may be used to:</p>
<ul>
<li>Create and manage user accounts</li>
<li>Authenticate users</li>
<li>Provide wardrobe-management features</li>
<li>Provide outfit planning and styling functionality</li>
<li>Generate personalised recommendations</li>
<li>Provide weather-related functionality</li>
<li>Remember preferences and settings</li>
<li>Process and verify subscriptions and purchases</li>
<li>Provide customer support and service communications</li>
<li>Maintain the security and reliability of Aureve</li>
<li>Diagnose crashes, errors and technical problems</li>
<li>Analyse and improve app functionality and performance</li>
<li>Comply with applicable legal obligations</li>
</ul>
<p>We do not use your personal information for third-party advertising unless this Privacy Policy is updated to disclose such use and any required consent is obtained.</p>

<h2>3. Artificial Intelligence and Automated Features</h2>
<p>Aureve may use artificial intelligence or automated systems to provide features such as wardrobe analysis, styling assistance, recommendations and other personalised functionality.</p>
<p>Information you submit to these features may be processed as necessary to generate the requested result.</p>
<p>We take reasonable steps to limit information provided to service providers to what is necessary to operate the relevant feature.</p>

<h2>4. Third-Party Service Providers</h2>
<p>Aureve may rely on trusted third-party providers to operate parts of the service, including providers of:</p>
<ul>
<li>Cloud hosting and data storage</li>
<li>Authentication</li>
<li>Artificial intelligence services</li>
<li>Weather information</li>
<li>Analytics and diagnostics</li>
<li>Subscription and purchase management</li>
<li>Google Play services</li>
<li>Apple App Store services</li>
</ul>
<p>These providers may process information on our behalf where necessary to provide their services.</p>
<p>Third-party services may also operate under their own privacy policies and legal obligations.</p>

<h2>5. Data Sharing</h2>
<p>We do not sell your personal information.</p>
<p>Information may be shared with service providers where reasonably necessary to operate Aureve, process subscriptions, provide requested functionality, maintain security or comply with the law.</p>
<p>We may also disclose information where reasonably necessary to:</p>
<ul>
<li>Comply with a legal obligation, court order or lawful government request</li>
<li>Protect the rights, safety or security of Aureve, our users or others</li>
<li>Detect or prevent fraud, abuse or security threats</li>
</ul>

<h2>6. Data Security</h2>
<p>We use reasonable technical and organisational measures designed to protect information from unauthorised access, loss, misuse, alteration or disclosure.</p>
<p>Information transmitted between Aureve and its online services is encrypted in transit using appropriate secure communication technologies.</p>
<p>No internet-connected service can guarantee absolute security, but we take reasonable measures appropriate to the nature of the information we process.</p>

<h2>7. Data Retention</h2>
<p>We retain personal information only for as long as reasonably necessary to provide Aureve, maintain your account, fulfil the purposes described in this Privacy Policy, resolve disputes and meet applicable legal or regulatory obligations.</p>
<p>When information is no longer reasonably required, it may be deleted or de-identified.</p>
<p>Some information may remain temporarily in backups or system records after deletion where technically necessary, until those records are overwritten or removed in accordance with normal system processes.</p>

<h2>8. Your Choices and Controls</h2>
<p>Depending on the relevant feature, Aureve allows users to access, modify or delete information associated with their account.</p>
<p>For example, users may be able to:</p>
<ul>
<li>Edit profile information</li>
<li>Add or remove wardrobe items</li>
<li>Delete uploaded content and photos</li>
<li>Change app permissions through their device</li>
<li>Manage subscription settings through the relevant app store</li>
<li>Request deletion of personal information</li>
<li>Request deletion of their Aureve account and associated data</li>
</ul>

<h2>9. Account and Data Deletion</h2>
<p>Users may request deletion of their Aureve account and associated personal data through the account deletion options provided by Aureve or through the account/data deletion page linked from Aureve's Google Play listing.</p>
<p>Users may also delete certain information, such as wardrobe items and other user-provided content, without deleting their entire account where this functionality is available within the app.</p>
<p>When an account deletion request is completed, information associated with the account will be deleted or de-identified except where retention is reasonably necessary for legal, security, fraud-prevention, financial, dispute-resolution or other legitimate obligations.</p>

<h2>10. Children's Privacy</h2>
<p>Aureve is not designed to collect personal information from children below the minimum age permitted to independently use the service under applicable law.</p>
<p>Where age-related consent requirements apply, Aureve will comply with applicable platform and legal requirements.</p>

<h2>11. International Data Processing</h2>
<p>Some service providers used by Aureve may process or store information in countries outside Australia.</p>
<p>Where personal information is processed internationally, we take reasonable steps to use reputable service providers and appropriate safeguards consistent with applicable privacy requirements.</p>

<h2>12. Changes to This Privacy Policy</h2>
<p>We may update this Privacy Policy when Aureve's functionality, data practices, service providers or legal obligations change.</p>
<p>The current version will be made available through Aureve or its associated website. The effective date at the top of this policy will be updated when material changes are made.</p>

<h2>13. Contact Us</h2>
<p>Questions, concerns, privacy requests or requests relating to personal information can be directed to:</p>
<p>Aureve<br>House of FMR<br>Email: <a href="mailto:houseoffmr@gmail.com">houseoffmr@gmail.com</a><br>Australia</p>
</div></body></html>"""
    return HTMLResponse(content=html)


@api_router.get("/terms", response_class=HTMLResponse)
async def terms_page():
    """Aureve Terms of Use — publicly accessible (no login). Content mirrors the
    in-app Terms screen for consistency."""
    html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Terms of Service for Aureve</title>
<style>
  body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#FAF9F6;color:#232323;line-height:1.65}
  .wrap{max-width:720px;margin:0 auto;padding:48px 24px 96px}
  h1{font-size:30px;letter-spacing:-0.5px;margin:0 0 4px}
  .eff{color:#6B6B63;font-size:14px;margin-bottom:24px}
  h2{font-size:20px;margin:34px 0 8px}
  p{margin:10px 0}
  a{color:#5F7355;font-weight:600}
</style></head>
<body><div class="wrap">
<h1>Terms of Service for Aureve</h1>
<p class="eff">Effective date: June 2026</p>

<h2>Acceptance</h2>
<p>By using Aureve you agree to these Terms. If you do not agree, please do not use the app. Effective June 2026.</p>

<h2>Your account</h2>
<p>You are responsible for keeping your login details secure and for activity under your account. You must provide accurate information when creating an account.</p>

<h2>Acceptable use</h2>
<p>Use Aureve for your personal styling only. Do not upload unlawful content, attempt to disrupt the service, or misuse the AI features.</p>

<h2>Styling &amp; AI suggestions</h2>
<p>Outfit, hair and body-shape suggestions are provided for guidance and inspiration only. They are generated automatically and may not always be accurate &mdash; use your own judgement.</p>

<h2>Subscriptions &amp; payments</h2>
<p>Some features may require a paid subscription. Billing, renewals and refunds are handled by the store or payment provider you purchase through (Apple, Google, or Stripe), subject to their terms.</p>

<h2>Your content</h2>
<p>You keep ownership of the photos and details you add. You grant us a limited licence to process them only to provide the app's features to you.</p>

<h2>Termination</h2>
<p>You may delete your account at any time. We may suspend accounts that violate these Terms.</p>

<h2>Disclaimer &amp; liability</h2>
<p>The app is provided &ldquo;as is&rdquo;. To the extent permitted by law, we are not liable for indirect or incidental losses arising from use of the app.</p>

<h2>Changes</h2>
<p>We may update these Terms from time to time; continued use means you accept the updated version.</p>

<h2>Contact</h2>
<p>Questions about these Terms? Contact us at <a href="mailto:houseoffmr@gmail.com">houseoffmr@gmail.com</a>.</p>
</div></body></html>"""
    return HTMLResponse(content=html)




@api_router.post("/membership/trial")
async def start_trial(account: dict = Depends(get_current_user)):
    """App-managed 7-day free trial — instant Premium, no card, once per account."""
    if not free_trial_enabled():
        raise HTTPException(status_code=403, detail="Free trial is not available.")
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


class EntitlementSync(BaseModel):
    """What the RevenueCat SDK reports from CustomerInfo on the device."""
    active: bool = False
    entitlement_id: Optional[str] = None
    # Absent for lifetime / promotional / "unlimited duration" entitlements.
    expires_at: Optional[str] = None
    product_id: Optional[str] = None
    app_user_id: Optional[str] = None


@api_router.post("/membership/entitlement")
async def sync_entitlement(payload: EntitlementSync, account: dict = Depends(get_current_user)):
    """Unlock Premium from the ACTIVE ENTITLEMENT in RevenueCat CustomerInfo.

    Any active entitlement unlocks Aureve — we never key off a particular
    product or subscription type, so lifetime, promotional and
    "unlimited duration" entitlements unlock exactly like a monthly plan.
    This only ever grants/extends: an inactive report is ignored so an offline
    or stale device can't lock a paying member out (expiry and cancellation are
    handled by premium_until and the RevenueCat webhook)."""
    if not payload.active:
        return {
            "premium": is_premium(account),
            "premium_until": account.get("premium_until"),
            "premium_source": account.get("premium_source"),
            "updated": False,
        }

    until: Optional[datetime] = None
    if payload.expires_at:
        try:
            dt = datetime.fromisoformat(payload.expires_at.replace("Z", "+00:00"))
            until = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            until = None
    if until is None:
        # No expiry date = non-expiring entitlement; keep it unlocked.
        until = now_utc() + timedelta(days=365 * 50)

    current = account.get("premium_until")
    if current:
        try:
            cur_dt = datetime.fromisoformat(current)
            if cur_dt.tzinfo is None:
                cur_dt = cur_dt.replace(tzinfo=timezone.utc)
            until = max(until, cur_dt)
        except Exception:
            pass

    await db.users.update_one(
        {"user_id": account["user_id"]},
        {"$set": {
            "premium_until": until.isoformat(),
            "premium_source": "revenuecat",
            "revenuecat_entitlement": payload.entitlement_id,
            "revenuecat_product": payload.product_id,
            "revenuecat_app_user_id": payload.app_user_id,
        }},
    )
    logger.info(
        f"RevenueCat entitlement sync for {account['user_id']}: "
        f"{payload.entitlement_id or 'active'} until {until.isoformat()}"
    )
    return {
        "premium": True,
        "premium_until": until.isoformat(),
        "premium_source": "revenuecat",
        "updated": True,
    }


REVENUECAT_WEBHOOK_AUTH = os.environ.get("REVENUECAT_WEBHOOK_AUTH", "")
REVENUECAT_WEBHOOK_SECRET = os.environ.get("REVENUECAT_WEBHOOK_SECRET", "")
_RC_ACTIVE_TYPES = {
    "INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION",
    "PRODUCT_CHANGE", "NON_RENEWING_PURCHASE", "SUBSCRIPTION_EXTENDED",
    "TEMPORARY_ENTITLEMENT_GRANT",
}


@api_router.post("/webhooks/revenuecat")
async def revenuecat_webhook(request: Request, authorization: Optional[str] = Header(None)):
    """Receive RevenueCat subscription events and sync the account's premium
    status. Configure a matching Authorization header in the RevenueCat
    dashboard (stored in REVENUECAT_WEBHOOK_AUTH)."""
    raw = await request.body()

    # Auth: RevenueCat sends a custom Authorization header you configure.
    if REVENUECAT_WEBHOOK_AUTH:
        if not authorization or not hmac.compare_digest(authorization, REVENUECAT_WEBHOOK_AUTH):
            raise HTTPException(status_code=401, detail="Unauthorized webhook")
    # Optional HMAC signature (if enabled on the dashboard).
    if REVENUECAT_WEBHOOK_SECRET:
        sig = request.headers.get("X-RevenueCat-Signature") or request.headers.get("x-revenuecat-webhook-signature")
        if sig:
            mac = hmac.new(REVENUECAT_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
            provided = sig.split(",")[-1].split("=")[-1]
            if not hmac.compare_digest(mac, provided):
                raise HTTPException(status_code=401, detail="Bad signature")

    try:
        payload = json.loads(raw)
        evt = payload["event"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_id = evt.get("id")
    if event_id:
        if await db.revenuecat_events.find_one({"event_id": event_id}):
            return {"ok": True}
        await db.revenuecat_events.insert_one({"event_id": event_id, "received_at": now_utc()})

    app_user_id = evt.get("app_user_id")
    if not app_user_id:
        return {"ok": True}

    etype = evt.get("type", "")
    exp_ms = evt.get("expiration_at_ms")
    if exp_ms:
        until_dt = datetime.fromtimestamp(int(exp_ms) / 1000, tz=timezone.utc)
        active = until_dt > now_utc() and etype not in ("EXPIRATION",)
    else:
        active = etype in _RC_ACTIVE_TYPES
        # No expiry on an active event means a non-expiring entitlement
        # (lifetime / promotional / "unlimited duration"); a temporary grant is
        # the one case that genuinely runs out, so keep that short.
        if not active:
            until_dt = None
        elif etype == "TEMPORARY_ENTITLEMENT_GRANT":
            until_dt = now_utc() + timedelta(days=31)
        else:
            until_dt = now_utc() + timedelta(days=365 * 50)

    update = {
        "premium_source": "revenuecat",
        "premium_until": until_dt.isoformat() if (active and until_dt) else None,
    }
    await db.users.update_one({"user_id": app_user_id}, {"$set": update})
    logger.info(f"RevenueCat {etype} for {app_user_id}: premium={'yes' if active else 'no'}")
    return {"ok": True}



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
    for i, pr in enumerate(profs):
        pr["is_primary"] = i == 0
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
    prof["is_primary"] = False
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
    for coll in (db.items, db.outfits, db.wear_logs, db.plans, db.style_suggestions, db.stylist_threads):
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
    # User-corrected subcategory (presentation filter). "" = classify automatically.
    subcategory: Optional[str] = ""
    # Matching set / suit: pieces designed to be worn together. "" = not in a set.
    set_name: Optional[str] = ""
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
    photo: Optional[str] = None        # base64 (hanging, cleaned when available)
    orig_photo: Optional[str] = None   # base64 (original upload, kept internally)
    worn_photo: Optional[str] = None   # base64 (worn — never altered)
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
    subcategory: Optional[str] = None
    set_name: Optional[str] = None
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
    avoid_item_ids: Optional[List[str]] = None  # items already used elsewhere this week


class WearLog(BaseModel):
    outfit_id: Optional[str] = None
    name: Optional[str] = ""        # what the look was called when it was worn
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


def make_thumb(b64: Optional[str]) -> Optional[str]:
    """Grid-sized preview (~320px). Detail screens still load the full photo."""
    return compress_b64(b64, max_side=320, quality=60)


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


@api_router.get("/items/capacity")
async def wardrobe_capacity(user: dict = Depends(get_scope)):
    """How much room is left, so the app can offer the right thing instead of
    letting an upload fail. The cap itself is still enforced on create."""
    count = await db.items.count_documents(items_scope(user))
    premium = bool(user.get("account_premium"))
    return {
        "count": count,
        "cap": None if premium else FREE_ITEM_CAP,
        "remaining": None if premium else max(0, FREE_ITEM_CAP - count),
        "full": (not premium) and count >= FREE_ITEM_CAP,
        "premium": premium,
    }


@api_router.post("/items")
async def create_item(payload: ItemCreate, user: dict = Depends(get_scope)):
    has_image = bool((payload.photo or "").strip()) or bool((payload.worn_photo or "").strip())
    if not has_image:
        raise HTTPException(status_code=400, detail="A photo is required to add an item.")
    if not user.get("account_premium"):
        active = await db.items.count_documents(items_scope(user))
        if active >= FREE_ITEM_CAP:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Free wardrobes hold up to {FREE_ITEM_CAP} pieces. "
                    "Delete a piece to free a slot, or go Premium for unlimited."
                ),
            )
    item = payload.dict()
    item["photo"] = compress_b64(item.get("photo"))
    item["worn_photo"] = compress_b64(item.get("worn_photo"))
    # Small grid preview so the wardrobe list never ships full-resolution photos.
    item["thumb"] = make_thumb(item.get("photo") or item.get("worn_photo"))
    item["id"] = new_id("item")
    item["user_id"] = user["user_id"]
    item["wear_count"] = 0
    item["last_worn"] = None
    item["created_at"] = now_utc().isoformat()
    await db.items.insert_one({**item})
    item.pop("_id", None)
    return item


@api_router.get("/items")
async def list_items(category: Optional[str] = None, summary: bool = False,
                     user: dict = Depends(get_scope)):
    # Grid/list views only ever need the small preview, so the heavy originals
    # are never sent (a 200-piece wardrobe used to ship tens of MB per load).
    # summary=1 drops imagery entirely — used for wardrobe category/subcategory
    # browsing, which shows counts only.
    projection = {"_id": 0, "orig_photo": 0}
    if summary:
        projection.update({"photo": 0, "worn_photo": 0, "thumb": 0})
    all_items = await db.items.find(
        items_scope(user), projection
    ).sort("created_at", -1).to_list(1000)
    counts = compute_pairs_counts(all_items)
    if category and category.lower() != "all":
        items = [it for it in all_items if it.get("category") == category]
    else:
        items = all_items
    backfilled = 0
    for it in items:
        it["pairs_count"] = counts.get(it["id"], 0)
        if summary:
            continue
        thumb = it.get("thumb")
        if not thumb and backfilled < 20:
            # One-off backfill for pieces catalogued before thumbnails existed.
            thumb = make_thumb(it.get("photo") or it.get("worn_photo"))
            if thumb:
                await db.items.update_one({"id": it["id"]}, {"$set": {"thumb": thumb}})
                backfilled += 1
        it["photo"] = thumb or it.get("photo")
        it["worn_photo"] = None if it.get("photo") else it.get("worn_photo")
        it.pop("thumb", None)
    return items


@api_router.get("/laundry")
async def laundry(user: dict = Depends(get_scope)):
    items = await db.items.find(
        {**items_scope(user), "availability": {"$in": ["Dirty", "Washing", "Drying"]}},
        {"_id": 0, "orig_photo": 0},
    ).sort("name", 1).to_list(1000)
    return items


@api_router.get("/items/{item_id}")
async def get_item(item_id: str, user: dict = Depends(get_scope)):
    item = await db.items.find_one({**items_scope(user), "id": item_id}, {"_id": 0})
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
        updates["thumb"] = make_thumb(updates["photo"])
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


class BulkDeleteRequest(BaseModel):
    item_ids: List[str]


@api_router.post("/items/bulk-delete")
async def bulk_delete_items(payload: BulkDeleteRequest, user: dict = Depends(get_scope)):
    """Delete several of the scope's own wardrobe items in one go."""
    ids = [i for i in (payload.item_ids or []) if i]
    if not ids:
        raise HTTPException(status_code=400, detail="No items selected")
    res = await db.items.delete_many({"user_id": user["user_id"], "id": {"$in": ids}})
    return {"deleted": res.deleted_count}


# ----------------------------- AI: Analyze Item -----------------------------
ANALYZE_SYSTEM = (
    "You are a fashion cataloguing assistant. These are REAL customer phone photos, "
    "NOT studio product shots — expect imperfect lighting, household or cluttered backgrounds, "
    "angled or folded items, items being worn, shadows and reflections. Identify the single main "
    "fashion item a human would obviously recognise and catalogue it anyway; do not refuse or "
    "default to a generic guess just because the background is messy. "
    "Return a strict JSON object. Keys: name (short descriptive name, e.g. 'Purple oversized sunglasses'), "
    "category (ALWAYS your best guess from exactly: Tops, Bottoms, Dresses, Outerwear, Shoes, Bags, Accessories, Jewellery — "
    "sunglasses/hats/belts/scarves = Accessories; rings/necklaces/earrings/watches = Jewellery; never leave blank), "
    "Identify the SPECIFIC garment type and let it win over general appearance — never decide from sleeve "
    "length, colour, height or silhouette alone. Jumpsuits, playsuits and rompers are one-piece garments: "
    "call them a jumpsuit and file them under Tops (Aureve groups them with bodysuits). High-top sneakers "
    "are sneakers, not boots. Wedge sandals are sandals, not heels. Sweatshirts and hoodies are jumpers "
    "(Outerwear); a leather jacket is a jacket; a blazer is a blazer; a cardigan is a cardigan. "
    "Soft, relaxed, pull-on or drawstring pants (track pants, joggers, sweatpants, lounge pants) must be named "
    "as lounge/track pants — never call them trousers, which are tailored/structured pants, chinos or dress pants. "
    "A lightweight long-sleeve top (jersey, tee-style or blouse construction, thin knit) is a long-sleeve TOP, "
    "not a jumper; only call something a jumper/sweatshirt/hoodie/fleece when it is a heavier warmth layer with "
    "obvious jumper construction. "
    "For bags, name the carry style from the construction, not from the presence of a strap: two shoulder "
    "straps worn on the back = backpack; a bag carried by hand/arm/shoulder or across the body = handbag; a "
    "small bag held in the hand for evening = clutch. "
    "A suit jacket is a blazer. Jumpsuits and playsuits are one-piece garments filed under Tops. "
    "Skorts are skirts. For sleeveless tops, a delicate/dressy piece (satin, silk-look, lace, slip or cowl "
    "styling) is a camisole while a basic cotton/jersey/ribbed one is a singlet — strap width decides nothing. "
    "For footwear, say whether it is heeled: heeled sandals, wedges and pumps are heels; flat sandals, slides "
    "and thongs are flats; high-top sneakers are sneakers, not boots. "
    "IMPORTANT for tops: bodysuits/leotards/jumpsuits (one-piece garments that fasten through the crotch), "
    "corsets/bustiers, camisoles, singlets, halter tops, cropped tops, polo shirts and "
    "vests/waistcoats are ALL category Tops — never "
    "Dresses or Outerwear. Always state the actual garment type in the name (e.g. 'Black long-sleeve "
    "bodysuit', 'Ivory halterneck top', 'Cream silk camisole', 'White cotton t-shirt', 'Navy poplin shirt', "
    "'Green pique polo shirt', 'Grey wool waistcoat', 'Black ribbed singlet', 'Blue denim shorts', "
    "'Beige trench coat', 'Tan leather loafers', 'Black leather crossbody bag', 'Gold hoop earrings'). "
    "Use the plain garment word a shopper would use — never a vague name like 'top' or 'shoes' when a "
    "specific type (t-shirt, polo, blouse, shirt, cami, singlet, vest, jeans, leggings, skirt, shorts, "
    "blazer, cardigan, jumper, coat, jacket, sneakers, boots, heels, flats, sandals, dress shoes, "
    "handbag, backpack, clutch, briefcase, crossbody, hat, sunglasses, scarf, tie, belt, gloves, "
    "necklace, bracelet, earrings, ring, watch) is visible, "
    "photo_quality (\"good\" or \"poor\" — say \"poor\" ONLY when glare, harsh shadow, blown "
    "highlights, washed-out colour or a very dark garment blending into the background genuinely "
    "obscures the item's real colour or detail), "
    "photo_quality_note (empty string when good, otherwise ONE short plain sentence naming what is "
    "affecting the photo), "
    "confidence (integer 0-100 = how sure you are of the item identity AND category; be honest — "
    "use a low number when the photo is ambiguous or the object is partly hidden), "
    "colour (primary colour word), fabric (best guess, e.g. cotton/denim/wool/linen/leather/silk/metal/plastic), "
    "pattern (e.g. solid, striped, floral, checked), style (e.g. blazer, trench, bomber, pencil skirt, sunglasses, tote), "
    "sleeve_length (e.g. sleeveless, short, three-quarter, long, n/a), "
    "formality (one of: Casual, Smart Casual, Business, Formal), "
    "tone (one of: Warm, Cool, Neutral), "
    "season (one of: All, Spring, Summer, Autumn, Winter), "
    "condition (one of: New, Excellent, Good, Worn), "
    "needs_care (short string, e.g. 'needs steaming' or 'none'), "
    "estimated_value (integer estimate of resale/retail value in USD), "
    "description (one short sentence). Return ONLY the JSON object, no prose."
)


async def _analyze_core(image_b64: str, category_hint: Optional[str], scope_id: str,
                        worn: bool = False) -> dict:
    chat = await ai_chat(f"analyze-{scope_id}-{uuid.uuid4().hex[:6]}", ANALYZE_SYSTEM)
    if worn and not category_hint:
        text = (
            "This is a real phone photo of a person WEARING the item. Catalogue the single most "
            "prominent garment they are wearing (ignore the person, the background and secondary "
            "layers). Always pick the closest category from the allowed list and set confidence "
            "honestly. Return JSON only."
        )
    elif category_hint:
        text = (
            f"The person in the photo may be wearing several garments. Focus ONLY on the "
            f"{category_hint} and catalogue that single item, ignoring everything else "
            f"they are wearing. Set the category to '{category_hint}'. Return JSON only."
        )
    else:
        text = (
            "This is a real phone photo, possibly with an everyday background or imperfect lighting. "
            "Identify the single main fashion item a person would obviously recognise and catalogue it. "
            "Always pick the closest category from the allowed list and set confidence honestly. Return JSON only."
        )
    resp = await chat.send_message(UserMessage(text=text, file_contents=[ImageContent(image_base64=image_b64)]))
    return parse_json_block(resp) or {}


async def _clean_photo(image_b64: str) -> Optional[str]:
    """Background-removed, catalogue-style version of a garment photo (best-effort)."""
    instruction = (
        "Isolate the single main clothing item or accessory in this photo and remove EVERYTHING else. "
        "Remove the coat hanger, hook, clip, peg, rail, rack, wardrobe door, mannequin, hands, furniture, "
        "floor, wall and any other background clutter completely — no hanger hook or loop may remain. "
        "Return the SAME item with its shape, colour, pattern, texture and details completely unchanged — "
        "do NOT restyle, recolour or redesign it, and do not add or remove garment details. Place it centred "
        "on a clean, seamless, light neutral (#F1EFEA) studio background, flat product-catalogue style. "
        "Output only the image."
    )

    async def _attempt():
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"clean-{uuid.uuid4().hex[:8]}",
            system_message="You are a product-photo background remover for a clothing catalogue.",
        ).with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
        _text, images = await chat.send_message_multimodal_response(
            UserMessage(text=instruction, file_contents=[ImageContent(image_b64)])
        )
        return compress_b64(images[0]["data"]) if images else None

    # One retry only when the first pass errors or comes back empty, so a
    # transient failure can't leave an item permanently uncleaned.
    try:
        out = await _attempt()
    except Exception as e:
        logger.warning("clean pass 1 failed, retrying once: %s", e)
        out = None
    if not out:
        out = await _attempt()
    return out


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
    # True when the photo shows the item being worn (worn-photo slot).
    worn: bool = False


def _norm(v) -> str:
    return str(v or "").strip().lower()


def find_similar_items(analysis: dict, items: List[dict], limit: int = 3) -> List[dict]:
    """Flag only pieces that look like the SAME garment being added twice (or a
    near-identical second photo of it). Deliberately strict: a shared colour or
    garment type is NOT a duplicate, because loose matching pollutes both the
    Bulk Add warnings and Shopping Intelligence."""
    cat = _norm(analysis.get("category"))
    colour = _norm(analysis.get("colour"))
    if not cat or not colour:
        return []
    style, fabric = _norm(analysis.get("style")), _norm(analysis.get("fabric"))
    pattern = _norm(analysis.get("pattern"))
    stop = {"a", "an", "the", "new", "with", "and", "in", "of", "top", "piece"}
    words = {w for w in re.split(r"[^a-z0-9]+", _norm(analysis.get("name"))) if len(w) > 2 and w not in stop}
    out = []
    def same_colour(other: str) -> bool:
        o = _norm(other)
        if not o:
            return False
        # "Rust" vs "Rust orange" is the same garment described twice.
        return o == colour or o in colour or colour in o or o.split()[0] == colour.split()[0]

    for it in items:
        if _norm(it.get("category")) != cat or not same_colour(it.get("colour")):
            continue
        detail_matches = sum(
            1 for a, b in ((style, it.get("style")), (fabric, it.get("fabric")), (pattern, it.get("pattern")))
            if a and _norm(b) == a
        )
        other_words = {w for w in re.split(r"[^a-z0-9]+", _norm(it.get("name"))) if len(w) > 2 and w not in stop}
        shared = words & other_words
        # Same category + same colour + at least two matching descriptors +
        # a genuinely overlapping name. Anything looser is just "similar".
        if detail_matches < 2 or len(shared) < 2:
            continue
        out.append({
            "id": it["id"],
            "name": it.get("name", ""),
            "category": it.get("category", ""),
            "colour": it.get("colour", ""),
            "photo": it.get("photo"),
            "reason": (
                f"Same category and colour as your {it.get('name') or 'existing piece'}"
                + (f", also {', '.join(sorted(shared))}" if shared else "")
            ),
        })
        if len(out) >= limit:
            break
    return out


@api_router.post("/capture")
async def capture_item(payload: CaptureRequest, user: dict = Depends(get_scope)):
    """Recognition pass for a captured garment photo. Background removal is a
    separate call (/clean-photo) so recognition stays fast and reliable on real
    mobile networks; pass clean=true only if both are wanted in one request."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    kb = int(len(payload.image or "") * 3 / 4 / 1024)
    logger.info("capture: received image %sKB clean=%s hint=%s user=%s",
                kb, payload.clean, payload.category_hint, user["user_id"])
    started = _time.monotonic()
    tasks = [_analyze_core(payload.image, payload.category_hint, user["user_id"], payload.worn)]
    if payload.clean:
        tasks.append(_clean_photo(payload.image))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    analysis = results[0]
    if isinstance(analysis, Exception) or not analysis:
        logger.warning("capture: analyze FAILED after %.1fs: %s", _time.monotonic() - started, analysis)
        analysis = {}
    else:
        logger.info("capture: analyzed in %.1fs -> name=%r category=%r confidence=%s",
                    _time.monotonic() - started, analysis.get("name"),
                    analysis.get("category"), analysis.get("confidence"))
    clean_img = None
    if payload.clean and len(results) > 1:
        cr = results[1]
        if isinstance(cr, Exception):
            logger.warning("capture clean failed: %s", cr)
        else:
            clean_img = cr
    duplicates = []
    if analysis:
        existing = await wardrobe_pool(user, 1000)
        # Only the few flagged duplicates are shown, so only they need imagery.
        duplicates = await hydrate_photos(user, find_similar_items(analysis, existing), ("photo",))
    return {"analysis": analysis, "clean_image": clean_img, "duplicates": duplicates}


class CleanPhotoRequest(BaseModel):
    image: str


@api_router.post("/items/{item_id}/clean")
async def clean_item_photo(item_id: str, user: dict = Depends(get_scope)):
    """Run catalogue-style background cleanup on an item that was saved with its
    raw photo (the Bulk Add path). The original is preserved in `orig_photo`,
    worn photos are never touched, and a failure leaves the item untouched so a
    cleanup problem can never fail an upload."""
    item = await db.items.find_one({"id": item_id, "user_id": user["user_id"]}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    source = item.get("orig_photo") or item.get("photo")
    if not source:
        return {"cleaned": False, "reason": "no photo"}
    if not EMERGENT_LLM_KEY:
        return {"cleaned": False, "reason": "ai key not configured"}
    try:
        img = await _clean_photo(source)
    except Exception as e:
        logger.warning("item clean failed for %s: %s", item_id, e)
        return {"cleaned": False, "reason": "clean failed"}
    if not img:
        return {"cleaned": False, "reason": "empty result"}
    await db.items.update_one(
        {"id": item_id, "user_id": user["user_id"]},
        {"$set": {"photo": img, "orig_photo": source, "thumb": make_thumb(img)}},
    )
    return {"cleaned": True, "photo": img}


@api_router.post("/clean-photo")
async def clean_photo(payload: CleanPhotoRequest, user: dict = Depends(get_scope)):
    """Background-removed, catalogue-style version of a garment photo. Called
    separately (and non-blockingly) after recognition so a slow or failed
    background removal can never break adding an item."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    started = _time.monotonic()
    try:
        img = await _clean_photo(payload.image)
    except Exception as e:
        logger.warning("clean-photo failed after %.1fs: %s", _time.monotonic() - started, e)
        raise HTTPException(status_code=502, detail="Couldn't clean up the photo")
    logger.info("clean-photo: done in %.1fs (image=%s)", _time.monotonic() - started, bool(img))
    return {"clean_image": img}


class ClientLogRequest(BaseModel):
    stage: str
    data: Optional[dict] = None
    platform: Optional[str] = None


@api_router.post("/diag/log")
async def diag_log(payload: ClientLogRequest):
    """Stage-level client diagnostics. Console logs are invisible on TestFlight,
    so the app ships each pipeline stage here to land in the server log."""
    logger.info("CLIENT[%s] %s %s", payload.platform or "?", payload.stage,
                json.dumps(payload.data or {})[:600])
    return {"ok": True}


# ----------------------------- AI: Stylist Suggest -----------------------------
def summarize_items_for_ai(items: List[dict]) -> str:
    lines = []
    for it in items:
        lines.append(
            f"- id:{it['id']} | {it.get('category','')} | name:{it.get('name','')} | "
            f"colour:{it.get('colour','')} | fabric:{it.get('fabric','')} | "
            f"season:{it.get('season','All')} | formality:{it.get('formality','')} | "
            f"tone:{it.get('tone','')} | fit:{it.get('fit_notes','')} | "
            f"flatters:{it.get('flatters')} | worn:{it.get('wear_count', 0) or 0}x | "
            f"last_worn:{(it.get('last_worn') or 'never')[:10]}"
        )
    return "\n".join(lines)


def underused_line(items: List[dict], limit: int = 10) -> str:
    """Name the pieces the user owns but rarely (or never) wears, so the stylist
    can help them rediscover their own wardrobe instead of recycling favourites."""
    ranked = sorted(items, key=lambda it: ((it.get("wear_count", 0) or 0), it.get("last_worn") or ""))
    picks = [it for it in ranked if (it.get("wear_count", 0) or 0) <= 1][:limit]
    if not picks:
        return ""
    names = ", ".join(f"{it.get('name')} ({it.get('category')}, worn {it.get('wear_count', 0) or 0}x)" for it in picks)
    return f"UNDERUSED / FORGOTTEN pieces they own: {names}.\n"


async def recent_looks_line(user_id: str, limit: int = 6) -> str:
    """Summarise outfits the user actually logged as worn."""
    logs = await db.wear_logs.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    combos = [",".join(lg.get("item_ids", [])) for lg in logs if lg.get("item_ids")]
    if not combos:
        return ""
    return "RECENTLY WORN combinations (do not simply rebuild these): " + " | ".join(combos) + "\n"


async def recent_suggestions(user_id: str, source: str = "dressme", limit: int = 12) -> List[dict]:
    """Persisted AI suggestion history. This is deliberately separate from wear_logs:
    a suggested outfit must influence rotation without pretending it was actually worn."""
    return await db.style_suggestions.find(
        {"user_id": user_id, "source": source}, {"_id": 0}
    ).sort("created_at", -1).to_list(limit)


def recent_suggestions_line(history: List[dict]) -> str:
    combos = [",".join(x.get("item_ids", [])) for x in history if x.get("item_ids")]
    if not combos:
        return ""
    counts = {}
    for row in history:
        for iid in row.get("item_ids", []):
            counts[iid] = counts.get(iid, 0) + 1
    repeated = [iid for iid, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True) if n >= 2][:12]
    extra = f" Frequently suggested item ids to strongly deprioritise: {','.join(repeated)}." if repeated else ""
    return (
        "RECENTLY SUGGESTED combinations (do not repeat these, even if they were never logged as worn): "
        + " | ".join(combos) + extra + "\n"
    )


async def record_style_suggestion(user_id: str, source: str, occasion: str, item_ids: List[str]):
    ids = [i for i in item_ids if i]
    if not ids:
        return
    await db.style_suggestions.insert_one({
        "id": new_id("sugg"),
        "user_id": user_id,
        "source": source,
        "occasion": occasion or "",
        "item_ids": ids,
        "created_at": now_utc().isoformat(),
    })
    # Bound storage per wardrobe/source. Keep the newest 60 only.
    stale = await db.style_suggestions.find(
        {"user_id": user_id, "source": source}, {"_id": 0, "id": 1}
    ).sort("created_at", -1).skip(60).to_list(500)
    if stale:
        await db.style_suggestions.delete_many({"id": {"$in": [x["id"] for x in stale]}})


def available_items(items: List[dict]) -> List[dict]:
    """Items ready to wear — excludes anything in the laundry cycle."""
    return [it for it in items if (it.get("availability") or "Ready") == "Ready"]


# The AI endpoints describe the wardrobe to the model as TEXT (see
# summarize_items_for_ai), so loading every piece's base64 imagery is pure
# waste — a 300-piece wardrobe is tens of MB of strings per request, held for
# the whole AI call. wardrobe_pool() loads metadata only; hydrate_photos()
# re-attaches imagery for the handful of pieces that end up in the response.
AI_POOL_PROJECTION = {"_id": 0, "orig_photo": 0, "photo": 0, "thumb": 0, "worn_photo": 0}


async def wardrobe_pool(user: dict, limit: int = 2000) -> List[dict]:
    return await db.items.find(items_scope(user), AI_POOL_PROJECTION).to_list(limit)


async def hydrate_photos(user: dict, items: List[dict], keys=("photo", "thumb", "worn_photo")) -> List[dict]:
    """Re-attach display imagery to pieces loaded by wardrobe_pool. Mutates in
    place, so item dicts shared across several response keys are all covered."""
    ids = list({it["id"] for it in items if isinstance(it, dict) and it.get("id")})
    if not ids:
        return items
    docs = await db.items.find(
        {**items_scope(user), "id": {"$in": ids}},
        {"_id": 0, "id": 1, **{k: 1 for k in keys}},
    ).to_list(len(ids))
    by_id = {d["id"]: d for d in docs}
    for it in items:
        d = by_id.get(it.get("id")) if isinstance(it, dict) else None
        if not d:
            continue
        for key in keys:
            if key in d:
                it[key] = d[key]
    return items



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
    "Build the CORE outfit first: a top + bottom, OR a dress/bodysuit/jumpsuit, plus shoes, plus outerwear ONLY "
    "when the weather, occasion or styling genuinely calls for it. Extras are then OPTIONAL: add a bag, jewellery, "
    "belt, scarf or sunglasses ONLY when it genuinely improves or completes the look. Never fill one item from every "
    "category: most everyday looks need NO bag and NO jewellery, so only add an extra when you can give a "
    "concrete styling reason for it, and returning no bag, no jewellery and no accessory is a perfectly good "
    "answer. "
    "Mark every item with necessity: \"core\" (part of the outfit), \"recommended\" (an extra that genuinely "
    "improves it, e.g. a belt that fixes the silhouette or a jacket needed for the weather) or \"optional\" "
    "(a nice-to-have addition). Never style a backpack, briefcase, laptop bag or work bag as the outfit's bag. "
    "Consider the occasion, temperature, weather, the user's learned preferences and which items flatter them. "
    "Help them wear MORE of what they already own: rotate the wardrobe, favour suitable pieces they rarely wear, "
    "and avoid rebuilding a look they have just worn. Versatile staples may repeat when styled differently. "
    "Return STRICT JSON with keys: "
    "items (array of objects with keys slot, item_id, necessity (core|recommended|optional), reason — reason "
    "explains WHY it works, like a stylist), "
    "confidence_score (integer 0-100 rating the outfit on colour harmony, style cohesion, occasion + weather "
    "suitability, proportion/silhouette and use of existing wardrobe), "
    "score_reasons (array of 3-5 short bullet strings justifying the score), "
    "styling_notes (string), hair (string), confidence_tip (string), "
    "summary (ONE short editorial styling line, max ~12 words, describing the vibe and how it "
    "suits the occasion/weather — e.g. \"Clean, smart casual and ideal for today's cool drizzle.\" "
    "Do NOT list the garment names in the summary). "
    "slot values should be human labels like Top, Bottom, Dress, Outerwear, Shoes, Bag, Belt, Scarf, Sunglasses, "
    "Jewellery, Accessory. Only include item_id values that exist in the provided wardrobe. Return ONLY JSON."
)


@api_router.post("/stylist/suggest", dependencies=[Depends(unreleased("planner"))])
async def stylist_suggest(payload: SuggestRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "stylist")
    return await _build_outfit(user, payload.occasion, payload.temperature, payload.weather, payload.notes, payload.avoid_item_ids)


STYLIST_CHAT_SYSTEM = (
    "You are Aureve, a warm, expert personal stylist having a real conversation with the user about their own "
    "clothes, outfits and personal style. This is a COLLABORATION, not an outfit generator: discuss specific "
    "pieces they own by name, give an honest opinion on a combination, say what you would change and why, "
    "suggest which shoes or layers to add, name what their wardrobe is genuinely missing, and answer follow-ups "
    "in context. "
    "Reply conversationally and concisely — like a knowledgeable, encouraging friend, never robotic or list-heavy "
    "unless the user asks for options. You may ONLY reference items that exist in the user's wardrobe (by exact id). "
    "Never give generic fashion advice when you can talk about the pieces they actually own. "
    "Never invent items; if they genuinely don't own something the look needs, say so plainly. "
    "Consider occasion, weather, colour, proportion, what flatters them and what they actually wear. "
    "READ THE REQUEST THEY ACTUALLY MADE and answer THAT: "
    "(a) 'style something I own' → work from their wardrobe; "
    "(b) 'what should I wear today' → wardrobe plus occasion and weather; "
    "(c) 'what am I missing' → talk about genuine gaps; "
    "(d) 'give me a completely different look / it doesn't have to be from my wardrobe / style reset' → "
    "design the look freely from their style profile, colouring and proportions. In that case do NOT "
    "restrict yourself to owned pieces, do NOT ask what the occasion is unless it is genuinely "
    "impossible to answer without it, and do NOT turn it into shopping or gap analysis. You may relate "
    "the concept back to pieces they own AFTERWARDS, but only once you have answered what they asked. "
    "Never force a question when the request is already clear. "
    "KEEP IT READABLE ON A PHONE: lead with the recommendation, then a short reason, then the actual "
    "pieces, then at most one extra note. Aim for under ~120 words unless they ask for detail, and "
    "never repeat their question back to them. Warm and conversational, never a wall of text. "
    "When (and only when) you are recommending a specific complete outfit to wear, append at the very END of your "
    "message a fenced JSON block exactly like ```json{\"outfit\": {\"name\": \"<short name>\", \"item_ids\": [\"<id>\", \"<id>\"]}}``` "
    "using real ids from the wardrobe. Keep the conversational text natural and free of raw ids or JSON."
)


class StylistChatMessage(BaseModel):
    role: str
    content: str


# Words that describe WHEN, not WHAT — they carry no styling context on their own.
_VAGUE_TIME = re.compile(r"\b(today|tonight|this morning|this afternoon|this evening|tomorrow|later|now|the weekend)\b", re.I)
_ASKS_WHAT_TO_WEAR = re.compile(
    r"(what should i wear|what do i wear|what to wear|help me dress|dress me|style me|"
    r"what should i put on|outfit ideas?|pick (?:me )?an outfit)", re.I)
_HAS_OCCASION = re.compile(
    r"\b(work|office|meeting|presentation|conference|interview|wedding|funeral|church|"
    r"date|dinner|lunch|brunch|drinks|party|birthday|club|nightclub|pub|gig|concert|theatre|"
    r"movie|movies|cinema|picnic|bbq|barbecue|school|uni|gym|workout|yoga|run|walk|hike|beach|"
    r"pool|shopping|errands|airport|flight|travel|holiday|vacation|graduation|christening|"
    r"baby shower|race day|gala|formal|black tie|cocktail|casual|smart casual|home|"
    r"working from home|festival|funeral|reunion|girls night|night out|weekend away)\b", re.I)


_UNRESTRICTED = re.compile(
    r"(does\s*n[o']?t have to (?:be|use|come from)|doesn't have to (?:be|use)|"
    r"not (?:just )?from my wardrobe|outside my wardrobe|don'?t (?:have to |need to )?use (?:my|anything i own)|"
    r"completely different (?:look|style|outfit)|totally different (?:look|style|outfit)|style reset|"
    r"new look entirely|anything at all|ignore my wardrobe|regardless of what i own)", re.I)


def needs_occasion_context(messages: List["StylistChatMessage"]) -> bool:
    """True when the user has asked what to wear but given nothing to style for.
    One short follow-up beats a confident guess — and we only ever ask once."""
    users = [m.content or "" for m in messages if (m.role or "").lower() == "user"]
    if not users:
        return False
    latest = users[-1]
    if not _ASKS_WHAT_TO_WEAR.search(latest):
        return False
    # An explicit "give me something completely different, it doesn't have to be
    # from my wardrobe" is a clear brief — never answer it with a question.
    if any(_UNRESTRICTED.search(u) for u in users):
        return False
    # Never ask twice in the same conversation.
    for m in messages[:-1]:
        if (m.role or "").lower() == "assistant" and (m.content or "").rstrip().endswith("?"):
            return False
    # Any occasion mentioned anywhere in the conversation is enough to proceed.
    return not any(_HAS_OCCASION.search(u) for u in users)


def occasion_question(text: str) -> str:
    when = _VAGUE_TIME.search(text or "")
    when_txt = when.group(0).lower() if when else "it"
    return (f"Happy to style you — what are you doing {when_txt}? "
            "Tell me the occasion (work, dinner, date, church, drinks, something casual…) "
            "and I'll build the right look.")


class StylistChatRequest(BaseModel):
    messages: List[StylistChatMessage]
    temperature: Optional[float] = None
    weather: Optional[str] = None
    item_ids: List[str] = []   # pieces the user attached to the conversation
    thread_id: Optional[str] = None  # continue an existing conversation


def thread_title_from(text: str) -> str:
    """A short, human title so a saved conversation is recognisable at a glance."""
    t = re.sub(r"\s+", " ", (text or "").strip()).strip(" ?.!,")
    if not t:
        return "Styling chat"
    words = t.split(" ")
    title = " ".join(words[:6])
    return (title[:1].upper() + title[1:])[:48]


async def persist_stylist_turn(user: dict, thread_id: Optional[str], user_text: str,
                               reply: str, outfit: Optional[dict]) -> str:
    """Conversations live in Mongo, so leaving the screen never loses them."""
    now = now_utc().isoformat()
    turn = [
        {"role": "user", "content": user_text, "created_at": now},
        {"role": "assistant", "content": reply,
         "outfit_item_ids": (outfit or {}).get("item_ids") or [], "created_at": now},
    ]
    thread = None
    if thread_id:
        thread = await db.stylist_threads.find_one(
            {"id": thread_id, "user_id": user["user_id"]}, {"_id": 0, "messages": 0}
        )
    if not thread:
        thread_id = new_id("sthread")
        await db.stylist_threads.insert_one({
            "id": thread_id, "user_id": user["user_id"],
            "title": thread_title_from(user_text), "summary": "",
            "messages": turn, "archived": False,
            "created_at": now, "updated_at": now,
        })
        return thread_id
    await db.stylist_threads.update_one(
        {"id": thread_id, "user_id": user["user_id"]},
        {"$push": {"messages": {"$each": turn}},
         "$set": {"updated_at": now, "archived": False}},
    )
    return thread_id


async def earlier_threads_line(user_id: str, current_id: Optional[str], limit: int = 3) -> str:
    """Summaries of earlier conversations — continuity without pretending to
    remember anything that was not actually stored."""
    rows = await db.stylist_threads.find(
        {"user_id": user_id, "summary": {"$nin": ["", None]}}, {"_id": 0, "messages": 0}
    ).sort("updated_at", -1).to_list(limit + 1)
    rows = [r for r in rows if r.get("id") != current_id][:limit]
    if not rows:
        return ""
    parts = [f"{r.get('title')}: {r.get('summary')}" for r in rows]
    return "EARLIER STYLING CONVERSATIONS with this user: " + " | ".join(parts) + "\n"


@api_router.post("/stylist/chat")
async def stylist_chat(payload: StylistChatRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    # A vague "what should I wear tonight?" gets one short question instead of a
    # guessed outfit. No AI call, so it costs the user nothing.
    latest_user = next((m.content for m in reversed(payload.messages) if (m.role or "").lower() == "user"), "")
    if needs_occasion_context(payload.messages):
        question = occasion_question(latest_user)
        tid = await persist_stylist_turn(user, payload.thread_id, latest_user, question, None)
        return {"reply": question, "outfit": None, "needs_context": True, "thread_id": tid}
    await enforce_limit(user, "stylist")
    all_items = await wardrobe_pool(user, 1000)
    items = available_items(all_items)
    wardrobe = summarize_items_for_ai(items) if items else "No items yet."
    weather_line = ""
    if payload.temperature is not None:
        weather_line = f"Current weather: {payload.temperature}°C, {payload.weather or 'n/a'}.\n"
    else:
        # Aureve reads the weather itself, so never send the user hunting for it.
        weather_line = (
            "Today's local weather could not be read just now. Style for the season and for what "
            "they describe. NEVER ask the user for their city, location or the weather, and never "
            "state what the weather is.\n"
        )
    # Pieces the user attached to the conversation ("style this", "what goes with this?").
    attached_line = ""
    if payload.item_ids:
        by_id_all = {it["id"]: it for it in all_items}
        named = [by_id_all[i] for i in payload.item_ids if i in by_id_all]
        if named:
            attached_line = (
                "THE USER IS ASKING ABOUT THESE SPECIFIC PIECES: "
                + "; ".join(f"{it.get('name')} (id {it['id']}, {it.get('category')}, {it.get('colour')})" for it in named)
                + ". Talk about these pieces directly.\n"
            )
    # Saved outfits give the stylist a feel for the looks they like enough to keep.
    saved = await db.outfits.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(8)
    saved_line = ""
    if saved:
        saved_line = "OUTFITS THEY HAVE SAVED: " + "; ".join(
            f"{o.get('name')} [{','.join(o.get('item_ids', []))}]" for o in saved
        ) + "\n"
    prefs = await learned_prefs(user["user_id"])
    convo = "\n".join(f"{m.role.upper()}: {m.content}" for m in payload.messages[-12:])
    prompt = (
        f"{profile_context(user)}\n{weather_line}"
        f"{attached_line}"
        f"Learned preferences: {prefs}\n"
        f"{underused_line(items)}"
        f"{await recent_looks_line(user['user_id'])}"
        f"{saved_line}"
        f"{await earlier_threads_line(user['user_id'], payload.thread_id)}"
        f"WARDROBE (use only these ids; 'worn' shows how often each piece has actually been worn):\n{wardrobe}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        "Reply as Aureve to the user's most recent message, referring to their real pieces by name. "
        "If their request is missing the one detail you genuinely need (usually the occasion), ask a "
        "single short question instead of guessing, and do not include an outfit block in that reply."
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
            await hydrate_photos(user, resolved)
            outfit = {"name": o.get("name", "Outfit"), "item_ids": [r["id"] for r in resolved], "items": resolved}
        reply = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", resp, flags=re.DOTALL).strip()
    if not reply:
        reply = "Here's what I'd suggest from your wardrobe."
    thread_id = await persist_stylist_turn(user, payload.thread_id, latest_user, reply, outfit)
    return {"reply": reply, "outfit": outfit, "thread_id": thread_id}


THREAD_SUMMARY_SYSTEM = (
    "You summarise a styling conversation for the user's own journal. Return STRICT JSON with keys: "
    "title (3-5 words naming the topic, e.g. 'Everyday polished style'), "
    "summary (1-2 short sentences, written to the user in the second person, saying what they wanted), "
    "recommendations (array of 1-3 very short strings capturing what Aureve actually recommended). "
    "Never invent anything that was not discussed. Return ONLY JSON."
)


@api_router.get("/stylist/threads")
async def list_stylist_threads(user: dict = Depends(get_scope)):
    """The stylist journal — past conversations, newest first."""
    rows = await db.stylist_threads.find(
        {"user_id": user["user_id"]}, {"_id": 0, "messages": 0}
    ).sort("updated_at", -1).to_list(40)
    for r in rows:
        r["recommendations"] = r.get("recommendations") or []
    return rows


@api_router.get("/stylist/threads/{thread_id}")
async def get_stylist_thread(thread_id: str, user: dict = Depends(get_scope)):
    thread = await db.stylist_threads.find_one(
        {"id": thread_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not thread:
        raise HTTPException(status_code=404, detail="That conversation isn't saved.")
    return thread


@api_router.post("/stylist/threads/{thread_id}/archive")
async def archive_stylist_thread(thread_id: str, user: dict = Depends(get_scope)):
    """Called when the user starts a new chat: the old conversation is kept and
    given a title, summary and the recommendations it produced."""
    thread = await db.stylist_threads.find_one(
        {"id": thread_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not thread:
        raise HTTPException(status_code=404, detail="That conversation isn't saved.")
    msgs = thread.get("messages") or []
    title = thread.get("title") or "Styling chat"
    summary = thread.get("summary") or ""
    recs: List[str] = thread.get("recommendations") or []
    if msgs and EMERGENT_LLM_KEY:
        convo = "\n".join(f"{m.get('role', '').upper()}: {m.get('content', '')}" for m in msgs[-20:])
        try:
            chat = await ai_chat(f"sthread-{user['user_id']}-{uuid.uuid4().hex[:6]}", THREAD_SUMMARY_SYSTEM)
            resp = await chat.send_message(UserMessage(text=f"Conversation:\n{convo}\n\nReturn JSON only."))
            parsed = parse_json_block(resp) or {}
            title = (parsed.get("title") or title)[:48]
            summary = parsed.get("summary") or summary
            recs = [str(r)[:160] for r in (parsed.get("recommendations") or [])][:3]
        except Exception:
            logger.exception("thread summary failed")
    if not summary:
        first_user = next((m.get("content") for m in msgs if m.get("role") == "user"), "")
        summary = (first_user or "")[:180]
    await db.stylist_threads.update_one(
        {"id": thread_id, "user_id": user["user_id"]},
        {"$set": {"archived": True, "title": title, "summary": summary,
                  "recommendations": recs, "updated_at": now_utc().isoformat()}},
    )
    return {"ok": True, "id": thread_id, "title": title, "summary": summary, "recommendations": recs}


def necessity_for(item: dict, ai_value: str, temperature: Optional[float],
                  weather: Optional[str]) -> str:
    """The core outfit is what you actually wear; everything else is an extra.
    The AI's own call is respected for outerwear, but clothing/shoes can never be
    demoted and bags/jewellery/accessories can never be presented as essential."""
    cat = str(item.get("category") or "")
    if cat in ("Tops", "Bottoms", "Dresses", "Shoes"):
        return "core"
    if cat == "Outerwear":
        cold_or_wet = (temperature is not None and temperature <= 15) or bool(
            re.search(r"rain|drizzle|shower|snow|storm|wind", str(weather or ""), re.I)
        )
        if cold_or_wet:
            return "core"
        return "recommended" if ai_value in ("core", "recommended") else "optional"
    # Bags, Jewellery, Accessories
    return "recommended" if ai_value == "recommended" else "optional"


async def _build_outfit(user: dict, occasion: str, temperature: Optional[float],
                        weather: Optional[str], notes: Optional[str],
                        avoid_item_ids: Optional[List[str]] = None,
                        source: str = "stylist",
                        base_item_ids: Optional[List[str]] = None):
    items = await wardrobe_pool(user, 1000)
    items = available_items(items)
    if len(items) < 2:
        raise HTTPException(status_code=400, detail="Not enough ready-to-wear items. Add more, or mark laundry as clean.")

    explicit_avoid = {i for i in (avoid_item_ids or []) if i}
    # Create Another Look is a hard instruction, not a polite hint. When the
    # wardrobe has enough alternatives, remove the current look from the candidate
    # pool entirely so the model cannot simply return it again.
    if explicit_avoid:
        alternatives = [it for it in items if it.get("id") not in explicit_avoid]
        if len(alternatives) >= 2:
            items = alternatives

    suggestion_history = await recent_suggestions(user["user_id"], source=source) if source == "dressme" else []
    prefs = await learned_prefs(user["user_id"])
    wardrobe = summarize_items_for_ai(items)
    weather_line = ""
    if temperature is not None:
        weather_line = f"Temperature: {temperature}°C. Conditions: {weather or 'n/a'}."
    variety_line = ""
    if explicit_avoid:
        variety_line = (
            "EXPLICIT EXCLUSION: the previous/current look must not be repeated. "
            f"Excluded item ids: {','.join(sorted(explicit_avoid))}. "
            "Build a materially different silhouette and hero-piece combination.\n"
        )
    refresh_line = ""
    base_ids = [i for i in (base_item_ids or []) if i]
    if base_ids:
        by_id_base = {it["id"]: it for it in items}
        listed = "; ".join(
            f"{by_id_base[i].get('name')} (id {i}, {by_id_base[i].get('category')})"
            for i in base_ids if i in by_id_base
        )
        refresh_line = (
            "REFRESH AN OUTFIT THEY ALREADY LIKE. Their current outfit is: "
            f"{listed or ', '.join(base_ids)}. Keep the pieces that still work for this "
            "occasion and weather — especially the hero/favourite piece — and change only "
            "ONE or TWO pieces so the look feels fresh rather than new. Do NOT rebuild the "
            "outfit from scratch and do not change everything.\n"
        )
    prompt = (
        f"Occasion: {occasion}\n{weather_line}\n"
        f"Extra notes: {notes or 'none'}\n"
        f"{variety_line}"
        f"{refresh_line}"
        f"{recent_suggestions_line(suggestion_history)}"
        f"{underused_line(items)}"
        f"{await recent_looks_line(user['user_id'])}"
        f"{profile_context(user)}\n"
        f"Learned preferences: {prefs}\n\n"
        f"WARDROBE (use only these ids; 'worn' shows how often each piece has been worn):\n{wardrobe}\n\n"
        "Build one cohesive, weather- and occasion-appropriate outfit: the core pieces first, and extras only "
        "when they genuinely add something (it is fine to return none). Work the WIDER wardrobe: "
        "where a forgotten or rarely-worn piece genuinely suits this occasion and weather, choose it "
        "over an obvious favourite and say so in its reason. Never force an unsuitable item just "
        "because it is underused — relevance always wins. Return JSON only."
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
            nec = str(slot.get("necessity") or "").strip().lower()
            if nec not in ("core", "recommended", "optional"):
                nec = ""
            enriched.append({
                "slot": slot.get("slot", it.get("category")),
                "necessity": necessity_for(it, nec, temperature, weather),
                "reason": slot.get("reason", ""),
                "item": it,
            })
    await hydrate_photos(user, [x["item"] for x in enriched])
    result["resolved_items"] = enriched
    selected_ids = [x["item"]["id"] for x in enriched if x.get("item")]
    if explicit_avoid and any(i in explicit_avoid for i in selected_ids):
        logger.warning("STYLE_ROTATION source=%s exclusion_violation avoid=%s selected=%s", source, sorted(explicit_avoid), selected_ids)
    else:
        logger.info("STYLE_ROTATION source=%s avoid=%s recent=%s selected=%s", source, sorted(explicit_avoid), len(suggestion_history), selected_ids)
    await record_style_suggestion(user["user_id"], source, occasion, selected_ids)
    return result


class DressMeRequest(BaseModel):
    temperature: Optional[float] = None
    weather: Optional[str] = None
    occasion: Optional[str] = None  # override; otherwise inferred from today's plan
    avoid_item_ids: List[str] = []  # current on-screen look when asking for another
    local_date: Optional[str] = None  # the user's OWN calendar date (YYYY-MM-DD)
    tz_offset: Optional[int] = None   # minutes east of UTC, so the day is the user's local day


@api_router.get("/dressme/context")
async def dressme_context(date: Optional[str] = None, tz_offset: int = 0,
                          user: dict = Depends(get_scope)):
    """Does today already have useful context (a planned look or calendar
    events)? If not, the app asks the user what they're doing before styling.
    `date` is the user's LOCAL calendar date — without it a UTC 'today' can read
    the previous day's plan for anyone ahead of UTC."""
    today = date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or "") else now_utc().strftime("%Y-%m-%d")
    plan = await db.plans.find_one({"user_id": user["user_id"], "date": today}, {"_id": 0})
    plan_occasion = ((plan or {}).get("occasion") or (plan or {}).get("title") or "").strip()
    events = await _gcal_events(user["account_id"], today, tz_offset)
    label = plan_occasion or (_fmt_events_for_ai(events) if events else "")
    return {
        "has_context": bool(plan_occasion or events),
        "source": "plan" if plan_occasion else ("calendar" if events else None),
        "label": label,
    }


@api_router.post("/dressme")
async def dress_me(payload: DressMeRequest, user: dict = Depends(get_scope)):
    """Flagship one-tap daily outfit — infers today's occasion from the planner
    (falls back to a normal day) and styles from the ready wardrobe + weather."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "dressme")
    today = (payload.local_date
             if re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload.local_date or "")
             else now_utc().strftime("%Y-%m-%d"))
    occasion = (payload.occasion or "").strip()
    plan_title = None
    cal_events = await _gcal_events(user["account_id"], today, payload.tz_offset or 0)
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
    result = await _build_outfit(
        user, occasion, payload.temperature, payload.weather, notes,
        payload.avoid_item_ids, source="dressme"
    )
    result["occasion_used"] = occasion
    result["from_plan"] = plan_title
    result["calendar_events"] = cal_events
    return result


class MixRequest(BaseModel):
    """Mix It Up — refresh an outfit the user already wore, keeping the pieces
    that still work and changing only one or two."""
    item_ids: List[str] = []
    wear_log_id: Optional[str] = None
    outfit_id: Optional[str] = None
    occasion: Optional[str] = ""
    temperature: Optional[float] = None
    weather: Optional[str] = None


@api_router.post("/outfits/mix")
async def mix_outfit(payload: MixRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    base_ids = [i for i in (payload.item_ids or []) if i]
    occasion = (payload.occasion or "").strip()
    if not base_ids and payload.wear_log_id:
        log = await db.wear_logs.find_one(
            {"id": payload.wear_log_id, "user_id": user["user_id"]}, {"_id": 0}
        )
        base_ids = [i for i in ((log or {}).get("item_ids") or []) if i]
        occasion = occasion or (log or {}).get("occasion") or ""
    if not base_ids and payload.outfit_id:
        outfit = await db.outfits.find_one(
            {"id": payload.outfit_id, "user_id": user["user_id"]}, {"_id": 0}
        )
        base_ids = [i for i in ((outfit or {}).get("item_ids") or []) if i]
        occasion = occasion or (outfit or {}).get("occasion") or ""
    if not base_ids:
        raise HTTPException(status_code=400, detail="Nothing to mix up — that look has no pieces.")
    await enforce_limit(user, "dressme")
    occasion = occasion or "a refreshed version of a look they already like"
    result = await _build_outfit(
        user, occasion, payload.temperature, payload.weather,
        "Mix it up — keep what works from this outfit and change only one or two pieces.",
        None, source="mix", base_item_ids=base_ids,
    )
    result["occasion_used"] = occasion
    result["mixed_from_item_ids"] = base_ids
    return result


# ----------------------------- AI: Virtual Try-On (Nano Banana) -----------------------------
class TryOnRequest(BaseModel):
    person_image: str            # base64 (no data-uri prefix) of the user
    item_ids: List[str] = []     # garments to render onto the person
    outfit_id: Optional[str] = None


@api_router.post("/tryon", dependencies=[Depends(unreleased("tryon"))])
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
        {**items_scope(user), "id": {"$in": item_ids}}, {"_id": 0, "orig_photo": 0}
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


@api_router.get("/tryon/photo", dependencies=[Depends(unreleased("tryon"))])
async def get_body_photo(user: dict = Depends(get_scope)):
    """The remembered full-body photo for the active profile (so try-on doesn't re-upload)."""
    doc = await db.body_photos.find_one({"profile_id": user["profile_id"]}, {"_id": 0})
    return {"photo": (doc or {}).get("photo")}


@api_router.put("/tryon/photo", dependencies=[Depends(unreleased("tryon"))])
async def set_body_photo(payload: BodyPhoto, user: dict = Depends(get_scope)):
    await db.body_photos.update_one(
        {"profile_id": user["profile_id"]},
        {"$set": {"profile_id": user["profile_id"], "photo": payload.photo, "updated_at": now_utc().isoformat()}},
        upsert=True,
    )
    return {"ok": True}


@api_router.delete("/tryon/photo", dependencies=[Depends(unreleased("tryon"))])
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


async def _gcal_events(account_id: str, date_str: str, tz_offset: int = 0) -> List[dict]:
    token = await _gcal_valid_token(account_id)
    if not token:
        return []
    try:
        day = datetime.fromisoformat(date_str)
    except Exception:
        day = now_utc()
    # tz_offset = minutes east of UTC, so the window is the user's LOCAL day.
    start = (day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
             - timedelta(minutes=tz_offset or 0))
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


def _gcal_redirect_uri(request: Request) -> str:
    """The OAuth redirect must match the registered URI EXACTLY (scheme, host,
    path) or Google returns redirect_uri_mismatch. Derived from the incoming
    request so preview and production each send their own host; the scheme is
    forced to https for real hosts because TLS is terminated at the ingress and
    the app server only ever sees http."""
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    if not host:
        return GCAL_REDIRECT_URI
    local = host.startswith("localhost") or host.startswith("127.0.0.1")
    # Drop the default port so the URI matches what is registered.
    if host.endswith(":443") or host.endswith(":80"):
        host = host.rsplit(":", 1)[0]
    scheme = "http" if local else "https"
    return f"{scheme}://{host}/api/calendar/callback"


@api_router.get("/diag/my-wardrobe-audit")
async def my_wardrobe_audit(account: dict = Depends(get_current_user)):
    """STRICTLY READ-ONLY audit of the CALLER'S OWN account: every wardrobe
    (profile) they own, how many items sit in each, how many are real vs seeded
    demo, and whether any items are stranded on a scope the app no longer shows.
    Makes no writes of any kind."""
    account_id = account["user_id"]
    profiles = await db.profiles.find({"user_id": account_id}, {"_id": 0}).sort("created_at", 1).to_list(50)
    wardrobes = []
    for p in profiles:
        total = await db.items.count_documents({"user_id": p["id"]})
        demo = await db.items.count_documents({"user_id": p["id"], "demo": True})
        no_photo = await db.items.count_documents(
            {"user_id": p["id"], "$or": [{"photo": None}, {"photo": ""}]}
        )
        first = await db.items.find({"user_id": p["id"]}, {"_id": 0, "created_at": 1}).sort("created_at", 1).to_list(1)
        last = await db.items.find({"user_id": p["id"]}, {"_id": 0, "created_at": 1}).sort("created_at", -1).to_list(1)
        wardrobes.append({
            "profile_id": p["id"],
            "name": p.get("name"),
            "created_at": p.get("created_at"),
            "items_total": total,
            "items_real": total - demo,
            "items_demo_seeded": demo,
            "items_without_photo": no_photo,
            "first_item_at": (first[0].get("created_at") if first else None),
            "last_item_at": (last[0].get("created_at") if last else None),
        })

    # Items written against the raw account id instead of a profile id would be
    # invisible in the app — surface them rather than silently losing them.
    stranded = await db.items.count_documents({"user_id": account_id})

    recent = await db.items.find(
        {"user_id": {"$in": [p["id"] for p in profiles] + [account_id]}},
        {"_id": 0, "name": 1, "category": 1, "created_at": 1, "user_id": 1, "photo": 1, "demo": 1},
    ).sort("created_at", -1).to_list(60)
    recent_list = [{
        "name": it.get("name"),
        "category": it.get("category"),
        "created_at": it.get("created_at"),
        "scope": it.get("user_id"),
        "has_photo": bool(it.get("photo")),
        "demo": bool(it.get("demo")),
    } for it in recent]

    # Same email signed up through a different provider = a SECOND account whose
    # wardrobe would look "missing". Restricted to the caller's own email.
    others = []
    email = _norm_email(account.get("email") or "")
    if email:
        dupes = await db.users.find(
            {"email": email, "user_id": {"$ne": account_id}}, {"_id": 0, "password_hash": 0}
        ).to_list(10)
        for d in dupes:
            d_profiles = await db.profiles.find({"user_id": d["user_id"]}, {"_id": 0}).to_list(20)
            wl = []
            for dp in d_profiles:
                tot = await db.items.count_documents({"user_id": dp["id"]})
                dem = await db.items.count_documents({"user_id": dp["id"], "demo": True})
                wl.append({"name": dp.get("name"), "items_total": tot, "items_real": tot - dem})
            others.append({
                "user_id": d["user_id"],
                "provider": d.get("provider"),
                "created_at": d.get("created_at"),
                "wardrobes": wl,
            })

    return {
        "account_email": account.get("email"),
        "account_id": account_id,
        "provider": account.get("provider"),
        "is_guest": bool(account.get("is_guest")),
        "wardrobes": wardrobes,
        "items_stranded_on_account_id": stranded,
        "items_total_all_wardrobes": sum(w["items_total"] for w in wardrobes) + stranded,
        "other_accounts_same_email": others,
        "recent_items": recent_list,
        "read_only": True,
    }


@api_router.get("/diag/wardrobe-scan")
async def wardrobe_scan(email: Optional[str] = None, account: dict = Depends(get_current_user)):
    """STRICTLY READ-ONLY scan to locate a wardrobe that is not showing up in the
    app (e.g. catalogued under a different sign-in method or under a guest
    session that was never migrated). Requires a valid session. Returns counts
    and coarse metadata only — no item names, no photos, emails partially
    masked. Diagnostic aid; makes no writes."""
    def mask(e: Optional[str]) -> str:
        if not e or "@" not in e:
            return e or ""
        name, dom = e.split("@", 1)
        return f"{name[:2]}***@{dom}"

    async def wardrobes_of(uid: str):
        out = []
        for pr in await db.profiles.find({"user_id": uid}, {"_id": 0}).sort("created_at", 1).to_list(20):
            total = await db.items.count_documents({"user_id": pr["id"]})
            demo = await db.items.count_documents({"user_id": pr["id"], "demo": True})
            last = await db.items.find({"user_id": pr["id"]}, {"_id": 0, "created_at": 1}).sort("created_at", -1).to_list(1)
            out.append({
                "profile_id": pr["id"],
                "name": pr.get("name"),
                "items_total": total,
                "items_real": total - demo,
                "items_demo": demo,
                "last_item_at": (last[0].get("created_at") if last else None),
            })
        return out

    matches = []
    if email:
        for u in await db.users.find({"email": _norm_email(email)}, {"_id": 0, "password_hash": 0}).to_list(10):
            matches.append({
                "account_id": u["user_id"],
                "email": mask(u.get("email")),
                "provider": u.get("provider") or "email",
                "is_guest": bool(u.get("is_guest")),
                "created_at": u.get("created_at"),
                "wardrobes": await wardrobes_of(u["user_id"]),
            })

    # Largest wardrobes in this database that hold REAL (non-demo) pieces. This
    # is how an unmigrated guest wardrobe gets found — guests have no email.
    biggest = []
    pipeline = [
        {"$match": {"demo": {"$ne": True}}},
        {"$group": {"_id": "$user_id", "n": {"$sum": 1}, "last": {"$max": "$created_at"}}},
        {"$sort": {"n": -1}},
        {"$limit": 10},
    ]
    async for row in db.items.aggregate(pipeline):
        pr = await db.profiles.find_one({"id": row["_id"]}, {"_id": 0})
        owner = await db.users.find_one({"user_id": pr["user_id"]}, {"_id": 0}) if pr else None
        biggest.append({
            "scope": row["_id"],
            "real_items": row["n"],
            "last_item_at": row.get("last"),
            "wardrobe_name": (pr or {}).get("name"),
            "owner_account_id": (pr or {}).get("user_id"),
            "owner_email": mask((owner or {}).get("email")),
            "owner_provider": (owner or {}).get("provider") or ("guest" if (owner or {}).get("is_guest") else "email"),
            "owner_is_guest": bool((owner or {}).get("is_guest")),
            "orphaned": pr is None,
        })

    return {
        "queried_email": email,
        "accounts_for_email": matches,
        "largest_real_wardrobes": biggest,
        "read_only": True,
    }


@api_router.get("/calendar/config")
async def calendar_config(request: Request):
    """Read-only OAuth diagnostic: shows the EXACT redirect_uri this environment
    sends to Google and which client id is in use, so it can be compared with
    what is registered on the Google Cloud OAuth client. The client id is public
    (it appears in the OAuth URL); the client secret is never returned."""
    cid = GCAL_CLIENT_ID or ""
    sent = _gcal_redirect_uri(request)
    return {
        "redirect_uri_sent_to_google": sent,
        "register_this_exact_uri_in_google_console": sent,
        "client_id": cid,
        "client_id_prefix": cid[:20],
        "client_id_length": len(cid),
        "client_secret_present": bool(GCAL_CLIENT_SECRET),
        "client_secret_length": len(GCAL_CLIENT_SECRET or ""),
        # Non-reversible fingerprint so the deployed secret can be compared with
        # the intended one without ever exposing it.
        "client_secret_fingerprint": (
            hashlib.sha256(GCAL_CLIENT_SECRET.encode()).hexdigest()[:10] if GCAL_CLIENT_SECRET else None
        ),
        "env_redirect_uri_fallback": GCAL_REDIRECT_URI,
        "request_host": request.headers.get("host"),
        "forwarded_host": request.headers.get("x-forwarded-host"),
        "forwarded_proto": request.headers.get("x-forwarded-proto"),
        "scope": GCAL_SCOPE,
        "last_callback_error": GCAL_LAST_ERROR or None,
    }


@api_router.get("/calendar/authorize")
async def calendar_authorize(request: Request, account: dict = Depends(get_current_user)):
    if not GCAL_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Calendar is not configured.")
    # A Google client secret is ~35 chars ("GOCSPX-..."). Anything shorter means
    # the deployed environment holds a truncated/placeholder value, which would
    # fail with invalid_client only AFTER the user granted access.
    if len(GCAL_CLIENT_SECRET) < 20:
        logger.error("gcal authorize blocked: client secret looks invalid (len=%s)", len(GCAL_CLIENT_SECRET))
        raise HTTPException(
            status_code=500,
            detail="Calendar isn't configured correctly on the server yet. Please try again later.",
        )
    redirect_uri = _gcal_redirect_uri(request)
    state = uuid.uuid4().hex
    await db.calendar_oauth_states.update_one(
        {"state": state},
        {"$set": {"state": state, "account_id": account["user_id"],
                  "redirect_uri": redirect_uri, "created_at": now_utc().isoformat()}},
        upsert=True,
    )
    params = {
        "client_id": GCAL_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GCAL_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + _urlparse.urlencode(params)
    logger.info("gcal authorize: redirect_uri=%s", redirect_uri)
    return {"url": url}


@app.get("/api/calendar/callback")
async def calendar_callback(request: Request, code: Optional[str] = None,
                            state: Optional[str] = None, error: Optional[str] = None):
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
    redirect_uri = st.get("redirect_uri") or _gcal_redirect_uri(request)
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GCAL_CLIENT_ID,
            "client_secret": GCAL_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
    await db.calendar_oauth_states.delete_one({"state": state})
    if r.status_code != 200:
        try:
            err = r.json()
        except Exception:
            err = {"error": "unknown"}
        reason = str(err.get("error") or "unknown")
        detail = str(err.get("error_description") or "")
        logger.error("gcal token exchange failed (%s): %s", r.status_code, r.text[:300])
        GCAL_LAST_ERROR.clear()
        GCAL_LAST_ERROR.update({
            "at": now_utc().isoformat(),
            "status": r.status_code,
            "error": reason,
            "error_description": detail,
            "client_id_prefix": (GCAL_CLIENT_ID or "")[:20],
            "redirect_uri": redirect_uri,
        })
        # Surface Google's own reason: invalid_client = the deployed client
        # id/secret pair doesn't match the OAuth client that granted consent.
        return _page(f"Couldn't connect calendar ({reason})")
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
    focus = await db.items.find_one({**items_scope(user), "id": item_id}, {"_id": 0, "orig_photo": 0})
    if not focus:
        raise HTTPException(status_code=404, detail="Item not found")
    others = [it for it in await wardrobe_pool(user, 1000) if it.get("id") != item_id]
    others = available_items(others)
    if len(others) < 1:
        raise HTTPException(status_code=400, detail="Add more items to see what pairs together")
    # Big wardrobes: score locally first and only ask the AI to rate the
    # strongest shortlist, so the request stays fast and never times out.
    total_compatible = sum(1 for it in others if _items_pair(focus, it))
    if len(others) > 14:
        pairable = [it for it in others if _items_pair(focus, it)]
        pool = pairable or others
        pool = sorted(pool, key=lambda it: ((it.get("wear_count", 0) or 0), it.get("name") or ""))
        others = pool[:12]
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
    await hydrate_photos(user, [m["item"] for m in resolved])
    result["match_count"] = len([m for m in resolved if m["stars"] >= 3])
    result["total_compatible"] = total_compatible
    result["shortlisted"] = len(others)
    result["focus"] = focus
    return result


OUTFIT_FEEDBACK_SYSTEM = (
    "You are Aureve, a warm, expert personal stylist. The user has put together their OWN outfit and "
    "wants your honest feedback on it. Be specific and genuinely useful — a good stylist tells the "
    "truth. If the colours fight, the proportions are off, the formality is mismatched, the seasons "
    "clash or one piece is clearly letting the look down, say so plainly and explain why. Do NOT open "
    "with a compliment you do not mean and do NOT praise an outfit that is not working; equally, if it "
    "genuinely works, say so and say why. Never mock or criticise the user, their body or their taste "
    "— judge the clothes, not the person. Assess colour harmony, formality, proportion and silhouette, "
    "season/weather suitability, the footwear, competing textures or patterns and overall cohesion "
    "— then comment on the ones that actually matter for this look and, "
    "only if it would clearly improve the look, suggest ONE optional "
    "swap using an item id from the REST OF WARDROBE list. A swap MUST stay in the SAME category as "
    "the piece it replaces (shoes for shoes, top for top, bottom for bottom, outerwear for "
    "outerwear) — never swap across categories. If what would really help is ADDING a piece the "
    "outfit does not have (e.g. a blazer over a top), do NOT put it in swap: describe it in `tip` "
    "instead. Never suggest replacing more than one piece and never invent items. Describe ONLY the "
    "pieces listed in THE USER'S OUTFIT — never speak as though an extra item is already being worn. "
    "Return STRICT JSON with keys: verdict (a short honest headline — it may be positive OR flag the "
    "main problem), feedback (2-3 sentences: what works, what does not, and why), swap (either null or an object: out_id, in_id, why — one short line), "
    "tip (optional one short line). Return ONLY JSON."
)


class OutfitFeedbackRequest(BaseModel):
    item_ids: List[str]
    temperature: Optional[float] = None
    weather: Optional[str] = ""
    occasion: Optional[str] = ""


@api_router.post("/outfit/feedback")
async def outfit_feedback(payload: OutfitFeedbackRequest, user: dict = Depends(get_scope)):
    """Feedback on the outfit the user chose themselves. Never returns a whole
    new look — at most one optional swap, in the context of their full outfit."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    ids = [i for i in (payload.item_ids or []) if i]
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="Pick at least two pieces first.")
    await enforce_limit(user, "stylist")
    all_items = await wardrobe_pool(user, 1000)
    by_id = {it["id"]: it for it in all_items}
    chosen = [by_id[i] for i in ids if i in by_id]
    if len(chosen) < 2:
        raise HTTPException(status_code=404, detail="Those pieces are no longer in your wardrobe.")
    rest = available_items([it for it in all_items if it["id"] not in set(ids)])[:60]
    weather_line = (f"Weather: {payload.temperature}°C, {payload.weather}.\n"
                    if payload.temperature is not None else "")
    prompt = (
        f"{profile_context(user)}\n{weather_line}"
        f"Occasion: {payload.occasion or 'not specified'}\n\n"
        f"THE USER'S OUTFIT:\n{summarize_items_for_ai(chosen)}\n\n"
        f"REST OF WARDROBE (only source for an optional swap):\n{summarize_items_for_ai(rest)}\n\n"
        "Give feedback on THIS outfit. Return JSON only."
    )
    chat = await ai_chat(f"outfitfb-{user['user_id']}-{uuid.uuid4().hex[:6]}", OUTFIT_FEEDBACK_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("outfit feedback failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp) or {}
    if not result.get("feedback"):
        raise HTTPException(status_code=502, detail="Could not review this outfit")
    swap = result.get("swap") if isinstance(result.get("swap"), dict) else None
    result["swap"] = None
    if swap:
        out_it, in_it = by_id.get(swap.get("out_id")), by_id.get(swap.get("in_id"))
        same_slot = bool(out_it and in_it) and _norm(out_it.get("category")) == _norm(in_it.get("category"))
        if out_it and in_it and out_it["id"] in set(ids) and same_slot:
            await hydrate_photos(user, [out_it, in_it])
            result["swap"] = {
                "out_id": out_it["id"], "in_id": in_it["id"], "why": swap.get("why", ""),
                "out_item": out_it, "in_item": in_it,
            }
        elif out_it and in_it and not same_slot:
            # Cross-category "swap" is really an addition. Never let it empty a
            # slot — surface it as optional advice instead.
            result["addition"] = {
                "name": in_it.get("name"), "category": in_it.get("category"),
                "why": swap.get("why", ""),
            }
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
    "outfits_added (integer count of GENUINELY NEW outfits buying it would unlock — outfits they "
    "could not already build with an equivalent piece they own. If they already own something "
    "substantially the same, this MUST be 0, because the same looks are already possible), "
    "fills_gap (boolean), gap_note (short string about the wardrobe gap it does or does not fill). "
    "Only use ids that exist in the wardrobe. Return ONLY JSON."
)


@api_router.post("/shop-check")
async def shop_check(payload: AnalyzeRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "shop")
    items = await wardrobe_pool(user, 1000)
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
    await hydrate_photos(user, result["similar_items"] + result["matches_with"])
    # A duplicate cannot "unlock" outfits the user can already build with the piece
    # they own, so the result tells ONE story instead of contradicting itself.
    duplicate = bool(result["similar_items"]) and not result.get("fills_gap")
    if duplicate or str(result.get("verdict") or "").lower() == "skip":
        result["outfits_added"] = 0
    if duplicate:
        owned = result["similar_items"][0].get("name") or "piece"
        result["already_covered"] = f"You can already create similar looks with the {owned} you own."
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


async def slim_items_by_id(items: List[dict]) -> dict:
    """Items embedded in list responses (outfits, plans, looks) only ever render
    as small tiles, so ship the grid thumbnail and drop the stored originals.
    Full-resolution photos still come from GET /items/{id}."""
    out = {}
    backfilled = 0
    for it in items:
        thumb = it.get("thumb")
        if not thumb and backfilled < 20:
            thumb = make_thumb(it.get("photo") or it.get("worn_photo"))
            if thumb:
                await db.items.update_one({"id": it["id"]}, {"$set": {"thumb": thumb}})
                backfilled += 1
        slim = {k: v for k, v in it.items() if k not in ("orig_photo", "thumb")}
        if thumb:
            slim["photo"] = thumb
            slim["worn_photo"] = None
        out[it["id"]] = slim
    return out


@api_router.get("/outfits")
async def list_outfits(user: dict = Depends(get_scope)):
    outfit_query = {"user_id": user["user_id"]}
    if not user.get("show_demo"):
        outfit_query["demo"] = {"$ne": True}
    outfits = await db.outfits.find(outfit_query, {"_id": 0}).sort("created_at", -1).to_list(500)
    by_id = await slim_items_by_id(
        await db.items.find(items_scope(user), {"_id": 0, "orig_photo": 0}).to_list(1000)
    )
    for o in outfits:
        o["items"] = [by_id[i] for i in o.get("item_ids", []) if i in by_id]
    return outfits


@api_router.delete("/outfits/{outfit_id}")
async def delete_outfit(outfit_id: str, user: dict = Depends(get_scope)):
    await db.outfits.delete_one({"id": outfit_id, "user_id": user["user_id"]})
    # keep collections tidy — drop the removed outfit from any collection
    await db.collections.update_many(
        {"user_id": user["user_id"]}, {"$pull": {"outfit_ids": outfit_id}}
    )
    return {"ok": True}


# ----------------------------- Collections -----------------------------
class CollectionCreate(BaseModel):
    name: str


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    add_outfit: Optional[str] = None
    remove_outfit: Optional[str] = None


async def _resolve_collection(coll: dict, user: dict, with_outfits: bool = False):
    """Attach a small cover (up to 4 item photos) and the outfit count. When
    with_outfits is set, also return each outfit resolved with its items."""
    outfit_ids = coll.get("outfit_ids", [])
    outfits = await db.outfits.find(
        {"id": {"$in": outfit_ids}, "user_id": user["user_id"]}, {"_id": 0}
    ).to_list(500)
    order = {oid: i for i, oid in enumerate(outfit_ids)}
    outfits.sort(key=lambda o: order.get(o["id"], 999))
    items_by_id = await slim_items_by_id(
        await db.items.find(items_scope(user), {"_id": 0, "orig_photo": 0}).to_list(1000)
    )
    cover: List[dict] = []
    for o in outfits:
        for iid in o.get("item_ids", []):
            it = items_by_id.get(iid)
            if it and len(cover) < 4:
                cover.append({"photo": it.get("photo"), "category": it.get("category")})
        if len(cover) >= 4:
            break
    coll["count"] = len(outfit_ids)
    coll["cover"] = cover
    if with_outfits:
        for o in outfits:
            o["items"] = [items_by_id[i] for i in o.get("item_ids", []) if i in items_by_id]
        coll["outfits"] = outfits
    return coll


@api_router.post("/collections")
async def create_collection(payload: CollectionCreate, user: dict = Depends(get_scope)):
    coll = {
        "id": new_id("coll"),
        "user_id": user["user_id"],
        "name": payload.name.strip() or "Collection",
        "outfit_ids": [],
        "created_at": now_utc().isoformat(),
    }
    await db.collections.insert_one({**coll})
    coll.pop("_id", None)
    return await _resolve_collection(coll, user)


@api_router.get("/collections")
async def list_collections(user: dict = Depends(get_scope)):
    colls = await db.collections.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [await _resolve_collection(c, user) for c in colls]


@api_router.get("/collections/{collection_id}")
async def get_collection(collection_id: str, user: dict = Depends(get_scope)):
    coll = await db.collections.find_one({"id": collection_id, "user_id": user["user_id"]}, {"_id": 0})
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    return await _resolve_collection(coll, user, with_outfits=True)


@api_router.patch("/collections/{collection_id}")
async def update_collection(collection_id: str, payload: CollectionUpdate, user: dict = Depends(get_scope)):
    coll = await db.collections.find_one({"id": collection_id, "user_id": user["user_id"]}, {"_id": 0})
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    sets: dict = {}
    if payload.name is not None and payload.name.strip():
        sets["name"] = payload.name.strip()
    if sets:
        await db.collections.update_one({"id": collection_id, "user_id": user["user_id"]}, {"$set": sets})
    if payload.add_outfit:
        await db.collections.update_one({"id": collection_id, "user_id": user["user_id"]}, {"$addToSet": {"outfit_ids": payload.add_outfit}})
    if payload.remove_outfit:
        await db.collections.update_one({"id": collection_id, "user_id": user["user_id"]}, {"$pull": {"outfit_ids": payload.remove_outfit}})
    coll = await db.collections.find_one({"id": collection_id, "user_id": user["user_id"]}, {"_id": 0})
    return await _resolve_collection(coll, user, with_outfits=True)


@api_router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str, user: dict = Depends(get_scope)):
    await db.collections.delete_one({"id": collection_id, "user_id": user["user_id"]})
    return {"ok": True}


# ----------------------------- Outfit Planner -----------------------------
class PlanCreate(BaseModel):
    date: str  # YYYY-MM-DD
    title: Optional[str] = ""
    occasion: Optional[str] = ""
    outfit_id: Optional[str] = None
    item_ids: List[str] = []
    notes: Optional[str] = ""


@api_router.post("/plans", dependencies=[Depends(unreleased("planner"))])
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


@api_router.get("/plans", dependencies=[Depends(unreleased("planner"))])
async def list_plans(from_date: Optional[str] = None, to_date: Optional[str] = None,
                     user: dict = Depends(get_scope)):
    query: dict = {"user_id": user["user_id"]}
    if from_date or to_date:
        query["date"] = {}
        if from_date:
            query["date"]["$gte"] = from_date
        if to_date:
            query["date"]["$lte"] = to_date
    if not user.get("show_demo"):
        query["demo"] = {"$ne": True}
    plans = await db.plans.find(query, {"_id": 0}).sort("date", 1).to_list(500)
    by_id = await slim_items_by_id(
        await db.items.find(items_scope(user), {"_id": 0, "orig_photo": 0}).to_list(1000)
    )
    for p in plans:
        p["items"] = [by_id[i] for i in p.get("item_ids", []) if i in by_id]
    return plans


@api_router.delete("/plans/{plan_id}", dependencies=[Depends(unreleased("planner"))])
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


class WearConfirmRequest(BaseModel):
    date: str                 # the user's LOCAL calendar date (YYYY-MM-DD)
    item_ids: List[str] = []
    wore: bool = False


@api_router.get("/wear/pending")
async def pending_wear_check(date: str, user: dict = Depends(get_scope)):
    """The look suggested for the user's LOCAL yesterday, if we haven't already
    asked about it. Being suggested never counts as worn — only a Yes here does.
    `date` is supplied by the app so this follows the user's local day, not UTC."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    asked = await db.wear_prompts.find_one({"user_id": user["user_id"], "date": date})
    if asked:
        return {"pending": False}
    # Already logged a wear for that day? Nothing to ask.
    logged = await db.wear_logs.find_one({
        "user_id": user["user_id"], "created_at": {"$regex": f"^{date}"},
    })
    if logged:
        return {"pending": False}
    sugg = await db.style_suggestions.find(
        {"user_id": user["user_id"], "created_at": {"$regex": f"^{date}"}}, {"_id": 0},
    ).sort("created_at", -1).to_list(1)
    if not sugg:
        plan = await db.plans.find_one({"user_id": user["user_id"], "date": date}, {"_id": 0})
        ids = (plan or {}).get("item_ids") or []
        occasion = (plan or {}).get("occasion") or (plan or {}).get("title") or ""
    else:
        ids, occasion = sugg[0].get("item_ids") or [], sugg[0].get("occasion") or ""
    ids = [i for i in ids if i]
    if not ids:
        return {"pending": False}
    items = await db.items.find({**items_scope(user), "id": {"$in": ids}}, {"_id": 0, "orig_photo": 0}).to_list(20)
    if not items:
        return {"pending": False}
    return {
        "pending": True,
        "date": date,
        "occasion": occasion,
        "item_ids": [it["id"] for it in items],
        "items": [{"id": it["id"], "name": it.get("name"), "category": it.get("category"),
                   "photo": it.get("photo")} for it in items],
    }


@api_router.post("/wear/confirm")
async def confirm_wear(payload: WearConfirmRequest, user: dict = Depends(get_scope)):
    """Yes updates wear_count/last_worn for that local date; No leaves wear
    history completely untouched. Either way we never ask about that day again."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload.date or ""):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    await db.wear_prompts.update_one(
        {"user_id": user["user_id"], "date": payload.date},
        {"$set": {"user_id": user["user_id"], "date": payload.date, "wore": bool(payload.wore),
                  "answered_at": now_utc().isoformat()}},
        upsert=True,
    )
    if not payload.wore:
        return {"ok": True, "recorded": False}
    ids = [i for i in (payload.item_ids or []) if i]
    if ids:
        await db.wear_logs.insert_one({
            "id": new_id("wear"), "user_id": user["user_id"], "item_ids": ids,
            "occasion": "", "flattering": 3, "comfort": 3, "confidence": 3,
            "created_at": f"{payload.date}T12:00:00+00:00",
        })
        for iid in ids:
            await db.items.update_one(
                {"id": iid, "user_id": user["user_id"]},
                {"$inc": {"wear_count": 1}, "$set": {"last_worn": f"{payload.date}T12:00:00+00:00"}},
            )
    return {"ok": True, "recorded": True, "items": len(ids)}


@api_router.get("/wear")
async def list_wear(user: dict = Depends(get_scope)):
    wear_query = {"user_id": user["user_id"]}
    if not user.get("show_demo"):
        wear_query["demo"] = {"$ne": True}
    logs = await db.wear_logs.find(wear_query, {"_id": 0}).sort("created_at", -1).to_list(500)
    by_id = await slim_items_by_id(
        await db.items.find(items_scope(user), {"_id": 0, "orig_photo": 0}).to_list(1000)
    )
    for lg in logs:
        lg["items"] = [by_id[i] for i in lg.get("item_ids", []) if i in by_id]
    return logs


@api_router.get("/wear/{log_id}")
async def get_wear(log_id: str, user: dict = Depends(get_scope)):
    """One recorded wear, with its pieces — powers the Worn outfit detail."""
    log = await db.wear_logs.find_one({"id": log_id, "user_id": user["user_id"]}, {"_id": 0})
    if not log:
        raise HTTPException(status_code=404, detail="That wear isn't in your history.")
    ids = [i for i in (log.get("item_ids") or []) if i]
    items = await db.items.find(
        {**items_scope(user), "id": {"$in": ids}}, {"_id": 0, "orig_photo": 0}
    ).to_list(50)
    by_id = await slim_items_by_id(items)
    log["items"] = [by_id[i] for i in ids if i in by_id]
    return log


# ----------------------------- Insights -----------------------------
@api_router.get("/insights")
async def insights(user: dict = Depends(get_scope)):
    items = await db.items.find(items_scope(user), {"_id": 0, "orig_photo": 0}).to_list(2000)
    logs = await db.wear_logs.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(2000)
    total_items = len(items)
    total_wears = sum(it.get("wear_count", 0) for it in items)

    slim = await slim_items_by_id(items)
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

    # THIS MONTH, from explicit Worn activity only (wear logs) — never suggestions.
    month_prefix = now_utc().strftime("%Y-%m")
    month_logs = [lg for lg in logs if str(lg.get("created_at") or "").startswith(month_prefix)]
    month_counts: dict = {}
    for lg in month_logs:
        for iid in lg.get("item_ids") or []:
            month_counts[iid] = month_counts.get(iid, 0) + 1
    top_month = [
        {"item": slim[iid], "wears": n}
        for iid, n in sorted(month_counts.items(), key=lambda kv: -kv[1])
        if iid in slim
    ][:6]
    unworn = [slim[it["id"]] for it in items if not (it.get("wear_count", 0) or 0)][:8]

    return {
        "total_items": total_items,
        "total_wears": total_wears,
        "outfits_logged": len(logs),
        "avg_flattering": avg("flattering"),
        "avg_comfort": avg("comfort"),
        "avg_confidence": avg("confidence"),
        "categories": cats,
        "most_worn": [slim[it["id"]] for it in most_worn if it["id"] in slim],
        "least_worn": [slim[it["id"]] for it in least_worn if it["id"] in slim],
        "unworn_count": sum(1 for it in items if not (it.get("wear_count", 0) or 0)),
        "month": {
            "label": now_utc().strftime("%B %Y"),
            "wears_logged": len(month_logs),
            "pieces_worn": len(month_counts),
            "top_worn": top_month,
            "unworn": unworn,
        },
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
    items = await wardrobe_pool(user, 2000)
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


SHOPPING_SYSTEM = (
    "You are Aureve's Shopping Intelligence — a sharp, honest wardrobe-gap and "
    "purchase advisor. Given the user's full wardrobe, recommend 3-4 NEW pieces "
    "that would add the MOST value: genuine gaps that unlock the most new outfits, "
    "never duplicates of what they already own well. Prefer versatile, foundational "
    "pieces that bridge existing items. "
    "Return STRICT JSON with keys: "
    "summary (one honest sentence reading their wardrobe's strengths and gaps), "
    "recommendations (array of 3-4 objects, each with: "
    "piece (specific item, e.g. 'A tailored navy blazer'), "
    "category (one wardrobe category), "
    "priority (one of 'High','Medium','Low'), "
    "why (2 sentences on the value it adds, referencing what they already own), "
    "pairs_with (array of 2-4 EXACT names of items they ALREADY own that it would combine with), "
    "outfits_added (integer estimate of new workable outfits it enables)), "
    "avoid (one honest sentence about a category they already over-own). "
    "Only reference items that exist in the wardrobe for pairs_with. Return ONLY JSON."
)


@api_router.post("/insights/shopping-intelligence")
async def shopping_intelligence(user: dict = Depends(get_scope)):
    """Premium wardrobe-gap shopping advisor: analyses what the user owns and
    recommends the highest-value NEW pieces (genuine gaps, not duplicates), why
    each helps, what it pairs with, and how many outfits it could unlock. Builds
    on the same wardrobe analysis as the Missing Piece insight."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "shop")
    items = await wardrobe_pool(user, 2000)
    if len(items) < 3:
        raise HTTPException(status_code=400, detail="Add a few more pieces so Aureve can find your real wardrobe gaps")
    wardrobe = summarize_items_for_ai(items)
    counts: dict = {}
    for it in items:
        counts[it.get("category", "Other")] = counts.get(it.get("category", "Other"), 0) + 1
    breakdown = ", ".join(f"{k}:{v}" for k, v in counts.items())
    prompt = (
        f"Wardrobe breakdown by count: {breakdown}\n\n"
        f"Full wardrobe:\n{wardrobe}\n\n"
        "Recommend the highest-value pieces to buy next. Return JSON only."
    )
    chat = await ai_chat(f"shopiq-{user['user_id']}-{uuid.uuid4().hex[:6]}", SHOPPING_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("shopping-intelligence failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result or not result.get("recommendations"):
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
    try:
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": name, "count": 1, "language": "en"},
            )
    except Exception as e:
        # A weather lookup must never fail the feature that asked for it.
        logger.warning("geocode failed for %r: %s", name, e)
        return None
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
    try:
        async with httpx.AsyncClient(timeout=10) as hc:
            r = await hc.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                    "forecast_days": min(total, 16), "timezone": "auto",
                },
            )
    except Exception as e:
        # Callers fall back to "forecast unavailable" copy rather than erroring.
        logger.warning("forecast failed for %s,%s: %s", lat, lon, e)
        return None
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


@api_router.post("/packing/plan", dependencies=[Depends(unreleased("packing"))])
async def packing_plan(payload: PackingRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "packing")
    items = await wardrobe_pool(user, 1000)
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
    await hydrate_photos(
        user,
        result["capsule_items"] + [it for o in result["resolved_outfits"] for it in o["items"]],
    )
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


@api_router.post("/capsule/build", dependencies=[Depends(unreleased("capsule"))])
async def capsule_build(payload: CapsuleRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "capsule")
    items = await wardrobe_pool(user, 1000)
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
    await hydrate_photos(
        user,
        result["capsule_items"] + [it for o in result["resolved_outfits"] for it in o["items"]],
    )
    return result


# ----------------------------- AI: Wardrobe Health Report -----------------------------
HEALTH_SYSTEM = (
    "You are Aureve's wardrobe health analyst. You are given wardrobe stats and the raw numbers. Write an honest, "
    "encouraging monthly report. Be candid and useful but NEVER judgemental — talk about underused pieces, low-wear "
    "items, wardrobe opportunities and pieces worth revisiting, never about wasted or squandered money. "
    "Write like a stylist talking to a person, NOT like a report full of figures: describe balance and "
    "opportunity in words (\"a strong mix of tops and bottoms\", \"a few unworn dresses\") and only ever "
    "quote a number when the insight makes no sense without it. Never list category totals or wardrobe counts. "
    "Return STRICT JSON with keys: "
    "headline (one punchy sentence summarising the month, no numbers), "
    "underused_summary (2-3 sentences about the pieces getting little wear and the opportunity there — "
    "name actual pieces rather than counts), "
    "lesson (one actionable sentence about what to wear more or rotate), "
    "missing_piece (object: recommendation, reason, unlock_note), "
    "wins (array of 1-3 short positive observations), "
    "nudges (array of 1-3 short gentle action nudges phrased humanly, e.g. 'Bring a few of your unworn "
    "dresses into rotation this month'). "
    "Return ONLY JSON."
)


@api_router.post("/insights/health-report")
async def health_report(user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "health")
    items = await wardrobe_pool(user, 2000)
    if len(items) < 3:
        raise HTTPException(status_code=400, detail="Add a few more pieces to generate your report")

    unworn = [it for it in items if (it.get("wear_count", 0) or 0) == 0]
    low_wear = sorted(
        items,
        key=lambda it: ((it.get("wear_count", 0) or 0), it.get("last_worn") or ""),
    )[:8]
    low_wear_desc = "; ".join(
        f"{it.get('name')} ({it.get('category')}, worn {it.get('wear_count', 0) or 0}x)"
        for it in low_wear
    ) or "none yet"
    counts: dict = {}
    for it in items:
        counts[it.get("category", "Other")] = counts.get(it.get("category", "Other"), 0) + 1
    breakdown = ", ".join(f"{k}:{v}" for k, v in counts.items())

    prompt = (
        f"Total pieces: {len(items)}.\n"
        f"Pieces not yet worn: {len(unworn)}.\n"
        f"Lowest-wear pieces: {low_wear_desc}.\n"
        f"Category breakdown: {breakdown}.\n\n"
        "Write the monthly wardrobe health report using wear history and category balance only. "
        "Focus on underused pieces and practical rotation opportunities. Do not mention purchase "
        "price, wardrobe value, money or cost-per-wear. Name the single purchase that would unlock "
        "the most outfits. Phrase nudges as gentle invitations, never as orders. The numbers above are "
        "context for YOU: do not quote wardrobe totals or category counts back to the user, and never "
        "invent figures. Return JSON only."
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
        "unworn_count": len(unworn),
        "worn_count": len(items) - len(unworn),
        "categories": counts,
    }
    return result


# ----------------------------- AI: Hair -----------------------------
class BeautyRequest(BaseModel):
    occasion: Optional[str] = ""
    neckline: Optional[str] = ""
    hair_length: Optional[str] = ""
    hair_type: Optional[str] = ""
    temperature: Optional[float] = None
    weather: Optional[str] = ""


HAIR_SYSTEM = (
    "You are Aureve's hair stylist. You recommend HAIRSTYLES ONLY — how to wear the hair for a "
    "specific occasion and outfit. Never mention hair colour, dye, highlights or toning, and never "
    "mention makeup, skincare or clothing colour palettes. Consider the occasion and its formality, "
    "the outfit's neckline (an updo or swept style suits high or embellished necklines; softer "
    "down-styles suit open or strapless necklines), the weather (humidity, rain, wind, heat), and "
    "the person's hair length and texture when given. Be specific, practical and warm; keep every "
    "string short. Stay inclusive of all genders and presentations. "
    "Return STRICT JSON with keys: "
    "summary (one sentence on the direction for this occasion and outfit), "
    "styles (array of 2-3 objects: name (the hairstyle), why (one short line on why it suits this "
    "occasion/neckline/weather), how (one or two short practical steps)), "
    "tip (one short practical string, e.g. holding it through the day or weather-proofing), "
    "occasion_note (one short sentence tailoring the look to the stated occasion). "
    "Return ONLY JSON."
)


@api_router.post("/beauty/suggest")
async def hair_suggest(payload: BeautyRequest, user: dict = Depends(get_scope)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="AI key not configured")
    await enforce_limit(user, "beauty")
    p = user.get("profile") or {}
    context = "; ".join(
        f"{k}: {v}" for k, v in [
            ("occasion", payload.occasion or "everyday"),
            ("outfit neckline", payload.neckline),
            ("hair length", payload.hair_length),
            ("hair type/texture", payload.hair_type),
            ("weather", f"{payload.temperature}°C, {payload.weather}" if payload.temperature is not None else payload.weather),
            ("personal notes", p.get("notes")),
        ] if v
    )
    prompt = (
        f"Context — {context}.\n\n"
        "Recommend hairstyles (no colour advice, no makeup) for this occasion and outfit. "
        "Return JSON only."
    )
    chat = await ai_chat(f"hair-{user['user_id']}-{uuid.uuid4().hex[:6]}", HAIR_SYSTEM)
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("hair suggest failed")
        raise HTTPException(status_code=502, detail=f"AI error: {e}")
    result = parse_json_block(resp)
    if not result:
        raise HTTPException(status_code=502, detail="Could not generate hair recommendations")
    return result


# ----------------------------- Weather -----------------------------
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow",
    75: "Heavy snow", 80: "Rain showers", 81: "Rain showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

# Last good reading per ~0.1 degree cell, so a provider stall degrades to
# slightly older conditions instead of no weather at all.
_WEATHER_CACHE: dict = {}
_WEATHER_CACHE_TTL = 60 * 60



@api_router.get("/weather")
async def weather(lat: float, lon: float):
    """Current conditions for Home, Dress Me, the stylist and Hair.

    Open-Meteo occasionally stalls from inside the cluster, so this answers in
    at most ~10s and keeps the last good reading per area: a provider blip then
    returns slightly older conditions instead of leaving the app with a dash.
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Invalid coordinates")
    cell = (round(lat, 1), round(lon, 1))
    data = None
    for timeout in (6, 4):
        try:
            async with httpx.AsyncClient(timeout=timeout) as hc:
                resp = await hc.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat, "longitude": lon,
                        "current": "temperature_2m,apparent_temperature,weather_code",
                        "timezone": "auto",
                    },
                )
            if resp.status_code == 200:
                data = resp.json().get("current", {})
                break
            logger.warning("weather provider returned %s", resp.status_code)
        except Exception as e:
            logger.warning("weather lookup failed (%ss timeout): %s", timeout, type(e).__name__)
    if data and data.get("temperature_2m") is not None:
        code = data.get("weather_code", 0)
        out = {
            "temperature": data.get("temperature_2m"),
            "feels_like": data.get("apparent_temperature"),
            "code": code,
            "description": WEATHER_CODES.get(code, "Unknown"),
        }
        if len(_WEATHER_CACHE) > 500:
            _WEATHER_CACHE.clear()
        _WEATHER_CACHE[cell] = (out, _time.monotonic())
        return out
    cached = _WEATHER_CACHE.get(cell)
    if cached and _time.monotonic() - cached[1] < _WEATHER_CACHE_TTL:
        logger.info("weather: provider unavailable, serving last good reading for %s", cell)
        return cached[0]
    raise HTTPException(status_code=502, detail="Weather unavailable")


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
    await seed_reviewer_account()


async def seed_reviewer_account():
    """Idempotently ensure a dedicated App Store review account exists in
    whatever database this backend is connected to (preview OR production).

    The reviewer signs in with email/password, is granted Premium via an
    explicit far-future ``premium_until`` (so it does NOT depend on
    TRIAL_UNLOCK_ALL), and gets a representative 16-item demo wardrobe so every
    feature — including Premium-only ones — is reachable during Apple review.

    The password comes from the REVIEWER_PASSWORD secret and is never stored in
    source. With the secret unset this is a no-op: an existing reviewer account
    is left exactly as it is rather than being given a blank password."""
    email = _norm_email(REVIEWER_EMAIL)
    password = os.environ.get("REVIEWER_PASSWORD", "")
    if not password:
        logger.warning("REVIEWER_PASSWORD not set — skipping reviewer account seeding")
        return
    premium_until = "2099-01-01T00:00:00+00:00"
    try:
        existing = await db.users.find_one({"email": email})
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        if existing:
            user_id = existing["user_id"]
            # A rotated password must not leave old bearer tokens working, so
            # detect a genuine change and drop that account's sessions. Checking
            # first means an ordinary restart does not sign the reviewer out.
            try:
                rotated = not bcrypt.checkpw(password.encode(), (existing.get("password_hash") or "").encode())
            except ValueError:
                rotated = True
            # Keep the known password valid and Premium active for the reviewer.
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"password_hash": pw_hash, "premium_until": premium_until,
                          "premium_source": "reviewer", "provider": "email"}},
            )
            if rotated:
                dropped = await db.user_sessions.delete_many({"user_id": user_id})
                logger.warning("Reviewer password rotated — invalidated %s active session(s)", dropped.deleted_count)
        else:
            user_id = new_id("user")
            await db.users.insert_one({
                "user_id": user_id,
                "email": email,
                "name": "Aureve Reviewer",
                "provider": "email",
                "password_hash": pw_hash,
                "premium_until": premium_until,
                "premium_source": "reviewer",
                "created_at": now_utc().isoformat(),
            })
        # Keep seeded samples only while the reviewer wardrobe is genuinely empty.
        # Once real uploads exist, remove old demo rows instead of resurrecting them
        # on every restart/deploy.
        prof = await ensure_default_profile(user_id, "Reviewer")
        real_item_count = await db.items.count_documents({
            "user_id": prof["id"],
            "demo": {"$ne": True},
        })
        if real_item_count == 0:
            await reconcile_reviewer_wardrobe(prof["id"])
        else:
            removed = await db.items.delete_many({"user_id": prof["id"], "demo": True})
            await db.outfits.delete_many({"user_id": prof["id"], "demo": True})
            await db.wear_logs.delete_many({"user_id": prof["id"], "demo": True})
            await db.plans.delete_many({"user_id": prof["id"], "demo": True})
            logger.info("Reviewer has %s real pieces; removed %s seeded demo pieces", real_item_count, removed.deleted_count)
        logger.info(f"Reviewer account ready: {email}")
    except Exception as e:
        logger.warning(f"Reviewer account seeding skipped: {e}")


async def reconcile_reviewer_wardrobe(profile_id: str):
    """Ensure EXACTLY one clean copy of each intended demo item exists on the
    reviewer profile. Uses deterministic ids (``revdemo-<index>``) + upserts so
    restarting/redeploying the backend updates in place instead of inserting
    fresh copies. Any other wardrobe rows on THIS profile (old random-id
    duplicates, demo or not) are pruned. Strictly scoped to the given reviewer
    profile — no other account or data is touched."""
    try:
        from demo_wardrobe import DEMO_ITEMS
    except Exception as e:
        logger.warning(f"Demo wardrobe unavailable: {e}")
        return
    now = now_utc().isoformat()
    canonical_ids = []
    for i, g in enumerate(DEMO_ITEMS):
        item_id = f"revdemo-{i}"
        canonical_ids.append(item_id)
        await db.items.update_one(
            {"id": item_id},
            {
                "$set": {
                    "id": item_id,
                    "user_id": profile_id,
                    "name": g["name"],
                    "category": g["category"],
                    "colour": g.get("colour", ""),
                    "fabric": g.get("fabric", ""),
                    "season": g.get("season", "All"),
                    "pattern": "",
                    "style": g.get("style", ""),
                    "sleeve_length": "",
                    "formality": g.get("formality", ""),
                    "tone": g.get("tone", ""),
                    "fit_notes": "",
                    "brand": "",
                    "size": "",
                    "price": None,
                    "condition": "",
                    "availability": "Ready",
                    "photo": g["photo"],
                    "worn_photo": None,
                    "flatters": g.get("flatters", True),
                    "demo": True,
                },
                "$setOnInsert": {"created_at": now, "wear_count": 0, "last_worn": None},
            },
            upsert=True,
        )
    # Prune only STALE DEMO rows on this reviewer profile (old random-id demo
    # duplicates). Items the reviewer/user added themselves are NEVER deleted —
    # a redeploy must not wipe real uploads made while signed in as this account.
    removed = await db.items.delete_many(
        {"user_id": profile_id, "demo": True, "id": {"$nin": canonical_ids}}
    )
    await db.outfits.delete_many({"user_id": profile_id, "demo": True})
    await db.wear_logs.delete_many({"user_id": profile_id, "demo": True})
    logger.info(
        f"Reviewer wardrobe reconciled: {len(canonical_ids)} canonical items, "
        f"pruned {removed.deleted_count} duplicates"
    )


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
