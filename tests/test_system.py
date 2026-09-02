from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from config import Settings
from content import _clean_fr, _fallback_script


def test_french_defaults_and_duration_window():
    settings = Settings()
    assert settings.language == "fr"
    assert settings.min_seconds == 15
    assert settings.max_seconds == 30


def test_fallback_script_is_french_and_has_six_scenes():
    script = _fallback_script("Pourquoi le cerveau rêve-t-il ?")
    assert len(script["scenes"]) == 6
    assert script["title"].endswith("?")
    assert "Tu vas comprendre" in script["description"]
    assert any("ton cerveau" in scene["narration"] for scene in script["scenes"])
    assert all(scene["narration"] for scene in script["scenes"])


def test_french_copy_normalizes_punctuation_spacing():
    assert _clean_fr("Pourquoi ça arrive  ?") == "Pourquoi ça arrive?"


def test_invalid_public_configuration_is_rejected(monkeypatch):
    monkeypatch.setenv("CHANNEL_LANGUAGE", "en")
    monkeypatch.setenv("TARGET_MIN_SECONDS", "30")
    monkeypatch.setenv("TARGET_MAX_SECONDS", "15")
    settings = Settings()
    errors = settings.validate()
    assert any("CHANNEL_LANGUAGE" in error for error in errors)
    assert any("valid window" in error for error in errors)


def test_dry_run_does_not_require_external_secrets(monkeypatch):
    for name in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "ALT_LLM_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DRY_RUN", "true")
    settings = Settings()
    assert settings.validate() == []
