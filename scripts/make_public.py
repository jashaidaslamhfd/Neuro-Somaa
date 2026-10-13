from __future__ import annotations

import os
import re


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
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)

def make_videos_public(video_ids: list[str]):
    if not video_ids:
        raise SystemExit("VIDEO_IDS is required; refusing to publish an implicit/default video")
    invalid = [vid for vid in video_ids if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid)]
    if invalid:
        raise SystemExit(f"Invalid YouTube video ID(s): {', '.join(invalid)}")
    yt = get_youtube()
    errors = []
    for vid in video_ids:
        try:
            res = yt.videos().list(part="snippet,status", id=vid).execute()
            items = res.get("items", [])
            if not items:
                print(f"[{vid}] Not found")
                continue
            item = items[0]
            curr_status = item["status"]
            
            # 1. Update status to public and remove publishAt
            # In YouTube API, updating status to public clears publishAt
            status_body = {
                "id": vid,
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": bool(curr_status.get("selfDeclaredMadeForKids", False))
                }
            }
            yt.videos().update(part="status", body=status_body).execute()
            print(f"[{vid}] Successfully transitioned to PUBLIC!")
        except Exception as e:
            message = f"[{vid}] Error: {e}"
            print(message)
            errors.append(message)
    if errors:
        raise RuntimeError("One or more videos could not be made public: " + "; ".join(errors))

if __name__ == "__main__":
    ids = [v.strip() for v in os.getenv("VIDEO_IDS", "").split(",") if v.strip()]
    make_videos_public(ids)
