from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from audio import WordTiming
from media import _caption_word_durations


def test_french_caption_punctuation_matches_tts_tokens():
    timings = [
        WordTiming("ATTENDS", 0.0, 0.4),
        WordTiming("ton", 0.4, 0.3),
        WordTiming("cerveau", 0.7, 0.6),
        WordTiming("fait", 1.3, 0.3),
        WordTiming("ça", 1.6, 0.4),
    ]
    durations = _caption_word_durations(
        "ATTENDS—ton cerveau fait ça.",
        "ATTENDS ton cerveau fait ça.",
        timings,
        2.0,
    )
    assert len(durations) == 4
    assert sum(durations) == pytest.approx(2.0)
    assert all(value > 0 for value in durations)


def test_short_hook_caption_falls_back_to_full_scene_split():
    timings = [WordTiming("Ton", 0.0, 0.3), WordTiming("cerveau", 0.3, 0.4), WordTiming("réagit", 0.7, 0.5)]
    durations = _caption_word_durations("Ton cerveau", "Ton cerveau réagit", timings, 1.8)
    assert len(durations) == 2
    assert sum(durations) == pytest.approx(1.8)
    assert durations == pytest.approx([0.9, 0.9])
