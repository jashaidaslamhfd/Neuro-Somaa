from __future__ import annotations

import json
import shutil
import sys

sys.path.insert(0, "src")
from config import SETTINGS


def main() -> int:
    checks = {
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "configuration": SETTINGS.validate() == [],
        "output_directory": True,
    }
    SETTINGS.ensure_dirs()
    report = {"ok": all(checks.values()), "checks": checks, "errors": SETTINGS.validate()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
