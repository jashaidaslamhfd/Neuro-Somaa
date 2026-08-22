#!/usr/bin/env python3
"""Render a batch of French Shorts re-cuts without uploading them.

The manifest is intentionally explicit: each item supplies a complete script
and either six image/video assets or ``--generate-assets`` to use the existing
provider chain. The script renders, audits, scores thumbnails, writes SRT and
JSON evidence, and never calls the uploader.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from final_video_audit import run_final_publication_audit
from media_validator import probe_video
from seo_analytics import score_thumbnail
from shorts_enhancer import build_shorts_report, generate_srt
from strict_quality_gate import require_strict_gate
from video_editor import build_video, generate_thumbnail_variants
from voice_generator import generate_voice_segments

logger = logging.getLogger("render_recut_batch")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

REQUIRED_SCRIPT_FIELDS = ("title", "hook", "scenes")
MAX_ITEMS = 5
MAX_THUMBNAIL_VARIANTS = 4


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    path.mkdir(parents=True, exist_ok=True)
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _load_manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise ValueError("Manifest must contain a non-empty 'items' array")
    if len(items) > MAX_ITEMS:
        raise ValueError(f"Manifest is capped at {MAX_ITEMS} items per batch")
    return items


def _validate_item(item: dict, index: int) -> list[str]:
    errors: list[str] = []
    label = item.get("id") or f"item-{index}"
    script = item.get("script") or {}
    for field in REQUIRED_SCRIPT_FIELDS:
        if not script.get(field):
            errors.append(f"{label}: script.{field} is required")
    scenes = script.get("scenes") or []
    if len(scenes) != 6:
        errors.append(f"{label}: script.scenes must contain exactly 6 scenes, got {len(scenes)}")
    for scene_index, scene in enumerate(scenes, start=1):
        if not scene.get("visual"):
            errors.append(f"{label}: scene {scene_index} missing visual")
        if not scene.get("caption"):
            errors.append(f"{label}: scene {scene_index} missing caption")
    paths = item.get("image_paths") or []
    if paths and len(paths) != len(scenes):
        errors.append(f"{label}: image_paths must match scene count")
    if not item.get("experiment_id"):
        errors.append(f"{label}: experiment_id is required for attribution")
    return errors


def _resolve_assets(item: dict, output_dir: Path, generate_assets: bool) -> tuple[list[str], list[str], list[str]]:
    script = item["script"]
    scenes = [dict(scene, topic=script.get("topic", item.get("topic", ""))) for scene in script["scenes"]]
    supplied = [str(Path(path).expanduser().resolve()) for path in item.get("image_paths", [])]
    if supplied:
        missing = [path for path in supplied if not Path(path).is_file()]
        if missing:
            raise FileNotFoundError(f"Missing supplied assets: {missing}")
        media_types = ["video" if Path(path).suffix.lower() in {".mp4", ".mov", ".webm"} else "image" for path in supplied]
        return supplied, ["manifest"] * len(supplied), media_types
    if not generate_assets:
        raise ValueError("No image_paths supplied; rerun with --generate-assets to use provider fallbacks")

    from image_generator import generate_scene_image

    used_hashes: set[str] = set()
    used_fallbacks: set[str] = set()
    paths: list[str] = []
    sources: list[str] = []
    media_types: list[str] = []
    with _working_directory(output_dir):
        for index, scene in enumerate(scenes):
            generated = generate_scene_image(index, scene, used_hashes, used_fallbacks)
            paths.append(str((Path.cwd() / generated["path"]).resolve()))
            sources.append(generated.get("source", "unknown"))
            media_types.append(generated.get("media_type", "image"))
    return paths, sources, media_types


def _render_one(item: dict, batch_dir: Path, generate_assets: bool) -> dict:
    item_id = str(item["id"])
    item_dir = (batch_dir / item_id).resolve()
    script = dict(item["script"])
    script["topic"] = script.get("topic", item.get("topic", ""))
    script["experiment_id"] = item["experiment_id"]
    script["source_video_id"] = item.get("source_video_id")
    assets_dir = item_dir / "assets"
    image_paths, image_sources, media_types = _resolve_assets(item, assets_dir, generate_assets)

    with _working_directory(item_dir):
        audio_segments = generate_voice_segments(
            script["scenes"],
            voice=item.get("voice", os.environ.get("KOKORO_VOICE", "ff_siwis")),
            output_dir="output/segments",
            speed=float(item.get("voice_speed", 1.0)),
            topic=script.get("topic", ""),
        )
        shorts_report = build_shorts_report(script, audio_segments, script.get("tags", []))
        script["shorts_report"] = shorts_report
        require_strict_gate(
            shorts_report.get("first_three_seconds", {}).get("ok", False),
            shorts_report.get("first_three_seconds", {}),
            f"first-three-second opening ({item_id})",
        )

        srt_path = Path("output/captions.srt")
        srt_path.parent.mkdir(parents=True, exist_ok=True)
        generate_srt(script["scenes"], audio_segments, output_path=str(srt_path))

        final_video = Path("output/final_video.mp4")
        build_video(image_paths, audio_segments, script["scenes"], output_path=str(final_video), media_types=media_types)

        thumb_text = script.get("thumbnail_text") or script["title"]
        thumb_paths = generate_thumbnail_variants(
            image_paths[0],
            thumb_text,
            output_dir="output/thumbnail_variants",
            category=script.get("category", "Body"),
            count=min(int(item.get("thumbnail_variant_count", 4)), MAX_THUMBNAIL_VARIANTS),
        )
        scored = [(path, score_thumbnail(path, thumb_text)) for path in thumb_paths]
        thumb_path, thumb_score = max(scored, key=lambda pair: pair[1].get("overall_thumbnail_score", 0))
        script["thumbnail_score"] = thumb_score
        script["thumbnail_variants"] = [
            {"path": path, "score": score} for path, score in scored
        ]
        minimum_thumbnail = int(item.get("minimum_thumbnail_score", os.environ.get("MIN_THUMBNAIL_SCORE", "80")))
        require_strict_gate(
            thumb_score.get("overall_thumbnail_score", 0) >= minimum_thumbnail,
            {"selected": thumb_score, "minimum": minimum_thumbnail, "variants": script["thumbnail_variants"]},
            f"thumbnail quality ({item_id})",
        )

        audit_ok, audit_report = run_final_publication_audit(
            str(final_video), thumb_path, script, audio_segments
        )
        require_strict_gate(audit_ok, audit_report, f"final rendered asset ({item_id})")
        media_report = probe_video(str(final_video))

        evidence = {
            "id": item_id,
            "source_video_id": item.get("source_video_id"),
            "experiment_id": item["experiment_id"],
            "title": script["title"],
            "hook": script["hook"],
            "image_sources": image_sources,
            "audio_segments": audio_segments,
            "shorts_report": shorts_report,
            "thumbnail_score": thumb_score,
            "thumbnail_variants": script["thumbnail_variants"],
            "final_audit": audit_report,
            "media_report": media_report,
            "outputs": {
                "video": str(final_video.resolve()),
                "captions": str(srt_path.resolve()),
                "thumbnail": str(Path(thumb_path).resolve()),
            },
            "uploaded": False,
        }
        (item_dir / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="JSON manifest containing up to five complete re-cut scripts")
    parser.add_argument("--output-dir", type=Path, default=Path("output/recut_batch"))
    parser.add_argument("--generate-assets", action="store_true", help="Generate missing scene assets through existing providers")
    parser.add_argument("--dry-run", action="store_true", help="Validate the manifest only; do not call TTS, image, or video generation")
    args = parser.parse_args()

    try:
        items = _load_manifest(args.manifest)
        errors = [error for index, item in enumerate(items, start=1) for error in _validate_item(item, index)]
        if errors:
            for error in errors:
                logger.error(error)
            return 2
        if args.dry_run:
            logger.info("Manifest valid: %s re-cut items; no media or network calls made", len(items))
            return 0

        args.output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for item in items:
            logger.info("Rendering re-cut %s", item["id"])
            results.append(_render_one(item, args.output_dir, args.generate_assets))
        summary = {"count": len(results), "uploaded": False, "items": results}
        (args.output_dir / "batch_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Batch complete: %s rendered; uploads intentionally disabled", len(results))
        return 0
    except Exception:
        logger.exception("Batch render failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
