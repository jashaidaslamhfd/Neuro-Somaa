from __future__ import annotations

import os
from datetime import UTC, datetime


def get_youtube():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(
        None,
        refresh_token=os.environ["REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def schedule(video_id: str, publish_at: str) -> dict[str, str]:
    youtube = get_youtube()
    current = youtube.videos().list(part="snippet,status", id=video_id).execute()
    items = current.get("items", [])
    if not items:
        raise RuntimeError(f"YouTube video not found: {video_id}")
    status = items[0]["status"]
    youtube.videos().update(
        part="status",
        body={
            "id": video_id,
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at,
                "selfDeclaredMadeForKids": status.get("selfDeclaredMadeForKids", False),
            },
        },
    ).execute()
    return {"video_id": video_id, "publish_at": publish_at, "url": f"https://youtu.be/{video_id}"}


if __name__ == "__main__":
    ids = [value.strip() for value in os.environ["VIDEO_IDS"].split(",") if value.strip()]
    times = [value.strip() for value in os.environ["PUBLISH_ATS"].split(",") if value.strip()]
    if len(ids) != len(times):
        raise SystemExit("VIDEO_IDS and PUBLISH_ATS must contain the same number of comma-separated values")
    for video_id, publish_at in zip(ids, times, strict=True):
        print(schedule(video_id, publish_at))
