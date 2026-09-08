from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from audio import mix_background_music, select_music_track, synthesize_narration
from config import Settings


def _silent_wav(path: Path, seconds: float, rate: int = 24000) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * int(seconds * rate))


def test_music_catalog_only_ever_returns_own_tracks():
    settings = Settings()
    settings.music_source = "own"
    track = select_music_track(settings, seed="any-video")
    assert track is not None
    assert track.name.startswith("own_")
    assert track.suffix == ".wav"


def test_music_source_other_than_own_disables_selection():
    settings = Settings()
    settings.music_source = "pixabay"
    assert select_music_track(settings, seed="any-video") is None


def test_music_selection_is_deterministic_per_seed():
    settings = Settings()
    settings.music_source = "own"
    first = select_music_track(settings, seed="Pourquoi ton cerveau rêve-t-il ?")
    second = select_music_track(settings, seed="Pourquoi ton cerveau rêve-t-il ?")
    assert first == second


def test_settings_validate_rejects_non_own_music_source():
    settings = Settings()
    settings.background_music = True
    settings.music_source = "pixabay"
    settings.dry_run = True
    errors = settings.validate()
    assert any("MUSIC_SOURCE" in error for error in errors)


def test_mix_background_music_preserves_narration_duration(tmp_path):
    settings = Settings()
    settings.music_source = "own"
    narration_path = tmp_path / "narration.wav"
    _silent_wav(narration_path, seconds=2.5)
    track = select_music_track(settings, seed="mix-test")
    out_path = tmp_path / "mixed.wav"
    mix_background_music(narration_path, track, start_offset=0.0, out_path=out_path, gain_db=-20)
    assert out_path.exists()
    with wave.open(str(out_path), "rb") as mixed:
        mixed_duration = mixed.getnframes() / mixed.getframerate()
    assert mixed_duration == pytest.approx(2.5, abs=0.05)


def test_mix_background_music_continuous_offset_does_not_crash_near_track_end(tmp_path):
    settings = Settings()
    settings.music_source = "own"
    track = select_music_track(settings, seed="offset-test")
    narration_path = tmp_path / "narration.wav"
    _silent_wav(narration_path, seconds=3.0)
    out_path = tmp_path / "mixed.wav"
    # A large offset forces the modulo-wrap path to be exercised.
    mix_background_music(narration_path, track, start_offset=9999.0, out_path=out_path, gain_db=-20)
    assert out_path.exists()


def test_synthesize_narration_dry_run_word_timings_span_full_duration(tmp_path):
    settings = Settings()
    settings.dry_run = True
    wav_path = tmp_path / "scene.wav"
    text = "Ton cerveau efface ça vite"
    duration, timings = synthesize_narration(text, wav_path, settings)
    assert wav_path.exists()
    assert len(timings) == len(text.split())
    assert sum(t.duration for t in timings) == pytest.approx(duration, abs=0.01)
