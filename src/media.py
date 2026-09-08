from __future__ import annotations

import hashlib
import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from audio import mix_background_music, select_music_track, synthesize_narration
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


def _draw_scene_card(caption: str, index: int, title: str, path: Path, background: Path | None = None, include_caption: bool = True) -> None:
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
    if include_caption:
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
        draw.multiline_text((WIDTH // 2, top), wrapped, font=caption_font, fill="#ffffff", anchor="ma", spacing=18, align="center", stroke_width=3, stroke_fill="#07111f")
    draw.text((90, 1760), "À retenir : observez votre corps, puis vérifiez la source.", font=_font(29), fill="#dbeafe")
    draw.text((90, 1815), title[:68], font=_font(27, True), fill=accent)
    image.save(path, format="PNG", optimize=True)


def _draw_caption_overlay(caption: str, index: int, title: str, path: Path, active_word: int | None = None) -> None:
    """Create a minimal Shorts overlay: one word, no box, border, logo, or footer."""
    _, _unused, accent = PALETTES[(index - 1) % len(PALETTES)]
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    words = caption.split() or [caption]
    caption_size = 112
    caption_font = _font(caption_size, True)
    while max(draw.textlength(word, font=caption_font) for word in words) > 900 and caption_size > 48:
        caption_size -= 2
        caption_font = _font(caption_size, True)
    word = words[active_word] if active_word is not None and active_word < len(words) else ""
    word_box = draw.textbbox((0, 0), word, font=caption_font, stroke_width=4)
    top = 860 - (word_box[3] - word_box[1]) // 2
    # Shorts-style captions: one centered word, no box or border.
    word_width = draw.textlength(word, font=caption_font)
    draw.text(((WIDTH - word_width) / 2, top), word, font=caption_font, fill=accent)
    overlay.save(path, format="PNG", optimize=True)


def render_video(script: dict[str, Any], settings: Settings) -> tuple[Path, list[dict[str, Any]]]:
    settings.ensure_dirs()
    audio_dir = settings.output_dir / "audio"
    scene_dir = settings.output_dir / "scenes"
    segment_dir = settings.output_dir / "segments"
    for directory in (audio_dir, scene_dir, segment_dir):
        directory.mkdir(parents=True, exist_ok=True)
    segments: list[dict[str, Any]] = []
    used_clip_hashes: set[str] = set()
    music_path = select_music_track(settings, seed=str(script.get("title", "video"))) if settings.background_music else None
    elapsed = 0.0
    for index, scene in enumerate(script["scenes"], start=1):
        narration = str(scene.get("narration") or scene.get("caption") or "").strip()
        caption = str(scene.get("caption") or narration).strip()
        audio_path = audio_dir / f"scene_{index:02d}.wav"
        image_path = scene_dir / f"scene_{index:02d}.png"
        segment_path = segment_dir / f"scene_{index:02d}.mp4"
        duration, word_timings = synthesize_narration(narration, audio_path, settings)
        mixed_path = audio_path
        if music_path is not None:
            mixed_path = audio_dir / f"scene_{index:02d}_mixed.wav"
            mix_background_music(audio_path, music_path, elapsed, mixed_path, settings.music_gain_db)
        elapsed += duration
        source_path, source_provider = fetch_visual(caption, index, scene_dir, settings)
        is_clip = source_path and source_path.suffix.lower() in {".mp4", ".mov", ".webm"}
        if not is_clip:
            raise RuntimeError(f"No moving stock clip available for scene {index}; refusing still-image fallback")
        clip_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if clip_hash in used_clip_hashes:
            raise RuntimeError(f"Duplicate moving clip detected in scene {index}; refusing render")
        used_clip_hashes.add(clip_hash)
        words = caption.split() or [caption]
        overlay_paths = []
        for word_index in range(len(words)):
            overlay_path = scene_dir / f"overlay_{index:02d}_{word_index:03d}.png"
            _draw_caption_overlay(caption, index, str(script.get("title", "")), overlay_path, word_index)
            overlay_paths.append(overlay_path)
        # Caption timing: use the TTS engine's own per-word timestamps when the
        # on-screen caption is the same text as what's spoken (the common
        # case), so captions land exactly on the spoken word instead of an
        # approximation. Falls back to an even split when they diverge (e.g.
        # a punchier hook caption over a longer narration line).
        if len(word_timings) == len(words):
            word_durations = [max(0.08, wt.duration) for wt in word_timings]
        else:
            word_durations = [duration / len(overlay_paths)] * len(overlay_paths)
        overlay_inputs = []
        overlay_labels = []
        for overlay_index, (overlay_path, word_dur) in enumerate(zip(overlay_paths, word_durations, strict=True), start=1):
            overlay_inputs.extend(["-loop", "1", "-t", f"{word_dur:.3f}", "-i", str(overlay_path)])
            overlay_labels.append(f"[{overlay_index}:v]")
        concat_filter = "".join(overlay_labels) + f"concat=n={len(overlay_paths)}:v=1:a=0[ov]"
        filter_graph = f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[base];{concat_filter};[base][ov]overlay=0:0:format=auto[v]"
        source_input = ["-stream_loop", "-1", "-i", str(source_path)] if is_clip else ["-loop", "1", "-i", str(image_path)]
        audio_index = len(overlay_paths) + 1
        command = ["ffmpeg", "-y", *source_input, *overlay_inputs, "-i", str(mixed_path), "-filter_complex", filter_graph, "-map", "[v]", "-map", f"{audio_index}:a", "-t", f"{duration:.3f}", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(segment_path)]
        subprocess.run(command, check=True, capture_output=True)
        segments.append({"path": str(mixed_path), "duration": duration, "text": narration, "caption": caption, "image_path": str(image_path), "segment_path": str(segment_path), "visual_provider": source_provider, "clip_hash": clip_hash, "music_track": music_path.name if music_path else None})
    total = sum(float(item["duration"]) for item in segments)
    if not settings.min_seconds <= total <= settings.max_seconds + 3.0:
        raise RuntimeError(f"Narration duration {total:.1f}s outside target tolerance {settings.min_seconds:g}-{settings.max_seconds:g}s")
    concat = settings.output_dir / "video_concat.txt"
    concat.write_text("\n".join(f"file '{Path(item['segment_path']).resolve()}'" for item in segments), encoding="utf-8")
    video = settings.output_dir / "neuro_somaa_fr.mp4"
    # Re-encode the concat: provider clips can carry different frame rates and
    # timebases, which makes stream-copy concat report wildly inflated duration.
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-t", f"{total:.3f}", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(video)], check=True, capture_output=True)
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
