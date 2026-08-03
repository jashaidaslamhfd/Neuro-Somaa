"""
src/platform_captions.py — one caption per platform, written for that
platform's ranking system (French Version).
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Dict, List, Sequence

YOUTUBE = "youtube_shorts"
FACEBOOK = "facebook_reels"
INSTAGRAM = "instagram_reels"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

_YT_CLOSERS = (
    "Abonnez-vous pour un nouveau Short sur le corps humain chaque jour.",
    "Abonne-toi — un mystère de ton corps expliqué quotidiennement.",
    "Suivez pour une science courte, précise et sans artifice.",
    "Rejoignez-nous pour comprendre la biologie du quotidien.",
)

_META_CLOSERS = (
    "Abonne-toi pour ta dose quotidienne de science du corps.",
    "Suivez pour plus de biologie expliquée simplement.",
    "Abonne-toi — un mystère du corps par jour.",
    "Suivez pour comprendre le corps dans lequel vous vivez.",
)

def _clean(text: object, limit: int = 400) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    value = re.sub(r"#[A-Za-z0-9_]+", "", value)
    return value[:limit]

def _sentence(text: str) -> str:
    value = (text or "").strip()
    if value and value[-1] not in ".!?…":
        value += "."
    return value

def build_youtube_description(script_data: Dict, tags: Sequence[str]) -> str:
    hook = _clean(script_data.get("hook"), 180)
    summary = _clean(script_data.get("description"), 400)
    parts = []
    if hook: parts.append(_sentence(hook))
    if summary: parts.append(_sentence(summary))
    parts.append("Abonnez-vous pour ne rien rater !")
    hashtags = ["#Shorts", "#Science", "#CorpsHumain"]
    parts.append(" ".join(hashtags))
    return "\n\n".join(parts)

def build_facebook_caption(script_data: Dict, tags: Sequence[str]) -> str:
    hook = _clean(script_data.get("hook"), 180)
    summary = _clean(script_data.get("description"), 400)
    parts = []
    if hook: parts.append(_sentence(hook))
    if summary: parts.append(_sentence(summary))
    parts.append(random.choice(_META_CLOSERS))
    parts.append("#Science #CorpsHumain #Savoir")
    return "\n\n".join(parts)

def build_instagram_caption(script_data: Dict, tags: Sequence[str]) -> str:
    return build_facebook_caption(script_data, tags)

import random
