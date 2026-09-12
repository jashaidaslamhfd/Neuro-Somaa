#!/usr/bin/env python3
"""Neuro-Somaa Intelligence Layer (2026-08-11).

Data-Science / ML / DL "full powers" for the French Shorts pipeline:

  features.py   engineered features from real video history
  models.py     ridge (closed form, k-fold CV) + TinyMLP (pure numpy) — "DL"
  bandit.py     Thompson sampling over title patterns (Beta + Gaussian)
  clustering.py TF-IDF + spherical k-means++ topic clusters
  anomaly.py    MAD-robust anomaly detection on performance
  forecast.py   Holt double-exponential 30-day growth projection
  stats.py      permutation testing (tiny-n safe, no scipy)
  report.py     rolling JSON + French markdown dashboard

Design contract with the existing pipeline:
  * RUN ONLY on real analytics (entries with `views`), never on placeholders;
  * every block declares its own minimum sample bar and honesty note;
  * pure numpy + stdlib — runs on analytics.yml's light dependency set;
  * advisory, not gating: this layer REcommends, the hard safety gates decide.

Run:  python -m intelligence          (from src/, or via analytics_updater Step D)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("intelligence")

ROOT = Path(__file__).resolve().parents[2]
HISTORY_PATH = Path(os.environ.get("VIDEO_HISTORY_PATH", str(ROOT / "data" / "video_history.json")))


def run_all(history_path: Path | str | None = None, output_dir: Path | str | None = None) -> dict:
    from . import (
        anomaly,
        bandit,
        clustering,
        features,
        forecast,
        models,
        report,
        stats,
        truth_gate,
        viral_miner,
    )

    path = Path(history_path) if history_path else HISTORY_PATH
    data_dir = Path(output_dir) if output_dir is not None else ROOT / "data"
    history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if isinstance(history, dict):
        history = history.get("videos", [])

    rows, targets, _ids = features.build_dataset(history)
    logger.info("intelligence: %d real-analytics videos scored", len(rows))

    anomalies = anomaly.detect_anomalies(history)
    fastlane_path = data_dir / "winner_fastlane.json"
    fastlane = viral_miner.mine_winner_fastlane(history, anomalies, output_path=fastlane_path)
    truth = truth_gate.run(history, status_path=data_dir / "truth_status.json")

    full = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_videos_analyzed": len(rows),
        "truth_gate": truth["calibration"],
        "data_quality": report._data_quality(history),
        "models": models.compare_models(rows, targets, features.FEATURE_NAMES),
        "bandit": bandit.bandit_report(history),
        "anomalies": anomalies,
        "forecast": forecast.forecast_growth(history),
        "clusters": clustering.cluster_topics(history),
        "retention": report._retention_distribution(history),
        "experiment": stats.compare_experiment_arms(history),
        "hook_arms": stats.compare_hook_arms(history),
        # Raw history for report-only consumers (growth_state vs views/j).
        # Underscore = not a model output; never written to the JSON report
        # unless write_reports opts in.
        "_history": history,
        "viral_fastlane": {
            "entries": len(fastlane["fastlane"]),
            "ttl_hours": fastlane["ttl_hours"],
            "items": fastlane["fastlane"],
            "fastlane_path": str(fastlane_path),
        },
        "schema_version": 1,
    }
    out = report.write_reports(full, output_dir=data_dir)
    logger.info("intelligence reports written: %s (%d bytes)", out["markdown"], out["bytes"])
    return full
