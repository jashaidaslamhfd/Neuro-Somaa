#!/usr/bin/env python3
"""Anomaly detection on video performance — median/MAD robust z-scores.

Mean/std z-scores break on skewed view counts (one 1.5k video inflates the
std and hides the real outliers). Median + MAD survive outliers by design.

modified_z = 0.6745 * (x - median) / MAD   →  |z| > 3.5 = outlier (Iglewicz-Hoaglin)

Actions stay conservative: under-performer → repair candidate list (which the
existing repair workflows already consume); over-performer → pattern mining
(mine WHAT worked, don't celebrate vanity numbers).
"""
from __future__ import annotations

import math


def detect_anomalies(history: list[dict], recent_n: int = 20) -> dict:
    points = []
    for entry in history or []:
        views = entry.get("views")
        if views is None:
            continue
        try:
            views = int(views)
        except (TypeError, ValueError):
            continue
        points.append({
            "video_id": entry.get("youtube_video_id") or "?",
            "title": str(entry.get("title") or ""),
            "views": views,
            "log_views": math.log1p(views),
            "retention_pct": entry.get("average_view_percentage"),
        })

    if len(points) < 8:
        return {"reliable": False, "reason": f"n={len(points)} too small", "anomalies": []}

    logv = sorted(p["log_views"] for p in points)
    n = len(logv)
    median = logv[n // 2] if n % 2 else (logv[n // 2 - 1] + logv[n // 2]) / 2
    deviations = sorted(abs(x - median) for x in logv)
    mad = deviations[n // 2] if n % 2 else (deviations[n // 2 - 1] + deviations[n // 2]) / 2
    mad = max(mad, 1e-6)

    anomalies = []
    for p in points[-recent_n:]:
        z = 0.6745 * (p["log_views"] - median) / mad
        if abs(z) <= 3.5:
            continue
        direction = "over" if z > 0 else "under"
        anomalies.append({
            "video_id": p["video_id"],
            "title": p["title"][:80],
            "views": p["views"],
            "modified_z": round(z, 2),
            "direction": direction,
            "action": (
                "mine the winning hook/topic pattern for reuse"
                if direction == "over" else
                "queue metadata+thumbnail repair (hooks, CTR signals)"
            ),
        })

    flagged = sorted(anomalies, key=lambda a: abs(a["modified_z"]), reverse=True)
    return {
        "reliable": True,
        "n_scored": len(points),
        "window": recent_n,
        "baseline_median_views": round(math.expm1(median), 1),
        "method": "modified z-score (median/MAD, Iglewicz-Hoaglin >3.5)",
        "anomalies": flagged,
        "underperformers": [a["video_id"] for a in flagged if a["direction"] == "under"],
    }
