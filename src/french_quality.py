from __future__ import annotations

import re
from typing import Any

_FILLERS = (
    "dans cette vidéo",
    "aujourd'hui on va",
    "aujourd’hui on va",
    "bonjour à tous",
    "salut tout le monde",
    "je vais vous expliquer",
    "dans cet épisode",
)

_ENGLISH_LEAKS = re.compile(
    r"\b(?:the|your|you|why|what|how|brain|body|sleep|memory|"
    r"this|that|today|video|subscribe|like|follow)\b",
    re.IGNORECASE,
)


def validate_french_script(script: dict[str, Any], min_seconds: float = 15, max_seconds: float = 22) -> list[str]:
    """Hard production gate for natural, compact French Shorts.

    This is deliberately conservative: a generation is retried instead of
    silently publishing a malformed title, filler intro, overlong narration,
    or metadata that does not match the requested French market.
    """
    errors: list[str] = []
    title = str(script.get("title", "")).strip()
    scenes = script.get("scenes", [])
    description = str(script.get("description", "")).strip()
    tags = script.get("tags", [])

    if not title:
        errors.append("titre vide")
    if len(title) > 60:
        errors.append("titre trop long pour un Short mobile")
    if "#" in title:
        errors.append("hashtags interdits dans le titre")

    if not isinstance(scenes, list) or not 6 <= len(scenes) <= 10:
        errors.append("le Short doit contenir 6 à 10 scènes courtes")

    captions: list[str] = []
    narration_words = 0
    for index, scene in enumerate(scenes, 1):
        caption = re.sub(r"\s+", " ", str(scene.get("caption", "")).strip())
        narration = re.sub(r"\s+", " ", str(scene.get("narration", "")).strip())
        if not caption or not narration:
            errors.append(f"scène {index} incomplète")
            continue
        words = caption.split()
        if not 2 <= len(words) <= 8:
            errors.append(f"caption scène {index} trop longue/courte")
        if len(narration.split()) > 16:
            errors.append(f"narration scène {index} trop longue")
        if any(filler in narration.lower() for filler in _FILLERS):
            errors.append(f"introduction générique en scène {index}")
        if _ENGLISH_LEAKS.search(caption + " " + narration):
            errors.append(f"anglais détecté en scène {index}")
        captions.append(caption.casefold())
        narration_words += len(narration.split())

    if len(captions) != len(set(captions)):
        errors.append("captions répétées")
    if not 42 <= narration_words <= 72:
        errors.append(f"volume de narration hors cible: {narration_words} mots")

    if description.count("#") < 3 or description.count("#") > 5:
        errors.append("description: 3 à 5 hashtags attendus")
    if not isinstance(tags, list) or not 8 <= len(tags) <= 12:
        errors.append("8 à 12 tags SEO attendus")

    return errors
