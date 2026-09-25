from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from config import Settings
from visual_providers import _procedural_motion_clip, fetch_visual


def test_fetch_visual_dry_run_produces_valid_moving_clip(tmp_path):
    settings = Settings()
    settings.dry_run = True

    scene_path, provider = fetch_visual("ATTENDS—ton corps fait ça.", 1, tmp_path, settings)
    assert scene_path is not None
    assert scene_path.exists()
    assert scene_path.suffix == ".mp4"
    assert provider == "procedural_motion"
    assert scene_path.stat().st_size > 5000


def test_procedural_clips_have_distinct_hashes_per_scene(tmp_path):
    import hashlib

    settings = Settings()
    settings.dry_run = True

    p1, _ = fetch_visual("Scène un", 1, tmp_path, settings)
    p2, _ = fetch_visual("Scène deux", 2, tmp_path, settings)

    assert p1 is not None and p2 is not None
    h1 = hashlib.sha256(p1.read_bytes()).hexdigest()
    h2 = hashlib.sha256(p2.read_bytes()).hexdigest()
    assert h1 != h2


def test_image_path_is_promoted_to_mp4_without_overwriting_the_image(tmp_path):
    image_path = tmp_path / "provider_image.jpg"
    output_path = _procedural_motion_clip(8, image_path, caption="cerveau mémoire")

    assert output_path == tmp_path / "provider_image.mp4"
    assert output_path.exists()
    assert output_path.stat().st_size > 5000
    assert not image_path.exists()


def test_duplicate_image_promotion_is_treated_as_clip(tmp_path):
    import hashlib
    dummy_img = tmp_path / "scene_04_ai.jpg"
    dummy_img.write_bytes(b"fake-image-bytes")
    img_hash = hashlib.sha256(dummy_img.read_bytes()).hexdigest()
    used_hashes = {img_hash}

    source_path = _procedural_motion_clip(4, dummy_img, caption="test:fallback:4")
    assert source_path.suffix == ".mp4"
    assert source_path.exists()

    is_clip = bool(source_path and source_path.suffix.lower() in {".mp4", ".mov", ".webm"})
    is_image = bool(source_path and source_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    assert is_clip is True
    assert is_image is False
