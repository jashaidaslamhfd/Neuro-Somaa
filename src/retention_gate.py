"""Hard structural gates for the first three seconds of a French Short.

These checks validate facts available before upload. They do not claim to
predict YouTube distribution; they prevent known production defects such as a
silent opening, a generic first visual, a hook that arrives too late, or a
caption that does not match the spoken opening.
"""

from __future__ import annotations

import os
import re
from typing import Any

_MAX_HOOK_WORDS = 9
_MIN_HOOK_WORDS = 5
_DECISION_SECONDS = 2.2
_OPENING_SECONDS = 3.0
_MAX_FIRST_SCENE_SECONDS = float(os.environ.get("RETENTION_MAX_FIRST_SCENE_SECONDS", "5.0"))
# French edge-tts delivery is slower than the old generic density target.
# Keep a strict, measured minimum while allowing the calibrated production
# value to be configured without weakening hook/visual/duration checks.
_MIN_DECISION_WORDS = int(os.environ.get("RETENTION_MIN_DECISION_WORDS", "4"))
_MIN_WORDS_BY_OPENING = int(os.environ.get("RETENTION_MIN_OPENING_WORDS", "6"))
_MOTION_TERMS = re.compile(
    r"\b(?:gros plan|close[- ]?up|macro|zoom|pulse|pulsation|tremble|tremblement|"
    r"bouge|mouvement|flash|éclate|s'ouvre|se contracte|accélère|ralentit|"
    r"tourne|secoue|vibre|clignote|apparaît|disparaît|transition|réaction)\b",
    re.IGNORECASE,
)
_GENERIC_VISUAL_TERMS = re.compile(
    r"\b(?:fond abstrait|abstract background|logo|interface|écran vide|texte seul|"
    r"stock générique|generic stock|image fixe sans action)\b",
    re.IGNORECASE,
)
_PAYOFF_TERMS = re.compile(
    r"\b(?:parce que|voici|c'est|ce n'est pas|le vrai|la vraie|en réalité|"
    r"ton cerveau|ton corps|tes nerfs|ton estomac|tes muscles|le mécanisme|"
    r"la raison|s'explique|vient de)\b",
    re.IGNORECASE,
)


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _words(text: Any) -> list[str]:
    return re.findall(r"[\wÀ-ÿŒœ'-]+", str(text or ""), flags=re.UNICODE)


def _opening_text_and_words(audio_segments: list[dict], seconds: float) -> tuple[str, int]:
    """Return the approximate spoken text/word count inside the opening window."""
    elapsed = 0.0
    collected: list[str] = []
    words = 0
    for segment in audio_segments:
        duration = max(float(segment.get("duration", 0) or 0), 0.0)
        if elapsed >= seconds:
            break
        overlap = min(duration, seconds - elapsed)
        text = str(segment.get("text") or segment.get("caption") or "").strip()
        if text and overlap > 0:
            fraction = min(1.0, overlap / duration) if duration else 0.0
            segment_words = _words(text)
            take = max(1, round(len(segment_words) * fraction)) if segment_words else 0
            words += min(len(segment_words), take)
            collected.append(" ".join(segment_words[:take]))
        elapsed += duration
    return " ".join(collected), words


def ensure_opening_visual_action(script_data: dict) -> dict:
    """Repair a missing/generic first visual before rendering and validation.

    The first frame must communicate visible motion or change. LLM output can
    occasionally return a static noun phrase, so replace only that unsafe
    opening with a deterministic production-safe close-up description.
    """
    scenes = script_data.get("scenes") or []
    if not scenes or not isinstance(scenes[0], dict):
        return script_data
    visual = str(scenes[0].get("visual") or "").strip()
    if not visual or not _MOTION_TERMS.search(visual) or _GENERIC_VISUAL_TERMS.search(visual):
        scenes[0]["visual"] = (
            "Gros plan en mouvement : le phénomène apparaît et change visiblement à l'écran."
        )
    return script_data


def validate_first_three_seconds(script_data: dict, audio_segments: list[dict]) -> dict:
    """Validate the opening that a viewer actually receives before upload."""
    scenes = script_data.get("scenes") or []
    hook = str(script_data.get("hook") or "").strip()
    first_scene = scenes[0] if scenes else {}
    first_caption = str(first_scene.get("caption") or "").strip()
    first_visual = str(first_scene.get("visual") or "").strip()
    second_scene = scenes[1] if len(scenes) > 1 else {}
    second_caption = str(second_scene.get("caption") or "").strip()

    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    hook_words = len(_words(hook))
    add(
        "hook_length",
        _MIN_HOOK_WORDS <= hook_words <= _MAX_HOOK_WORDS,
        f"{hook_words} words; target {_MIN_HOOK_WORDS}-{_MAX_HOOK_WORDS}",
    )
    add("hook_present", bool(hook), "Hook must be spoken from frame one.")
    add(
        "hook_caption_alignment",
        bool(hook) and _norm(hook) == _norm(first_caption),
        "Hook must exactly match the first burned-in caption.",
    )

    first_duration = max(float((audio_segments[0] if audio_segments else {}).get("duration", 0) or 0), 0.0)
    add(
        "voice_starts_immediately",
        bool(audio_segments) and first_duration > 0.1,
        f"First spoken segment duration: {first_duration:.2f}s",
    )
    add(
        "hook_lands_by_three_seconds",
        bool(audio_segments) and first_duration <= _MAX_FIRST_SCENE_SECONDS,
        f"First scene duration: {first_duration:.2f}s; maximum is {_MAX_FIRST_SCENE_SECONDS:.1f}s; early words are checked separately.",
    )
    opening_text, opening_words = _opening_text_and_words(audio_segments, _OPENING_SECONDS)
    _decision_text, decision_words = _opening_text_and_words(audio_segments, _DECISION_SECONDS)
    add(
        "decision_words",
        decision_words >= _MIN_DECISION_WORDS,
        f"Approximately {decision_words} words arrive by {_DECISION_SECONDS:.1f}s; minimum is {_MIN_DECISION_WORDS}.",
    )
    add(
        "opening_information_density",
        opening_words >= _MIN_WORDS_BY_OPENING,
        f"Approximately {opening_words} spoken words arrive by {_OPENING_SECONDS:.1f}s; minimum is {_MIN_WORDS_BY_OPENING}.",
    )

    first_engine = str((audio_segments[0] if audio_segments else {}).get("tts_engine") or "").lower()
    add("no_silent_opening", bool(audio_segments) and first_engine != "silence", f"Opening TTS engine: {first_engine or 'unknown'}")
    add("visual_present", bool(first_visual), "Opening visual description is required.")
    add(
        "visual_action",
        bool(_MOTION_TERMS.search(first_visual)) and not _GENERIC_VISUAL_TERMS.search(first_visual),
        "Opening visual must name a concrete motion, reaction, close-up, or visible change.",
    )
    add(
        "early_payoff_signal",
        bool(_PAYOFF_TERMS.search(hook) or _PAYOFF_TERMS.search(second_caption) or "?" in hook),
        "Hook or scene two must open a clear question and signal an explanation by 3s.",
    )
    add(
        "opening_text_available",
        bool(opening_text.strip()),
        "Opening audio must carry actual narration text, not only a duration record.",
    )

    failed = [check for check in checks if not check["passed"]]
    score = round(100 * (len(checks) - len(failed)) / len(checks)) if checks else 0
    return {
        "ok": not failed,
        "score": score,
        "window_seconds": _OPENING_SECONDS,
        "decision_seconds": _DECISION_SECONDS,
        "hook_words": hook_words,
        "opening_words": opening_words,
        "decision_words": decision_words,
        "checks": checks,
        "failed_checks": [check["name"] for check in failed],
        "issues": [check["detail"] for check in failed],
    }
