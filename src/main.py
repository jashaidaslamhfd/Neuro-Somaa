from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from datetime import datetime, timezone

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc  # noqa: UP017

from agent_brain import AgentBrain
from config import SETTINGS
from content import generate_script, load_topic, score_hook, score_script_quality
from media import render_video, validate_video
from meta import is_meta_configured, upload_to_facebook_reels
from thumbnails import build_thumbnail
from youtube import upload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("neuro_somaa")


def _fingerprint(script: dict) -> str:
    text = " ".join([str(script.get("title", ""))] + [str(s.get("caption", "")) for s in script.get("scenes", [])])
    return hashlib.sha256(re.sub(r"[^a-zà-ÿ0-9 ]+", "", text.lower()).encode()).hexdigest()


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


def _clip_history() -> list[dict]:
    path = SETTINGS.data_dir / "clip_history.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _checkpoint_path(fingerprint: str):
    return SETTINGS.data_dir / "upload_checkpoints" / f"{fingerprint}.json"


def _persist_state() -> None:
    """Persist state durably; never claim success when git synchronization failed."""
    paths = ["data/video_history.json", "data/clip_history.json", "data/queue_index_fr.json", "data/search_demand_queue_fr.json", "data/agent_memory.json", "data/agent_log.json", "data/upload_checkpoints"]
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", *paths], check=False)
    committed = subprocess.run(["git", "commit", "-m", "chore: persist Neuro-Somaa duplicate state"], capture_output=True, text=True, check=False)
    if committed.returncode != 0 and "nothing to commit" not in committed.stdout + committed.stderr:
        raise RuntimeError(f"State checkpoint commit failed: {committed.stderr.strip()}")
    if committed.returncode == 0:
        pulled = subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True, text=True, check=False)
        if pulled.returncode != 0:
            raise RuntimeError(f"State checkpoint rebase failed: {pulled.stderr.strip()}")
        pushed = subprocess.run(["git", "push", "origin", "HEAD:main"], capture_output=True, text=True, check=False)
        if pushed.returncode != 0:
            raise RuntimeError(f"State checkpoint push failed: {pushed.stderr.strip()}")


def run() -> dict:
    errors = SETTINGS.validate()
    if errors:
        raise RuntimeError("Configuration invalid: " + "; ".join(errors))
    SETTINGS.ensure_dirs()
    # Autonomous AI Agent Sensory & Reasoning Core
    agent = AgentBrain(SETTINGS.data_dir)
    sensory = agent.sense_youtube_performance()
    logger.info("Agent Sensory Feedback Status: %s", sensory.get("sync_status"))
    
    topic = load_topic(SETTINGS)
    plan = agent.reason_and_strategize(topic)
    logger.info("Agent Strategy Plan: topic='%s', tempo=%s, keywords=%s", topic, plan.get("chosen_tempo"), plan.get("detected_keywords"))
    
    script = generate_script(topic, SETTINGS)
    if not script.get("title") or len(script.get("scenes", [])) < 4:
        raise RuntimeError("Generated script is incomplete")
    hook_score = score_hook(str(script["title"]), str(script["scenes"][0].get("caption", "")))
    if hook_score < SETTINGS.min_hook_score:
        raise RuntimeError(f"Script rejected: hook score {hook_score} below MIN_HOOK_SCORE={SETTINGS.min_hook_score}")
    quality_score = score_script_quality(script["scenes"])
    if quality_score < SETTINGS.quality_approval_threshold:
        raise RuntimeError(f"Script rejected: quality score {quality_score} below QUALITY_APPROVAL_THRESHOLD={SETTINGS.quality_approval_threshold}")
    history_path = SETTINGS.data_dir / "video_history.json"
    try:
        history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
    except (OSError, json.JSONDecodeError):
        history = []
    current_fp = _fingerprint(script)
    if any(isinstance(row, dict) and row.get("fingerprint") == current_fp for row in history):
        raise RuntimeError("Duplicate French script rejected before rendering")
    checkpoint = _checkpoint_path(current_fp)
    if checkpoint.exists():
        try:
            previous = json.loads(checkpoint.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Upload checkpoint is unreadable: {checkpoint}") from exc
        if previous.get("status") == "uploaded" and previous.get("youtube_video_id"):
            logger.warning("Resuming previously uploaded fingerprint %s; skipping duplicate upload.", current_fp)
            return previous
    clip_history = _clip_history()
    historical_clip_hashes = {str(row.get("clip_hash")) for row in clip_history if isinstance(row, dict)}
    video_path, segments = render_video(script, SETTINGS, historical_clip_hashes=historical_clip_hashes)
    technical = validate_video(video_path, SETTINGS)
    thumbnail_path = build_thumbnail(script, SETTINGS)
    result = {
        "created_at": datetime.now(UTC).isoformat(),
        "topic": topic,
        "title": script["title"],
        "duration": technical["duration"],
        "hook_score": hook_score,
        "quality_score": quality_score,
        "video_path": str(video_path),
        "audio_segments": len(segments),
        "clip_hashes": [item.get("clip_hash") for item in segments],
        "visual_providers": [item.get("visual_provider") for item in segments],
        "thumbnail_path": str(thumbnail_path),
        "fingerprint": current_fp,
    }
    upload_result = upload(video_path, script, SETTINGS)
    result.update(upload_result)
    if result.get("status") == "uploaded":
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Multi-Platform Distribution: Meta (Facebook Page Reels)
    if not SETTINGS.dry_run and not SETTINGS.render_only and is_meta_configured():
        logger.info("Publishing cross-post to Facebook Page Reels...")
        meta_result = upload_to_facebook_reels(
            video_path=video_path,
            title=script["title"],
            description=script.get("description", ""),
        )
        result.update(meta_result)
    else:
        result["facebook_success"] = False
        result["facebook_note"] = "Dry run, render only, or Meta credentials not configured"
    # Agent Reflection & Episodic Memory Update
    agent.reflect_and_learn(result, plan)
    
    if not SETTINGS.dry_run and not SETTINGS.render_only and result.get("status") == "uploaded":
        _write_history(result)
        clip_history.extend({"clip_hash": item.get("clip_hash"), "title": result["title"], "created_at": result["created_at"]} for item in segments)
        (SETTINGS.data_dir / "clip_history.json").write_text(json.dumps(clip_history[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
        _persist_state()
        logger.info("Uploaded video state persisted.")

    # Clean intermediate render artifacts to conserve disk in CI runner
    for sub_dir in ("scenes", "segments"):
        target_dir = SETTINGS.output_dir / sub_dir
        if target_dir.exists():
            import shutil
            shutil.rmtree(target_dir, ignore_errors=True)
    if SETTINGS.dry_run or SETTINGS.render_only:
        logger.info("Dry-run/render-only complete; skipping history persistence.")
    logger.info("Pipeline complete: %s", result.get("url", result.get("status")))
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
