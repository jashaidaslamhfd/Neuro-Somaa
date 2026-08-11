#!/usr/bin/env python3
"""Prune dated data/ snapshots so git history stops bloating (2026-08-11 audit).

Between June and August 2026 the automation committed a NEW permanent file per
day per system (auto_repair_plan_20260729.json, premium_growth_dashboard_*,
self_maintenance_*, seo_diag_~100 Ko each, topic_gap_recommendations_*…).
Real analytics aggregate forever in rolling files (video_history.json); the
dated files are only daily diagnostics — keeping every one of them in git
forever serves nobody and buries real commits.

This pruner keeps, per family:
  * every snapshot from the last KEEP_DAYS days (default 7), and
  * the newest snapshot overall (the current one, whatever its age),
then unlinks the rest. Run before the analytics workflow commits data/.

Stdlib-only on purpose: analytics.yml runs on the light dependency set.

Usage:
    python scripts/cleanup_data_snapshots.py            # apply
    python scripts/cleanup_data_snapshots.py --dry-run  # preview
    DATA_SNAPSHOT_KEEP_DAYS=14 python scripts/cleanup_data_snapshots.py
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# family prefix -> regex capturing the YYYYMMDD (or YYYY-MM-DD) date
FAMILIES = {
    "auto_repair_plan": re.compile(r"^auto_repair_plan_(\d{8})\.json$"),
    "premium_growth_dashboard": re.compile(r"^premium_growth_dashboard_(\d{8})\.md$"),
    "self_maintenance": re.compile(r"^self_maintenance_(\d{8})\.md$"),
    "seo_diag": re.compile(r"^seo_diag_(\d{8})\.json$"),
    "topic_gap_recommendations": re.compile(r"^topic_gap_recommendations_(\d{8})\.json$"),
    "channel_seo_audit": re.compile(r"^channel_seo_audit_(\d{8})\.md$"),
    "seo_repair_plan": re.compile(r"^seo_repair_plan_(\d{8})\.json$"),
    "seo_repair_preview": re.compile(r"^seo_repair_preview_(\d{8})\.md$"),
    "video_audit": re.compile(r"^video_audit_(\d{8}|\d{4}-\d{2}-\d{2})\.json$"),
}


def _parse_date(raw: str) -> date:
    raw = raw.replace("-", "")
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def prune(data_dir: Path = DATA_DIR, keep_days: int = 7, dry_run: bool = False) -> dict:
    today = date.today()
    cutoff = today - timedelta(days=keep_days)
    summary = {"kept": 0, "deleted": 0, "by_family": {}}

    for family, pattern in FAMILIES.items():
        matches = []  # (date, path)
        for entry in data_dir.iterdir():
            m = pattern.match(entry.name)
            if m:
                try:
                    matches.append((_parse_date(m.group(1)), entry))
                except ValueError:
                    continue
        if not matches:
            continue
        newest = max(matches, key=lambda item: item[0])[1]
        kept = deleted = 0
        for snap_date, path in sorted(matches, key=lambda item: item[0], reverse=True):
            if snap_date >= cutoff or path == newest:
                kept += 1
                continue
            if dry_run:
                print(f"DRY-RUN would delete {path.relative_to(ROOT)}")
            else:
                path.unlink()
            deleted += 1
        summary["by_family"][family] = {"kept": kept, "deleted": deleted}
        summary["kept"] += kept
        summary["deleted"] += deleted

    action = "would delete" if dry_run else "deleted"
    print(f"[cleanup_data_snapshots] keep_days={keep_days}: "
          f"{action}={summary['deleted']}, kept={summary['kept']}")
    for family, row in summary["by_family"].items():
        print(f"  {family}: kept {row['kept']}, {action} {row['deleted']}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-days", type=int,
                    default=int(os.environ.get("DATA_SNAPSHOT_KEEP_DAYS", "7")))
    args = ap.parse_args()
    prune(keep_days=args.keep_days, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
