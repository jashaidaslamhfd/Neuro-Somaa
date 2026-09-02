from __future__ import annotations

import json
import os
import subprocess
import wave
from pathlib import Path
from typing import Any

from config import Settings


def _tts_segment(text: str, path: Path, settings: Settings) -> float:
    if not settings.dry_run:
        mp3_path = path.with_suffix(".mp3")
        voice = os.getenv("EDGE_FR_VOICE", "fr-FR-HenriNeural")
        rate = os.getenv("EDGE_FR_RATE", "-5%")
        try:
            subprocess.run(["edge-tts", "--voice", voice, "--rate", rate, "--text", text, "--write-media", str(mp3_path)], check=True, capture_output=True)
            subprocess.run(["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "24000", "-ac", "1", str(path)], check=True, capture_output=True)
            mp3_path.unlink(missing_ok=True)
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True)
            return float(probe.stdout.strip())
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            raise RuntimeError(f"French TTS failed for scene: {exc}") from exc
    duration = max(1.2, min(5.8, 0.38 * len(text.split())))
    rate_hz = 24000
    frames = int(duration * rate_hz)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate_hz)
        out.writeframes(b"\x00\x00" * frames)
    return duration


def render_video(script: dict[str, Any], settings: Settings) -> tuple[Path, list[dict[str, Any]]]:
    settings.ensure_dirs()
    audio_dir = settings.output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    segments: list[dict[str, Any]] = []
    for index, scene in enumerate(script["scenes"], start=1):
        narration = str(scene.get("narration") or scene.get("caption") or "").strip()
        path = audio_dir / f"scene_{index:02d}.wav"
        duration = _tts_segment(narration, path, settings)
        segments.append({"path": str(path), "duration": duration, "text": narration})
    total = sum(item["duration"] for item in segments)
    if not settings.min_seconds <= total <= settings.max_seconds + 3.0:
        raise RuntimeError(f"Narration duration {total:.1f}s outside target tolerance {settings.min_seconds:g}-{settings.max_seconds:g}s")
    concat = settings.output_dir / "audio_concat.txt"
    concat.write_text("\n".join(f"file '{Path(item['path']).resolve()}'" for item in segments), encoding="utf-8")
    audio = settings.output_dir / "narration.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(audio)], check=True, capture_output=True)
    video = settings.output_dir / "neuro_somaa_fr.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x101827:s=1080x1920:r=30", "-i", str(audio), "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video)], check=True, capture_output=True)
    return video, segments


def validate_video(path: Path, settings: Settings) -> dict[str, Any]:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path)], check=True, capture_output=True, text=True)
    payload = json.loads(probe.stdout)
    stream = next(item for item in payload.get("streams", []) if item.get("width"))
    duration = float(payload.get("format", {}).get("duration", 0))
    if (stream.get("width"), stream.get("height")) != (1080, 1920):
        raise RuntimeError("Rendered video must be 1080x1920")
    if duration <= 0 or duration > settings.max_seconds + 3.0:
        raise RuntimeError(f"Rendered video duration invalid: {duration:.2f}s")
    return {"width": stream["width"], "height": stream["height"], "duration": duration}
