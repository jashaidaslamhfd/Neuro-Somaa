from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from config import Settings
from growth import boost_description, ensure_seo_tags, is_allowed_growth_topic, is_weak_title
from media import validate_video
from youtube import upload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", default="output/neuro_somaa_fr.mp4")
    parser.add_argument("--title", required=True)
    args = parser.parse_args()

    title = " ".join(args.title.split()).strip()
    if not 18 <= len(title) <= 60 or "#" in title or is_weak_title(title):
        raise SystemExit("Refusing to publish: title must be a complete 18-60 character French curiosity title")
    if not is_allowed_growth_topic(title):
        raise SystemExit("Refusing to publish: title is outside the Neuro-Somaa brain/body/psychology niche")

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

    tags = ensure_seo_tags([], title)
    description = boost_description(
        f"{title} — un phénomène du cerveau, du corps ou du comportement expliqué simplement en français.",
        title,
        tags,
    )
    script = {
        "title": title,
        "description": description,
        "tags": tags,
    }
    result = upload(video, script, settings)
    print(result)


if __name__ == "__main__":
    main()


def test_placeholder() -> None:
    """Keep this module importable by the repository's test discovery."""
    return None
