"""Mint a refresh token with YouTube Analytics access.

Run locally, not in GitHub Actions. The refresh token is printed once so the
operator can replace the REFRESH_TOKEN GitHub secret. Never commit the output.
"""

from __future__ import annotations

import argparse
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client-secret-file",
        default=os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET_FILE", "client_secret.json"),
        help="OAuth desktop-client JSON downloaded from Google Cloud Console",
    )
    args = parser.parse_args()

    if not os.path.exists(args.client_secret_file):
        print(
            f"Missing {args.client_secret_file}. Download an OAuth Desktop app JSON "
            "from Google Cloud Console; do not use a service-account key.",
            file=sys.stderr,
        )
        return 2

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret_file, SCOPES)
    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    if not credentials.refresh_token:
        print(
            "Google returned no refresh token. Re-run with prompt=consent and revoke "
            "the old grant in your Google Account first.",
            file=sys.stderr,
        )
        return 3

    print("OAuth authorization complete.")
    print("Granted scopes:")
    for scope in sorted(credentials.scopes or []):
        print(f"  {scope}")
    print("\nReplace the GitHub Actions REFRESH_TOKEN secret with this value:")
    print(credentials.refresh_token)
    print("\nDo not commit this output or paste it into logs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
