#!/usr/bin/env python3
"""Sync YouTube Data API stats into data/video_history.json.

Restores the growth feedback loop: views, likes, comments, views_per_day,
growth_state (stalled/flat/growing/breakout), analytics_fetched_at.
Uses youtube.force-ssl scope only (same as upload).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc  # noqa: UP017

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("sync_analytics")

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
HISTORY = DATA / "video_history.json"


def _get_youtube():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(
        None,
        refresh_token=os.environ["REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def _growth_state(views: int, views_prev: int | None, views_per_day: float, apv: float | None) -> str:
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from growth import compute_growth_state
        return compute_growth_state(views, views_prev, views_per_day, apv)
    except Exception:
        if views >= 1000 and views_per_day >= 50:
            return "growing"
        if views < 20 or views_per_day < 2:
            return "stalled"
        return "flat"


def _days_since(iso: str | None) -> float:
    if not iso:
        return 1.0
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        return max(delta.total_seconds() / 86400.0, 0.25)
    except Exception:
        return 1.0


def sync(limit: int = 50) -> dict[str, Any]:
    if not HISTORY.exists():
        logger.warning("No video_history.json found at %s", HISTORY)
        return {"updated": 0, "reason": "missing_history"}

    rows: list[Any] = json.loads(HISTORY.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("video_history.json must be a JSON list")

    candidates = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        vid = row.get("youtube_video_id")
        if not vid or not isinstance(vid, str):
            continue
        priority = 0 if not row.get("analytics_fetched_at") else 1
        if row.get("growth_state") == "stalled":
            priority = 0
        candidates.append((priority, idx, row))

    candidates.sort(key=lambda x: (x[0], -x[1]))
    selected = candidates[:limit]
    if not selected:
        logger.info("No videos with youtube_video_id to sync.")
        return {"updated": 0}

    ids = [c[2]["youtube_video_id"] for c in selected]
    youtube = _get_youtube()
    stats_map: dict[str, dict[str, Any]] = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        resp = youtube.videos().list(part="statistics,status,snippet", id=",".join(chunk)).execute()
        for item in resp.get("items", []):
            stats_map[item["id"]] = item

    now = datetime.now(UTC).isoformat()
    updated = 0
    for _prio, idx, row in selected:
        vid = row["youtube_video_id"]
        item = stats_map.get(vid)
        if not item:
            logger.warning("Video %s not found or inaccessible", vid)
            continue

        stats = item.get("statistics", {})
        status = item.get("status", {})
        views = int(stats.get("viewCount") or 0)
        likes = int(stats.get("likeCount") or 0)
        comments = int(stats.get("commentCount") or 0)
        privacy = status.get("privacyStatus")

        views_prev = row.get("views")
        if views_prev is not None:
            try:
                views_prev = int(views_prev)
            except (TypeError, ValueError):
                views_prev = None

        days = _days_since(row.get("posted_at") or row.get("analytics_fetched_at"))
        if views_prev is not None and row.get("analytics_fetched_at"):
            delta_days = _days_since(row.get("analytics_fetched_at"))
            views_per_day = max(0.0, (views - views_prev) / max(delta_days, 0.25))
        else:
            views_per_day = views / days

        apv = row.get("average_view_percentage")
        try:
            apv_f = float(apv) if apv is not None else None
        except (TypeError, ValueError):
            apv_f = None

        state = _growth_state(views, views_prev, views_per_day, apv_f)
        stall = int(row.get("stall_streak") or 0)
        if state == "stalled":
            stall += 1
        elif state in ("growing", "breakout"):
            stall = 0

        row["views_prev"] = views_prev if views_prev is not None else row.get("views")
        row["views"] = views
        row["likes"] = likes
        row["comments"] = comments
        row["views_per_day"] = round(views_per_day, 2)
        row["growth_state"] = state
        row["stall_streak"] = stall
        row["privacy_status"] = privacy
        row["analytics_fetched_at"] = now
        row["analytics_via"] = "data_api"
        if not row.get("posted_at") and privacy == "public":
            row["posted_at"] = now
        if privacy == "private" and not status.get("publishAt"):
            row["needs_public"] = True
        rows[idx] = row
        updated += 1
        logger.info(
            "[%s] views=%s vpd=%.1f state=%s privacy=%s | %s",
            vid, views, views_per_day, state, privacy, str(row.get("title") or "")[:50],
        )

    tmp = HISTORY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(HISTORY)
    logger.info("Updated %d / %d videos in video_history.json", updated, len(selected))
    return {"updated": updated, "checked": len(selected)}


if __name__ == "__main__":
    lim = int(os.getenv("ANALYTICS_LIMIT", "50"))
    result = sync(limit=lim)
    print(json.dumps(result, ensure_ascii=False))
