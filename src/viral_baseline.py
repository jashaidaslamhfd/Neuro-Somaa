"""viral_baseline.py — the "make every video better than the last" feedback loop.

Aapka core demand: har nayi video pehle wali se BETTER ho. Single-video
retention scoring (which already exists in script_generator) only tells you
how good a script is in isolation. It never compares against what the channel
already shipped — so the pipeline happily re-produces the same average.

This module closes that gap:
  1. It reads the channel's script history (data/script_history.json) to build
     a BASELINE: the best hook, best topic angle, best retention score, best
     hook word-count, best "you-language" score.
  2. A new script is scored against the baseline, not just in isolation.
  3. If it falls short, it returns specific feedback the LLM uses to rewrite
     so the next draft beats what the channel has already done.

Written to data/script_history.json so the loop is durable across runs.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("viral_baseline")

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = os.environ.get("SCRIPT_HISTORY_PATH", str(ROOT / "data" / "script_history.json"))

# Defaults when the channel has no history yet.
DEFAULT_BASELINE = {
    "n": 0,
    "avg_retention_score": 70.0,
    "best_retention_score": 70.0,
    "best_hook": "",
    "best_hook_words": 8,
    "best_you_language": 0,
    "best_scene_count": 6,
}


def _load_json(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.warning("Could not load %s: %s", path, exc)
    return default


def _save_json(path: str, payload) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning("Could not save %s: %s", path, exc)


def _load_history() -> list:
    try:
        if os.path.exists(HISTORY_PATH):
            with open(HISTORY_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("Could not load script history: %s", exc)
    return []


def _save_history(history: list) -> None:
    try:
        os.makedirs(os.path.dirname(HISTORY_PATH) or ".", exist_ok=True)
        tmp = HISTORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        os.replace(tmp, HISTORY_PATH)
    except Exception as exc:
        logger.warning("Could not save script history: %s", exc)


def get_baseline() -> dict:
    """Return the channel's learned baseline for script quality."""
    history = _load_history()
    if not history:
        return dict(DEFAULT_BASELINE)

    scores = [h.get("retention_score", 0) for h in history if h.get("retention_score")]
    best = max(history, key=lambda h: h.get("retention_score", 0)) if history else {}

    return {
        "n": len(history),
        "avg_retention_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "best_retention_score": best.get("retention_score", DEFAULT_BASELINE["best_retention_score"]),
        "best_hook": best.get("hook", ""),
        "best_hook_words": best.get("hook_words", DEFAULT_BASELINE["best_hook_words"]),
        "best_you_language": best.get("you_language", DEFAULT_BASELINE["best_you_language"]),
        "best_scene_count": best.get("scene_count", DEFAULT_BASELINE["best_scene_count"]),
    }


def record_script(script_data: dict, retention_score: float) -> None:
    """Persist a generated script's quality signals so future scripts can
    compare against it."""
    history = _load_history()
    history.append(
        {
            "topic": script_data.get("topic", ""),
            "hook": script_data.get("hook", ""),
            "retention_score": round(float(retention_score), 1),
            "hook_words": len((script_data.get("hook") or "").split()),
            "you_language": sum(
                (script_data.get("voiceover") or "").lower().count(w) for w in ("vous", "votre", "tu", "ton")
            ),
            "scene_count": len(script_data.get("scenes", [])),
            "generated_at": script_data.get("generated_at"),
        }
    )
    # Keep only the last 500 scripts so the baseline stays recent.
    _save_history(history[-500:])


def feedback_to_beat_baseline(script_data: dict, retention_score: float) -> list[str]:
    """Compare a new script against the channel baseline and return concrete
    improvement feedback so the next draft EXCEEDS what has already shipped.

    Returns [] if the script already beats/meets the baseline.
    """
    baseline = get_baseline()
    if baseline["n"] < 3:
        return []  # not enough history to form a stable baseline yet

    feedback = []
    if retention_score <= baseline["avg_retention_score"]:
        feedback.append(
            f"Ce script ({retention_score:.0f}/100) ne dépasse pas la moyenne "
            f"de la chaîne ({baseline['avg_retention_score']:.0f}/100). "
            f"Renforce le hook et l'angle pour dépasser votre meilleur score "
            f"({baseline['best_retention_score']:.0f}/100)."
        )
    if script_data.get("hook") == baseline.get("best_hook"):
        feedback.append("Ce hook a déjà été utilisé — crée un hook nouveau et plus percutant.")
    if len((script_data.get("hook") or "").split()) > baseline.get("best_hook_words", 9):
        feedback.append(
            f"Ton meilleur hook avait {baseline['best_hook_words']} mots. "
            f"Raccourcis le hook à ~{baseline['best_hook_words']} mots pour un impact plus net."
        )
    return feedback


# ---------------------------------------------------------------------------
# ACTUAL-PERFORMANCE FEEDBACK LOOP (reads real YouTube data)
# ---------------------------------------------------------------------------

VIDEO_HISTORY_PATH = os.environ.get("VIDEO_HISTORY_PATH", str(ROOT / "data" / "video_history.json"))
PERFORMANCE_STATE_PATH = os.environ.get(
    "PERFORMANCE_STATE_PATH", str(ROOT / "data" / "performance_state.json")
)


def _load_video_history() -> list:
    try:
        if os.path.exists(VIDEO_HISTORY_PATH):
            with open(VIDEO_HISTORY_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("Could not load video_history: %s", exc)
    return []


def _retention(v) -> float:
    val = v.get("average_view_percentage")
    return float(val) if isinstance(val, (int, float)) else 0.0


def _views(v) -> int:
    val = v.get("views")
    return int(val) if isinstance(val, (int, float)) else 0


def learn_from_actual_performance() -> dict:
    """Read REAL YouTube views+retention from video_history and learn which
    topics/hooks actually perform. This is the true feedback loop: the script
    score (analyze_retention_potential) predicts, but actual YouTube numbers
    correct the prediction.

    Returns a summary dict and persists data/performance_state.json so the
    pipeline can prioritize what the channel ACTUALLY does well on.
    """
    history = _load_video_history()
    if not history:
        return {"n": 0}

    # Bucket by topic-pillar (if available) else raw topic, and by hook length.
    topic_ret = {}
    hook_ret = {}
    for v in history:
        if _views(v) == 0 and _retention(v) == 0:
            continue  # no real data yet
        topic = v.get("topic") or v.get("title") or "unknown"
        topic_ret.setdefault(topic, []).append({"views": _views(v), "ret": _retention(v)})
        hook = v.get("hook") or ""
        if hook:
            hook_ret.setdefault(len(hook.split()), []).append(_views(v))

    # Rank topics by a composite score (views mostly, retention as tiebreak)
    topic_rank = []
    for topic, entries in topic_ret.items():
        if len(entries) < 1:
            continue
        avg_views = sum(e["views"] for e in entries) / len(entries)
        avg_ret = sum(e["ret"] for e in entries) / len(entries)
        if avg_views <= 0:
            continue
        topic_rank.append(
            {
                "topic": topic,
                "n": len(entries),
                "avg_views": round(avg_views, 1),
                "avg_retention": round(avg_ret, 1),
            }
        )
    topic_rank.sort(key=lambda x: x["avg_views"], reverse=True)

    # Best hook word-count by views
    hook_rank = []
    for words, views in hook_ret.items():
        if views:
            hook_rank.append(
                {"words": words, "avg_views": round(sum(views) / len(views), 1), "n": len(views)}
            )
    hook_rank.sort(key=lambda x: x["avg_views"], reverse=True)

    state = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "total_with_data": len(history),
        "top_topics_by_views": topic_rank[:10],
        "top_hook_word_counts": hook_rank[:5],
        "best_topic": topic_rank[0] if topic_rank else None,
        "best_hook_words": hook_rank[0]["words"] if hook_rank else None,
    }
    _save_json(PERFORMANCE_STATE_PATH, state)
    logger.info(
        "Learned from %d real videos: best topic=%s best hook words=%s",
        len(history),
        (state.get("best_topic") or {}).get("topic"),
        state.get("best_hook_words"),
    )
    return state


def get_performance_state() -> dict:
    state = _load_json(PERFORMANCE_STATE_PATH, {})
    if not state or not state.get("generated_at"):
        return learn_from_actual_performance()
    return state


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    b = get_baseline()
    print(json.dumps(b, indent=2, ensure_ascii=False))
