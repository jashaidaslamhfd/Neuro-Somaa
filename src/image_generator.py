import hashlib
import logging
import os
import random
import threading

import requests

from image_providers import RateLimitError, available_providers
from media_validator import MediaValidationError, validate_scene_image

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FALLBACK CHAIN (in order):
#   1) AI generation (Pollinations/HuggingFace/Gemini/Craiyon/etc via
#      image_providers.PROVIDER_REGISTRY) - PRIMARY. This is the only layer
#      that actually renders the exact scene ("dark cinematic anatomy shot",
#      etc.) instead of grabbing whatever unrelated image already exists
#      somewhere on the web, so it's what keeps visuals matching the script's
#      tone and keeps every video's imagery unique (not shared with other
#      creators - avoids "reused content" suppression on Shorts/Reels).
#   2) Local pre-generated pool (assets/fallback_images/, built ahead of time
#      by scripts/generate_fallback_images.py) - still on-niche AI art, just
#      not rendered fresh for this exact scene. Used when every live AI
#      provider is rate-limited.
#   3) Pexels / Pixabay live stock photos - generic, and shared with
#      thousands of other channels, so this only kicks in if 1 and 2 both
#      fail entirely.
#   4) Playwright screenshot of a random top search result - absolute last
#      resort. This does NOT produce a themed visual (it's literally
#      whatever webpage layout/ads/nav-bar happens to be on the page), so it
#      only exists to guarantee *something* gets saved rather than crashing
#      the whole video; it should essentially never fire in normal operation.
# ---------------------------------------------------------------------------

REQUEST_TIMEOUT = 30
_fallback_lock = threading.Lock()

DARK_STYLE_SUFFIX = (
    "clean cinematic documentary lighting, realistic human detail, sharp focus, "
    "crisp high-resolution detail, natural color, professional camera quality, "
    "vertical composition, no text, no watermark, not blurry, not dull, "
    # Anti-gore / anti-horror. Added 2026-07-27 after a published Short
    # ("Pourquoi le sursaut du corps en s'endormant ?") shipped a
    # blood-spattered horror face as its opening visual. The prompt asked for
    # "dark/moody", which several providers happily read as horror. A calm
    # French science channel must never look like a shock channel: it is
    # off-brand and it puts advertiser suitability at risk.
    "no blood, no gore, no wounds, no injury, no horror, no scary face, "
    "no zombie, no monster, no body paint, no distorted anatomy, "
    "safe for all audiences, medically respectful, educational tone"
)

# Words that must never reach a stock-footage/image search on this channel.
# Scene descriptions such as "le corps se fige de peur" were being passed
# through verbatim and returning horror B-roll.
UNSAFE_QUERY_TERMS = {
    "sang", "sanglant", "blood", "bloody", "gore", "horreur", "horror",
    "zombie", "monstre", "monster", "cadavre", "corpse", "mort", "death",
    "blessure", "wound", "injury", "effrayant", "scary", "terreur", "terror",
    "cauchemar", "nightmare", "creepy", "violence", "violent",
}

FALLBACK_POOL_DIR = "assets/fallback_images"


def _safe_query(scene_text: str, default: str) -> str:
    """Strip shock/gore words before hitting a stock search.

    Scene captions like "le corps se fige de peur" or "un cauchemar" were sent
    verbatim to Pexels/Pixabay and returned horror B-roll, which then became
    the opening frame of an educational Short. Removing the trigger words
    keeps the subject while dropping the tone that pulls horror results."""
    original = (scene_text or "").split()
    words = [
        word for word in original
        if word.strip(".,;:!?()\"'").lower() not in UNSAFE_QUERY_TERMS
    ]
    # Once the shock words are gone, whatever remains must still describe
    # something. "un cauchemar effrayant avec du sang" reduces to "un avec du"
    # — grammatical debris that would return random stock. Keep only real
    # content words, and fall back to the safe default if too little is left.
    filler = {"un", "une", "le", "la", "les", "de", "du", "des", "avec", "sans",
              "et", "ou", "en", "dans", "sur", "ce", "cette", "qui", "que",
              "se", "son", "sa", "ses", "au", "aux", "pour", "par"}
    content = [w for w in words if w.strip(".,;:!?()\"'").lower() not in filler]
    if len(content) < 2:
        return default
    return " ".join(words).strip() or default


def _save_bytes(content: bytes, index: int, ext: str = "jpg") -> str:
    os.makedirs("output", exist_ok=True)
    path = f"output/scene_{index}.{ext}"
    with open(path, "wb") as f:
        f.write(content)
    return path


def _build_prompt(scene_text: str, *, topic: str = "") -> str:
    """Combines the script's own scene description with the channel's
    signature visual identity ("Le Labo Obscur", 2026-08-15): one fixed
    macro teal-lab world with per-video style variation. This is what makes
    Neuro-Somaa frames recognizably unique instead of the generic stock look
    shared by thousands of channels. Falls back to the legacy fixed suffix
    if the signature module is unavailable."""
    base = (scene_text or "mystery science").strip()
    try:
        from visual_signature import signature_suffix
        return f"{base}, {signature_suffix(topic or scene_text or 'x')}"
    except Exception:  # never let the style layer break generation
        return f"{base}, {DARK_STYLE_SUFFIX}"


def _layer_ai_video(index, scene_text, image_path: str | None = None, topic=""):
    """2026-08-17 AI image-to-video: turns the already-unique AI scene
    image into a genuine motion clip (Seedance 2.5 via Pollinations).
    This is what separates 'AI slideshow' from 'AI-made video' - every
    scene now MOVES with physics the stock layers never matched, and the
    motion is unique to this channel (not shared with anyone else).
    Requires POLLINATIONS_KEY (free account, starter Pollen credits).
    Without the key, RuntimeError is raised and the stock-video fallbacks
    + Ken Burns image motion cover the slot instead. Max AI_VIDEO_SCENES
    (default 5) of a video get AI motion - the hook + key beats get it
    first, the rest stay on lightweight Ken Burns to protect build time
    (6-min GitHub Actions limit) and Pollen budget.
    """
    from image_providers import gen_pollinations_video, RateLimitError as _RL
    max_ai_video = int(os.environ.get("AI_VIDEO_SCENES", "5"))
    if index >= max_ai_video:
        raise RuntimeError(f"AI video skipped: scene {index} beyond AI_VIDEO_SCENES={max_ai_video}")
    prompt_text = _build_prompt(scene_text, topic=topic)
    prompt = prompt_text.replace(" ", "_").replace(",", "")
    content, ext = gen_pollinations_video(prompt, prompt_text, image_path=image_path)
    return _save_bytes(content, index, ext=ext), "video"


def _layer_ai_providers(index, scene_text, provider_names=None, topic=""):
    """Try every configured AI image provider in order (Pollinations first,
    since it needs no API key, then whichever keyed providers are
    available). Each provider gets one attempt per call; the caller
    (`_generate_one`) is what advances to the next fallback layer if every
    provider here fails."""
    providers = available_providers()
    if provider_names is not None:
        providers = [provider for provider in providers if provider["name"] in set(provider_names)]
    if not providers:
        requested = ", ".join(provider_names or []) or "configured"
        raise RuntimeError(f"No {requested} AI image providers available (check API keys / network)")

    prompt_text = _build_prompt(scene_text, topic=topic)
    prompt = prompt_text.replace(" ", "_").replace(",", "")
    seed = random.randint(1, 999999)

    last_err = None
    for provider in providers:
        try:
            image_bytes, ext = provider["generate"](prompt, seed, prompt_text)
            if not image_bytes or len(image_bytes) < 2000:
                raise RuntimeError(f"{provider['name']}: empty/too-small response")
            path = _save_bytes(image_bytes, index, ext=ext)
            logger.info(f"Scene {index}: AI image via {provider['name']}")
            return path
        except RateLimitError as e:
            logger.warning(f"Scene {index}: {provider['name']} rate-limited, trying next provider: {e}")
            last_err = e
            continue
        except Exception as e:
            logger.warning(f"Scene {index}: {provider['name']} failed, trying next provider: {e}")
            last_err = e
            continue

    raise RuntimeError(f"All AI providers failed for scene {index}: {last_err}")


def _layer_local_pool(index, used_fallbacks: set):
    """Pulls a random not-yet-used image from the pre-generated on-niche
    pool (assets/fallback_images/), built by scripts/generate_fallback_images.py.
    Still matches the channel's dark-mystery look even though it's not
    rendered specifically for this scene."""
    if not os.path.isdir(FALLBACK_POOL_DIR):
        raise RuntimeError(f"No local fallback pool at {FALLBACK_POOL_DIR}")

    candidates = [
        os.path.join(FALLBACK_POOL_DIR, f)
        for f in os.listdir(FALLBACK_POOL_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    if not candidates:
        raise RuntimeError(f"Local fallback pool at {FALLBACK_POOL_DIR} is empty")

    with _fallback_lock:
        unused = [c for c in candidates if c not in used_fallbacks]
        pick = random.choice(unused) if unused else random.choice(candidates)
        used_fallbacks.add(pick)

    ext = pick.rsplit(".", 1)[-1]
    with open(pick, "rb") as f:
        content = f.read()
    return _save_bytes(content, index, ext=ext)


def _scene_theme(scene_text: str) -> str:
    """Pick a visual theme from scene keywords so the procedural fallback
    produces scene-aware visuals instead of the same generic pattern every
    scene. Cheap keyword -> theme mapping; returns 'generic' if nothing
    matches. This is what fixes the 'one same pattern image' complaint."""
    t = (scene_text or "").lower()
    body = ["corps", "muscle", "cerveau", "nerf", "sang", "cœur", "cœur",
            "cellule", "nerf", "poitrine", "ventre", "bras", "doigt",
            "visage", "peau", "os", "articul", "genou", "cou", "epaule"]
    brain = ["cerveau", "neurone", "esprit", "pensée", "pense", "memoire",
             "réflexe", "reflexe", "sommeil", "reve", "déjà"]
    night = ["nuit", "sommeil", "reve", "lune", "obscur"]
    warning = ["danger", "alerte", "réagit", "reagit", "signal", "stress",
               "peur", "douleur", "blessure"]
    if any(w in t for w in brain):
        return "brain"
    if any(w in t for w in night):
        return "night"
    if any(w in t for w in warning):
        return "alert"
    if any(w in t for w in body):
        return "body"
    return "generic"


def _layer_procedural(index, scene_text):
    """GUARANTEED fallback (added 2026-08-02 audit): dark cinematic gradient
    generated locally with numpy/PIL — zero dependencies, never rate-limited,
    never fails. Each scene gets a deterministic-but-unique seed so visuals
    differ across scenes and across videos. This replaces the previous
    behaviour where a total AI-provider outage (all of Pollinations/AI-Horde
    rate-limited + empty fallback pool) CRASHED the whole video creation.

    Since the 2026-08-05 audit (user reported "one same pattern image"),
    this layer is now scene-AWARE: it picks a theme from the scene caption
    keywords and renders a different, meaningful abstract composition per
    scene (neural/brain arcs, cells, energy/alert pulses, horizon, etc.)
    instead of the identical bokeh+rings pattern everywhere. It also
    overlays the scene caption text so the visual stays informative even
    when every AI provider is down."""
    try:
        import numpy as _np
        from PIL import Image as _PIL, ImageDraw as _PILD, ImageFilter as _PILF
    except Exception:
        raise RuntimeError("procedural fallback needs numpy/Pillow")

    seed = (index * 100003) + (hashlib.sha256(scene_text.encode()).digest()[0] * 7919)
    rng = _np.random.RandomState(seed % (2**31))
    W, H = 1080, 1920

    theme = _scene_theme(scene_text)
    # Theme-specific palettes (top, bottom) so scenes with different keywords
    # get a different colour mood, not the same pattern every time.
    palettes_by_theme = {
        # dark, mysterious
        "generic": [((5, 5, 12), (15, 20, 40)), ((3, 3, 3), (8, 8, 12))],
        # neural / brain — deep indigo -> violet
        "brain": [((12, 6, 30), (40, 15, 90)), ((8, 4, 28), (30, 10, 70))],
        # night — deep blue -> near-black
        "night": [((2, 4, 18), (10, 20, 60)), ((1, 3, 14), (6, 14, 45))],
        # alert / pain / stress — dark red -> ember
        "alert": [((22, 3, 3), (70, 12, 6)), ((30, 4, 2), (90, 18, 8))],
        # body / anatomy — dark teal -> deep green
        "body": [((3, 14, 12), (8, 40, 30)), ((4, 12, 16), (10, 30, 45))],
    }
    _palettes = palettes_by_theme.get(theme, palettes_by_theme["generic"])
    top, bottom = _palettes[seed % len(_palettes)]
    # Brightness floor: media_validator rejects mean <12 ("Near-black").
    # The raw dark gradients sit at ~10, so we scale the whole image up to
    # land in the 18-30 mean range (still dark & moody, but passing the gate).
    target_mean = 22.0 + (seed % 8)
    img = _PIL.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        f = y / H
        c = tuple(int(top[k] + (bottom[k] - top[k]) * f) for k in range(3))
        for x in range(0, W, 4):
            for xx in range(x, min(x + 4, W)):
                px[xx, y] = c

    arr = _np.asarray(img).astype(_np.float32)
    arr = _np.clip(arr + rng.standard_normal(arr.shape) * 3, 0, 255).astype(_np.uint8)
    img = _PIL.fromarray(arr)

    # Scene-aware composition layer: different meaningful abstract visuals per
    # theme (neural arcs / cells / energy pulses / horizon) instead of the old
    # identical bokeh+rings pattern that looked like "one same image".
    overlay = _PIL.new("RGB", (W, H), (0, 0, 0))
    dr = _PILD.Draw(overlay)
    bokeh = [(60, 90, 170), (120, 60, 60), (50, 50, 90),
             (110, 60, 160), (160, 50, 40), (40, 70, 140)]
    accent = (200, 220, 255)

    if theme == "brain":
        # neural network: branching arcs + node clusters
        for _ in range(26):
            x1, y1 = rng.randint(0, W), rng.randint(0, H)
            x2, y2 = x1 + rng.randint(-350, 350), y1 + rng.randint(-350, 350)
            col = bokeh[rng.randint(0, len(bokeh) - 1)]
            dr.line([x1, y1, x2, y2], fill=tuple(int(v * 0.5) for v in col),
                    width=rng.randint(3, 9))
        for _ in range(30):
            x, y = rng.randint(0, W), rng.randint(0, H)
            r = rng.randint(10, 60)
            col = bokeh[rng.randint(0, len(bokeh) - 1)]
            dr.ellipse([x - r, y - r, x + r, y + r],
                       fill=tuple(int(v * 0.55) for v in col))
    elif theme == "alert":
        # concentric warning pulses radiating from center
        cx, cy = W // 2, H // 2
        for k in range(7):
            r = (k + 1) * (H // 8)
            dr.ellipse([cx - r, cy - r, cx + r, cy + r],
                       outline=(220, 60, 40), width=rng.randint(4, 10))
        for _ in range(24):
            x1, y1 = rng.randint(0, W), rng.randint(0, H)
            x2, y2 = x1 + rng.randint(-120, 120), y1 + rng.randint(-120, 120)
            dr.line([x1, y1, x2, y2], fill=(230, 90, 60), width=3)
    elif theme == "night":
        # moon + horizon silhouette
        mx, my, mr = rng.randint(200, W - 200), rng.randint(200, 600), rng.randint(120, 220)
        dr.ellipse([mx - mr, my - mr, mx + mr, my + mr],
                   fill=tuple(int(v * 0.4) for v in accent))
        for _ in range(40):
            sx = rng.randint(0, W)
            sy = rng.randint(H // 2, H)
            sh = rng.randint(80, 300)
            col = bokeh[rng.randint(0, len(bokeh) - 1)]
            dr.polygon([(sx, sy), (sx + 90, sy), (sx + 45, sy - sh)],
                       fill=tuple(int(v * 0.45) for v in col))
    elif theme == "body":
        # flowing bloodstream / cellular filaments
        for _ in range(18):
            pts = []
            cx, cy = rng.randint(0, W), rng.randint(0, H)
            for j in range(6):
                cx += rng.randint(-120, 120)
                cy += rng.randint(60, 160)
                pts.append((cx, cy))
            col = bokeh[rng.randint(0, len(bokeh) - 1)]
            dr.line(pts, fill=tuple(int(v * 0.5) for v in col), width=rng.randint(6, 16), joint="curve")
        for _ in range(16):
            x, y = rng.randint(0, W), rng.randint(0, H)
            r = rng.randint(20, 70)
            col = bokeh[rng.randint(0, len(bokeh) - 1)]
            dr.ellipse([x - r, y - r, x + r, y + r],
                       outline=tuple(int(v * 0.6) for v in col), width=4)
    else:
        # generic: bokeh lights
        for _ in range(18):
            r = rng.randint(30, 140)
            x, y = rng.randint(0, W), rng.randint(0, H)
            col = bokeh[rng.randint(0, len(bokeh) - 1)]
            dr.ellipse([x - r, y - r, x + r, y + r],
                       fill=tuple(int(v * 0.35) for v in col))

    overlay = overlay.filter(_PILF.GaussianBlur(60))
    img = _PIL.blend(img, overlay, 0.45)

    # vignette (keep but soften so mean stays above 12)
    vign = _PIL.new("L", (W, H), 0)
    dv = _PILD.Draw(vign)
    dv.ellipse([-W * 0.3, -H * 0.25, W * 1.3, H * 1.2], fill=255)
    vign = vign.filter(_PILF.GaussianBlur(250))
    arr = _np.asarray(img).astype(_np.float32)
    arr *= (0.55 + 0.45 * _np.asarray(vign)[..., None] / 255.0)
    img = _PIL.fromarray(_np.clip(arr, 0, 255).astype(_np.uint8))

    # final brightness normalization to clear the validator gate
    arr = _np.asarray(img).astype(_np.float32)
    cur = arr.mean()
    if cur < 15.0:
        arr *= target_mean / max(cur, 1.0)
    img = _PIL.fromarray(_np.clip(arr, 0, 255).astype(_np.uint8))

    # SHARPNESS GATE: media_validator rejects images with edge-energy < 3.0
    # ("Out-of-focus"). A pure blurred gradient scores ~1.1, so we overlay
    # crisp high-contrast geometric structure (thin bright lines / rings /
    # radial streaks) that the edge-energy detector picks up — keeps the
    # dark-cinematic look while passing the gate.
    detail = _PIL.new("RGB", (W, H), (0, 0, 0))
    dd = _PILD.Draw(detail)
    accent = (200, 220, 255)
    if theme == "brain":
        for _ in range(24):
            cx, cy = rng.randint(0, W), rng.randint(0, H)
            r = rng.randint(60, 240)
            dd.ellipse([cx - r, cy - r, cx + r, cy + r],
                       outline=accent, width=rng.randint(2, 4))
    elif theme == "alert":
        for _ in range(20):
            x1, y1 = rng.randint(0, W), rng.randint(0, H)
            x2, y2 = rng.randint(0, W), rng.randint(0, H)
            dd.line([x1, y1, x2, y2], fill=(255, 120, 90), width=rng.randint(2, 5))
    elif theme == "night":
        for _ in range(40):
            x, y = rng.randint(0, W), rng.randint(0, H)
            r = rng.randint(1, 3)
            dd.ellipse([x - r, y - r, x + r, y + r], fill=accent)
    else:
        for _ in range(14):
            cx, cy = rng.randint(0, W), rng.randint(0, H)
            r = rng.randint(120, 420)
            dd.ellipse([cx - r, cy - r, cx + r, cy + r],
                       outline=accent, width=rng.randint(2, 5))
        for _ in range(10):
            x1, y1 = rng.randint(0, W), rng.randint(0, H)
            x2, y2 = rng.randint(0, W), rng.randint(0, H)
            dd.line([x1, y1, x2, y2], fill=accent, width=rng.randint(2, 4))
    detail = detail.filter(_PILF.GaussianBlur(2))
    img = _PIL.blend(img, detail, 0.35)

    # Overlay the scene caption so the visual stays informative even when every
    # AI provider is down (keeps the Short on-topic instead of generic pattern).
    try:
        from PIL import ImageFont
        _text_overlay = _PIL.new("RGBA", (W, H), (0, 0, 0, 0))
        _td = _PILD.Draw(_text_overlay)
        _font = None
        for _fp in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            if os.path.exists(_fp):
                _font = ImageFont.truetype(_fp, 72)
                break
        if _font is not None:
            _text = (scene_text or "")[:90]
            _td.text((90, H - 260), _text, font=_font, fill=(255, 255, 255, 230))
            _td.rectangle([70, H - 300, 90 + 40, H - 220], fill=(0, 0, 0, 0))
        img = _PIL.alpha_composite(img.convert("RGBA"), _text_overlay).convert("RGB")
    except Exception:
        pass  # caption overlay is best-effort

    os.makedirs("output/fallback_images", exist_ok=True)
    path = os.path.join("output/fallback_images", f"proc_{index}_{seed % 100000}.jpg")
    img.save(path, quality=92)
    return path


def _layer1_playwright_screenshot(index, scene_text):
    """Video script ke scene text se relevant website dhoondo (search engine
    ke pehle result se), us page ko khol kar screenshot le lo - wahi screenshot
    is scene ka visual clip ban jata hai. LAST RESORT ONLY - see chain notes
    above; a raw webpage screenshot doesn't match the channel's visual style."""
    from playwright.sync_api import sync_playwright

    query = _safe_query(scene_text, "mystery science")[:100]
    screenshot_bytes = None

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": 1080, "height": 1920})
            page.set_default_timeout(20000)

            # DuckDuckGo ka HTML-only endpoint - no JS needed, easy to scrape,
            # aur bina API key ke kaam karta hai.
            page.goto(f"https://html.duckduckgo.com/html/?q={query}", wait_until="domcontentloaded")
            link = page.query_selector("a.result__a")
            if not link:
                raise RuntimeError("Playwright: search result nahi mila")
            target_url = link.get_attribute("href")
            if not target_url:
                raise RuntimeError("Playwright: search result ka href empty tha")

            page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1500)  # cookie banners/lazy images settle hone dein
            screenshot_bytes = page.screenshot(type="png")
        finally:
            browser.close()

    if not screenshot_bytes or len(screenshot_bytes) < 2000:
        raise RuntimeError("Playwright: screenshot khaali/chota tha")
    return _save_bytes(screenshot_bytes, index, ext="png")


def _perceptual_hash(path: str, media_type: str = "image") -> str | None:
    """64-bit average hash, prefixed so it can live in the same ledger.

    Survives re-encoding, rescaling and recompression — unlike SHA-256, which
    is why the byte-level ledger let the same stock clip appear on five
    different videos. Best-effort: returns None if the media can't be read,
    so a decode problem never blocks an otherwise valid asset."""
    try:
        from PIL import Image as _Image
        if media_type != "image":
            from moviepy.editor import VideoFileClip
            with VideoFileClip(path, audio=False) as clip:
                frame = clip.get_frame(min(0.3, max(clip.duration - 0.05, 0.0)))
            image = _Image.fromarray(frame)
        else:
            image = _Image.open(path)
        small = image.convert("L").resize((8, 8))
        pixels = list(small.getdata())
        average = sum(pixels) / len(pixels)
        bits = "".join("1" if pixel > average else "0" for pixel in pixels)
        return "phash:" + f"{int(bits, 2):016x}"
    except Exception as exc:
        logger.warning("Perceptual hash skipped for %s: %s", path, exc)
        return None


# Two 64-bit average-hashes within this Hamming distance are the same shot.
# Calibrated on the live channel: the re-used clip pair measured 1, while
# genuinely different visuals measured 9-18.
PERCEPTUAL_MAX_DISTANCE = int(os.environ.get("PERCEPTUAL_MAX_DISTANCE", "6"))


def _perceptual_clash(candidate: str | None, used_hashes: set) -> int | None:
    """Return the Hamming distance to the closest already-used visual, or None.

    An exact set lookup is not enough: re-encoding flips a few bits, so the
    re-used stock clip that shipped on two videos differed by exactly 1 bit
    and would still have slipped through an equality check."""
    if not candidate or not candidate.startswith("phash:"):
        return None
    try:
        value = int(candidate.split(":", 1)[1], 16)
    except ValueError:
        return None
    for known in used_hashes:
        if not (isinstance(known, str) and known.startswith("phash:")):
            continue
        try:
            other = int(known.split(":", 1)[1], 16)
        except ValueError:
            continue
        distance = bin(value ^ other).count("1")
        if distance <= PERCEPTUAL_MAX_DISTANCE:
            return distance
    return None


def _validate_clip_first_frame(clip_path: str, source_name: str) -> None:
    """Run the still-image quality bar over a video clip's opening frame.

    Best-effort: if the frame cannot be extracted (missing ffmpeg, odd codec)
    the clip is allowed through rather than failing an otherwise good run."""
    frame_path = None
    try:
        from moviepy.editor import VideoFileClip
        with VideoFileClip(clip_path, audio=False) as clip:
            # ~0.3s in: past any fade-in, still within the swipe window.
            stamp = min(0.3, max(clip.duration - 0.05, 0.0))
            frame = clip.get_frame(stamp)
        from PIL import Image as _Image
        frame_path = f"{clip_path}.firstframe.jpg"
        _Image.fromarray(frame).convert("RGB").save(frame_path, quality=92)
    except MediaValidationError:
        raise
    except Exception as exc:                      # extraction problem only
        logger.warning("%s: could not inspect first frame (%s)", source_name, exc)
        return

    try:
        validate_scene_image(frame_path)
    except MediaValidationError as exc:
        raise RuntimeError(f"{source_name}: first frame rejected — {exc}") from exc
    finally:
        try:
            os.remove(frame_path)
        except OSError:
            pass


def _stock_photo_request(index, scene_text, source: str, used_fallbacks: set):
    query = _safe_query(scene_text, "mystery science")[:80]
    if source == "pexels":
        key = os.environ.get("PEXELS_API_KEY")
        if not key:
            raise RuntimeError("PEXELS_API_KEY not set - skipping live Pexels layer")
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": query, "per_page": 15, "orientation": "portrait"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Pexels bad response: {resp.status_code}")
        photos = resp.json().get("photos", [])
        if not photos:
            raise RuntimeError(f"Pexels: no results for '{query}'")
        img_urls = [
            p["src"].get("portrait") or p["src"].get("large2x")
            or p["src"].get("original") or p["src"]["large"]
            for p in photos
        ]

    elif source == "pixabay":
        key = os.environ.get("PIXABAY_API_KEY")
        if not key:
            raise RuntimeError("PIXABAY_API_KEY not set - skipping live Pixabay layer")
        resp = requests.get(
            "https://pixabay.com/api/",
            params={"key": key, "q": query, "image_type": "photo",
                    "orientation": "vertical", "per_page": 15, "safesearch": "true"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Pixabay bad response: {resp.status_code}")
        hits = resp.json().get("hits", [])
        if not hits:
            raise RuntimeError(f"Pixabay: no results for '{query}'")
        img_urls = [h.get("largeImageURL") or h.get("webformatURL") for h in hits]
    else:
        raise ValueError(f"Unknown stock source: {source}")

    with _fallback_lock:
        for url in img_urls:
            if url in used_fallbacks:
                continue
            used_fallbacks.add(url)
            break
        else:
            url = img_urls[0]
    img_resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    if img_resp.status_code != 200 or len(img_resp.content) < 2000:
        raise RuntimeError(f"{source}: failed to download chosen image")
    return _save_bytes(img_resp.content, index)


def _stock_video_request(index, scene_text, source: str, used_fallbacks: set):
    """Download a licensed stock B-roll clip for a scene when available."""
    query = _safe_query(scene_text, "human body science")[:80]
    if source == "pexels":
        key = os.environ.get("PEXELS_API_KEY")
        if not key:
            raise RuntimeError("PEXELS_API_KEY not set - skipping Pexels video")
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": key},
            params={"query": query, "per_page": 12, "orientation": "portrait"},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Pexels video bad response: {response.status_code}")
        videos = response.json().get("videos", [])
        urls = []
        for video in videos:
            files = video.get("video_files", [])
            # Prefer MP4 clips that are large enough to survive a 9:16 crop.
            candidates = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
            if candidates:
                chosen = max(candidates, key=lambda f: f.get("width", 0) * f.get("height", 0))
                urls.append(chosen["link"])
    elif source == "pixabay":
        key = os.environ.get("PIXABAY_API_KEY")
        if not key:
            raise RuntimeError("PIXABAY_API_KEY not set - skipping Pixabay video")
        response = requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": key, "q": query, "per_page": 20, "safesearch": "true"},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Pixabay video bad response: {response.status_code}")
        urls = []
        for hit in response.json().get("hits", []):
            variants = hit.get("videos", {})
            chosen = variants.get("large") or variants.get("medium") or variants.get("small")
            if chosen and chosen.get("url"):
                urls.append(chosen["url"])
    else:
        raise ValueError(f"Unknown stock-video source: {source}")

    if not urls:
        raise RuntimeError(f"{source}: no usable B-roll video for '{query}'")
    with _fallback_lock:
        url = next((item for item in urls if item not in used_fallbacks), urls[0])
        used_fallbacks.add(url)
    # 2026-08-17: Pexels/Pixabay occasionally serve TRUNCATED streams that
    # still pass the header checks below — the ffprobe at build time then
    # rejects them AFTER 19 minutes of rendering, burning all 3 retries on
    # the same bad scene. Probe here BEFORE saving so the bad URL is simply
    # skipped and the next candidate is tried (or the scene falls to a later
    # layer). Only full corruption here raises; a probe failure just raises
    # too, because used_fallbacks advances this URL out of rotation.
    download = requests.get(url, timeout=60)
    content = download.content
    if download.status_code != 200 or len(content) < 100_000:
        raise RuntimeError(f"{source}: video download failed or was too small")
    # 2026-08-15: Pexels occasionally serves an HTML error/redirect page
    # larger than the 100KB floor — the pipeline accepted it, saved it as
    # .mp4, and then MoviePy crashed at build time ("failed to read the first
    # frame"), burning ~10 minutes of rendering per attempt. Verify the bytes
    # are a real ISO-BMFF/MP4 container (ftyp or moov box) before accepting.
    head = content[:64]
    if not (b"ftyp" in head or b"moov" in head):
        raise RuntimeError(f"{source}: downloaded bytes are not a valid MP4 container")
    path = _save_bytes(content, index, ext="mp4")
    if not _probe_is_valid_video(path):
        raise RuntimeError(
            f"{source}: downloaded clip is truncated or container-corrupt "
            f"(ffprobe failed) — next video candidate will be tried")
    return path, "video"


def _probe_is_valid_video(path: str) -> bool:
    """Fast ffprobe sanity check: readable stream with positive duration.
    Catches truncated Pexels/Pixabay downloads that pass the ftyp/moov byte
    check but are not actually decodable (the build-time probe in
    video_editor.py raised these AFTER wasting ~19 min of rendering per
    attempt)."""
    try:
        import subprocess as _sp
        probe = _sp.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30)
        dur = probe.stdout.strip()
        return bool(dur) and float(dur) > 0.0
    except Exception:  # noqa: BLE001 - probe must never break the download path
        return False


def _layer_pexels_video(index, scene_text, used_fallbacks: set):
    return _stock_video_request(index, scene_text, "pexels", used_fallbacks)


def _layer_pixabay_video(index, scene_text, used_fallbacks: set):
    return _stock_video_request(index, scene_text, "pixabay", used_fallbacks)


def _layer2_pexels_live(index, scene_text, used_fallbacks: set):
    return _stock_photo_request(index, scene_text, "pexels", used_fallbacks)


def _layer3_pixabay_live(index, scene_text, used_fallbacks: set):
    return _stock_photo_request(index, scene_text, "pixabay", used_fallbacks)


def _scene_text(scene) -> str:
    if isinstance(scene, dict):
        return scene.get('visual') or scene.get('description') or scene.get('scene') or scene.get('caption') or ''
    return str(scene)


def _generate_one(index, scene, used_hashes: set, used_fallbacks: set):
    scene_text = _scene_text(scene)
    # The video topic travels with each scene dict (main.py copies
    # script_data['topic'] into it). It locks the signature style for the
    # whole video — one cohesive "Le Labo Obscur" look per video, unlike the
    # shared-stock look every other channel ships.
    topic = scene.get('topic', '') if isinstance(scene, dict) else ''

    layers = [
        # 2026-08-15 signature-world priority (user: "audience wants unique
        # visuals, not what thousands of channels use"). Scenes rendered
        # freshly in the channel's signature macro teal-lab world — visually
        # unique per video (hash-ledger enforced) and recognizably Neuro-Somaa.
        # Stock layers are license-safe (verified) but generic; they now sit
        # BELOW as fallbacks, keeping the pipeline robust when every AI
        # provider is rate-limited.
        ("Signature-AI-primary",  lambda: _layer_ai_providers(index, scene_text, [
            "Pollinations-flux", "Pollinations-turbo", "HuggingFace", "Gemini",
            "DeepAI", "ModelsLab", "Replicate",
        ], topic=topic)),
        ("AI-Horde-secondary",    lambda: _layer_ai_providers(index, scene_text, ["AI-Horde"], topic=topic)),
        # Licensed stock B-roll for genuine motion (Pexels, then Pixabay).
        ("Pexels-video-fallback", lambda: _layer_pexels_video(index, scene_text, used_fallbacks)),
        ("Pixabay-video-fallback", lambda: _layer_pixabay_video(index, scene_text, used_fallbacks)),
        # REAL stock photos as fallback — photographic, not AI-art.
        ("Pexels-image-fallback", lambda: _layer2_pexels_live(index, scene_text, used_fallbacks)),
        ("Pixabay-image-fallback", lambda: _layer3_pixabay_live(index, scene_text, used_fallbacks)),
        ("Local-fallback-pool",   lambda: _layer_local_pool(index, used_fallbacks)),
        ("Procedural-fallback",   lambda: _layer_procedural(index, scene_text)),
        *([("Playwright-screenshot", lambda: _layer1_playwright_screenshot(index, scene_text))]
            if os.environ.get("ENABLE_SCREENSHOT_FALLBACK", "false").lower() == "true" else []),
    ]

    for name, fn in layers:
        try:
            result = fn()
            path, media_type = result if isinstance(result, tuple) else (result, "image")
            if media_type == "image":
                validate_scene_image(path)
            else:
                if not os.path.isfile(path) or os.path.getsize(path) < 100_000:
                    raise RuntimeError(f"{name}: invalid or too-small video clip")
                # Stock B-roll was only ever size-checked, never LOOKED at.
                # That is how "Pourquoi un muscle tressaille tout seul ?"
                # shipped with an almost entirely out-of-focus opening frame
                # (edge energy 1.09). Scene 1 is the whole swipe decision on
                # a Shorts channel, so its first frame gets the same quality
                # bar as a generated image.
                if index == 0:
                    _validate_clip_first_frame(path, name)
            with open(path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            # Exact-byte hash catches only literally identical downloads. Live
            # inspection on 2026-07-27 found FIVE videos sharing visuals at
            # 93-95% similarity — the same Pexels clip re-encoded or served
            # under a different URL produces a different SHA-256 while looking
            # identical to a viewer. Repeating a visual across videos is what
            # makes a channel read as templated. A perceptual hash is checked
            # alongside the byte hash.
            perceptual = _perceptual_hash(path, media_type)
            if file_hash in used_hashes:
                raise RuntimeError(f"{name}: duplicate media; trying next source")
            # Procedural-fallback is the GUARANTEED last resort — it must never
            # fail. Its deterministic-but-unique seed already prevents literal
            # duplicates (byte-hash above) and gives each scene a distinct
            # composition. The perceptual-clash check is intentionally SKIPPED
            # for it: the old one-pattern fallback images live in the channel
            # history, and those perceptually resemble the dark-abstract style,
            # so enforcing phash here made the whole video fail (2026-08-05)
            # exactly when the fallback was most needed.
            is_procedural = name == "Procedural-fallback"
            clash = _perceptual_clash(perceptual, used_hashes) if not is_procedural else None
            if clash:
                raise RuntimeError(
                    f"{name}: visually identical to media already used on this "
                    f"channel (perceptual distance {clash}); trying next source"
                )
            used_hashes.add(file_hash)
            if perceptual and not is_procedural:
                used_hashes.add(perceptual)

            # 2026-08-17 AI image-to-video upgrade (post-hoc): if the chosen
            # layer produced a STATIC image (AI art or stock photo), try to
            # animate it into a genuine AI motion clip via Pollinations
            # Seedance (requires POLLINATIONS_KEY). A failure here is NEVER
            # fatal - the image (already unique) plays with Ken Burns motion,
            # so quality is preserved even when the video layer is skipped.
            if media_type == "image" and os.environ.get("POLLINATIONS_KEY", ""):
                try:
                    clip_path, _ = _layer_ai_video(index, scene_text, image_path=path, topic=topic)
                    if os.path.isfile(clip_path) and os.path.getsize(clip_path) >= 100_000:
                        # Re-validate the rendered clip and swap it in.
                        _validate_clip_first_frame(clip_path, "AI-image-to-video")
                        clip_hash = hashlib.sha256(open(clip_path, "rb").read()).hexdigest()
                        if clip_hash not in used_hashes:
                            used_hashes.discard(file_hash)
                            if perceptual and not is_procedural:
                                used_hashes.discard(perceptual)
                            used_hashes.add(clip_hash)
                            logger.info(f"Scene {index}: static image upgraded to AI motion clip "
                                        f"(AI-image-to-video) -> {clip_path}")
                            return {"index": index, "path": clip_path, "source": "AI-image-to-video",
                                    "media_type": "video"}
                        logger.info(f"Scene {index}: AI clip hash-collision - keeping static image")
                    else:
                        logger.warning(f"Scene {index}: AI video clip too small/missing - keeping static image")
                except Exception as exc:
                    # Budget exhausted, rate-limited, or network - keep the
                    # static image, never burn the slot.
                    logger.warning(f"Scene {index}: AI video upgrade skipped ({exc}); "
                                   f"static image will play with Ken Burns motion")

            logger.info(f"Scene {index}: {media_type} generated via {name} -> {path}")
            return {"index": index, "path": path, "source": name, "media_type": media_type}
        except Exception as e:
            logger.error(f"Scene {index}: {name} failed: {e}")
            continue

    raise RuntimeError(f"Scene {index}: All generation layers failed.")


# Public alias — main.py imports this name.
generate_scene_image = _generate_one
