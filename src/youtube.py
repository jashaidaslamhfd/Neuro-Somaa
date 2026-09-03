from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from config import Settings


def upload(video_path: Path, script: dict[str, Any], settings: Settings) -> dict[str, Any]:
    if settings.dry_run:
        return {"status": "dry_run", "video": str(video_path), "title": script["title"]}
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

        local_zone = ZoneInfo("Asia/Karachi")
        now_local = datetime.now(UTC).astimezone(local_zone)
        targets = [
            now_local.replace(hour=1, minute=0, second=0, microsecond=0),
            now_local.replace(hour=21, minute=0, second=0, microsecond=0),
        ]
        target = next((item for item in targets if item > now_local), None)
        if target is None:
            target = (now_local + timedelta(days=1)).replace(hour=1, minute=0, second=0, microsecond=0)
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
