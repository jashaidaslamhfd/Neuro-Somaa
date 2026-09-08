from __future__ import annotations

import asyncio
import hashlib
import os
import wave
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment

from config import Settings

SAMPLE_RATE = 24000


@dataclass
class WordTiming:
    text: str
    start: float
    duration: float


def _synthetic_narration(text: str, wav_path: Path) -> tuple[float, list[WordTiming]]:
    """Silent placeholder audio for dry-run / offline development.

    Keeps the same deterministic duration estimate the pipeline has always
    used offline, but now also returns evenly-spaced word timings so the
    caller doesn't need a separate code path for dry-run vs. real synthesis.
    """
    duration = max(1.2, min(5.8, 0.38 * len(text.split())))
    frames = int(duration * SAMPLE_RATE)
    with wave.open(str(wav_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(b"\x00\x00" * frames)
    words = text.split() or [text]
    each = duration / len(words)
    timings = [WordTiming(word, i * each, each) for i, word in enumerate(words)]
    return duration, timings


async def _synthesize_edge_tts(text: str, mp3_path: Path, voice: str, rate: str) -> list[WordTiming]:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    boundaries: list[WordTiming] = []
    with open(mp3_path, "wb") as handle:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                handle.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                boundaries.append(WordTiming(
                    text=chunk.get("text", ""),
                    start=chunk["offset"] / 1e7,
                    duration=chunk["duration"] / 1e7,
                ))
    return boundaries


def synthesize_narration(text: str, wav_path: Path, settings: Settings) -> tuple[float, list[WordTiming]]:
    """Synthesize French narration and return (duration_seconds, word_timings).

    Word timings come straight from the TTS engine's own word-boundary
    events, not a naive equal split, so on-screen captions can be aligned
    to what is actually spoken instead of an approximation.
    """
    if settings.dry_run:
        return _synthetic_narration(text, wav_path)
    voice = os.getenv("EDGE_FR_VOICE", "fr-FR-HenriNeural")
    rate = os.getenv("EDGE_FR_RATE", "-5%")
    mp3_path = wav_path.with_suffix(".mp3")
    try:
        timings = asyncio.run(_synthesize_edge_tts(text, mp3_path, voice, rate))
        audio = AudioSegment.from_file(mp3_path, format="mp3")
        audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
        audio.export(wav_path, format="wav")
        duration = len(audio) / 1000.0
        if not timings:
            words = text.split() or [text]
            each = duration / len(words)
            timings = [WordTiming(word, i * each, each) for i, word in enumerate(words)]
        return duration, timings
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"French TTS failed for scene: {exc}") from exc
    finally:
        mp3_path.unlink(missing_ok=True)


def _music_catalog(settings: Settings) -> list[Path]:
    """Only ever return the repo's own, Content-ID-safe original tracks.

    Anything not matching the ``own_*`` naming convention is a third-party
    track with an unverified license (see assets/music/ATTRIBUTION.md) and
    must never be auto-selected here — that file documents a prior incident
    where unverified tracks were quarantined for exactly this reason.
    """
    if settings.music_source != "own":
        return []
    music_dir = Path(__file__).parents[1] / "assets" / "music"
    return sorted(music_dir.glob("own_*.wav"))


def select_music_track(settings: Settings, seed: str) -> Path | None:
    """Deterministically pick a background track for this video (same seed → same track)."""
    catalog = _music_catalog(settings)
    if not catalog:
        return None
    index = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % len(catalog)
    return catalog[index]


def mix_background_music(narration_path: Path, music_path: Path, start_offset: float, out_path: Path, gain_db: float) -> None:
    """Duck a slice of the background track under narration and export the mix.

    ``start_offset`` (seconds into the track) keeps the music timeline
    continuous across scenes instead of restarting the track at zero for
    every clip, which would sound jarring at scene boundaries.
    """
    narration = AudioSegment.from_file(narration_path, format="wav")
    music = AudioSegment.from_file(music_path).set_frame_rate(SAMPLE_RATE).set_channels(1)
    duration_ms = len(narration)
    if len(music) == 0 or duration_ms == 0:
        narration.export(out_path, format="wav")
        return
    loop_count = duration_ms // len(music) + 2
    looped = music * loop_count
    offset_ms = int(start_offset * 1000) % len(music)
    bed = looped[offset_ms:offset_ms + duration_ms]
    fade_ms = min(300, duration_ms // 4) or 1
    bed = bed.fade_in(fade_ms).fade_out(fade_ms).apply_gain(gain_db)
    mixed = narration.overlay(bed)
    mixed = mixed.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
    mixed.export(out_path, format="wav")
