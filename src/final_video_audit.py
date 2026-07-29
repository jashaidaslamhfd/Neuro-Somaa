"""Final pre-upload audit for rendered SKILLOR Shorts.

Earlier gates inspect the script, metadata, images and audio separately. This
module checks the exact artefacts that are about to be uploaded: rendered MP4,
thumbnail, final French metadata and generated audio segments. It is designed to
fail hard only on public-quality blockers and report softer CTR/retention risks
as warnings.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from french_quality_gate import validate_publication_quality
from media_validator import probe_video
from seo_analytics import score_thumbnail
from shorts_enhancer import build_shorts_report

logger = logging.getLogger(__name__)

MIN_THUMBNAIL_SCORE = int(os.environ.get("MIN_THUMBNAIL_SCORE", "45"))
MIN_AUDIO_PEAK = float(os.environ.get("MIN_AUDIO_PEAK", "0.015"))
MAX_AUDIO_PEAK = float(os.environ.get("MAX_AUDIO_PEAK", "0.99"))


def _audio_segment_health(audio_segments: list[dict[str, Any]]) -> tuple[list[str], list[str], dict]:
    issues: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {"segments": len(audio_segments), "peaks": []}
    if not audio_segments:
        return ["No audio segments were generated"], warnings, details

    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        warnings.append(f"Audio waveform inspection skipped: {exc}")
        return issues, warnings, details

    for index, segment in enumerate(audio_segments, start=1):
        path = segment.get("path")
        if not path or not Path(path).is_file():
            issues.append(f"Audio segment {index} is missing: {path}")
            continue
        try:
            samples, sample_rate = sf.read(path, dtype="float32", always_2d=False)
            if getattr(samples, "ndim", 1) > 1:
                samples = samples.mean(axis=1)
            peak = float(np.abs(samples).max()) if samples.size else 0.0
            rms = float((samples * samples).mean() ** 0.5) if samples.size else 0.0
            duration = float(samples.size / sample_rate) if sample_rate else 0.0
            details["peaks"].append(round(peak, 4))
            if duration < 0.25:
                issues.append(f"Audio segment {index} is too short ({duration:.2f}s)")
            if peak < MIN_AUDIO_PEAK:
                issues.append(f"Audio segment {index} is near-silent (peak={peak:.4f})")
            if peak > MAX_AUDIO_PEAK:
                warnings.append(f"Audio segment {index} may be clipped (peak={peak:.3f})")
            if rms < MIN_AUDIO_PEAK / 3:
                warnings.append(f"Audio segment {index} has very low RMS ({rms:.4f})")
        except Exception as exc:  # corrupt file / unreadable codec
            issues.append(f"Audio segment {index} unreadable: {exc}")
    return issues, warnings, details


def run_final_publication_audit(
    video_path: str,
    thumbnail_path: str,
    script_data: dict,
    audio_segments: list[dict],
) -> tuple[bool, dict]:
    """Return (approved, report) for the final rendered assets."""
    issues: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    try:
        details["video"] = probe_video(video_path)
    except Exception as exc:
        issues.append(f"Rendered video technical validation failed: {exc}")

    gate_ok, gate_report = validate_publication_quality(script_data)
    details["french_gate"] = gate_report
    if not gate_ok:
        issues.extend(f"French/publication gate: {item}" for item in gate_report.get("issues", []))

    audio_issues, audio_warnings, audio_details = _audio_segment_health(audio_segments)
    issues.extend(audio_issues)
    warnings.extend(audio_warnings)
    details["audio"] = audio_details

    try:
        thumb = score_thumbnail(thumbnail_path, script_data.get("title", ""))
        details["thumbnail"] = thumb
        score = thumb.get("overall_thumbnail_score")
        if isinstance(score, (int, float)) and score < MIN_THUMBNAIL_SCORE:
            warnings.append(f"Thumbnail score is low ({score}/{MIN_THUMBNAIL_SCORE})")
    except Exception as exc:
        warnings.append(f"Thumbnail scoring skipped: {exc}")

    try:
        shorts = build_shorts_report(script_data, audio_segments, script_data.get("tags", []))
        details["shorts_report"] = shorts
        pacing = shorts.get("caption_pacing", {})
        if pacing.get("all_readable") is False:
            issues.extend(f"Caption pacing: {item}" for item in pacing.get("issues", [])[:3])
        cliff = shorts.get("five_second_cliff", {})
        if not cliff.get("ok", True):
            warnings.extend(f"5s cliff: {item}" for item in cliff.get("issues", [])[:3])
    except Exception as exc:
        warnings.append(f"Shorts report in final audit skipped: {exc}")

    report = {
        "approved": not issues,
        "issues": issues,
        "warnings": warnings,
        "details": details,
    }
    if issues:
        logger.error("Final publication audit failed: %s", issues)
    elif warnings:
        logger.warning("Final publication audit passed with warnings: %s", warnings)
    else:
        logger.info("Final publication audit approved all rendered assets")
    return report["approved"], report
