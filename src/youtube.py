from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from config import Settings


def upload(video_path: Path, script: dict[str, Any], settings: Settings) -> dict[str, Any]:
    if settings.dry_run or settings.render_only:
        return {"status": "render_only" if settings.render_only else "dry_run", "video": str(video_path), "title": script["title"]}
    if not settings.youtube_ready:
        raise RuntimeError("YouTube OAuth secrets are incomplete")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError("Google API dependencies are missing") from exc
    credentials = Credentials(
        None,
        refresh_token=os.environ["REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    credentials.refresh(Request())
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    status: dict[str, object] = {"privacyStatus": settings.privacy_status, "selfDeclaredMadeForKids": False}
    if settings.schedule_publish and settings.privacy_status == "private":
        from zoneinfo import ZoneInfo

        local_zone = ZoneInfo(settings.timezone)
        now_local = datetime.now(UTC).astimezone(local_zone)
        # Publish slots: data-backed best performers from the channel's own
        # upload_slot_intel_fr.json (24/12/15 samples respectively), not the
        # generic README default — that default's 12:30 slot had the fewest
        # samples and 19:30 was flagged as underperforming in growth_state.json
        # until the schedule below shifted it 30 minutes later.
        slot_hours = ((17, 30), (19, 30), (21, 30))
        # PUBLISH_SLOT (set per scheduled workflow run, see main.yml) lets each
        # of the day's runs own one specific slot deterministically. Without
        # this, "next slot after now" meant two runs/day always landed on
        # either side of 19:30 and that slot was structurally never used.
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
                target = (now_local + timedelta(days=1)).replace(hour=slot_hours[0][0], minute=slot_hours[0][1], second=0, microsecond=0)
        status["publishAt"] = target.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    body = {
        "snippet": {"title": script["title"][:100], "description": script["description"][:5000], "tags": script.get("tags", []), "categoryId": "27", "defaultLanguage": "fr", "defaultAudioLanguage": "fr"},
        "status": status,
    }
    result = youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)).execute()
    thumbnail_path = settings.output_dir / "thumbnail.jpg"
    thumbnail_status = "not_available"
    if thumbnail_path.exists():
        youtube.thumbnails().set(videoId=result["id"], media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")).execute()
        thumbnail_status = "uploaded"
    return {"status": "uploaded", "youtube_video_id": result["id"], "url": f"https://youtu.be/{result['id']}", "title": script["title"], "thumbnail_status": thumbnail_status}
