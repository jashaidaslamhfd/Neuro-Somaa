"""Channel growth engine for Neuro-Somaa French Shorts.

Goal: reduce swipe-away and compound views with consistent public posts.

Levers:
1. Felt-science topic allowlist (body glitch, cerveau, sommeil, stress, attention)
2. Hard ban on news / medical-drama / politics pollution
3. Viral title shaping (tu/ton, curiosity gap, complete sentence)
4. Opening-hook enforcement (first narration = question or shock, no filler)
5. SEO description + hashtag pack for French Shorts discovery
6. Growth-state machine + history-ranked topic bias
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("neuro_somaa.growth")

_ALLOW_KEYWORDS = (
    "cerveau", "mémoire", "souvenir", "attention", "décision", "conscience",
    "sommeil", "rêve", "insomnie", "réveil", "fatigue",
    "stress", "anxiété", "panique", "émotion",
    "corps", "muscle", "nerf", "peau", "cœur", "ventre", "pied", "main",
    "œil", "oeil", "paupière", "mâchoire", "fourmillement", "tressaille",
    "bâille", "baille", "démange", "gratte", "engourd",
    "téléphone", "écran", "notification", "scroll", "dopamine",
    "habitude", "addiction", "récompense", "comportement",
    "temps", "danger", "réflexe",
)

_BAN_KEYWORDS = (
    "tumeur", "cancer", "alzheimer", "ukraine", "gaza", "guerre", "élection",
    "politique", "festival", "exposition", "témoignage", "prix nobel",
    "concarneau", "bannalec", "artistes", "leçons politiques",
    "surcharge mentale, perte", "jour de mémoire",
    "on lui découvre", "quatre artistes",
)

_BANNED_WEAK_OPENERS = (
    "pourquoi quatre",
    "pourquoi on lui",
    "pourquoi jour de",
    "pourquoi stress, surcharge",
    "pourquoi développons",
    "sommeil en orbite",
    "le secret du fruit",
    "alzheimer: la vérité",
    "pourquoi les jeunes deviennent",
)

_HIGH_VELOCITY_CLUSTERS = (
    ("cerveau", "mémoire", "attention", "décision", "souvenir"),
    ("sommeil", "rêve", "insomnie", "réveil", "fatigue"),
    ("stress", "anxiété", "panique", "corps", "ventre", "cœur"),
    ("téléphone", "écran", "notification", "scroll", "dopamine"),
    ("pied", "main", "peau", "œil", "oeil", "mâchoire", "fourmillement"),
)

_FILLER_OPENERS = (
    "dans cette vidéo",
    "aujourd'hui on va",
    "aujourd’hui on va",
    "bonjour",
    "salut tout le monde",
    "je vais vous",
    "dans cet épisode",
)

_SHORTS_HASHTAG_CORE = (
    "#shorts",
    "#science",
    "#cerveau",
    "#france",
    "#psychologie",
)

_VIRAL_TITLE_TEMPLATES = (
    "Pourquoi ton cerveau fait ça ?",
    "Ton corps réagit sans que tu le saches",
    "Pourquoi tu ressens ça vraiment ?",
    "Ce que ton cerveau cache vraiment",
    "Pourquoi ton sommeil te ment ?",
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_allowed_growth_topic(topic: str) -> bool:
    """True if topic is felt-science and not news/medical-drama pollution."""
    t = _clean(topic).lower()
    if len(t) < 12:
        return False
    if any(b in t for b in _BAN_KEYWORDS):
        return False
    if any(b in t for b in _BANNED_WEAK_OPENERS):
        return False
    if not any(k in t for k in _ALLOW_KEYWORDS):
        if t.startswith("pourquoi") and any(
            w in t for w in ("ton ", "ta ", "tes ", "tu ", "corps", "cerveau")
        ):
            return True
        return False
    return True


def is_weak_title(title: str) -> bool:
    t = title.lower().strip()
    if len(t) < 18:
        return True
    if len(t) > 60:
        return True
    if t.endswith("?") and t.count("?") > 1:
        return True
    if any(b in t for b in _BANNED_WEAK_OPENERS):
        return True
    if any(b in t for b in _BAN_KEYWORDS):
        return True
    if t.endswith(
        ("la ?", "de ?", "le ?", "les ?", "des ?", "du ?", "un ?", "une ?", "et ?", "à ?", "a ?")
    ):
        return True
    if re.search(r"\b(pourquoi|comment)\s+\w{1,3}\s*\?$", t):
        return True
    if t.endswith(("capte ?", "déforme ?", "fait ?", "est ?")) and len(t) < 32:
        return True
    return False


def shape_viral_title(title: str, topic: str = "") -> str:
    """Keep strong titles; repair weak/truncated ones without generic spam."""
    original = _clean(title)
    topic_c = _clean(topic)

    if not is_weak_title(original) and 18 <= len(original) <= 58:
        if original[-1] not in "?!":
            original = original.rstrip(".") + " ?"
        return original

    source = topic_c if topic_c and len(topic_c) >= len(original) else original
    source = source.rstrip(" ?.")

    low = source.lower()
    if not re.search(r"\b(ton|ta|tes|tu|toi)\b", low):
        if low.startswith("pourquoi "):
            rest = source[9:].lstrip()
            if not rest.lower().startswith(("ton ", "ta ", "tes ")):
                source = f"Pourquoi ton {rest}"
        else:
            source = f"Pourquoi ton cerveau {source}" if "cerveau" not in low else source

    if not source.lower().startswith(
        ("pourquoi", "comment", "ton ", "ta ", "ce que", "attention")
    ):
        source = f"Pourquoi {source}" if not source.lower().startswith("pourquoi") else source

    t = _clean(source)
    if not t.endswith("?"):
        t = t.rstrip(".") + " ?"

    if len(t) > 58:
        t = t[:58].rsplit(" ", 1)[0].rstrip(" ,.;:")
        if not t.endswith("?"):
            t = t + " ?"

    if is_weak_title(t) or len(t) < 18:
        blob = f"{original} {topic_c}".lower()
        for cluster in _HIGH_VELOCITY_CLUSTERS:
            if any(k in blob for k in cluster):
                primary = cluster[0]
                candidate = f"Pourquoi ton {primary} réagit comme ça ?"
                if 18 <= len(candidate) <= 58:
                    return candidate
        return _VIRAL_TITLE_TEMPLATES[0]
    return t


def boost_description(description: str, title: str, tags: list[str] | None = None) -> str:
    base = _clean(description or "")
    base = re.sub(r"#\w+", "", base).strip()
    if not base:
        base = f"{title} — expliqué simplement."

    tag_words = [str(t).strip().lstrip("#") for t in (tags or []) if str(t).strip()]
    extra: list[str] = []
    for w in tag_words:
        h = f"#{w.replace(' ', '')}"
        if h.lower() not in {x.lower() for x in _SHORTS_HASHTAG_CORE} and h not in extra:
            extra.append(h)
        if len(extra) >= 3:
            break

    packed: list[str] = []
    seen: set[str] = set()
    for h in list(_SHORTS_HASHTAG_CORE) + extra:
        key = h.lower()
        if key not in seen:
            seen.add(key)
            packed.append(h)

    block = (
        f"{base}\n\n"
        f"Neuro-Somaa — cerveau, corps, sommeil et comportements expliqués simplement.\n\n"
        f"{' '.join(packed[:8])}"
    )
    return block[:4900]


def enforce_opening_hook(script: dict[str, Any]) -> dict[str, Any]:
    """Ensure scene 1 narration hooks fast (no filler intro)."""
    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return script

    title = str(script.get("title") or "").strip()
    first = scenes[0] if isinstance(scenes[0], dict) else {}
    narration = _clean(str(first.get("narration") or ""))
    caption = _clean(str(first.get("caption") or ""))

    low = narration.lower()
    if any(f in low for f in _FILLER_OPENERS):
        narration = title if title.endswith("?") else (title.rstrip(".") + " ?")

    if len(narration.split()) > 14 or not narration:
        narration = title if title else "Regarde ce que fait ton cerveau."

    if not caption or len(caption.split()) > 8:
        words = re.findall(r"[\wà-ÿ']+", title, flags=re.IGNORECASE)
        caption = " ".join(words[:5]) if words else "Regarde ça"

    scenes[0] = {**first, "narration": narration, "caption": caption}
    script["scenes"] = scenes
    script["hook_enforced"] = True
    return script


def ensure_seo_tags(tags: list[Any] | None, title: str = "") -> list[str]:
    base = [
        "science",
        "corps humain",
        "cerveau",
        "psychologie",
        "neurosciences",
        "curiosité",
        "france",
        "shorts français",
        "comportement",
        "mémoire",
    ]
    words = [
        w
        for w in re.sub(r"[^\wà-ÿ' ]", " ", (title or "").lower()).split()
        if len(w) > 3
    ]
    merged = [str(t).strip() for t in (tags or []) if str(t).strip()] + words[:4] + base
    seen: list[str] = []
    for tag in merged:
        if tag.lower() not in {s.lower() for s in seen}:
            seen.append(tag)
        if len(seen) >= 12:
            break
    while len(seen) < 8:
        for pad in ("attention", "stress", "sommeil", "réflexe", "émotion"):
            if pad not in {s.lower() for s in seen}:
                seen.append(pad)
            if len(seen) >= 8:
                break
        break
    return seen[:12]


def compute_growth_state(
    views: int | None = None,
    views_prev: int | None = None,
    views_per_day: float | None = None,
    average_view_percentage: float | None = None,
) -> str:
    views = int(views or 0)
    prev = int(views_prev) if views_prev is not None else views
    vpd = float(views_per_day or 0.0)
    apv = float(average_view_percentage or 0.0)

    if views >= 5000 and vpd >= 200:
        return "breakout"
    if views >= 1000 and vpd >= 50:
        return "growing"
    if views >= 200 and vpd >= 15:
        return "growing"
    if views >= 50 and vpd >= 5:
        return "flat"
    if views > 0 and views <= prev and vpd < 2:
        return "stalled"
    if views < 20:
        return "stalled"
    if apv > 0 and apv < 25 and views >= 30:
        return "stalled"
    return "flat"


def rank_topics_by_history(history_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    try:
        rows = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
    except (OSError, json.JSONDecodeError):
        rows = []
    if not isinstance(rows, list):
        rows = []

    buckets: dict[str, dict[str, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        views = int(row.get("views") or 0)
        if views < 5:
            continue
        topic = _clean(str(row.get("topic") or row.get("title") or ""))
        if not topic or not is_allowed_growth_topic(topic):
            continue
        key = topic.lower()[:80]
        bucket = buckets.setdefault(key, {"views": 0.0, "count": 0.0, "topic": topic})
        bucket["views"] += views
        bucket["count"] += 1

    ranked = []
    for bucket in buckets.values():
        avg = bucket["views"] / max(1.0, bucket["count"])
        ranked.append(
            {
                "topic": bucket["topic"],
                "avg_views": round(avg, 1),
                "samples": int(bucket["count"]),
                "score": round(avg * (1.0 + 0.1 * min(bucket["count"], 10)), 1),
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:limit]


def pick_biased_topic(fallback_topic: str, history_path: Path) -> str:
    """Prefer allowed queue topic; else fall back to top historical felt topic."""
    if is_allowed_growth_topic(fallback_topic):
        return fallback_topic
    ranked = rank_topics_by_history(history_path, limit=8)
    if ranked:
        logger.info("Topic rejected by growth gate; using historical winner: %s", ranked[0]["topic"])
        return str(ranked[0]["topic"])
    return fallback_topic


def apply_growth_metadata(script: dict[str, Any]) -> dict[str, Any]:
    topic = str(script.get("topic") or "")
    title = shape_viral_title(str(script.get("title") or ""), topic)
    tags = ensure_seo_tags(list(script.get("tags") or []), title)
    description = boost_description(str(script.get("description") or ""), title, tags)
    script["title"] = title
    script["tags"] = tags
    script["description"] = description
    script["growth_optimized"] = True
    return enforce_opening_hook(script)
