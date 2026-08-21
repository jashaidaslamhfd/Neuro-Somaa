#!/usr/bin/env python3
"""Read-only YouTube comment intelligence for SKILLOR FR.

Purpose: learn real audience requests without automating fake engagement.
It fetches recent top-level comments, extracts French question/topic requests,
and writes `data/comments_intel_fr.json` for the premium growth loop.

Requires OAuth env vars with youtube.force-ssl or readonly-compatible access:
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, REFRESH_TOKEN.
Missing credentials are non-fatal and produce an empty report.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
API = "https://www.googleapis.com/youtube/v3"
LOG = logging.getLogger("comments-intel")

REQUEST_PATTERNS = [
    re.compile(
        r"(?:peux[- ]tu|pouvez[- ]vous|tu peux|vous pouvez).{0,40}\b(?:expliquer|faire|parler de)\s+([^?.!\n]{4,80})",
        re.IGNORECASE,
    ),
    re.compile(r"(?:une vidéo|un short)\s+sur\s+([^?.!\n]{4,80})", re.IGNORECASE),
    re.compile(r"(?:pourquoi|comment)\s+([^?.!\n]{6,90})\?", re.IGNORECASE),
]
STOP_FRAGMENTS = {"merci", "svp", "stp", "s'il te plaît", "s'il vous plaît", "prochaine", "video", "vidéo"}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _token() -> str | None:
    required = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REFRESH_TOKEN"]
    if any(not os.environ.get(name) for name in required):
        LOG.warning("OAuth env vars missing; writing empty comment intelligence.")
        return None
    data = urllib.parse.urlencode(
        {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }
    ).encode()
    try:
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)["access_token"]
    except Exception as exc:
        LOG.warning("OAuth token refresh failed: %s", exc)
        return None


def _req(token: str, path: str, params: dict) -> dict:
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def _uploads_playlist(token: str) -> str | None:
    data = _req(token, "channels", {"part": "contentDetails", "mine": "true"})
    items = data.get("items") or []
    if not items:
        return None
    return items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")


def _recent_video_ids(token: str, limit: int) -> list[str]:
    playlist = _uploads_playlist(token)
    if not playlist:
        return []
    data = _req(
        token,
        "playlistItems",
        {"part": "contentDetails", "playlistId": playlist, "maxResults": min(limit, 50)},
    )
    return [
        item.get("contentDetails", {}).get("videoId")
        for item in data.get("items", [])
        if item.get("contentDetails", {}).get("videoId")
    ]


def _comments_for_video(token: str, video_id: str, max_comments: int) -> list[dict]:
    comments = []
    page = ""
    while len(comments) < max_comments:
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(100, max_comments - len(comments)),
            "textFormat": "plainText",
            "order": "relevance",
        }
        if page:
            params["pageToken"] = page
        try:
            data = _req(token, "commentThreads", params)
        except urllib.error.HTTPError as exc:
            if exc.code in {403, 404}:  # comments disabled / video unavailable
                break
            raise
        for item in data.get("items", []):
            sn = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            comments.append(
                {
                    "video_id": video_id,
                    "text": sn.get("textDisplay", ""),
                    "like_count": sn.get("likeCount", 0),
                    "published_at": sn.get("publishedAt"),
                }
            )
        page = data.get("nextPageToken") or ""
        if not page:
            break
    return comments


def _clean_topic(raw: str) -> str:
    text = re.sub(r"\s+", " ", (raw or "").strip(" .?!:;,-"))
    text = re.sub(
        r"\b(" + "|".join(re.escape(x) for x in STOP_FRAGMENTS) + r")\b", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"\s+", " ", text).strip(" .?!:;,-")
    return text[:90]


def extract_topic_requests(comments: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for comment in comments:
        text = comment.get("text", "")
        for pattern in REQUEST_PATTERNS:
            for match in pattern.finditer(text):
                topic = _clean_topic(match.group(1))
                if len(topic) >= 4:
                    key = topic.lower()
                    counts[key] += 1 + int(comment.get("like_count") or 0) * 0.25
                    examples.setdefault(key, text[:180])
    return [
        {"topic": topic, "count": round(count, 2), "example": examples.get(topic, "")}
        for topic, count in counts.most_common(30)
    ]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--videos", type=int, default=int(os.environ.get("COMMENTS_INTEL_VIDEOS", "20")))
    parser.add_argument(
        "--comments-per-video", type=int, default=int(os.environ.get("COMMENTS_PER_VIDEO", "50"))
    )
    parser.add_argument("--out", default=os.environ.get("COMMENTS_INTEL_PATH", "data/comments_intel_fr.json"))
    args = parser.parse_args(argv)

    token = _token()
    if not token:
        _write_json(
            Path(args.out),
            {
                "generated_at_utc": datetime.now(UTC).isoformat(),
                "configured": False,
                "comments": [],
                "topic_requests": [],
            },
        )
        return 0

    ids = _recent_video_ids(token, args.videos)
    comments: list[dict] = []
    for vid in ids:
        try:
            comments.extend(_comments_for_video(token, vid, args.comments_per_video))
        except Exception as exc:
            LOG.warning("comments for %s skipped: %s", vid, exc)
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "configured": True,
        "video_count": len(ids),
        "comment_count": len(comments),
        "topic_requests": extract_topic_requests(comments),
        "comments": comments[:300],
    }
    _write_json(Path(args.out), report)
    LOG.info("Wrote comment intelligence: %s (%d comments)", args.out, len(comments))
    return 0


if __name__ == "__main__":
    sys.exit(main())
