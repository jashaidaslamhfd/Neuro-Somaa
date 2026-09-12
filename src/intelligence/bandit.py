#!/usr/bin/env python3
"""Thompson-sampling bandits for title patterns (pure stdlib math).

Two honest views of each title pattern:
  1. Winner-rate bandit (Beta-Binomial): P(pattern beats WINNER_VIEWS).
     Robust to skew — recommended for decisions.
  2. Views bandit (Gaussian posterior on log-views): mean effect size.

Uses seo_analytics._title_pattern so pattern definitions stay SINGLE-source.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from .features import WINNER_VIEWS

MIN_SAMPLES_DECISION = 5  # same bar as slots/experiments


def _pattern_of(title: str) -> str:
    try:
        from seo_analytics import _title_pattern

        return _title_pattern(title)
    except Exception:
        t = title.lower()
        if t.startswith("pourquoi"):
            return "POURQUOI"
        if t.startswith("comment"):
            return "COMMENT"
        if "?" in title:
            return "QUESTION"
        return "OTHER"


def bandit_report(history: list[dict], samples: int = 4000, seed: int = 11) -> dict:
    groups: dict[str, list[int]] = {}
    for entry in history or []:
        views = entry.get("views")
        if views is None:
            continue
        try:
            views = int(views)
        except (TypeError, ValueError):
            continue
        groups.setdefault(_pattern_of(str(entry.get("title") or "")), []).append(views)

    rng = random.Random(seed)
    arms = {}
    for pattern, views in sorted(groups.items()):
        n = len(views)
        wins = sum(1 for v in views if v >= WINNER_VIEWS)
        logv = [math.log1p(v) for v in views]
        mean = sum(logv) / n
        var = sum((x - mean) ** 2 for x in logv) / max(n - 1, 1)

        # Thompson: beta posterior for winner-rate; gaussian approx for log-views
        beta_wins = sum(rng.betavariate(1 + wins, 1 + n - wins) for _ in range(samples)) / samples
        gauss = sum(rng.gauss(mean, math.sqrt(var / n + 1e-9)) for _ in range(min(samples, 800))) / min(
            samples, 800
        )
        arms[pattern] = {
            "n": n,
            "wins_ge_1000_views": wins,
            "winner_rate": round(wins / n, 4),
            "thompson_score": round(beta_wins, 4),
            "posterior_mean_logviews": round(mean, 4),
            "avg_views": round(sum(views) / n, 1),
            "confident": n >= MIN_SAMPLES_DECISION,
        }
        arms[pattern]["_gauss_draw"] = gauss

    ranked = sorted(arms.items(), key=lambda kv: kv[1]["thompson_score"], reverse=True)
    recommendation = None
    for pattern, a in ranked:
        if a["confident"]:
            recommendation = {
                "pattern": pattern,
                "why": f"highest winner-rate among patterns with ≥{MIN_SAMPLES_DECISION} samples",
                "thompson_score": a["thompson_score"],
                "avg_views": a["avg_views"],
            }
            break

    for a in arms.values():
        a.pop("_gauss_draw", None)
    return {
        "arms": arms,
        "recommended_pattern": recommendation,
        "min_samples_rule": MIN_SAMPLES_DECISION,
        "winner_threshold_views": WINNER_VIEWS,
        "honesty": "Beta posterior beats raw avg ranking at small n; "
        "patterns below the sample bar are reported but never recommended.",
    }
