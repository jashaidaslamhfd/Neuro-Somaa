from __future__ import annotations
import os
from schedule_videos import get_youtube

def unschedule(video_id: str) -> None:
    youtube = get_youtube()
    current = youtube.videos().list(part="status", id=video_id).execute().get("items", [])
    if not current:
        raise RuntimeError(f"YouTube video not found: {video_id}")
    status = current[0]["status"]
    youtube.videos().update(part="status", body={"id": video_id, "status": {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": status.get("selfDeclaredMadeForKids", False),
    }}).execute()
    print({"video_id": video_id, "status": "private_unscheduled"})

if __name__ == "__main__":
    ids = [value.strip() for value in os.getenv("UNSCHEDULE_IDS", "").split(",") if value.strip()]
    if not ids:
        raise SystemExit("UNSCHEDULE_IDS is required")
    for video_id in ids:
        unschedule(video_id)
