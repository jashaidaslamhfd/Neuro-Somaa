"""Fast deterministic QA for the rendered Shorts MP4."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def probe(path: Path) -> dict:
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        text=True,
    )
    return json.loads(raw)


def _select_final_video() -> Path | None:
    output_dir = Path("output")
    # The renderer leaves per-scene MP4 intermediates beside the assembled
    # video. Selecting the newest file can therefore probe scene_5.mp4, which
    # intentionally has no audio stream, and falsely fail final QA. Prefer the
    # canonical assembled outputs and ignore scene intermediates entirely.
    for name in ("final_video.mp4", "dryrun_final.mp4"):
        candidate = output_dir / name
        if candidate.exists():
            return candidate
    candidates = sorted(
        (p for p in output_dir.glob("*.mp4") if not p.name.startswith("scene_")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def main() -> int:
    path = _select_final_video()
    if path is None:
        print("No assembled rendered MP4 found", file=sys.stderr)
        return 1
    report = probe(path)
    streams = report.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(report.get("format", {}).get("duration") or 0)
    width = int(video.get("width") or 0) if video else 0
    height = int(video.get("height") or 0) if video else 0
    checks = {
        "file_exists": path.exists() and path.stat().st_size > 100_000,
        "portrait": width > 0 and height > width,
        "shorts_ratio": width > 0 and height / width >= 1.7,
        "duration": 10 <= duration <= 60,
        "audio": audio is not None,
    }
    result = {"path": str(path), "bytes": path.stat().st_size, "width": width, "height": height, "duration": duration, "checks": checks, "ok": all(checks.values())}
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
