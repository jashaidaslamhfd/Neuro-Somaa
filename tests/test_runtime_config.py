from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from config import Settings
from content import score_hook, score_script_quality

ROOT = Path(__file__).parents[1]


def _env_example_value(name: str) -> str:
    text = (ROOT / "env.example").read_text(encoding="utf-8")
    match = re.search(rf"^{name}=(.*)$", text, re.MULTILINE)
    assert match, f"{name} missing from env.example"
    return match.group(1).strip()


def _workflow_value(name: str) -> str:
    text = (ROOT / ".github/workflows/main.yml").read_text(encoding="utf-8")
    match = re.search(rf"^\s*{name}:\s*\"?([^\"\n]+)\"?\s*$", text, re.MULTILINE)
    assert match, f"{name} missing from .github/workflows/main.yml"
    return match.group(1).strip()


def test_quality_thresholds_match_between_env_example_and_workflow():
    for name in ("MIN_HOOK_SCORE", "QUALITY_APPROVAL_THRESHOLD", "TARGET_MIN_SECONDS", "TARGET_MAX_SECONDS", "PUBLISH_TIMEZONE"):
        assert _env_example_value(name) == _workflow_value(name), f"{name} differs between env.example and main.yml"


def test_settings_defaults_match_env_example(monkeypatch):
    for name in ("MIN_HOOK_SCORE", "QUALITY_APPROVAL_THRESHOLD"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.min_hook_score == int(_env_example_value("MIN_HOOK_SCORE"))
    assert settings.quality_approval_threshold == int(_env_example_value("QUALITY_APPROVAL_THRESHOLD"))


def test_strong_hook_clears_default_threshold():
    score = score_hook("Pourquoi ton cerveau rêve-t-il ?", "ATTENDS—ton cerveau fait ça.")
    assert score >= 70


def test_generic_opener_fails_default_threshold():
    score = score_hook(
        "Le cerveau et le sommeil",
        "Dans cette vidéo on va parler de plein de choses interessantes aujourdhui",
    )
    assert score < 70


def test_script_quality_rejects_filler_pacing():
    filler_scenes = [{"caption": "Dans cette vidéo on va vous expliquer plein de choses en detail"}] * 8
    assert score_script_quality(filler_scenes) < 60
