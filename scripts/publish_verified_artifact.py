from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from config import Settings
from media import validate_video
from youtube import upload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", default="output/neuro_somaa_fr.mp4")
    parser.add_argument("--title", required=True)
    args = parser.parse_args()

    settings = Settings()
    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"Verified artifact video not found: {video}")
    try:
        technical = validate_video(video, settings)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Refusing to publish unverified media: {exc}") from exc
    print(f"Verified media: {technical['width']}x{technical['height']}, {technical['duration']:.2f}s")
    if settings.privacy_status != "public" or settings.schedule_publish:
        raise SystemExit("Refusing to publish: expected public immediate settings")
    if not settings.youtube_ready:
        raise SystemExit("YouTube OAuth secrets are incomplete")

    description = (
        "Une histoire vraie de perception, de santé et de cerveau. "
        "Neuro-Somaa explique les phénomènes scientifiques du quotidien en français."
    )
    script = {
        "title": args.title,
        "description": description,
        "tags": ["science", "cerveau", "santé", "psychologie", "neurosciences", "Neuro-Somaa"],
    }
    result = upload(video, script, settings)
    print(result)


if __name__ == "__main__":
    main()


def test_placeholder() -> None:
    """Keep this module importable by the repository's test discovery."""
    return None
