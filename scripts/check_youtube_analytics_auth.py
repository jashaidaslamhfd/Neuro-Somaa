"""Validate the production YouTube OAuth grant without exposing credentials."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from youtube_oauth import (
    ANALYTICS_SCOPE,
    YouTubeOAuthError,
    _request_json,
    refresh_session,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-analytics",
        action="store_true",
        help="Exit non-zero unless yt-analytics.readonly is granted",
    )
    args = parser.parse_args()

    try:
        session = refresh_session()
        print(f"OAuth refresh: OK (expires_in={session.expires_in})")
        print(f"Analytics scope: {'OK' if session.analytics_scope_granted else 'MISSING'}")
        print(f"Data read scope: {'OK' if session.data_read_scope_granted else 'MISSING'}")
        print(f"Granted scope count: {len(session.granted_scopes)}")
        if args.require_analytics and not session.analytics_scope_granted:
            print(
                f"Required scope missing: {ANALYTICS_SCOPE}. "
                "Run scripts/reauthorize_youtube_analytics.py locally and update "
                "the GitHub REFRESH_TOKEN secret.",
                file=sys.stderr,
            )
            return 4
        channel = _request_json(
            session,
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "id,snippet", "mine": "true"},
        )
        items = channel.get("items") or []
        if not items:
            print("Channel identity: FAILED (no channel returned)", file=sys.stderr)
            return 5
        item = items[0]
        print(f"Channel identity: OK (id={item.get('id')})")
        print(f"Channel title: {((item.get('snippet') or {}).get('title') or 'unknown')[:80]}")
        return 0
    except YouTubeOAuthError as exc:
        print(f"OAuth health-check failed: {str(exc)[:400]}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
