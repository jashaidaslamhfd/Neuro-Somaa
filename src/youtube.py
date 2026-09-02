from __future__ import annotations

import os
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
    body = {
        "snippet": {"title": script["title"][:100], "description": script["description"][:5000], "tags": script.get("tags", []), "categoryId": "27", "defaultLanguage": "fr", "defaultAudioLanguage": "fr"},
        "status": {"privacyStatus": settings.privacy_status, "selfDeclaredMadeForKids": False},
    }
    result = youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)).execute()
    return {"status": "uploaded", "youtube_video_id": result["id"], "url": f"https://youtu.be/{result['id']}", "title": script["title"]}
