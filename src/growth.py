"""Channel growth engine for Neuro-Somaa.

Expert levers that move Shorts from stalled → thousands of views:
1. Viral title shaping (feed-native, curiosity gap, personal "tu")
2. SEO description + hashtag pack optimized for French Shorts discovery
3. Growth-state machine from observed views (stalled / flat / growing / breakout)
4. Topic ranking bias toward historically high-view clusters
5. Immediate-public publish mode (schedule is optional; private kills early algorithm tests)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import timezone
from pathlib import Path
from typing import Any

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc  # noqa: UP017

logger = logging.getLogger("neuro_somaa.growth")

_VIRAL_TITLE_TEMPLATES = (
    "Ton cerveau fait ça sans que tu le saches",
    "Pourquoi ton corps réagit comme ça ?",
    "Ce que ton cerveau cache vraiment",
    "Pourquoi tu oublies ça tout le temps ?",
    "Ton sommeil te ment (voici pourquoi)",
    "Ce stress change ton cerveau en silence",
    "Pourquoi ton téléphone te vole l'attention ?",
    "Ton cerveau te piège chaque jour",
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
    ("cerveau", "mémoire", "attention", "décision"),
    ("sommeil", "rêve", "insomnie", "réveil"),
    ("stress", "anxiété", "panique", "corps"),
    ("téléphone", "écran", "notification", "scroll"),
    ("dopamine", "habitude", "addiction", "récompense"),
)

_SHORTS_HASHTAG_CORE = (
    "#shorts",
    "#science",
    "#cerveau",
    "#france",
    "#psychologie",
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_weak_title(title: str) -> bool:
    t = title.lower().strip()
    if len(t) < 12:
        return True
    if t.endswith("?") and t.count("?") > 1:
        return True
    if any(b in t for b in _BANNED_WEAK_OPENERS):
        return True
    if t.endswith(("la?", "de?", "le?", "les?", "des?", "du?", "un?", "une?")):
        return True
    return bool(re.search(r"\b(pourquoi|comment)\s+\w{1,3}\s*\?$", t))


def shape_viral_title(title: str, topic: str = "") -> str:
    original = _clean(title)
    if not is_weak_title(original) and 18 <= len(original) <= 58:
        return original

    blob = f"{original} {topic}".lower()
    cluster_hit = None
    for cluster in _HIGH_VELOCITY_CLUSTERS:
        if any(k in blob for k in cluster):
            cluster_hit = cluster
            break

    if cluster_hit:
        primary = cluster_hit[0]
        candidates = [
            f"Ton {primary} fait ça sans que tu le saches",
            f"Pourquoi ton {primary} réagit comme ça ?",
            f"Ce que ton {primary} cache vraiment",
            f"Ton {primary} te piège (voici pourquoi)",
        ]
        for c in candidates:
            if 18 <= len(c) <= 58:
                return c

    t = original
    if not re.search(r"\b(ton|ta|tes|tu|toi)\b", t.lower()):
        if t.lower().startswith("pourquoi "):
            rest = t[9:].lstrip()
            t = f"Pourquoi ton cerveau {rest}" if "cerveau" not in rest.lower() else t
        elif not t.endswith("?"):
            t = f"{t.rstrip('.')} ?"

    t = _clean(t)
    if len(t) > 58:
        t = t[:58].rsplit(" ", 1)[0].rstrip(" ,.;:")
        if not t.endswith("?"):
            t = t + " ?"
    if len(t) < 12:
        return _VIRAL_TITLE_TEMPLATES[0]
    return t


def boost_description(description: str, title: str, tags: list[str] | None = None) -> str:
    base = _clean(description or "")
    base = re.sub(r"#\w+", "", base).strip()
    if not base:
        base = f"{title} — expliqué simplement."

    tag_words = [str(t).strip().lstrip("#") for t in (tags or []) if str(t).strip()]
    extra = []
    for w in tag_words:
        h = f"#{w.replace(' ', '')}"
        if h.lower() not in {x.lower() for x in _SHORTS_HASHTAG_CORE} and h not in extra:
            extra.append(h)
        if len(extra) >= 3:
            break

    hashtags = list(_SHORTS_HASHTAG_CORE) + extra
    seen: set[str] = set()
    packed: list[str] = []
    for h in hashtags:
        key = h.lower()
        if key not in seen:
            seen.add(key)
            packed.append(h)

    block = (
        f"{base}\n\n"
        f"Neuro-Somaa — mystères du cerveau, sommeil, stress et comportements.\n\n"
        f"{' '.join(packed[:8])}"
    )
    return block[:4900]


def compute_growth_state(
    views: int,
    views_prev: int | None,
    views_per_day: float,
    average_view_percentage: float | None = None,
) -> str:
    views = max(0, int(views or 0))
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
        if not topic:
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


def apply_growth_metadata(script: dict[str, Any]) -> dict[str, Any]:
    title = shape_viral_title(str(script.get("title") or ""), str(script.get("topic") or ""))
    tags = list(script.get("tags") or [])
    for must in ("shorts français", "cerveau", "science", "france", "psychologie"):
        if must not in [t.lower() for t in tags]:
            tags.append(must)
    tags = tags[:12]
    description = boost_description(str(script.get("description") or ""), title, tags)
    script["title"] = title
    script["tags"] = tags
    script["description"] = description
    script["growth_optimized"] = True
    return script
