from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from config import SETTINGS
from content import generate_script, load_topic
from media import render_video, validate_video
from thumbnails import build_thumbnail
from youtube import upload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("neuro_somaa")


def _write_history(result: dict) -> None:
    path = SETTINGS.data_dir / "video_history.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(rows, list):
            rows = []
    except (OSError, json.JSONDecodeError):
        rows = []
    rows.append(result)
    path.write_text(json.dumps(rows[-200:], ensure_ascii=False, indent=2), encoding="utf-8")


def run() -> dict:
    errors = SETTINGS.validate()
    if errors:
        raise RuntimeError("Configuration invalid: " + "; ".join(errors))
    SETTINGS.ensure_dirs()
    topic = load_topic(SETTINGS)
    logger.info("French topic selected: %s", topic)
    script = generate_script(topic, SETTINGS)
    if not script.get("title") or len(script.get("scenes", [])) < 4:
        raise RuntimeError("Generated script is incomplete")
    video_path, segments = render_video(script, SETTINGS)
    technical = validate_video(video_path, SETTINGS)
    thumbnail_path = build_thumbnail(script, SETTINGS)
    result = {
        "created_at": datetime.now(UTC).isoformat(),
        "topic": topic,
        "title": script["title"],
        "duration": technical["duration"],
        "video_path": str(video_path),
        "audio_segments": len(segments),
        "thumbnail_path": str(thumbnail_path),
    }
    upload_result = upload(video_path, script, SETTINGS)
    result.update(upload_result)
    _write_history(result)
    logger.info("Pipeline complete: %s", result.get("url", result.get("status")))
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
