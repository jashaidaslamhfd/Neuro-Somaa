#!/usr/bin/env python3
"""Feature engineering for the Neuro-Somaa intelligence layer.

Turns data/video_history.json entries into a numeric feature matrix.
Pure stdlib — no numpy needed here (models.py does the numerics).

Feature groups (all honest, all observable BEFORE upload except slot/day):
  title:    length, word count, is question, interrogative lead, digits,
            exclamation, apostrophes ("s'"), emphasis caps ratio
  seo:      hook_score, seo_score, predicted_ctr, predicted_retention
  slot:     hour-of-day (Paris), sin/cos; day-of-week sin/cos
  topic:    base phenomenon hash bucket (8 buckets), question-pattern
Target:   log1p(views)  (regression) / winner = views >= WINNER_VIEWS
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
WINNER_VIEWS = 1000  # channel-scale "winner" threshold (median is ~760)

FEATURE_NAMES = [
    "title_chars", "title_words", "is_question", "starts_pourquoi",
    "starts_comment", "has_second_person", "has_digits", "caps_ratio",
    "hook_score", "seo_score", "predicted_ctr", "predicted_retention",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos",
    "topic_bucket_0", "topic_bucket_1", "topic_bucket_2", "topic_bucket_3",
    "phrase_words",
]


def _parse_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("UTC"))
    except ValueError:
        return None


def extract_features(entry: dict) -> dict:
    """One row of features for a video_history entry."""
    import math
    import re

    title = str(entry.get("title") or "")
    words = title.split()
    lower = title.lower()
    letters = [c for c in title if c.isalpha()]
    caps_ratio = (sum(1 for c in letters if c.isupper()) / len(letters)) if letters else 0.0

    when = _parse_dt(entry.get("publish_at") or entry.get("posted_at"))
    hour, dow = 19.5, 2  # French prime-time prior when unknown
    if when:
        p = when.astimezone(PARIS)
        hour = p.hour + p.minute / 60
        dow = p.weekday()

    topic = str(entry.get("base_phenomenon") or entry.get("topic") or "")
    # stable across processes (hash() is randomized per Python run!)
    import zlib
    bucket = (zlib.crc32(topic.encode("utf-8")) % 4) if topic else -1

    def _num(key: str, default: float = 0.0) -> float:
        try:
            v = entry.get(key)
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    return {
        "title_chars": float(len(title)),
        "title_words": float(len(words)),
        "is_question": 1.0 if title.rstrip().endswith("?") else 0.0,
        "starts_pourquoi": 1.0 if lower.startswith("pourquoi") else 0.0,
        "starts_comment": 1.0 if lower.startswith("comment") else 0.0,
        "has_second_person": 1.0 if re.search(r"\b(ton|ta|votre|vous|ton)\b", lower) else 0.0,
        "has_digits": 1.0 if any(c.isdigit() for c in title) else 0.0,
        "caps_ratio": caps_ratio,
        "hook_score": _num("hook_score", 70.0) / 100.0,
        "seo_score": _num("seo_score", 70.0) / 100.0,
        "predicted_ctr": _num("predicted_ctr"),
        "predicted_retention": _num("predicted_retention"),
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
        "dow_sin": math.sin(2 * math.pi * dow / 7),
        "dow_cos": math.cos(2 * math.pi * dow / 7),
        "topic_bucket_0": 1.0 if bucket == 0 else 0.0,
        "topic_bucket_1": 1.0 if bucket == 1 else 0.0,
        "topic_bucket_2": 1.0 if bucket == 2 else 0.0,
        "topic_bucket_3": 1.0 if bucket == 3 else 0.0,
        "phrase_words": float(len(str(entry.get("question_phrase") or "").split())),
    }


def build_dataset(history: list[dict], min_views: int | None = 0) -> tuple[list[dict], list[float], list[str]]:
    """Return (feature_rows, targets_log1p_views, video_ids) for entries with real views."""
    import math

    rows, targets, ids = [], [], []
    for entry in history or []:
        views = entry.get("views")
        if views is None:
            continue
        try:
            views = int(views)
        except (TypeError, ValueError):
            continue
        if min_views is not None and views < min_views:
            continue
        rows.append(extract_features(entry))
        targets.append(math.log1p(max(views, 0)))
        ids.append(entry.get("youtube_video_id") or "?")
    return rows, targets, ids
