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
    history.append({
        "topic": script_data.get("topic", ""),
        "hook": script_data.get("hook", ""),
        "retention_score": round(float(retention_score), 1),
        "hook_words": len((script_data.get("hook") or "").split()),
        "you_language": sum(
            (script_data.get("voiceover") or "").lower().count(w)
            for w in ("vous", "votre", "tu", "ton")
        ),
        "scene_count": len(script_data.get("scenes", [])),
        "generated_at": script_data.get("generated_at"),
    })
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    b = get_baseline()
    print(json.dumps(b, indent=2, ensure_ascii=False))
