#!/usr/bin/env python3
"""niche_migration.py — wipe old-niche scheduled videos + retrain ML on the new niche.

Used when the channel switches editorial niche (e.g. body-glitches -> surprising
body/brain facts). Steps:

  1. Find still-PRIVATE scheduled videos (future publishAt) in video_history.json
     and DELETE them from YouTube (videos.delete) — they are old-niche content
     that should not go live.
  2. Remove those deleted entries from video_history.json + upload_state.json so
     the ledger no longer references dead videos.
  3. Rebuild the NEW-niche topic catalogue (generate_body_glitch_topics.py,
     which now emits faits_surprenants_fr topics) and retrain the ML brain on
     the new niche data (niche_intel + ml_brain).

Run: python scripts/niche_migration.py            # dry-run
     python scripts/niche_migration.py --apply     # actually delete + retrain
Needs GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN for --apply.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

log = logging.getLogger("niche-migration")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

VIDEO_HISTORY_PATH = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")
UPLOAD_STATE_PATH = os.environ.get("UPLOAD_STATE_PATH", "data/upload_state.json")


def _token() -> str:
    data = urllib.parse.urlencode(
        {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }
    ).encode()
    with urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data), timeout=30
    ) as r:
        return json.load(r)["access_token"]


def _yt_delete(token: str, vid: str) -> None:
    req = urllib.request.Request(
        f"https://www.googleapis.com/youtube/v3/videos?id={vid}",
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        r.read()


def _future_private_videos() -> list[dict]:
    """Return video_history entries that are still scheduled (publishAt future)."""
    if not os.path.exists(VIDEO_HISTORY_PATH):
        return []
    with open(VIDEO_HISTORY_PATH, encoding="utf-8") as f:
        history = json.load(f)
    if not isinstance(history, list):
        return []
    now = datetime.now(UTC)
    out = []
    for v in history:
        pa = v.get("publish_at")
        vid = v.get("youtube_video_id")
        if not pa or not vid:
            continue
        try:
            padt = datetime.fromisoformat(pa)
            if padt.tzinfo is None:
                padt = padt.replace(tzinfo=UTC)
        except Exception:
            continue
        if padt > now:  # still scheduled / private
            out.append(v)
    return out


def _clean_ledger(vids: list[dict]) -> None:
    """Remove deleted videos from video_history.json and upload_state.json."""
    # video_history
    if os.path.exists(VIDEO_HISTORY_PATH):
        with open(VIDEO_HISTORY_PATH, encoding="utf-8") as f:
            history = json.load(f)
        if isinstance(history, list):
            dead_ids = {v["youtube_video_id"] for v in vids}
            history = [v for v in history if v.get("youtube_video_id") not in dead_ids]
            tmp = VIDEO_HISTORY_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            os.replace(tmp, VIDEO_HISTORY_PATH)
            log.info("Removed %d old-niche entries from video_history", len(dead_ids))

    # upload_state
    if os.path.exists(UPLOAD_STATE_PATH):
        with open(UPLOAD_STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
        if isinstance(state, dict):
            for v in vids:
                vid = v.get("youtube_video_id")
                # upload_state keys are content fingerprints; remove any record
                # whose youtube_video_id matches.
                to_drop = [
                    k
                    for k, rec in state.items()
                    if isinstance(rec, dict) and rec.get("youtube_video_id") == vid
                ]
                for k in to_drop:
                    state.pop(k, None)
            tmp = UPLOAD_STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp, UPLOAD_STATE_PATH)
            log.info("Cleaned %d entries from upload_state", len(vids))


def _retrain_new_niche() -> None:
    """Rebuild new-niche catalogue + retrain ML."""
    log.info("Rebuilding new-niche topic catalogue...")
    os.system("python scripts/generate_body_glitch_topics.py")
    log.info("Running niche intelligence + ML retrain on new niche...")
    os.system("python scripts/niche_intel.py || true")
    os.system("python scripts/ml_brain.py || true")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply", action="store_true", help="actually delete scheduled videos + retrain (default dry-run)"
    )
    args = ap.parse_args()

    vids = _future_private_videos()
    log.info("Found %d scheduled (private) old-niche video(s)", len(vids))
    for v in vids:
        log.info("  - %s | %s", v.get("youtube_video_id"), str(v.get("title"))[:45])

    if not args.apply:
        log.info("DRY RUN — pass --apply to delete + retrain.")
        return 0

    token = _token()
    deleted = 0
    for v in vids:
        vid = v.get("youtube_video_id")
        try:
            _yt_delete(token, vid)
            log.info("DELETED %s (%s)", vid, str(v.get("title"))[:40])
            deleted += 1
        except Exception as exc:
            log.warning("Failed to delete %s: %s", vid, exc)

    if vids:
        _clean_ledger(vids)

    _retrain_new_niche()
    log.info("Migration complete: deleted %d, retrained ML on new niche", deleted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
