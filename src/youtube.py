from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc  # noqa: UP017

from pathlib import Path
from typing import Any

from config import Settings

logger = logging.getLogger("neuro_somaa.youtube")


def _safe_truncate(text: str, limit: int) -> str:
    """Truncate at the last full word before `limit`, never mid-word."""
    text = text.strip()
    if len(text) <= limit:
        return text
    truncated = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:!?-")
    return truncated or text[:limit]


def upload(video_path: Path, script: dict[str, Any], settings: Settings) -> dict[str, Any]:
    if settings.dry_run or settings.render_only:
        return {
            "status": "render_only" if settings.render_only else "dry_run",
            "video": str(video_path),
            "title": script["title"],
        }

    if not settings.youtube_ready:
        raise RuntimeError("YouTube OAuth secrets are incomplete")

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError("Google API dependencies are missing") from exc

    try:
        credentials = Credentials(
            None,
            refresh_token=os.environ["REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=[
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.force-ssl",
            ],
        )
        credentials.refresh(Request())
    except Exception as exc:
        raise RuntimeError(f"YouTube OAuth token refresh failed: {exc}") from exc

    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    status: dict[str, object] = {
        "privacyStatus": settings.privacy_status,
        "selfDeclaredMadeForKids": False,
    }

    if settings.schedule_publish and settings.privacy_status == "private":
        from zoneinfo import ZoneInfo

        local_zone = ZoneInfo(settings.timezone)
        now_local = datetime.now(UTC).astimezone(local_zone)
        slot_hours = ((14, 30), (17, 30), (20, 00))
        slot_env = os.getenv("PUBLISH_SLOT", "").strip()
        if slot_env:
            try:
                hour, minute = (int(part) for part in slot_env.split(":"))
            except ValueError:
                hour, minute = slot_hours[0]
            target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now_local:
                target += timedelta(days=1)
        else:
            targets = sorted(
                now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
                for hour, minute in slot_hours
            )
            target = next((item for item in targets if item > now_local), None)
            if target is None:
                target = (now_local + timedelta(days=1)).replace(
                    hour=slot_hours[0][0], minute=slot_hours[0][1], second=0, microsecond=0
                )
        status["publishAt"] = target.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    body = {
        "snippet": {
            "title": _safe_truncate(script["title"], 100),
            "description": _safe_truncate(script["description"], 5000),
            "tags": script.get("tags", []),
            "categoryId": "27",
            "defaultLanguage": "fr",
            "defaultAudioLanguage": "fr",
        },
        "status": status,
    }

    # Resumable 2MB Chunk Iteration with Exponential Backoff
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=2 * 1024 * 1024,
        resumable=True,
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retries = 0
    max_retries = 8
    logger.info("Initiating chunked resumable upload for '%s'...", script["title"])

    while response is None:
        try:
            upload_progress, response = request.next_chunk()
            if upload_progress:
                logger.info("Upload progress: %d%%", int(upload_progress.progress() * 100))
        except HttpError as exc:
            if exc.resp.status in (403, 400):
                content = exc.content.decode("utf-8", errors="ignore") if exc.content else ""
                if "quotaExceeded" in content:
                    logger.critical("YouTube Data API Quota Exceeded (10,000 unit limit reached).")
                    raise RuntimeError("YouTube upload halted: Daily API quota limit reached.") from exc
                raise
            if exc.resp.status in (500, 502, 503, 504, 429):
                retries += 1
                if retries > max_retries:
                    raise RuntimeError(
                        f"Upload failed after {max_retries} chunk retries (HTTP {exc.resp.status})"
                    ) from exc
                delay = (2**retries) + random.uniform(0.5, 1.5)
                logger.warning(
                    "Transient HTTP %d. Backing off %.1fs before resuming chunk...",
                    exc.resp.status,
                    delay,
                )
                time.sleep(delay)
            else:
                raise
        except (TimeoutError, ConnectionResetError, BrokenPipeError) as exc:
            retries += 1
            if retries > max_retries:
                raise RuntimeError("Network disconnects exceeded max retry allowance") from exc
            delay = (2**retries) + random.uniform(1.0, 2.0)
            logger.warning("Socket drop (%s). Resuming chunk in %.1fs...", exc, delay)
            time.sleep(delay)

    video_id = response["id"]
    logger.info("Video successfully uploaded! ID: %s", video_id)

    # Safe Thumbnail Attachment - Never crash if account lacks phone verification
    thumbnail_path = settings.output_dir / "thumbnail.jpg"
    thumbnail_status = "not_available"
    if thumbnail_path.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg"),
            ).execute()
            thumbnail_status = "uploaded"
            logger.info("Custom thumbnail set successfully.")
        except HttpError as exc:
            logger.warning(
                "Thumbnail upload skipped (account may lack phone verification): %s",
                exc,
            )
            thumbnail_status = f"skipped: {exc.resp.status}"
        except Exception as exc:
            logger.warning("Non-fatal thumbnail attachment error: %s", exc)
            thumbnail_status = "skipped: error"

    return {
        "status": "uploaded",
        "youtube_video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "title": script["title"],
        "thumbnail_status": thumbnail_status,
    }
