"""CLI entrypoint: python -m intelligence [history_path]"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intelligence import run_all  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

if __name__ == "__main__":
    result = run_all(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps({
        "n": result["n_videos_analyzed"],
        "ridge": {k: v for k, v in result["models"]["ridge"].items() if k != "top_features"},
        "recommended_pattern": result["bandit"].get("recommended_pattern"),
        "anomalies": len(result["anomalies"].get("anomalies", [])),
        "underperformers": result["anomalies"].get("underperformers", []),
        "forecast_reliable": result["forecast"].get("reliable"),
        "winner_cluster": result["clusters"].get("winner_cluster"),
        "experiment": {k: result["experiment"].get(k) for k in ("significant", "p_value", "winner")},
    }, indent=2, ensure_ascii=False))
