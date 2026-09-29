from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from config import Settings
from content import _GeminiAdapter, _OpenRouterAdapter
from thumbnails import build_thumbnail
from visual_providers import _archive_clip


def test_gemini_adapter_formatting():
    adapter = _GeminiAdapter("fake-key")
    messages = [
        {"role": "system", "content": "System directive"},
        {"role": "user", "content": "User request"},
    ]
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"scenes": [{"caption": "test"}]}'}]}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        res = adapter.create("gemini-2.0-flash", messages)
        assert res.choices[0].message.content == '{"scenes": [{"caption": "test"}]}'
        assert mock_post.called
        call_url = mock_post.call_args[0][0]
        assert "gemini-2.0-flash" in call_url
        assert "fake-key" in call_url


def test_openrouter_adapter_formatting():
    adapter = _OpenRouterAdapter("fake-openrouter-key")
    messages = [
        {"role": "system", "content": "System directive"},
        {"role": "user", "content": "User request"},
    ]
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"scenes": [{"caption": "test"}]}'}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        res = adapter.create("meta-llama/llama-3.3-70b-instruct", messages)
        assert res.choices[0].message.content == '{"scenes": [{"caption": "test"}]}'
        assert mock_post.called
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer fake-openrouter-key"


def test_archive_clip_sanitizes_special_characters(tmp_path):
    clip_path = tmp_path / "clip.mp4"
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"response": {"docs": []}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # Caption with quotes, colons, and punctuation
        _archive_clip("ATTENDS—ton cœur bat: pourquoi ?", clip_path)
        assert mock_get.called
        q_param = mock_get.call_args[1]["params"]["q"]
        assert "ATTENDS ton cœur bat pourquoi" in q_param
        assert "—" not in q_param
        assert "bat:" not in q_param


def test_build_thumbnail_creates_output_directory(tmp_path):
    settings = Settings()
    settings.output_dir = tmp_path / "nested" / "nonexistent" / "output"
    assert not settings.output_dir.exists()

    script = {"title": "Pourquoi ton cerveau rêve-t-il ?"}
    thumb_path = build_thumbnail(script, settings)
    assert thumb_path.exists()
    assert thumb_path.parent.exists()
