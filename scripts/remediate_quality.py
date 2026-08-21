#!/usr/bin/env python3
"""Safely remediate Ruff findings for Neuro-Somaa.

The command is intentionally explicit about unsafe fixes.  It never hides
remaining violations by changing the Ruff rule set, and it writes a JSON report
that can be consumed by CI or a maintainer.

Examples:
    python scripts/remediate_quality.py --check
    python scripts/remediate_quality.py
    python scripts/remediate_quality.py --unsafe-fixes
    python scripts/remediate_quality.py --paths src scripts tests
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = ("src", "scripts", "tests")
DEFAULT_REPORT = ROOT / "quality_remediation_report.json"


@dataclass(frozen=True)
class RuffFinding:
    filename: str
    row: int
    column: int
    code: str
    message: str
    fixable: bool


def run(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a command from the repository root with deterministic text output."""
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def ruff_findings(paths: list[str]) -> list[RuffFinding]:
    """Return Ruff findings without making changes."""
    result = run(["ruff", "check", *paths, "--output-format", "json"])
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "ruff check failed to execute")
    if not result.stdout.strip():
        return []
    try:
        payload: list[dict[str, Any]] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse Ruff JSON output: {exc}") from exc
    return [
        RuffFinding(
            filename=str(item.get("filename", "")),
            row=int(item.get("location", {}).get("row", 0)),
            column=int(item.get("location", {}).get("column", 0)),
            code=str(item.get("code", "")),
            message=str(item.get("message", "")),
            fixable=bool(item.get("fix")),
        )
        for item in payload
    ]


def tracked_source_files(paths: list[str]) -> list[Path]:
    """Return tracked Python files in the requested paths for backup."""
    result = run(["git", "ls-files", "--", *paths], check=True)
    files = []
    for raw in result.stdout.splitlines():
        path = ROOT / raw
        if path.suffix == ".py" and path.is_file():
            files.append(path)
    return files


def make_backup(files: list[Path]) -> Path:
    """Copy source files to a temporary rollback directory."""
    backup = Path(tempfile.mkdtemp(prefix="neuro-somaa-ruff-backup-"))
    for source in files:
        destination = backup / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return backup


def restore_backup(backup: Path) -> None:
    """Restore files after a failed remediation command."""
    for source in backup.rglob("*.py"):
        destination = ROOT / source.relative_to(backup)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only report findings; do not modify files.",
    )
    parser.add_argument(
        "--unsafe-fixes",
        action="store_true",
        help="Allow Ruff fixes classified as unsafe. Review the diff carefully.",
    )
    parser.add_argument(
        "--allow-remaining",
        action="store_true",
        help="Return success even when Ruff findings remain (useful for staged migration only).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"JSON report path (default: {DEFAULT_REPORT.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        default=list(DEFAULT_PATHS),
        help="Repository-relative paths to scan.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = [str(Path(path)) for path in args.paths]
    before = ruff_findings(paths)
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "paths": paths,
        "check_only": args.check,
        "unsafe_fixes": args.unsafe_fixes,
        "before_count": len(before),
        "before_fixable_count": sum(item.fixable for item in before),
        "commands": [],
        "backup": None,
    }

    print(f"Ruff findings before remediation: {len(before)}")
    print(f"Fixable with safe fixes: {report['before_fixable_count']}")

    if not args.check and before:
        files = tracked_source_files(paths)
        backup = make_backup(files)
        report["backup"] = str(backup)
        fix_command = ["ruff", "check", *paths, "--fix"]
        if args.unsafe_fixes:
            fix_command.append("--unsafe-fixes")
        format_command = ["ruff", "format", *paths]
        report["commands"].extend([fix_command, format_command])
        try:
            fix_result = run(fix_command)
            print(fix_result.stdout.strip())
            if fix_result.returncode not in (0, 1):
                raise RuntimeError(fix_result.stderr.strip() or "Ruff auto-fix failed")
            format_result = run(format_command)
            print(format_result.stdout.strip())
            if format_result.returncode != 0:
                raise RuntimeError(format_result.stderr.strip() or "Ruff format failed")
        except Exception:
            restore_backup(backup)
            print(f"Remediation failed; restored backup from {backup}", file=sys.stderr)
            raise

    after = ruff_findings(paths)
    report["after_count"] = len(after)
    report["after_fixable_count"] = sum(item.fixable for item in after)
    report["remaining"] = [asdict(item) for item in after]
    report["success"] = not after

    report_path = args.report if args.report.is_absolute() else ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Ruff findings after remediation: {len(after)}")
    print(f"Report: {report_path}")
    if after:
        print("Remaining findings:")
        for item in after[:40]:
            print(f"  {item.filename}:{item.row}:{item.column} {item.code} {item.message}")
        if len(after) > 40:
            print(f"  ... and {len(after) - 40} more")
    if after and not args.allow_remaining:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as exc:
        print(f"Required executable not found: {exc.filename}. Install Ruff first.", file=sys.stderr)
        raise SystemExit(2) from exc
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
