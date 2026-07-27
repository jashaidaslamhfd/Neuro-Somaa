#!/usr/bin/env python3
"""Operation Cleanup FR (2026-07-26) — scan + delete algorithm-dead uploads.

Lists EVERY upload on the NeuroSomaa channel with views + age, prints the
full table, and with --apply deletes the ones YouTube's recommendation
system has already fully rejected (default: <=10 views after >=7 days).

Safety rails:
  - scheduled (private + publishAt) videos are NEVER touched
  - anything younger than --min-age-days is kept (48-72h data rule)
  - anything above --max-views is kept (underperforming != rejected)

DRY by default; pass --apply to delete for real.
Needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / REFRESH_TOKEN env (FR OAuth).
"""
import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("yt-dead-cleanup-fr")
API = "https://www.googleapis.com/youtube/v3"


def _token() -> str:
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["REFRESH_TOKEN"],
        "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(
            urllib.request.Request("https://oauth2.googleapis.com/token", data=data),
            timeout=30) as r:
        return json.load(r)["access_token"]


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-views", type=int, default=10)
    ap.add_argument("--min-age-days", type=int, default=7)
    args = ap.parse_args()
    token = _token()

    channel = _get(f"{API}/channels?part=contentDetails&mine=true", token)
    uploads = channel["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, page = [], None
    while True:
        url = f"{API}/playlistItems?part=contentDetails&playlistId={uploads}&maxResults=50"
        if page:
            url += f"&pageToken={page}"
        data = _get(url, token)
        ids += [i["contentDetails"]["videoId"] for i in data.get("items", [])]
        page = data.get("nextPageToken")
        if not page:
            break

    rows = []
    for i in range(0, len(ids), 50):
        data = _get(f"{API}/videos?part=snippet,status,statistics&id={','.join(ids[i:i + 50])}", token)
        for video in data.get("items", []):
            snippet = video.get("snippet", {})
            status = video.get("status", {})
            stats = video.get("statistics", {})
            published = datetime.fromisoformat(snippet["publishedAt"])
            age_days = (datetime.now(UTC) - published).total_seconds() / 86400
            rows.append({
                "id": video["id"],
                "title": snippet.get("title", "")[:60],
                "views": int(stats.get("viewCount", 0)),
                "age_days": age_days,
                "scheduled": bool(status.get("publishAt")),
            })

    dead, kept = [], []
    for row in rows:
        if row["scheduled"]:
            kept.append(row)  # not yet live — never touch
        elif row["views"] <= args.max_views and row["age_days"] >= args.min_age_days:
            dead.append(row)
        else:
            kept.append(row)

    log.info("channel uploads: %d | dead (<= %d views, >= %d days): %d | kept: %d",
             len(rows), args.max_views, args.min_age_days, len(dead), len(kept))
    for row in sorted(rows, key=lambda r: r["views"]):
        marker = "DEAD " if row in dead else ("SCHED" if row["scheduled"] else "keep ")
        log.info("%s %5d views | %5.1fd | %s (%s)", marker, row["views"], row["age_days"], row["title"], row["id"])

    deleted, failed = 0, 0
    for row in dead:
        if not args.apply:
            log.info("[dry] would DELETE %s (%d views, %.0f days)", row["id"], row["views"], row["age_days"])
            continue
        try:
            req = urllib.request.Request(f"{API}/videos?id={row['id']}", method="DELETE")
            req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, timeout=40) as r:
                r.read()
            deleted += 1
            log.info("DELETED %s (%d views, %.0f days — %s)", row["id"], row["views"], row["age_days"], row["title"])
        except Exception as exc:
            failed += 1
            log.error("FAILED %s: %s", row["id"], exc)
        time.sleep(1)
    log.info("done (apply=%s, deleted=%d, failed=%d)", args.apply, deleted, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
