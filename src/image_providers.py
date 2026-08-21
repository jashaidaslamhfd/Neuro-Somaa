"""
image_providers.py
--------------------
SHARED provider registry — dono jagah use hota hai:
  1. src/image_generator.py          (live, per-video scene images)
  2. scripts/generate_fallback_images.py  (one-time 500-image pool builder)

Pehle Pollinations hardcoded tha har jagah, isliye agar Pollinations
rate-limit ho jaye to poora bulk-generation atak jata tha. Ab yahan ek
hi jagah provider list maintain hoti hai — jitne providers yahan add
karoge, dono scripts automatically unhe fallback order mein try karenge.

Har provider function ka signature same hai:
    fn(prompt: str, seed: int, scene_text: str | None) -> (bytes, ext)
        - prompt      : underscore-joined text (Pollinations-style URL prompt)
        - seed        : random int, variety ke liye
        - scene_text  : original human-readable text (APIs jo JSON body
                         lete hain unke liye, jaise HuggingFace/Gemini)
        - Return      : (image_bytes, file_extension e.g. "jpg"/"png")
        - Fail/Quota  : RuntimeError ya RateLimitError raise karo

Naya provider add karne ke liye: neeche TEMPLATE copy karo, apna function
likho, aur PROVIDER_REGISTRY list mein ek entry add kar do. Bas itna hi —
generate_images() aur generate_fallback_images.py mein kuch badalne ki
zaroorat nahi.
"""

import base64
import os
import random
import time

import requests

REQUEST_TIMEOUT = 30

# Pollinations gets its own shorter timeout. Real-world log evidence: in this
# environment Pollinations was timing out at the full 30s on 7-8 out of 9
# scenes per video (both flux and turbo), meaning ~60s was being burned per
# scene just waiting on a provider that was going to fail anyway before ever
# reaching a provider that actually responds (Pexels). Failing faster here
# doesn't change the eventual outcome when Pollinations is down/degraded -
# it just gets to a working image sooner.
POLLINATIONS_TIMEOUT = 25  # 2026-08-20: raised 15->25s after live runs showed
# intermittent flux/turbo responses landing at 20-24s
# (was being wrongly retried and failed to the wrong
# provider before the response could finish)

POLLINATIONS_URL = "https://image.pollinations.ai/prompt"
HF_API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
GEMINI_IMAGE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
)


class RateLimitError(RuntimeError):
    """Provider ka quota/rate-limit khatam ho gaya — turant agle provider pe jump karo."""


# ---------------------------------------------------------------------------
# 1) POLLINATIONS - flux model (free, no key)
# ---------------------------------------------------------------------------
def _pollinations_request(prompt, seed, model):
    url = f"{POLLINATIONS_URL}/{prompt}?width=1080&height=1920&seed={seed}&model={model}&nologo=true"
    last_status = None
    for attempt in range(2):  # 2026-08-20: 3 attempts -> 2 (one retry only)
        try:
            response = requests.get(url, timeout=POLLINATIONS_TIMEOUT)
            if response.status_code == 200 and len(response.content) > 2000:
                return response.content
            last_status = response.status_code
        except Exception:  # network flake during a long 25s request - retry once
            continue
        if last_status == 429:
            time.sleep(2 + attempt * 3)
            continue
        break
    if last_status == 429:
        raise RateLimitError(f"Pollinations({model}): rate limited")
    raise RuntimeError(f"Pollinations({model}) bad response: {last_status}")


def gen_pollinations_flux(prompt, seed, scene_text=None):
    return _pollinations_request(prompt, seed, "flux"), "jpg"


# ---------------------------------------------------------------------------
# 2) POLLINATIONS - turbo model, fresh seed (free, no key, genuinely
#    different request rather than a duplicate retry of layer 1)
# ---------------------------------------------------------------------------
def gen_pollinations_turbo(prompt, seed, scene_text=None):
    new_seed = random.randint(10000, 99999)
    return _pollinations_request(prompt, new_seed, "turbo"), "jpg"


# ---------------------------------------------------------------------------
# 3) HUGGING FACE Inference API (needs HF_API_KEY env var)
# ---------------------------------------------------------------------------
def gen_huggingface(prompt, seed, scene_text=None):
    hf_key = os.environ.get("HF_API_KEY")
    if not hf_key:
        raise RuntimeError("HF_API_KEY not set")
    text = scene_text or prompt.replace("_", " ")
    headers = {"Authorization": f"Bearer {hf_key}"}
    # 2026-08-17 video-quality fix: without an explicit size, most HF
    # diffusion models default to a 1024x1024 SQUARE image. video_editor's
    # _cover_fit then center-crops that to the 1080x1920 vertical canvas,
    # throwing away ~44% of the image's width (and whatever the subject
    # was standing near the edges) on every scene that lands on this
    # provider. Request the vertical aspect directly instead — 896x1584 is
    # a multiple of 8 close to the 9:16 target most SDXL-class models accept.
    payload = {
        "inputs": text,
        "parameters": {"width": 896, "height": 1584},
    }
    response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    if response.status_code == 429:
        raise RateLimitError("HuggingFace: rate limited")
    if response.status_code == 200 and response.headers.get("content-type", "").startswith("image"):
        return response.content, "jpg"
    raise RuntimeError(f"HuggingFace bad response: {response.status_code} {response.text[:150]}")


# ---------------------------------------------------------------------------
# 4) GOOGLE GEMINI image generation (needs GEMINI_API_KEY env var,
#    free ~50 requests/day via Google AI Studio, no card needed)
# ---------------------------------------------------------------------------
def gen_gemini(prompt, seed, scene_text=None):
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    text = scene_text or prompt.replace("_", " ")
    # 2026-08-17 video-quality fix: the old prompt only ASKED for "vertical"
    # in prose, which this model frequently ignores, returning a square
    # image that then loses ~44% of its width to center-crop when fit onto
    # the 1080x1920 canvas. imageConfig.aspectRatio is the actual control
    # knob for Gemini image generation; setting it directly is far more
    # reliable than hoping the prompt wording is honored.
    payload = {
        "contents": [{"parts": [{"text": f"Generate a photorealistic image, portrait orientation: {text}"}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "9:16"},
        },
    }
    url = f"{GEMINI_IMAGE_URL}?key={gemini_key}"
    response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    if response.status_code == 429:
        raise RateLimitError("Gemini: quota exceeded")
    if response.status_code != 200:
        raise RuntimeError(f"Gemini bad response: {response.status_code} {response.text[:150]}")

    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"]), "png"
    raise RuntimeError("Gemini response contained no image data")


# ---------------------------------------------------------------------------
# 5) DEEPAI text2img (needs DEEPAI_API_KEY, free tier). NOTE: the workflow
#    and env.example were already passing DEEPAI_API_KEY through, but no
#    function/registry entry ever existed to consume it - this was a
#    completely dead env var. Wiring it up here actually uses that free
#    provider slot instead of silently discarding it.
# ---------------------------------------------------------------------------
def gen_deepai(prompt, seed, scene_text=None):
    api_key = os.environ.get("DEEPAI_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPAI_API_KEY not set")
    text = scene_text or prompt.replace("_", " ")
    # 2026-08-17 video-quality fix: DeepAI's text2img has no reliable
    # width/height API parameter, so the aspect ratio has to be steered
    # through the prompt itself — otherwise this defaults to a square
    # image and loses ~44% of its width to the vertical center-crop.
    resp = requests.post(
        "https://api.deepai.org/api/text2img",
        data={"text": f"{text}, vertical 9:16 portrait composition"},
        headers={"api-key": api_key},
        timeout=60,
    )
    if resp.status_code == 429:
        raise RateLimitError("DeepAI: rate limited")
    if resp.status_code != 200:
        raise RuntimeError(f"DeepAI bad response: {resp.status_code} {resp.text[:150]}")
    data = resp.json()
    img_url = data.get("output_url")
    if not img_url:
        raise RuntimeError(f"DeepAI: no output_url in response: {data}")
    img_resp = requests.get(img_url, timeout=30)
    return img_resp.content, "jpg"


# ---------------------------------------------------------------------------
# 6) AI HORDE (aihorde.net - genuinely free, no signup, no key required.
#    Replaces Craiyon, which was confirmed to have NO official public API -
#    the "craiyon.com/v3" endpoint below was always a reverse-engineered/
#    unofficial route, which is exactly why it was 403ing on every single
#    run from day one, not a temporary outage. AI Horde is a real,
#    documented, community-run REST API (crowdsourced volunteer GPUs) that
#    works anonymously via the public "0000000000" key - anonymous requests
#    just get lower queue priority, so this polls for up to ~90s before
#    giving up and letting the next provider take over.)
# ---------------------------------------------------------------------------
import contextlib
import logging as _logging

logger = _logging.getLogger("image_providers")
_HORDE_ANON_KEY = "0000000000"

# Run-scoped flag: a secret AI_HORDE_API_KEY that returns 401 InvalidAPIKey
# (expired/typo'ed) is silently downgraded to the anonymous key once, instead
# of failing every AI-Horde scene with the same spammy error for the whole
# run. Detected InvalidAPIKey responses always fall back to anonymous.
_horde_key_invalidated = [False]


def gen_ai_horde(prompt, seed, scene_text=None):
    text = (scene_text or prompt.replace("_", " "))[:1000]
    headers = {"apikey": os.environ.get("AI_HORDE_API_KEY", _HORDE_ANON_KEY)}

    def _horde_was_invalid(resp):
        """Detect the 401 InvalidAPIKey response from an invalid secret key."""
        if resp.status_code != 401:
            return False
        try:
            payload = resp.json()
        except Exception:
            return False
        return payload.get("rc") == "InvalidAPIKey" or "InvalidAPIKey" in payload.get("message", "")

    # Anonymous requests share a dynamic, demand-based max PIXEL-AREA cap,
    # expressed by AI Horde as "requests over NxN" (i.e. width*height must
    # stay under N*N). Observed caps in practice range ~576x576 (331,776px)
    # up to ~669x669 (447,561px), and fluctuate run to run with load.
    #
    # HD tip: that cap applies to the *anonymous* "0000000000" key. A free
    # AI Horde account (https://aihorde.net/register - no card, just an
    # email) gets a real API key with a much higher priority + resolution
    # allowance, and costs nothing. Set it as the AI_HORDE_API_KEY secret
    # in your GitHub repo (Settings -> Secrets and variables -> Actions) and
    # this function picks it up automatically (falls back to anonymous if
    # unset) - that alone is usually enough to get the top (768x1344) tier
    # below through consistently instead of falling back to the small ones.
    #
    # Try progressively smaller sizes - multiples of 64, as required by the
    # underlying SD models - until one fits under whatever the current cap
    # happens to be. The first two tiers are HD-ish (close to the final
    # 1080x1920 Shorts canvas); the rest are the original small fallbacks
    # for when demand is high and even a registered key gets capped.
    size_tiers = [(768, 1344), (640, 1152), (576, 1024), (448, 768), (384, 640), (320, 512)]

    submit = None
    last_size_err = None
    for width, height in size_tiers:
        submit = requests.post(
            "https://aihorde.net/api/v2/generate/async",
            json={
                "prompt": text,
                "params": {
                    "width": width,
                    "height": height,
                    "steps": 30,
                    "n": 1,
                    "sampler_name": "k_euler_a",
                    "cfg_scale": 7,
                },
                "negative_prompt": "blurry, soft focus, low resolution, dull, dark, grainy, distorted, watermark, text, logo",
                "nsfw": False,
                "censor_nsfw": True,
            },
            headers=headers,
            timeout=20,
        )
        if submit.status_code == 429:
            raise RateLimitError("AI Horde: rate limited")
        if submit.status_code == 403:
            # This size tier is over the current demand cap - shrink and retry.
            last_size_err = f"{width}x{height} rejected: {submit.text[:150]}"
            continue
        if _horde_was_invalid(submit):
            # 2026-08-15: the repo secret AI_HORDE_API_KEY is set but invalid
            # (401 InvalidAPIKey - expired or typo). Retry this tier once with
            # the anonymous key and keep going for the whole run.
            if headers["apikey"] != _HORDE_ANON_KEY:
                logger.warning(
                    "AI Horde: secret key invalid (%s) — retrying with "
                    "anonymous key for the rest of this run",
                    submit.text[:120],
                )
                headers = {"apikey": _HORDE_ANON_KEY}
                _horde_key_invalidated[0] = True
                continue
            raise RuntimeError(f"AI Horde submit bad response: {submit.status_code} {submit.text[:150]}")
        if submit.status_code not in (200, 202):
            raise RuntimeError(f"AI Horde submit bad response: {submit.status_code} {submit.text[:150]}")
        break
    else:
        raise RuntimeError(f"AI Horde: all size tiers over demand cap - {last_size_err}")

    job_id = submit.json().get("id")
    if not job_id:
        raise RuntimeError(f"AI Horde: no job id in response: {submit.json()}")

    # Anonymous key = lowest queue priority, so this can take a while. Poll
    # for up to ~60s (12 x 5s); if it's not done by then, give up and let
    # the next provider in the chain take over rather than blocking.
    max_wait_seconds = int(os.environ.get("AI_HORDE_MAX_WAIT", "300"))
    poll_interval = 5
    for _ in range(max(1, max_wait_seconds // poll_interval)):
        time.sleep(poll_interval)
        check = requests.get(f"https://aihorde.net/api/v2/generate/check/{job_id}", timeout=15).json()
        if check.get("done"):
            break
        if check.get("faulted"):
            raise RuntimeError("AI Horde: job faulted")
    else:
        with contextlib.suppress(Exception):
            requests.delete(
                f"https://aihorde.net/api/v2/generate/status/{job_id}",
                headers=headers,
                timeout=15,
            )
        raise RuntimeError(f"AI Horde: timed out after {max_wait_seconds} seconds")

    status = requests.get(f"https://aihorde.net/api/v2/generate/status/{job_id}", timeout=15).json()
    generations = status.get("generations", [])
    if not generations:
        raise RuntimeError("AI Horde: no generations returned")
    img_url = generations[0].get("img")
    if not img_url:
        raise RuntimeError("AI Horde: generation had no image URL")
    img_resp = requests.get(img_url, timeout=30)
    return img_resp.content, "webp"


# ---------------------------------------------------------------------------
# 7) MODELSLAB (needs MODELSLAB_API_KEY, free tier ~100 calls/day, no card)
#    10,000+ models (Flux, SDXL, SD3.5) via one REST endpoint.
# ---------------------------------------------------------------------------
def gen_modelslab(prompt, seed, scene_text=None):
    api_key = os.environ.get("MODELSLAB_API_KEY")
    if not api_key:
        raise RuntimeError("MODELSLAB_API_KEY not set")
    text = scene_text or prompt.replace("_", " ")
    # 2026-08-17 video-quality fix: this was requesting a literal 1024x1024
    # SQUARE image against a 1080x1920 vertical Shorts canvas — video_editor's
    # _cover_fit center-crops that down to ~56% of its width, cutting off
    # whatever the subject was near the edges on every scene this provider
    # served. 768x1344 is a multiple of 64 (required by the underlying SD
    # models) and matches the same near-9:16 tier already used successfully
    # for AI-Horde's top resolution.
    payload = {
        "key": api_key,
        "prompt": text,
        "negative_prompt": "blurry, low quality, watermark",
        "width": "768",
        "height": "1344",
        "samples": "1",
        "safety_checker": "no",
    }
    resp = requests.post("https://modelslab.com/api/v6/images/text2img", json=payload, timeout=60)
    if resp.status_code == 429:
        raise RateLimitError("ModelsLab: rate limited")
    if resp.status_code != 200:
        raise RuntimeError(f"ModelsLab bad response: {resp.status_code}")
    data = resp.json()
    if data.get("status") not in ("success", "processing"):
        raise RuntimeError(f"ModelsLab error: {data.get('message', data)}")
    images = data.get("output") or data.get("images") or []
    if not images:
        raise RuntimeError("ModelsLab: no image URL returned (may need to poll fetch_result)")
    img_resp = requests.get(images[0], timeout=60)
    return img_resp.content, "jpg"


# ---------------------------------------------------------------------------
# 8) REPLICATE (needs REPLICATE_API_TOKEN, free trial credits on signup)
#    Uses black-forest-labs/flux-schnell, polls until prediction completes.
# ---------------------------------------------------------------------------
def gen_replicate(prompt, seed, scene_text=None):
    api_token = os.environ.get("REPLICATE_API_TOKEN")
    if not api_token:
        raise RuntimeError("REPLICATE_API_TOKEN not set")
    text = scene_text or prompt.replace("_", " ")
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    resp = requests.post(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
        headers=headers,
        # 2026-08-17 video-quality fix: flux-schnell defaults to a 1024x1024
        # square image without this. aspect_ratio is a documented input on
        # this model — "9:16" matches the Shorts canvas directly instead of
        # relying on video_editor's center-crop to fix it up after the fact.
        json={"input": {"prompt": text, "aspect_ratio": "9:16"}},
        timeout=30,
    )
    if resp.status_code == 429:
        raise RateLimitError("Replicate: rate limited")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Replicate bad response: {resp.status_code} {resp.text[:150]}")

    prediction = resp.json()
    get_url = prediction.get("urls", {}).get("get")
    if not get_url:
        raise RuntimeError("Replicate: no polling URL in response")

    for _ in range(20):  # poll up to ~20s
        time.sleep(1)
        poll = requests.get(get_url, headers=headers, timeout=15).json()
        status = poll.get("status")
        if status == "succeeded":
            output = poll.get("output")
            img_url = output[0] if isinstance(output, list) else output
            if not img_url:
                raise RuntimeError("Replicate: succeeded but no output URL")
            img_resp = requests.get(img_url, timeout=30)
            return img_resp.content, "jpg"
        if status == "failed":
            raise RuntimeError(f"Replicate: prediction failed - {poll.get('error')}")
    raise RuntimeError("Replicate: timed out waiting for prediction")


# ---------------------------------------------------------------------------
# TEMPLATE — naya provider add karne ke liye ye copy karein
# ---------------------------------------------------------------------------
def gen_TEMPLATE(prompt, seed, scene_text=None):
    """
    1. os.environ.get("YOUR_KEY_NAME") se key uthao (agar chahiye)
    2. Provider ko request bhejo
    3. Rate-limit/quota mile to RateLimitError raise karo
    4. Koi aur error ho to RuntimeError raise karo
    5. Success par (image_bytes, "jpg"/"png") return karo
    """
    raise NotImplementedError(
        "Ye sirf template hai — PROVIDER_REGISTRY mein register mat karo jab tak likha na ho"
    )


# ---------------------------------------------------------------------------
# REGISTRY — fallback order yahan control hota hai (upar se neeche try hoga)
# env_keys: [] matlab koi key nahi chahiye, warna un sab env vars ka set
# hona zaroori hai warna wo provider automatically skip ho jata hai.
# 50 tak yahan providers add kar sakte hain — bas ek line.
# ---------------------------------------------------------------------------
PROVIDER_REGISTRY = [
    {"name": "AI-Horde", "env_keys": [], "generate": gen_ai_horde},
    {"name": "Pollinations-flux", "env_keys": [], "generate": gen_pollinations_flux},
    {"name": "Pollinations-turbo", "env_keys": [], "generate": gen_pollinations_turbo},
    {"name": "HuggingFace", "env_keys": ["HF_API_KEY"], "generate": gen_huggingface},
    {"name": "Gemini", "env_keys": ["GEMINI_API_KEY"], "generate": gen_gemini},
    {"name": "DeepAI", "env_keys": ["DEEPAI_API_KEY"], "generate": gen_deepai},
    {"name": "ModelsLab", "env_keys": ["MODELSLAB_API_KEY"], "generate": gen_modelslab},
    {"name": "Replicate", "env_keys": ["REPLICATE_API_TOKEN"], "generate": gen_replicate},
    # --- Yahan neeche naye providers add karte jayein (up to 50) ---
    # Big platforms jo isi TEMPLATE pattern se add ho sakte hain jaise jaise
    # aap unki free/trial keys banate hain — README.md mein poori list hai:
    # Stability AI, Leonardo AI, Segmind, Together AI, Fireworks AI,
    # Cloudflare Workers AI, Ideogram, Getimg.ai, Playground AI, OpenAI
    # DALL-E, Adobe Firefly, Microsoft Designer, NightCafe, Fal.ai, etc.
    # {"name": "my_provider_9", "env_keys": ["MY_KEY"], "generate": gen_my_provider_9},
]


# ---------------------------------------------------------------------------
# 9) POLLINATIONS VIDEO - AI image-to-video (2026-08-17)
#    Stock B-roll was always shared with thousands of other channels. AI
#    image-to-video renders motion that exists ONLY on this channel: each
#    unique scene image becomes a 4s 720p clip via Seedance 2.5
#    (gen.pollinations.ai). Account: free Pollinations key from
#    https://enter.pollinations.ai/keys (Pollen wallet gives free starter
#    credits; ~0.10 Pollen per video-second) stored in POLLINATIONS_KEY.
#    Without the key this layer is skipped and the pipeline falls back to
#    the signature AI image + professional Ken Burns motion.
#    NOTE: does NOT follow the (bytes, ext) image-provider signature — it
#    is a video layer called directly by _layer_ai_video (image_generator).
# ---------------------------------------------------------------------------
POLLINATIONS_VIDEO_URL = "https://gen.pollinations.ai/video"
POLLINATIONS_VIDEO_TIMEOUT = int(os.environ.get("POLLINATIONS_VIDEO_TIMEOUT", "90"))


def gen_pollinations_video(
    prompt: str,
    scene_text: str,
    image_path: str | None = None,
    model: str | None = None,
    duration: str | None = None,
):
    """Generate a vertical AI motion clip from text (+ optional source image).
    Returns (bytes, ext) or raises RuntimeError / RateLimitError."""
    key = os.environ.get("POLLINATIONS_KEY", "")
    if not key:
        raise RuntimeError("POLLINATIONS_KEY not set - AI video layer skipped")
    model = model or os.environ.get("AI_VIDEO_MODEL", "seedance-2.5")
    duration = duration or os.environ.get("AI_VIDEO_DURATION", "4")
    params = {
        "model": model,
        "aspectRatio": os.environ.get("AI_VIDEO_ASPECT", "9:16"),
        "duration": duration,
        "key": key,
    }
    # seedance-2.5 accepts first/last reference frames -> true image-to-video:
    # the rendered scene image becomes frame 1, so the clip visually matches
    # the caption exactly (APIDOCS 2026-08-13).
    if image_path and os.path.isfile(image_path):
        try:
            with open(image_path, "rb") as fh:
                upload = requests.post(
                    "https://media.pollinations.ai/upload",
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": (os.path.basename(image_path), fh, "image/jpeg")},
                    timeout=30,
                )
            if upload.status_code == 200:
                data = upload.json()
                media_id = data.get("id")
                if media_id:
                    params["image[0]"] = (
                        str(media_id)
                        if str(media_id).startswith("http")
                        else f"https://media.pollinations.ai/{media_id}"
                    )
                elif data.get("url"):
                    params["image[0]"] = data["url"]
        except Exception as exc:  # media upload is optional - never block the run
            logger.warning(
                "AI-video: reference image upload failed (%s) - falling back to text-to-video", exc
            )
    url = f"{POLLINATIONS_VIDEO_URL}/{prompt}"
    resp = requests.get(url, params=params, timeout=POLLINATIONS_VIDEO_TIMEOUT)
    if resp.status_code == 401:
        raise RateLimitError("Pollinations-video: key rejected/missing")
    if resp.status_code == 402:
        raise RateLimitError("Pollinations-video: free Pollen budget exhausted")
    if resp.status_code == 429:
        raise RateLimitError("Pollinations-video: rate limited")
    if resp.status_code == 503:
        raise RuntimeError("Pollinations-video: service busy")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Pollinations-video bad response: {resp.status_code} {resp.text[:150]}")
    content = resp.content
    if len(content) < 50_000:
        raise RuntimeError("Pollinations-video: response too small")
    if not (b"ftyp" in content[:64] or b"moov" in content[:64]):
        raise RuntimeError("Pollinations-video: response is not a valid MP4")
    return content, "mp4"


def available_providers():
    """Sirf wo providers return karta hai jinke required env vars set hain
    (no-key providers hamesha available hote hain)."""
    return [p for p in PROVIDER_REGISTRY if all(os.environ.get(k) for k in p["env_keys"])]
