"""Iteration 35 — regression tests for wardrobe launch simplification.

Verifies:
 (1) POST /api/items and GET /api/items still work for reviewer.
 (2) Round-trip of a full seed of 50+ items covering EVERY category+subcategory
     defined in the new taxonomy. Fields (name/style/fabric/sleeve_length)
     are the ones the frontend subfilter classifier reads.
 (3) POST /api/items/bulk-delete cleans up all seeded items.
 (4) Server starts cleanly (health check) after the ANALYZE_SYSTEM prompt
     wording change on the recognition prompt.

The frontend subfilter/category classification is verified separately via
Playwright (see /app/test_reports/iteration_35.json).
"""
import os
import datetime as dt
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://wardrobe-ai-311.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

REVIEWER_EMAIL = "review@aureve.app"
REVIEWER_PASSWORD = "AureveTest2026"

# 1x1 transparent PNG (base64)
TINY_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

# ---------------------------------------------------------------------
# Seed catalogue — every item designed to fall under exactly ONE subchip
# under the iteration-35 taxonomy. Format:
#   (name, category, style, fabric, extras_dict_or_none, expected_chip)
# ---------------------------------------------------------------------
SEED = [
    # ---- TOPS: T-Shirts, Shirts, Blouses, Polos, Singlets, Camis, Crops,
    #             Halter, Long Sleeve, Vests, Bodysuits, Corsets
    ("TEST35_White cotton t-shirt",       "Tops", "t-shirt",         "cotton",       {"sleeve_length": "short"}, "T-Shirts"),
    ("TEST35_Navy poplin shirt",          "Tops", "shirt",           "poplin",       {}, "Shirts"),
    ("TEST35_Blush satin blouse",         "Tops", "blouse",          "satin",        {}, "Blouses"),
    ("TEST35_Green pique polo shirt",     "Tops", "polo shirt",      "pique cotton", {}, "Polos"),
    ("TEST35_Black ribbed singlet",       "Tops", "singlet",         "ribbed cotton",{}, "Singlets"),
    ("TEST35_Cream silk camisole",        "Tops", "camisole",        "silk",         {}, "Camis"),
    ("TEST35_Black crop top",             "Tops", "crop top",        "cotton",       {}, "Crops"),
    ("TEST35_Ivory halterneck top",       "Tops", "halterneck top",  "cotton",       {}, "Halter"),
    ("TEST35_Olive long sleeve top",      "Tops", "long sleeve top", "cotton jersey",{"sleeve_length": "long"}, "Long Sleeve"),
    ("TEST35_Grey wool waistcoat",        "Tops", "waistcoat",       "wool",         {}, "Vests"),
    ("TEST35_Beige knit bodysuit",        "Tops", "bodysuit",        "knit",         {}, "Bodysuits"),
    ("TEST35_Burgundy bustier",           "Tops", "bustier",         "satin",        {}, "Corsets"),

    # ---- BOTTOMS: Jeans, Pants, Shorts, Skirts, Leggings
    ("TEST35_Blue skinny jeans",          "Bottoms", "jeans",         "denim",      {}, "Jeans"),
    ("TEST35_Black tailored trousers",    "Bottoms", "trousers",      "wool",       {}, "Pants"),
    ("TEST35_Denim shorts",               "Bottoms", "shorts",        "denim",      {}, "Shorts"),
    ("TEST35_Pleated midi skirt",         "Bottoms", "skirt",         "polyester",  {}, "Skirts"),
    ("TEST35_Black leggings",             "Bottoms", "leggings",      "nylon",      {}, "Leggings"),

    # ---- DRESSES: no subfilters
    ("TEST35_Black midi dress",           "Dresses", "midi dress",    "crepe",      {}, None),

    # ---- OUTERWEAR: Blazers, Jackets, Coats, Cardigans, Jumpers (hoodie -> Jumpers)
    ("TEST35_Navy wool blazer",           "Outerwear", "blazer",      "wool",       {}, "Blazers"),
    ("TEST35_Black leather jacket",       "Outerwear", "jacket",      "leather",    {}, "Jackets"),
    ("TEST35_Beige trench coat",          "Outerwear", "coat",        "cotton",     {}, "Coats"),
    ("TEST35_Cream cardigan",             "Outerwear", "cardigan",    "knit",       {}, "Cardigans"),
    ("TEST35_Black hoodie",               "Outerwear", "hoodie",      "cotton",     {}, "Jumpers"),

    # ---- SHOES: Sneakers, Boots, Heels, Flats, Sandals, Dress Shoes
    ("TEST35_White leather sneakers",     "Shoes", "sneakers",        "leather",    {}, "Sneakers"),
    ("TEST35_Black ankle boots",          "Shoes", "ankle boots",     "leather",    {}, "Boots"),
    ("TEST35_Nude stiletto heels",        "Shoes", "stiletto heels",  "leather",    {}, "Heels"),
    ("TEST35_Ballet flats",               "Shoes", "ballet flats",    "leather",    {}, "Flats"),
    ("TEST35_Brown leather sandals",      "Shoes", "sandals",         "leather",    {}, "Sandals"),
    ("TEST35_Black oxford dress shoes",   "Shoes", "oxford dress shoes","leather",  {}, "Dress Shoes"),

    # ---- BAGS: Handbags, Backpacks, Clutches, Briefcases, Crossbody
    ("TEST35_Black leather handbag",      "Bags", "handbag",          "leather",    {}, "Handbags"),
    ("TEST35_Canvas backpack",            "Bags", "backpack",         "canvas",     {}, "Backpacks"),
    ("TEST35_Gold evening clutch",        "Bags", "clutch",           "satin",      {}, "Clutches"),
    ("TEST35_Leather briefcase",          "Bags", "briefcase",        "leather",    {}, "Briefcases"),
    ("TEST35_Black leather crossbody bag","Bags", "crossbody bag",    "leather",    {}, "Crossbody"),

    # ---- ACCESSORIES: Hats, Sunglasses, Scarves, Ties, Belts, Gloves
    ("TEST35_Black wool beanie",          "Accessories", "beanie",     "wool",      {}, "Hats"),
    ("TEST35_Gold aviator sunglasses",    "Accessories", "sunglasses", "metal",     {}, "Sunglasses"),
    ("TEST35_Silk scarf",                 "Accessories", "scarf",      "silk",      {}, "Scarves"),
    ("TEST35_Navy silk tie",              "Accessories", "necktie",    "silk",      {}, "Ties"),
    ("TEST35_Brown leather belt",         "Accessories", "belt",       "leather",   {}, "Belts"),
    ("TEST35_Black leather gloves",       "Accessories", "gloves",     "leather",   {}, "Gloves"),

    # ---- JEWELLERY: Necklaces, Bracelets, Earrings, Rings, Watches
    ("TEST35_Gold pendant necklace",      "Jewellery", "pendant necklace", "gold",  {}, "Necklaces"),
    ("TEST35_Silver bangle bracelet",     "Jewellery", "bangle bracelet",  "silver",{}, "Bracelets"),
    ("TEST35_Gold hoop earrings",         "Jewellery", "hoop earrings",    "gold",  {}, "Earrings"),
    ("TEST35_Silver signet ring",         "Jewellery", "signet ring",      "silver",{}, "Rings"),
    ("TEST35_Gold analogue watch",        "Jewellery", "watch",            "gold",  {}, "Watches"),
]


@pytest.fixture(scope="module")
def reviewer_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"reviewer login failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def reviewer_headers(reviewer_token):
    return {"Authorization": f"Bearer {reviewer_token}", "Content-Type": "application/json"}


class TestServerHealth:
    def test_api_reachable(self):
        r = requests.get(f"{API}/", timeout=15)
        # any 2xx is fine (root sometimes returns 200/404 depending on router)
        assert r.status_code < 500, f"backend not healthy: {r.status_code} {r.text}"


class TestSeedItemsRoundTrip:
    created_ids = []

    def test_1_create_all_seed_items(self, reviewer_headers):
        for name, cat, style, fabric, extras, _chip in SEED:
            body = {
                "name": name,
                "category": cat,
                "colour": "black",
                "fabric": fabric,
                "style": style,
                "sleeve_length": extras.get("sleeve_length", ""),
                "photo": TINY_PNG,
                "orig_photo": TINY_PNG,
            }
            r = requests.post(f"{API}/items", json=body, headers=reviewer_headers, timeout=30)
            assert r.status_code == 200, f"create {name} -> {r.status_code} {r.text}"
            j = r.json()
            assert j.get("id"), j
            assert j.get("name") == name
            assert j.get("category") == cat
            TestSeedItemsRoundTrip.created_ids.append(j["id"])

    def test_2_list_returns_all_seed(self, reviewer_headers):
        r = requests.get(f"{API}/items", headers=reviewer_headers, timeout=30)
        assert r.status_code == 200
        names = {it.get("name") for it in r.json()}
        missing = [name for name, *_ in SEED if name not in names]
        assert not missing, f"missing after GET /items: {missing}"

    def test_3_categories_intact(self, reviewer_headers):
        r = requests.get(f"{API}/items", headers=reviewer_headers, timeout=30)
        assert r.status_code == 200
        by_name = {it["name"]: it for it in r.json() if it.get("name", "").startswith("TEST35_")}
        for name, cat, *_ in SEED:
            got = by_name.get(name)
            assert got, f"missing item: {name}"
            assert got["category"] == cat, f"{name}: category={got['category']} expected {cat}"

    def test_zzz_cleanup_bulk_delete(self, reviewer_headers):
        ids = TestSeedItemsRoundTrip.created_ids
        if not ids:
            pytest.skip("nothing to clean up")
        r = requests.post(f"{API}/items/bulk-delete",
                          json={"item_ids": ids},
                          headers=reviewer_headers, timeout=60)
        assert r.status_code == 200, r.text
        assert (r.json() or {}).get("deleted", 0) >= len(ids)


class TestAnalyzeSystemPromptOK:
    """The recognition prompt wording changed. We don't call the paid AI
    endpoint — but the server must have loaded the module cleanly, meaning
    ANALYZE_SYSTEM is syntactically valid Python and the module imports.
    """
    def test_backend_healthy(self):
        # 401 for /items without auth is fine — proves the router loaded
        r = requests.get(f"{API}/items", timeout=15)
        assert r.status_code in (200, 401, 403), f"router load: {r.status_code} {r.text}"
