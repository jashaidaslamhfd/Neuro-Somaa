from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

VIDEO_ID_RE = r"^[A-Za-z0-9_-]{6,20}$"


def get_client():
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


def audit(video: dict[str, Any]) -> dict[str, Any]:
    snippet = video.get("snippet", {})
    status = video.get("status", {})
    thumbs = snippet.get("thumbnails", {})
    required = {
        "title": bool(snippet.get("title")),
        "description": bool(snippet.get("description")),
        "default_language": snippet.get("defaultLanguage") == "fr",
        "default_audio_language": snippet.get("defaultAudioLanguage") == "fr",
        "thumbnail": bool(thumbs.get("high") or thumbs.get("medium") or thumbs.get("default")),
        "category": snippet.get("categoryId") == "27",
    }
    return {
        "video_id": video.get("id"),
        "title": snippet.get("title"),
        "description_length": len(snippet.get("description", "")),
        "tags_count": len(snippet.get("tags", [])),
        "default_language": snippet.get("defaultLanguage"),
        "default_audio_language": snippet.get("defaultAudioLanguage"),
        "category_id": snippet.get("categoryId"),
        "privacy_status": status.get("privacyStatus"),
        "upload_status": status.get("uploadStatus"),
        "made_for_kids": status.get("madeForKids"),
        "thumbnail_sizes": sorted(thumbs.keys()),
        "checks": required,
        "all_checks_pass": all(required.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--make-public", action="store_true")
    args = parser.parse_args()
    import re
    if not re.fullmatch(VIDEO_ID_RE, args.video_id):
        raise SystemExit("Invalid YouTube video ID")
    youtube = get_client()
    response = youtube.videos().list(part="snippet,status", id=args.video_id).execute()
    items = response.get("items", [])
    if not items:
        raise SystemExit("Video not found or inaccessible")
    before = audit(items[0])
    print(json.dumps({"before": before}, ensure_ascii=False, indent=2))
    if args.make_public:
        if not before["all_checks_pass"]:
            raise SystemExit("Metadata or thumbnail checks failed; video will remain private")
        current_status = items[0].get("status", {})
        status = {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": bool(current_status.get("selfDeclaredMadeForKids", False)),
        }
        updated = youtube.videos().update(part="status", body={"id": args.video_id, "status": status}).execute()
        after = audit(updated)
        print(json.dumps({"after": after, "public": after["privacy_status"] == "public"}, ensure_ascii=False, indent=2))
        return 0 if after["privacy_status"] == "public" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
