"""Write a compact, secret-safe manifest for each production run."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atomic_io import write_json_atomic


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _files(root: str) -> list[dict]:
    base = Path(root)
    if not base.exists():
        return []
    items = []
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.stat().st_size < 512 * 1024 * 1024:
            items.append({"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)})
    return items


def build_manifest() -> dict:
    output = Path(os.environ.get("OUTPUT_DIR", "output"))
    data = Path(os.environ.get("DATA_DIR", "data"))
    safe_env = {
        key: os.environ.get(key, "")
        for key in (
            "TARGET_MIN_SECONDS", "TARGET_MAX_SECONDS", "TTS_ENGINE", "EDGE_FR_VOICE",
            "GROQ_MODEL", "GROQ_MODEL_FALLBACK", "ALT_LLM_MODEL", "CONTENT_SERIES",
            "THUMBNAIL_VARIANT_COUNT", "MIN_THUMBNAIL_SCORE", "MIN_RETENTION",
            "DRY_RUN", "YT_PRIVACY_STATUS", "YT_SCHEDULE_PUBLISH", "PUBLISH_TIMEZONE",
            "ALLOW_LOCAL_SCRIPT_FALLBACK", "USE_DYNAMIC_SCHEDULE",
        )
    }
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "github": {key.lower(): os.environ.get(key, "") for key in ("GITHUB_RUN_ID", "GITHUB_RUN_NUMBER", "GITHUB_WORKFLOW", "GITHUB_EVENT_NAME")},
        "config": safe_env,
        "outputs": _files(str(output)),
        "data_files": _files(str(data)),
        "failure_diagnostic_present": (data / "pipeline_last_failure.json").exists(),
        "upload_state_present": (data / "upload_state.json").exists(),
    }


def main() -> int:
    destination = Path(os.environ.get("RUN_MANIFEST_PATH", "data/run_manifest.json"))
    write_json_atomic(destination, build_manifest())
    print(f"Wrote run manifest: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
