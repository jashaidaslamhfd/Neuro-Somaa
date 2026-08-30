"""Fast production preflight checks for the Shorts pipeline.

This command intentionally performs no paid generation and no upload. It catches
missing local capabilities and impossible configuration before the long render.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def _check(name: str, ok: bool, detail: str, required: bool = True) -> dict:
    return {"name": name, "ok": bool(ok), "required": required, "detail": detail}


def run() -> int:
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    checks: list[dict] = []
    for binary in ("ffmpeg", "ffprobe"):
        path = shutil.which(binary)
        checks.append(_check(binary, bool(path), path or "not found"))

    target_min = float(os.environ.get("TARGET_MIN_SECONDS", "20"))
    target_max = float(os.environ.get("TARGET_MAX_SECONDS", "24"))
    checks.append(_check("duration-window", 0 < target_min < target_max <= 60, f"{target_min:g}-{target_max:g}s"))

    providers = {
        "GROQ_API_KEY": bool(os.environ.get("GROQ_API_KEY")),
        "OPENROUTER_API_KEY": bool(os.environ.get("OPENROUTER_API_KEY")),
        "ALT_LLM_API_KEY": bool(os.environ.get("ALT_LLM_API_KEY")),
    }
    checks.append(_check("llm-provider", any(providers.values()), str(dict(providers))))

    youtube = all(os.environ.get(key) for key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REFRESH_TOKEN"))
    checks.append(_check("youtube-oauth", youtube or dry_run, "configured" if youtube else "missing OAuth variables", required=not dry_run))

    output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        writable = os.access(output_dir, os.W_OK)
    except OSError:
        writable = False
    checks.append(_check("output-directory", writable, str(output_dir)))

    schedule_enabled = os.environ.get("YT_SCHEDULE_PUBLISH", "true").lower() == "true"
    if schedule_enabled:
        checks.append(_check("scheduled-privacy", os.environ.get("YT_PRIVACY_STATUS", "private").lower() == "private", "scheduled uploads require private status"))

    dynamic_schedule = os.environ.get("USE_DYNAMIC_SCHEDULE", "false").lower()
    checks.append(_check("dynamic-schedule-flag", dynamic_schedule in {"true", "false"}, dynamic_schedule))
    local_fallback = os.environ.get("ALLOW_LOCAL_SCRIPT_FALLBACK", "true").lower() == "true"
    checks.append(_check("local-script-fallback", not local_fallback, "enabled: provenance will be recorded" if local_fallback else "disabled", required=False))

    failed = [item for item in checks if item["required"] and not item["ok"]]
    report = {"ok": not failed, "dry_run": dry_run, "checks": checks}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())


def testable_report() -> dict:
    """Small importable seam for offline tests and operator diagnostics."""
    return {"target_max_seconds": os.environ.get("TARGET_MAX_SECONDS", "24")}


def main() -> int:
    return run()
