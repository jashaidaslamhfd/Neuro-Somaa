from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_shared_thumbnail_geometry_is_inside_vertical_canvas():
    from safe_zones import thumbnail_action_safe

    left, top, right, bottom = thumbnail_action_safe(1080, 1920)
    assert 0 < left < right < 1080
    assert 0 < top < bottom < 1920
    assert right <= int(1080 * 0.88)
    assert bottom <= int(1920 * 0.80)


def test_thumbnail_variants_are_distinct_and_scoreable(tmp_path):
    from PIL import Image, ImageDraw

    from seo_analytics import score_thumbnail
    from video_editor import generate_thumbnail_variants

    source = tmp_path / "source.jpg"
    image = Image.new("RGB", (720, 1280), (20, 45, 70))
    draw = ImageDraw.Draw(image)
    draw.ellipse((120, 220, 600, 700), fill=(220, 90, 70))
    image.save(source)

    paths = generate_thumbnail_variants(
        str(source),
        "TEMPS RALENTI ?",
        output_dir=str(tmp_path / "variants"),
        category="Brain",
        count=4,
    )
    assert len(paths) == 4
    digests = {hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}
    assert len(digests) == 4

    scores = [score_thumbnail(path, "TEMPS RALENTI ?") for path in paths]
    assert all(score["overall_thumbnail_score"] >= 0 for score in scores)
    assert all("mobile_readability_score" in score for score in scores)
    assert all("score_geometry" in score for score in scores)


def test_thumbnail_scorer_does_not_measure_only_bottom_strip(tmp_path):
    from PIL import Image, ImageDraw

    from seo_analytics import score_thumbnail

    path = tmp_path / "thumb.jpg"
    image = Image.new("RGB", (1080, 1920), (8, 18, 35))
    draw = ImageDraw.Draw(image)
    # Put the high-contrast content in the real headline band, not at the
    # bottom 220 pixels that the former scorer incorrectly inspected.
    draw.rectangle((60, 1040, 900, 1400), fill=(245, 220, 40))
    image.save(path)

    score = score_thumbnail(str(path), "TEMPS RALENTI ?")
    assert score["score_geometry"]["text_band"] == [1017, 1459]
    assert score["contrast_score"] > 0


def test_main_marks_missed_slots_as_process_failure():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    missed_block = source[source.index('if result.get("missed")') : source.index("except KeyboardInterrupt")]
    assert "sys.exit(2)" in missed_block
    assert "sys.exit(0)" not in missed_block


def test_thumbnail_variant_count_is_bounded():
    source = inspect.getsource(__import__("video_editor").generate_thumbnail_variants)
    assert "min(int(count), 4)" in source


def test_upload_without_youtube_id_is_blocked_before_history_save():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert "uploader returned no youtube_video_id" in source
    assert "history must not record this run as published" in source


def test_thumbnail_diagnostics_are_persisted():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert '"thumbnail_score": script_data.get("thumbnail_score")' in source
    assert '"thumbnail_variants": script_data.get("thumbnail_variants", [])' in source
