from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from config import Settings
from visual_providers import fetch_visual


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
