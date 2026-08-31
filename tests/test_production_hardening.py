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


def test_missed_slots_write_a_durable_failure_diagnostic():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    missed_block = source[source.index('if result.get("missed")') : source.index("except KeyboardInterrupt")]
    assert '"data/pipeline_last_failure.json"' in missed_block
    assert '"failure_kind": "slot_missed_after_guard_retries"' in missed_block


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



def test_first_three_seconds_gate_accepts_immediate_french_opening():
    from retention_gate import validate_first_three_seconds

    script = {
        "hook": "Ton cerveau ralentit le temps en danger ?",
        "scenes": [
            {
                "visual": "Gros plan sur un visage, les yeux s'ouvrent brusquement",
                "caption": "Ton cerveau ralentit le temps en danger ?",
            },
            {"visual": "Neurones en flash, le signal accélère", "caption": "C'est une réponse de survie."},
        ],
    }
    segments = [
        {"text": script["hook"], "duration": 2.0, "tts_engine": "edge_tts"},
        {"text": "C'est une réponse de survie.", "duration": 2.0, "tts_engine": "edge_tts"},
    ]

    report = validate_first_three_seconds(script, segments)

    assert report["ok"]
    assert report["failed_checks"] == []
    assert report["decision_words"] >= 4
    assert report["opening_words"] >= 6


def test_first_three_seconds_gate_rejects_silent_generic_opening():
    from retention_gate import validate_first_three_seconds

    script = {
        "hook": "Vous avez déjà ressenti cela ?",
        "scenes": [
            {"visual": "Fond abstrait bleu", "caption": "Vous avez déjà ressenti cela ?"},
            {"visual": "Image fixe", "caption": "La réponse arrive ensuite."},
        ],
    }
    segments = [
        {"text": script["hook"], "duration": 4.5, "tts_engine": "silence"},
        {"text": "La réponse arrive ensuite.", "duration": 2.0, "tts_engine": "edge_tts"},
    ]

    report = validate_first_three_seconds(script, segments)

    assert not report["ok"]
    assert "no_silent_opening" in report["failed_checks"]
    assert "visual_action" in report["failed_checks"]
    assert "decision_words" in report["failed_checks"]


def test_atomic_json_writer_replaces_complete_documents(tmp_path):
    import json

    from atomic_io import write_json_atomic

    destination = tmp_path / "state" / "run.json"
    write_json_atomic(destination, {"version": 1, "status": "old"})
    write_json_atomic(destination, {"version": 2, "status": "new"})
    assert json.loads(destination.read_text(encoding="utf-8")) == {"version": 2, "status": "new"}
    assert not list(destination.parent.glob("*.tmp"))


def test_pipeline_persists_script_provider_provenance():
    source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert '"script_provider": script_data.get("provider", "unknown")' in source
    assert '"used_local_script_fallback": script_data.get("provider") == "local_fallback"' in source


def test_run_manifest_and_failure_diagnostics_use_atomic_json_writer():
    manifest = (ROOT / "scripts" / "run_manifest.py").read_text(encoding="utf-8")
    pipeline = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert "write_json_atomic(destination, build_manifest())" in manifest
    assert "write_json_atomic(data_log, payload, default=str)" in pipeline
    assert '"data/slot_skipped.json"' in pipeline


def test_deterministic_fallback_normalizes_repeated_pourquoi_prefix(monkeypatch):
    import script_generator

    monkeypatch.setenv("FORCE_LOCAL_FALLBACK", "true")
    script = script_generator.generate_script("Pourquoi. Pourquoi des fourmillements apparaissent", max_retries=1)
    assert "Pourquoi. Pourquoi" not in script["hook"]
    assert script["scenes"][0]["caption"] == script["hook"]
    assert 7 <= len(script["scenes"][0]["caption"].split()) <= 9


def test_deterministic_fallback_handles_prefix_only_topic(monkeypatch):
    import script_generator

    monkeypatch.setenv("FORCE_LOCAL_FALLBACK", "true")
    script = script_generator.generate_script("Pourquoi.", max_retries=1)
    assert script["hook"].startswith("Pourquoi un mécanisme surprenant")
    assert "Pourquoi. Pourquoi" not in script["hook"]


def test_visual_qa_prefers_assembled_video_over_scene_intermediate(tmp_path, monkeypatch):
    import importlib.util

    module_path = ROOT / "scripts" / "visual_qa.py"
    spec = importlib.util.spec_from_file_location("visual_qa", module_path)
    visual_qa = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(visual_qa)

    output = tmp_path / "output"
    output.mkdir()
    final_video = output / "final_video.mp4"
    scene_video = output / "scene_5.mp4"
    final_video.write_bytes(b"final")
    scene_video.write_bytes(b"scene")
    monkeypatch.chdir(tmp_path)
    assert visual_qa._select_final_video().resolve() == final_video.resolve()
