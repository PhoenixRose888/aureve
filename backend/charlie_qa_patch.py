from pathlib import Path

path = Path(__file__).with_name("server.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str):
    global text
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 match, found {n}")
    text = text.replace(old, new, 1)
    print(f"patched: {label}")

replace_once(
'''class DressMeRequest(BaseModel):
    temperature: Optional[float] = None
    weather: Optional[str] = None
    occasion: Optional[str] = None  # override; otherwise inferred from today's plan
''',
'''class DressMeRequest(BaseModel):
    temperature: Optional[float] = None
    weather: Optional[str] = None
    occasion: Optional[str] = None  # override; otherwise inferred from today's plan
    avoid_item_ids: List[str] = []  # current look when user asks for another
''',
"Dress Me request supports avoid_item_ids",
)

replace_once(
'''    result = await _build_outfit(user, occasion, payload.temperature, payload.weather, notes)
''',
'''    result = await _build_outfit(
        user,
        occasion,
        payload.temperature,
        payload.weather,
        notes,
        payload.avoid_item_ids,
    )
''',
"Dress Me forwards avoid_item_ids",
)

replace_once(
'''    plans = await db.plans.find(query, {"_id": 0}).sort("date", 1).to_list(500)
''',
'''    if not user.get("show_demo"):
        query["demo"] = {"$ne": True}
    plans = await db.plans.find(query, {"_id": 0}).sort("date", 1).to_list(500)
''',
"exclude demo plans server-side",
)

replace_once(
'''async def list_wear(user: dict = Depends(get_scope)):
    logs = await db.wear_logs.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
''',
'''async def list_wear(user: dict = Depends(get_scope)):
    wear_query = {"user_id": user["user_id"]}
    if not user.get("show_demo"):
        wear_query["demo"] = {"$ne": True}
    logs = await db.wear_logs.find(wear_query, {"_id": 0}).sort("created_at", -1).to_list(500)
''',
"exclude demo wear logs server-side",
)

replace_once(
'''    confidence = int(analysis.get("confidence") or 0)
''',
'''    try:
        confidence = int(float(analysis.get("confidence") or 0))
    except (TypeError, ValueError):
        confidence = 0
''',
"make duplicate confidence parsing safe",
)

path.write_text(text, encoding="utf-8")
print("final QA backend patch complete")
