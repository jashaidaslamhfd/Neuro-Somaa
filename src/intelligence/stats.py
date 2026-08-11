#!/usr/bin/env python3
"""Statistical tests without scipy — permutation tests (exact-ish, tiny-n safe).

A permutation (randomization) test needs no distribution assumptions and no
scipy: shuffle group labels N times, measure how often the shuffled mean-gap
beats the observed one. Ideal for n≈10-40 channel experiments.
"""
from __future__ import annotations

import math
import random


def permutation_test(a: list[float], b: list[float], iters: int = 5000, seed: int = 3) -> dict:
    """Two-sided permutation test on mean difference between arms a and b."""
    a = [float(x) for x in a]
    b = [float(x) for x in b]
    if len(a) < 3 or len(b) < 3:
        return {
            "significant": False,
            "reason": f"need ≥3 per arm (a={len(a)}, b={len(b)}) — keep collecting",
            "n_a": len(a), "n_b": len(b),
        }
    observed = abs(sum(a) / len(a) - sum(b) / len(b))
    pooled = a + b
    rng = random.Random(seed)
    exceed = 0
    na = len(a)
    for _ in range(iters):
        rng.shuffle(pooled)
        gap = abs(sum(pooled[:na]) / na - sum(pooled[na:]) / len(pooled[na:]))
        if gap >= observed - 1e-12:
            exceed += 1
    p = (exceed + 1) / (iters + 1)  # +1 avoids p=0 claims
    return {
        "significant": p < 0.05,
        "p_value": round(p, 4),
        "mean_a": round(sum(a) / len(a), 2),
        "mean_b": round(sum(b) / len(b), 2),
        "diff": round(sum(a) / len(a) - sum(b) / len(b), 2),
        "n_a": len(a), "n_b": len(b),
        "method": f"two-sided permutation test ({iters} shuffles)",
        "honesty": "p<0.05 at tiny n still means 'watch it', not 'proved it'.",
    }


def compare_experiment_arms(history: list[dict], experiment_path: str = "data/duration_experiment.json") -> dict:
    """Compare experiment arms (e.g. control_long vs test_short) on real views."""
    import json
    from pathlib import Path

    try:
        experiment = json.loads(Path(experiment_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "reason": "no experiment file"}

    views_by_id = {}
    for e in history or []:
        vid, views = e.get("youtube_video_id"), e.get("views")
        if vid and views is not None:
            try:
                views_by_id[vid] = int(views)
            except (TypeError, ValueError):
                continue

    arms: dict[str, list[int]] = {}
    for row in experiment.get("assignments", []):
        vid = row.get("video_id")
        arm = row.get("arm")
        if vid in views_by_id and arm:
            arms.setdefault(arm, []).append(views_by_id[vid])

    groups = list(arms.items())
    if len(groups) < 2:
        return {"available": False, "reason": "fewer than 2 arms have real views yet",
                "arms": {k: len(v) for k, v in arms.items()}}
    (name_a, a), (name_b, b) = groups[0], groups[1]
    result = permutation_test(a, b)
    result.update({
        "available": True,
        "arm_a": name_a, "arm_b": name_b,
        "winner": (name_a if result.get("diff", 0) > 0 else name_b) if result.get("significant") else None,
    })
    return result
