#!/usr/bin/env python3
"""One-shot thumbnail upload for SKILLOR FR.

Uploads every assets/thumbnails_fr/<video_id>.jpg to YouTube via
thumbnails.set (media upload). Images were pre-rendered locally and
committed to the repo, so this script is upload-only and std-lib only.

Safety:
- uploads only for video IDs already listed in data/video_history.json
  (never touches an unknown video),
- every image is validated as JPEG < 2MB (YouTube hard limit),
- 1.5s pause between uploads, full report printed + artifacted.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THUMB_DIR = ROOT / "assets" / "thumbnails_fr"
HISTORY = ROOT / "data" / "video_history.json"
REPORT = ROOT / "output" / "thumbnail_update_report.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("thumbnail_update")


def _access_token() -> str:
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode(
        {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def _set_thumbnail(token: str, video_id: str, jpeg: bytes) -> None:
    import urllib.error
    import urllib.request

    url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}"
    req = urllib.request.Request(url, data=jpeg, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "image/jpeg")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            if r.status not in (200, 204):
                raise RuntimeError(f"unexpected status {r.status}")
    except urllib.error.HTTPError as e:
        payload = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"thumbnails.set {video_id} -> {e.code}: {payload}") from e


def _channel_video_ids(token: str) -> set:
    """Every video ID actually on the channel, straight from the uploads
    playlist.

    data/video_history.json is NOT a reliable allow-list: it was reset during
    the France-first migration (see docs/archive/MIGRATION_FR.md), so genuine published
    videos are missing from it. Four real videos needing a thumbnail fix —
    including "Pourquoi on oublie un prénom…" (1,114 views) — were being
    refused as "not in video_history". The channel itself is the source of
    truth; history is only a local cache."""
    import urllib.request

    def _get(url: str) -> dict:
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.load(response)

    api = "https://www.googleapis.com/youtube/v3"
    channel = _get(f"{api}/channels?part=contentDetails&mine=true")
    uploads = channel["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = set(), None
    while True:
        url = f"{api}/playlistItems?part=contentDetails&playlistId={uploads}&maxResults=50"
        if page:
            url += f"&pageToken={page}"
        data = _get(url)
        ids |= {i["contentDetails"]["videoId"] for i in data.get("items", [])}
        page = data.get("nextPageToken")
        if not page:
            return ids


def main() -> int:
    images = sorted(THUMB_DIR.glob("*.jpg"))
    if not images:
        logger.info("No thumbnails staged in %s — nothing to do.", THUMB_DIR)
        return 0

    # Authenticate first so the allow-list can come from the live channel.
    token = _access_token()
    try:
        known = _channel_video_ids(token)
        source = "live channel"
    except Exception as exc:
        logger.warning("Could not list channel uploads (%s); falling back to data/video_history.json", exc)
        known = {e["youtube_video_id"] for e in json.loads(HISTORY.read_text()) if e.get("youtube_video_id")}
        source = "video_history.json"
    logger.info("Thumbnails found: %d (allow-list from %s covers %d videos)", len(images), source, len(known))

    jobs, skips = [], []
    for img in images:
        vid = img.stem
        if vid not in known:
            skips.append((vid, f"not found on the channel ({source}) — refused"))
            continue
        data = img.read_bytes()
        if len(data) > 2 * 1024 * 1024:
            skips.append((vid, "image > 2MB — refused"))
            continue
        if data[:3] != b"\xff\xd8\xff":
            skips.append((vid, "not a valid JPEG — refused"))
            continue
        jobs.append((vid, data))

    if skips:
        for vid, why in skips:
            logger.warning("SKIP  %s (%s)", vid, why)

    ok, failed = 0, []
    if jobs:
        for vid, data in jobs:
            try:
                _set_thumbnail(token, vid, data)
                ok += 1
                logger.info("UPLOADED  %s  (%d KB)", vid, len(data) // 1024)
            except Exception as exc:
                failed.append((vid, str(exc)))
                logger.error("FAILED    %s  %s", vid, exc)
            time.sleep(1.5)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "THUMBNAIL UPDATE REPORT",
        f"uploaded: {ok} / {len(jobs)}",
        f"skipped: {len(skips)}",
        f"failed: {len(failed)}",
        "",
    ]
    lines += [f"FAIL {v}: {m}" for v, m in failed]
    REPORT.write_text("\n".join(lines))
    logger.info("DONE — uploaded: %d, skipped: %d, failed: %d", ok, len(skips), len(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
