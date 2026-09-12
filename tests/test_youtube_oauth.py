from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.youtube_oauth import (
    ANALYTICS_SCOPE,
    YouTubeAPIError,
    YouTubeOAuthError,
    analytics_query,
    refresh_session,
    require_scope,
)


def response(status: int, payload: dict):
    item = Mock()
    item.status_code = status
    item.ok = 200 <= status < 300
    item.json.return_value = payload
    item.text = str(payload)
    return item


def test_refresh_does_not_send_scope_parameter():
    token = response(200, {"access_token": "access", "expires_in": 3600})
    info = response(200, {"scope": f"{ANALYTICS_SCOPE} https://www.googleapis.com/auth/youtube.upload"})
    with patch.dict(
        "os.environ",
        {"GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "secret", "REFRESH_TOKEN": "refresh"},
        clear=False,
    ), patch("src.youtube_oauth.requests.post", return_value=token) as post, patch(
        "src.youtube_oauth.requests.get", return_value=info
    ):
        session = refresh_session()

    assert session.analytics_scope_granted
    body = post.call_args.kwargs["data"]
    assert "scope" not in body
    assert body["grant_type"] == "refresh_token"


def test_require_scope_gives_reauthorization_instruction():
    session = type("Session", (), {"granted_scopes": frozenset()})()
    with pytest.raises(YouTubeOAuthError, match="Re-authorize"):
        require_scope(session)


def test_analytics_query_requires_scope_before_network_call():
    session = type("Session", (), {"granted_scopes": frozenset(), "access_token": "secret"})()
    with pytest.raises(YouTubeOAuthError, match="Required OAuth scope"):
        analytics_query(session, ids="channel==MINE")


def test_api_error_preserves_status_for_metric_self_healing():
    error = YouTubeAPIError(400, "Unknown identifier (impressions)")
    assert error.status == 400
    assert "impressions" in error.detail


def test_refresh_failure_does_not_echo_refresh_token():
    token = response(400, {"error": "invalid_grant", "error_description": "bad token"})
    with patch.dict(
        "os.environ",
        {"GOOGLE_CLIENT_ID": "id", "GOOGLE_CLIENT_SECRET": "secret", "REFRESH_TOKEN": "do-not-print"},
        clear=False,
    ), patch("src.youtube_oauth.requests.post", return_value=token), pytest.raises(YouTubeOAuthError) as exc:
        refresh_session()
    assert "do-not-print" not in str(exc.value)



def test_analytics_query_returns_shorts_feed_metrics_and_aliases(monkeypatch):
    from src import seo_analytics

    session = type("Session", (), {"granted_scopes": frozenset({ANALYTICS_SCOPE}), "access_token": "access"})()
    payload = {
        "columnHeaders": [
            {"name": "views"},
            {"name": "engagedViews"},
            {"name": "averageViewDuration"},
            {"name": "averageViewPercentage"},
            {"name": "stayedToWatch"},
        ],
        "rows": [[120, 95, 12, 48.5, 62.0]],
    }
    monkeypatch.setattr("youtube_oauth.refresh_session", lambda: session)
    monkeypatch.setattr("youtube_oauth.analytics_query", lambda *_args, **_kwargs: payload)

    result = seo_analytics.fetch_actual_performance("video-1")

    assert result["views"] == 120
    assert result["engaged_views"] == 95
    assert result["stayed_to_watch"] == 62.0
    assert result["viewed_vs_swiped_away"] == 62.0
    assert "stayedToWatch" in result["available_metrics"]
    assert "shortsFeedShown" in result["unavailable_metrics"]


def test_analytics_metric_probe_drops_unsupported_shorts_fields(monkeypatch):
    from src import seo_analytics
    from youtube_oauth import YouTubeAPIError as RuntimeYouTubeAPIError

    session = type("Session", (), {"granted_scopes": frozenset({ANALYTICS_SCOPE}), "access_token": "access"})()
    calls = []

    def query(*_args, **kwargs):
        calls.append(kwargs["metrics"])
        metrics = kwargs["metrics"].split(",")
        unsupported = next((metric for metric in metrics if metric == "shortsFeedShown"), None)
        if unsupported:
            raise RuntimeYouTubeAPIError(400, f"Unknown identifier ({unsupported})")
        return {
            "columnHeaders": [{"name": "views"}, {"name": "engagedViews"}],
            "rows": [[8, 7]],
        }

    monkeypatch.setattr("youtube_oauth.refresh_session", lambda: session)
    monkeypatch.setattr("youtube_oauth.analytics_query", query)

    result = seo_analytics.fetch_actual_performance("video-2")

    assert result["views"] == 8
    assert result["engaged_views"] == 7
    assert "shortsFeedShown" in result["unavailable_metrics"]
    assert len(calls) >= 2
