from __future__ import annotations

import json
import os
import subprocess
import textwrap
import wave
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import Settings
from visual_providers import fetch_visual

WIDTH, HEIGHT = 1080, 1920
PALETTES = (("#101827", "#29476b", "#6ee7d8"), ("#180f2e", "#55318a", "#f5a3ff"), ("#102b2d", "#176b73", "#f7d774"), ("#2a1420", "#74324c", "#ffb36b"))


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _draw_scene_card(caption: str, index: int, title: str, path: Path, background: Path | None = None) -> None:
    first, second, accent = PALETTES[(index - 1) % len(PALETTES)]
    if background and background.exists():
        with Image.open(background) as source:
            image = ImageOps.fit(source.convert("RGB"), (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        # Keep the fetched visual sharp and visible.  The previous ``aa`` alpha
        # (67%) washed out most of the image and looked like a blur behind text.
        tint = Image.new("RGBA", image.size, first + "28")
        image = Image.alpha_composite(image.convert("RGBA"), tint).convert("RGB")
    else:
        image = Image.new("RGB", (WIDTH, HEIGHT), first)
    draw = ImageDraw.Draw(image)
    # Abstract science visual: layered circles, orbit lines, and a focal glow.
    for radius in range(760, 80, -80):
        alpha = max(12, 90 - radius // 12)
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.ellipse((WIDTH // 2 - radius, 380 - radius, WIDTH // 2 + radius, 380 + radius), outline=accent + f"{alpha:02x}", width=5)
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 80, 1010, 215), radius=38, fill=second)
    draw.text((105, 112), "NEURO-SOMAA · SCIENCE DU QUOTIDIEN", font=_font(30, True), fill="#ffffff")
    draw.text((88, 250), f"{index:02d}", font=_font(76, True), fill=accent)
    draw.text((210, 280), "LE DÉTAIL QUI CHANGE TOUT", font=_font(30, True), fill="#dbeafe")
    # Keep the on-screen French caption short, centered, and readable on mobile.
    wrapped = textwrap.fill(caption.strip(), width=18, break_long_words=False, break_on_hyphens=False)
    caption_size = 82
    caption_font = _font(caption_size, True)
    box = draw.multiline_textbbox((0, 0), wrapped, font=caption_font, spacing=18, align="center")
    while box[2] - box[0] > 850 and caption_size > 48:
        caption_size -= 2
        caption_font = _font(caption_size, True)
        box = draw.multiline_textbbox((0, 0), wrapped, font=caption_font, spacing=18, align="center")
    box_height = box[3] - box[1]
    top = 860 - box_height // 2
    # Use a translucent backing only for contrast; it must not hide the visual
    # underneath the caption.  The dark stroke keeps text readable without blur.
    draw.rounded_rectangle((70, top - 55, 1010, top + box_height + 65), radius=42, fill="#07111f70", outline=accent, width=5)
    draw.multiline_text((WIDTH // 2, top), wrapped, font=caption_font, fill="#ffffff", anchor="ma", spacing=18, align="center", stroke_width=3, stroke_fill="#07111f")
    draw.text((90, 1760), "À retenir : observez votre corps, puis vérifiez la source.", font=_font(29), fill="#dbeafe")
    draw.text((90, 1815), title[:68], font=_font(27, True), fill=accent)
    image.save(path, format="PNG", optimize=True)


def _tts_segment(text: str, path: Path, settings: Settings) -> float:
    if not settings.dry_run:
        mp3_path = path.with_suffix(".mp3")
        voice = os.getenv("EDGE_FR_VOICE", "fr-FR-HenriNeural")
        rate = os.getenv("EDGE_FR_RATE", "-5%")
        try:
            subprocess.run(["edge-tts", "--voice", voice, f"--rate={rate}", "--text", text, "--write-media", str(mp3_path)], check=True, capture_output=True)
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
    scene_dir = settings.output_dir / "scenes"
    segment_dir = settings.output_dir / "segments"
    for directory in (audio_dir, scene_dir, segment_dir):
        directory.mkdir(parents=True, exist_ok=True)
    segments: list[dict[str, Any]] = []
    for index, scene in enumerate(script["scenes"], start=1):
        narration = str(scene.get("narration") or scene.get("caption") or "").strip()
        caption = str(scene.get("caption") or narration).strip()
        audio_path = audio_dir / f"scene_{index:02d}.wav"
        image_path = scene_dir / f"scene_{index:02d}.png"
        segment_path = segment_dir / f"scene_{index:02d}.mp4"
        duration = _tts_segment(narration, audio_path, settings)
        source_path, source_provider = fetch_visual(caption, index, scene_dir, settings)
        _draw_scene_card(caption, index, str(script.get("title", "")), image_path, source_path)
        subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-i", str(audio_path), "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(segment_path)], check=True, capture_output=True)
        segments.append({"path": str(audio_path), "duration": duration, "text": narration, "caption": caption, "image_path": str(image_path), "segment_path": str(segment_path), "visual_provider": source_provider})
    total = sum(float(item["duration"]) for item in segments)
    if not settings.min_seconds <= total <= settings.max_seconds + 3.0:
        raise RuntimeError(f"Narration duration {total:.1f}s outside target tolerance {settings.min_seconds:g}-{settings.max_seconds:g}s")
    concat = settings.output_dir / "video_concat.txt"
    concat.write_text("\n".join(f"file '{Path(item['segment_path']).resolve()}'" for item in segments), encoding="utf-8")
    video = settings.output_dir / "neuro_somaa_fr.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(video)], check=True, capture_output=True)
    return video, segments


def validate_video(path: Path, settings: Settings) -> dict[str, Any]:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,codec_type:format=duration", "-of", "json", str(path)], check=True, capture_output=True, text=True)
    payload = json.loads(probe.stdout)
    stream = next(item for item in payload.get("streams", []) if item.get("width"))
    audio = next((item for item in payload.get("streams", []) if item.get("codec_type") == "audio"), None)
    duration = float(payload.get("format", {}).get("duration", 0))
    if (stream.get("width"), stream.get("height")) != (WIDTH, HEIGHT):
        raise RuntimeError("Rendered video must be 1080x1920")
    if not audio:
        raise RuntimeError("Rendered video must contain an audio stream")
    if duration <= 0 or duration > settings.max_seconds + 3.0:
        raise RuntimeError(f"Rendered video duration invalid: {duration:.2f}s")
    return {"width": stream["width"], "height": stream["height"], "duration": duration, "audio": True}
