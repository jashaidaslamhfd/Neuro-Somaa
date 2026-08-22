"""Production-safe YouTube OAuth and Analytics API helpers.

The refresh-token grant must not include a ``scope`` parameter: Google can
reject a valid refresh token with ``invalid_scope`` when a caller attempts to
narrow or alter the scopes originally granted. Scope validation is therefore
performed after refresh through tokeninfo, while the grant itself stays bare.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
ANALYTICS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
DATA_API_URL = "https://www.googleapis.com/youtube/v3"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
DATA_READ_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"


class YouTubeOAuthError(RuntimeError):
    """A safe, operator-facing OAuth/API configuration error."""


class YouTubeAPIError(YouTubeOAuthError):
    """An API response that callers may classify by status and body."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


@dataclass(frozen=True)
class OAuthSession:
    access_token: str
    expires_in: int | None
    granted_scopes: frozenset[str]

    @property
    def analytics_scope_granted(self) -> bool:
        return ANALYTICS_SCOPE in self.granted_scopes

    @property
    def data_read_scope_granted(self) -> bool:
        return DATA_READ_SCOPE in self.granted_scopes


def _credentials_from_env() -> tuple[str, str, str]:
    values = {
        "GOOGLE_CLIENT_ID": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        "GOOGLE_CLIENT_SECRET": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        "REFRESH_TOKEN": os.environ.get("REFRESH_TOKEN", "").strip(),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise YouTubeOAuthError(f"Missing OAuth environment variables: {', '.join(missing)}")
    return values["GOOGLE_CLIENT_ID"], values["GOOGLE_CLIENT_SECRET"], values["REFRESH_TOKEN"]


def _safe_error(response: requests.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return str(payload.get("error_description") or payload.get("error") or payload)
    except (ValueError, json.JSONDecodeError):
        pass
    return response.text[:300].replace("\n", " ")


def refresh_session(timeout: int = 30) -> OAuthSession:
    """Refresh access and validate the scopes carried by the access token."""
    client_id, client_secret, refresh_token = _credentials_from_env()
    # Deliberately no ``scope`` field here. It prevents Google's invalid_scope
    # response for refresh tokens minted with a broader/different set.
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=timeout,
    )
    if not response.ok:
        raise YouTubeOAuthError(f"OAuth refresh failed ({response.status_code}): {_safe_error(response)}")
    try:
        payload = response.json()
        access_token = str(payload["access_token"])
    except (ValueError, KeyError, TypeError) as exc:
        raise YouTubeOAuthError("OAuth refresh returned malformed JSON") from exc

    info = requests.get(TOKENINFO_URL, params={"access_token": access_token}, timeout=timeout)
    if not info.ok:
        raise YouTubeOAuthError(f"OAuth tokeninfo failed ({info.status_code}): {_safe_error(info)}")
    try:
        info_payload = info.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise YouTubeOAuthError("OAuth tokeninfo returned malformed JSON") from exc
    scopes = frozenset(str(info_payload.get("scope", "")).split())
    return OAuthSession(
        access_token=access_token,
        expires_in=payload.get("expires_in"),
        granted_scopes=scopes,
    )


def require_scope(session: OAuthSession, scope: str = ANALYTICS_SCOPE) -> None:
    if scope not in session.granted_scopes:
        raise YouTubeOAuthError(
            "Required OAuth scope is missing: "
            f"{scope}. Re-authorize the refresh token with the complete scope set; "
            "do not try to add scopes to the refresh request itself."
        )


def _request_json(
    session: OAuthSession,
    url: str,
    *,
    params: dict[str, Any],
    timeout: int = 60,
    retries: int = 3,
) -> dict[str, Any]:
    last_error = "unknown error"
    for attempt in range(max(1, retries)):
        response = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {session.access_token}"},
            timeout=timeout,
        )
        if response.ok:
            try:
                return response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                raise YouTubeOAuthError(f"API returned malformed JSON: {exc}") from exc
        detail = _safe_error(response)
        last_error = f"HTTP {response.status_code}: {detail}"
        if response.status_code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
            time.sleep(2**attempt)
            continue
        raise YouTubeAPIError(response.status_code, detail)
    raise YouTubeAPIError(response.status_code, last_error)


def analytics_query(session: OAuthSession, **params: Any) -> dict[str, Any]:
    require_scope(session)
    return _request_json(session, ANALYTICS_URL, params=params)


def data_video_statistics(session: OAuthSession, video_id: str) -> dict[str, Any]:
    return _request_json(
        session,
        f"{DATA_API_URL}/videos",
        params={"part": "statistics", "id": video_id},
    )
