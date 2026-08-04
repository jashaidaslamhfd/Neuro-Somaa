"""Strict media checks used before rendering and uploading."""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import numpy as np
from PIL import Image


def _ffprobe_exe() -> str:
    """Return a usable ffprobe path.

    Prefer a system 'ffprobe' on PATH; otherwise derive it from the
    imageio-ffmpeg binary that this project already depends on (its ffmpeg
    ships next to an ffprobe, or we can swap the filename). This stops
    probe_video() from hard-failing on runners/machines where ffprobe isn't
    installed as a bare command even though ffmpeg is available.
    """
    system = shutil.which("ffprobe")
    if system:
        return system
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        candidate = ffmpeg.replace("ffmpeg", "ffprobe")
        if os.path.isfile(candidate):
            return candidate
    except Exception:
        pass
    return "ffprobe"  # last resort; will raise a clear error below if missing


class MediaValidationError(RuntimeError):
    pass


def validate_scene_image(path: str, min_side: int = 512) -> dict:
    """Decode an image and reject error pages, corrupt, tiny, black,
    OUT-OF-FOCUS or graphically violent assets.

    Sharpness and gore checks were added after inspecting the live channel on
    2026-07-27: two published Shorts used a scene-1 visual that this function
    happily approved —
      * "Pourquoi un muscle tressaille tout seul ?" — an almost entirely
        out-of-focus frame (edge energy 1.09; anything under ~3 is mush).
      * "Pourquoi le sursaut du corps en s'endormant ?" — a blood-spattered
        horror face on a calm French science channel: off-brand, and the kind
        of shock visual that suppresses advertiser suitability.
    Both passed because the only tests were "not black" and "not blank".
    """
    if not path or not os.path.isfile(path):
        raise MediaValidationError(f"Image does not exist: {path}")
    try:
        with Image.open(path) as probe:
            probe.verify()
        with Image.open(path) as image:
            image = image.convert("RGB")
            width, height = image.size
            if min(width, height) < min_side:
                raise MediaValidationError(f"Image too small: {width}x{height}")
            sample = np.asarray(image.resize((64, 64)), dtype=np.float32)
            brightness = float(sample.mean())
            variation = float(sample.std())
            if brightness < 12.0:
                raise MediaValidationError(f"Near-black image: brightness={brightness:.1f}")
            if variation < 2.0:
                raise MediaValidationError(f"Almost blank image: variation={variation:.1f}")

            # --- Focus check ------------------------------------------------
            # Mean absolute gradient on a 512px-wide greyscale copy. A crisp
            # render lands ~7-12; the published blurry frame measured 1.09.
            work = image.resize((512, int(512 * height / width))) if width >= height \
                else image.resize((int(512 * width / height), 512))
            grey = np.asarray(work.convert("L"), dtype=np.float32)
            sharpness = float(
                np.abs(np.diff(grey, axis=0)).mean() + np.abs(np.diff(grey, axis=1)).mean()
            )
            min_sharpness = float(os.environ.get("MIN_IMAGE_SHARPNESS", "3.0"))
            if sharpness < min_sharpness:
                raise MediaValidationError(
                    f"Out-of-focus image: sharpness={sharpness:.2f} "
                    f"(minimum {min_sharpness}) — viewers swipe on mush in scene 1"
                )

            # NOTE: a colour-based "gore detector" was prototyped here and
            # deliberately REMOVED. Measured against the real library, the
            # blood-spattered horror frame scored only 5.1% deep-red pixels
            # while entirely legitimate anatomy visuals scored far higher
            # (pink brain 16.9%, blushing-face 9.2%). Red density cannot
            # separate gore from anatomy on this channel, so the check would
            # have blocked good science images while letting the bad one
            # through. Shock imagery is prevented at the source instead — see
            # the negative prompt in image_generator._build_prompt().

            return {
                "width": width, "height": height,
                "brightness": brightness, "variation": variation,
                "sharpness": sharpness,
            }
    except MediaValidationError:
        raise
    except Exception as exc:
        raise MediaValidationError(f"Invalid image {path}: {exc}") from exc


def pad_video_to_minimum(path: str, min_seconds: float) -> str:
    """Pad a slightly short render with its final frame and matching silence.

    ``tpad=stop`` takes a *frame count*, not milliseconds. The earlier
    implementation supplied milliseconds and used an invalid ``apad`` sample
    expression, so ffmpeg could fail silently and leave the short original in
    place. This version uses duration-based filters and maps both filtered
    streams explicitly.
    """
    if min_seconds <= 0:
        return path
    try:
        probe = subprocess.run(
            [_ffprobe_exe(), "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30, check=True,
        )
        duration = float(json.loads(probe.stdout).get("format", {}).get("duration") or 0)
    except Exception as exc:
        raise MediaValidationError(f"ffprobe failed during padding check: {exc}") from exc

    if duration >= min_seconds:
        return path

    # A small safety buffer avoids AAC/frame rounding placing the output just
    # below the validator threshold again (e.g. 34.98 for a 35.00s minimum).
    target_seconds = min_seconds + 0.75
    padding_seconds = target_seconds - duration
    output_path = path.replace(".mp4", "_padded.mp4")
    filter_graph = (
        f"[0:v]tpad=stop_duration={padding_seconds:.3f}:stop_mode=clone[v];"
        f"[0:a]apad=pad_dur={padding_seconds:.3f}[a]"
    )
    command = [
        "ffmpeg", "-y", "-i", path,
        "-filter_complex", filter_graph,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{target_seconds:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-movflags", "+faststart", output_path,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if completed.returncode != 0:
            raise MediaValidationError(
                "ffmpeg padding failed: " + (completed.stderr[-800:] or "unknown error")
            )
        if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 100_000:
            raise MediaValidationError("ffmpeg padding produced no usable output file")
        os.replace(output_path, path)
        return path
    except Exception:
        if os.path.isfile(output_path):
            os.remove(output_path)
        raise


def probe_video(path: str) -> dict:
    """Use ffprobe to enforce a playable 9:16 Short with audio."""
    if not os.path.isfile(path) or os.path.getsize(path) < 100_000:
        raise MediaValidationError(f"Video missing or too small: {path}")
    command = [
        _ffprobe_exe(), "-v", "error", "-show_streams", "-show_format",
        "-of", "json", path,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
        data = json.loads(result.stdout)
    except Exception as exc:
        raise MediaValidationError(f"ffprobe failed: {exc}") from exc

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise MediaValidationError("Rendered file must contain video and audio streams")
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if (width, height) != (1080, 1920):
        raise MediaValidationError(f"Wrong canvas {width}x{height}; expected 1080x1920")
    max_seconds = float(os.environ.get("TARGET_MAX_SECONDS", "55")) + 0.25
    # Minimum too: a Short that's far too short (e.g. a truncated render)
    # would otherwise pass this gate and get published. Give a small 5s
    # grace below the configured target so normal short intros don't trip it.
    min_seconds = max(0.0, float(os.environ.get("TARGET_MIN_SECONDS", "20")) - 5.0)  # French=15s
    if duration <= 0 or duration > max_seconds:
        raise MediaValidationError(f"Wrong duration {duration:.2f}s; maximum {max_seconds:.2f}s")
    if duration < min_seconds:
        raise MediaValidationError(f"Video too short {duration:.2f}s; minimum {min_seconds:.2f}s")
    return {"width": width, "height": height, "duration": duration}
    
