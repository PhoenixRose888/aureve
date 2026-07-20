import os
import base64
import io
import pytest
import requests

# Use base URL from frontend/.env (preview URL). Also matches /api routing on ingress.
BASE_URL = "https://wardrobe-ai-311.preview.emergentagent.com/api"
TEST_TOKEN = "test-session-token-aura-123"


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _make_clothing_image_b64() -> str:
    """Create a realistic-ish clothing-like JPEG (textured, non-uniform)."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
        import random
        random.seed(42)
        w, h = 320, 400
        img = Image.new("RGB", (w, h), (240, 235, 225))
        d = ImageDraw.Draw(img)
        # background gradient
        for y in range(h):
            shade = 230 - int(20 * y / h)
            d.line([(0, y), (w, y)], fill=(shade, shade - 5, shade - 10))
        # T-shirt silhouette (white cotton tee)
        body = [(80, 120), (240, 120), (250, 380), (70, 380)]
        d.polygon(body, fill=(245, 245, 245), outline=(180, 180, 180))
        # sleeves
        d.polygon([(80, 120), (40, 180), (60, 210), (95, 155)], fill=(238, 238, 238), outline=(170, 170, 170))
        d.polygon([(240, 120), (280, 180), (260, 210), (225, 155)], fill=(238, 238, 238), outline=(170, 170, 170))
        # collar
        d.arc([130, 105, 190, 155], 0, 180, fill=(120, 120, 120), width=3)
        # texture noise
        for _ in range(4000):
            x = random.randint(70, 250)
            y = random.randint(120, 380)
            c = 235 + random.randint(-15, 15)
            d.point((x, y), fill=(c, c, c))
        img = img.filter(ImageFilter.SMOOTH)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        # Fallback: 1x1 will not pass AI; but ensures test runs
        return base64.b64encode(b"\xff\xd8\xff\xd9").decode()


@pytest.fixture(scope="session")
def clothing_image_b64():
    return _make_clothing_image_b64()
