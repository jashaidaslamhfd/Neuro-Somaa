"""AI-generated viral dark-science background music (Neuro-Somaa, FR).

2026-08-20: ported from the Khateb-Ishq sad-poetry music engine and
retuned for Neuro-Somaa's brand: mystery/medical documentary BGM rather
than sad poetry. Emotional minor-key piano + soft strings + quiet
pulse — the vibe behind viral French science Shorts — unique to EVERY
video (no stock repetition, no Content ID claims, royalty-free).

Engine: ModelsLab text-to-music (MODELSLAB_API_KEY already in repo
secrets). Fallback: legacy mood-picked stock track / synth drone — the
pipeline NEVER blocks.
"""

import contextlib
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request

import requests

BASE_VAULT = os.path.join("assets", "music", "generated")
MAX_POLL = 10
POLL_INTERVAL = 8


# ---------------------------------------------------------------------------
# Prompt crafting — viral dark-science bed template + theme words
# ---------------------------------------------------------------------------
_BASE_PROMPT = (
    "Cinematic dark-science documentary instrumental, haunting emotional "
    "minor-key piano melody with soft atmospheric strings, subtle deep "
    "ambient pulse and delicate clockwork texture in the background, slow "
    "{bpm} BPM, mysterious and thoughtful, French science-YouTube viral "
    "aesthetic, instrumental only, no vocals, no loud drums, no "
    "percussion, smooth and seamless loop-friendly, studio quality"
)

_MUSIC_GEN_URL = "https://modelslab.com/api/v6/voice/music_gen"


def _make_prompt(theme: str, bpm: int = 70) -> str:
    clean = re.sub(r"[^\w\s\u00C0-\u024F]+", "", theme or "")
    words = " ".join(clean.split())[:60]
    text = _BASE_PROMPT.format(bpm=bpm)
    if words:
        text += f", inspired mood: {words}"
    return text


# ---------------------------------------------------------------------------
# Generation via ModelsLab
# ---------------------------------------------------------------------------
def generate_sad_music(theme: str = "", duration: int = 30) -> str | None:
    """Generate a unique sad-poetry BGM. Returns output path or None on
    failure (caller should fall back to legacy _pick_music)."""
    api_key = os.environ.get("MODELSLAB_API_KEY", "").strip()
    if not api_key:
        return None
    import logging

    logger = logging.getLogger("music_generator")
    os.makedirs(BASE_VAULT, exist_ok=True)
    payload = {
        "key": api_key,
        "prompt": _make_prompt(theme),
        "duration": duration,
        "output_format": "wav",
    }
    try:
        resp = requests.post(_MUSIC_GEN_URL, json=payload, timeout=120)
    except Exception as exc:
        logger.warning("Music API unreachable (%s) — using stock track", exc)
        return None
    if resp.status_code == 429:
        logger.warning("Music API rate-limited — using stock track")
        return None
    if resp.status_code != 200:
        logger.warning("Music API HTTP %s — using stock track", resp.status_code)
        return None
    data = resp.json()
    status = data.get("status")
    urls = data.get("output") or []
    if status == "success" and urls:
        return _download_track(urls[0], theme)
    if status in ("processing", "not_found") and data.get("fetch_result"):
        # queued async — poll for the result URL
        fetch = data["fetch_result"]
        for _ in range(MAX_POLL):
            time.sleep(POLL_INTERVAL)
            try:
                with urllib.request.urlopen(fetch, timeout=30) as r:
                    d = json.load(r)
            except Exception:
                continue
            out = d.get("output") or []
            if d.get("status") == "success" and out:
                return _download_track(out[0], theme)
            if d.get("status") == "failed":
                return None
        logger.warning("Music API polling timeout — using stock track")
    return None


def _download_track(url: str, theme: str) -> str:
    slug = re.sub(r"[^\w]+", "_", theme or "mystery")[:40]
    path = os.path.join(
        BASE_VAULT, f"viral_dark_{slug}_{int(time.time())}_{random.randint(100, 999)}".strip() + ".wav"
    )
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as f:
            f.write(r.read())
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(path)
        return None
    size = os.path.getsize(path)
    if size < 100000:  # empty/broken response
        with contextlib.suppress(OSError):
            os.remove(path)
        return None
    return path


def pick_track(theme: str = "", target_duration: float = 0.0) -> str | None:
    """Public entry: try AI-generated viral track first; fall back to the
    legacy mood-picked stock track so rendering never breaks."""
    gen = generate_sad_music(theme=theme, duration=max(20, int(target_duration)))
    if gen:
        return gen
    try:
        from video_editor import _pick_music  # legacy mood selection

        return _pick_music(theme=theme)
    except ImportError:
        return None
