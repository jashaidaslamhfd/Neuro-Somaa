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


def _build_prompt(scene_text: str) -> str:
    """Combines the script's own scene description with a fixed dark/moody
    style suffix, so every AI-generated image stays on-brand for the
    dark-mystery-science niche instead of a generic photo of the subject."""
    base = (scene_text or "mystery science").strip()
    return f"{base}, {DARK_STYLE_SUFFIX}"


def _layer_ai_providers(index, scene_text, provider_names=None):
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

    prompt_text = _build_prompt(scene_text)
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
    download = requests.get(url, timeout=60)
    if download.status_code != 200 or len(download.content) < 100_000:
        raise RuntimeError(f"{source}: video download failed or was too small")
    return _save_bytes(download.content, index, ext="mp4"), "video"


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

    layers = [
        # First use licensed stock B-roll (Pexels, then Pixabay) for genuine motion.
        # If no suitable clip exists, generate a unique AI Horde visual before
        # any other image source, reducing repeated-stock-image dependence.
        ("Pexels-video-first",    lambda: _layer_pexels_video(index, scene_text, used_fallbacks)),
        ("Pixabay-video-second",  lambda: _layer_pixabay_video(index, scene_text, used_fallbacks)),
        ("AI-Horde-image",        lambda: _layer_ai_providers(index, scene_text, ["AI-Horde"])),
        ("Other-AI-image",        lambda: _layer_ai_providers(index, scene_text, [
            "Pollinations-flux", "Pollinations-turbo", "HuggingFace", "Gemini",
            "DeepAI", "ModelsLab", "Replicate",
        ])),
        ("Local-fallback-pool",   lambda: _layer_local_pool(index, used_fallbacks)),
        ("Pexels-image",          lambda: _layer2_pexels_live(index, scene_text, used_fallbacks)),
        ("Pixabay-image",         lambda: _layer3_pixabay_live(index, scene_text, used_fallbacks)),
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
            clash = _perceptual_clash(perceptual, used_hashes)
            if clash:
                raise RuntimeError(
                    f"{name}: visually identical to media already used on this "
                    f"channel (perceptual distance {clash}); trying next source"
                )
            used_hashes.add(file_hash)
            if perceptual:
                used_hashes.add(perceptual)

            logger.info(f"Scene {index}: {media_type} generated via {name} -> {path}")
            return {"index": index, "path": path, "source": name, "media_type": media_type}
        except Exception as e:
            logger.error(f"Scene {index}: {name} failed: {e}")
            continue

    raise RuntimeError(f"Scene {index}: All generation layers failed.")


# Public alias — main.py imports this name.
generate_scene_image = _generate_one
