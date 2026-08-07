"""autonomous_controller.py — the ML "brain" that actually MANAGES the system.

Until now the ML modules (growth_engine, ml_brain, autonomous_brain) only
PRODUCED signals and reports; nothing in the pipeline ENFORCED them. That is
why the system could still triple-post, repeat flop topics, or keep a dead
cadence. This module closes the loop: it reads every learned signal and turns
it into concrete decisions the pipeline MUST obey.

Responsibilities (all auto, no human):
  * recommended_cadence  -> how many videos/day (from growth_engine)
  * topic_blocklist      -> topics that flopped hard are auto-banned
  * winner_topics        -> proven topics get priority in selection
  * preferred_hook_frame -> best-performing hook style is preferred
  * auto_repair_list     -> videos under-performing get flagged for repair
  * post_health          -> if recent videos flopped, throttle to protect feed

It writes data/autonomous_state.json so a human can audit every decision,
and exposes a single `get_controls()` the pipeline calls at runtime.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("autonomous_controller")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("SKILLOR_DATA_DIR", str(ROOT / "data")))

AUTONOMOUS_STATE_PATH = os.environ.get(
    "AUTONOMOUS_STATE_PATH", str(DATA_DIR / "autonomous_state.json")
)
VIDEO_HISTORY_PATH = os.environ.get("VIDEO_HISTORY_PATH", str(DATA_DIR / "video_history.json"))
GROWTH_STATE_PATH = os.environ.get("GROWTH_STATE_PATH", str(DATA_DIR / "growth_state.json"))

# A topic that averages below this many views after enough samples is a flop
# and gets auto-banned from future selection.
FLOP_VIEW_THRESHOLD = int(os.environ.get("AUTONOMOUS_FLOP_VIEWS", "25"))
# Min samples before we trust a topic verdict (avoid banning on 1 lucky video).
MIN_TOPIC_SAMPLES = int(os.environ.get("AUTONOMOUS_MIN_TOPIC_SAMPLES", "2"))
# If the last N videos averaged below this, throttle (post less often).
POST_THROTTLE_VIEWS = int(os.environ.get("AUTONOMOUS_THROTTLE_VIEWS", "150"))
POST_THROTTLE_WINDOW = int(os.environ.get("AUTONOMOUS_THROTTLE_WINDOW", "5"))
# Low-performance threshold for auto-repair of an already-uploaded video.
REPAIR_LOW_VIEWS = int(os.environ.get("AUTONOMOUS_REPAIR_VIEWS", "300"))
REPAIR_MIN_AGE_HOURS = int(os.environ.get("AUTONOMOUS_REPAIR_MIN_AGE_HOURS", "48"))


def _load_json(path: str, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return default


def _save_json(path: str, payload) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning("Could not save autonomous state: %s", exc)


def _hours_since(iso_str: str) -> float | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except Exception:
        return None


def analyse() -> dict:
    """Compute autonomous controls from learned + live data. Safe, idempotent."""
    history = _load_json(VIDEO_HISTORY_PATH, [])
    if not isinstance(history, list):
        history = []
    growth = _load_json(GROWTH_STATE_PATH, {}) or {}

    # --- Cadence from growth_engine (fall back to 3 if unavailable) ---
    cadence = int(growth.get("recommended_cadence") or 3)
    cadence = max(1, min(cadence, 5))

    # --- Topic performance: block flops, reward winners ---
    topic_views: dict[str, list] = {}
    for entry in history:
        topic = (entry.get("topic") or "").strip().lower()
        views = int(entry.get("views") or (entry.get("youtube_shorts") or {}).get("views") or 0)
        if not topic:
            continue
        topic_views.setdefault(topic, []).append(views)

    blocklist: list[str] = []
    winner_topics: list[str] = []
    for topic, views in topic_views.items():
        if len(views) < MIN_TOPIC_SAMPLES:
            continue
        avg = sum(views) / len(views)
        if avg < FLOP_VIEW_THRESHOLD:
            blocklist.append(topic)
        elif avg >= 500:
            winner_topics.append(topic)
    winner_topics.sort(key=lambda t: -sum(topic_views[t]) / len(topic_views[t]))

    # --- Post-health throttle: if recent videos flopped, suggest slower cadence ---
    mature = [v for v in history if _hours_since(v.get("posted_at")) is not None]
    recent = mature[-POST_THROTTLE_WINDOW:]
    recent_avg = 0.0
    if recent:
        recent_views = [int(v.get("views") or 0) for v in recent]
        recent_avg = sum(recent_views) / len(recent_views)
    throttled = bool(recent_avg < POST_THROTTLE_VIEWS and len(recent) >= 3)

    # --- Preferred hook frame from growth_engine ---
    preferred_hook = growth.get("best_hook_frame")

    # --- Auto-repair candidates (under-performing, old enough) ---
    repair_list = []
    for entry in history:
        vid = entry.get("youtube_video_id")
        views = int(entry.get("views") or 0)
        age = _hours_since(entry.get("posted_at"))
        if vid and views is not None and views < REPAIR_LOW_VIEWS and age is not None and age >= REPAIR_MIN_AGE_HOURS:
            repair_list.append({
                "video_id": vid,
                "title": entry.get("title"),
                "views": views,
                "age_hours": round(age, 1),
            })
    repair_list.sort(key=lambda r: r["views"])

    controls = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recommended_cadence": cadence,
        "cadence_reason": growth.get("cadence_reason"),
        "throttle": throttled,
        "throttle_reason": f"last {len(recent)} videos avg {recent_avg:.0f} views",
        "topic_blocklist": blocklist,
        "winner_topics": winner_topics,
        "preferred_hook_frame": preferred_hook,
        "auto_repair_candidates": repair_list,
        "auto_repair_count": len(repair_list),
    }
    _save_json(AUTONOMOUS_STATE_PATH, controls)
    logger.info(
        "Autonomous controls: cadence=%d throttle=%s block=%d winners=%d repairs=%d",
        cadence, throttled, len(blocklist), len(winner_topics), len(repair_list),
    )
    return controls


def get_controls() -> dict:
    """Read the last computed controls (or compute fresh if missing)."""
    state = _load_json(AUTONOMOUS_STATE_PATH, {})
    if not state or not state.get("generated_at"):
        return analyse()
    return state


def should_skip_topic(topic: str) -> bool:
    """Return True if the ML brain has auto-banned this topic."""
    if not topic:
        return False
    t = topic.strip().lower()
    return t in set(get_controls().get("topic_blocklist", []))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    controls = analyse()
    print(json.dumps(controls, indent=2, ensure_ascii=False))
