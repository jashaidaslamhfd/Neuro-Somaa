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


def compare_hook_arms(history: list[dict]) -> dict:
    """Which hook STYLE (question / shock_fact / pov_reveal) retains/pays?

    hook_arm is logged per video from 2026-08-12 onward. Until every arm has
    ≥5 videos with real views, this block stays explicitly underpowered.
    Pairwise permutation tests on views; multiple-comparison honesty note.
    """
    arms: dict[str, list[int]] = {}
    for e in history or []:
        arm = e.get("hook_arm")
        views = e.get("views")
        if not arm or views is None:
            continue
        try:
            arms.setdefault(arm, []).append(int(views))
        except (TypeError, ValueError):
            continue

    sizes = {k: len(v) for k, v in arms.items()}
    mature = {k: v for k, v in arms.items() if len(v) >= 5}
    if len(mature) < 2:
        return {
            "available": False,
            "reason": "hook-arm experiment needs ≥5 real-view videos per arm "
                      f"(have: {sizes or 'none yet'}); arms start accruing from "
                      "the first run after 2026-08-12",
            "sample_sizes": sizes,
        }

    pairs = []
    names = list(mature)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            res = permutation_test(mature[names[i]], mature[names[j]])
            pairs.append({"a": names[i], "b": names[j], **res})
    best = max(mature.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    return {
        "available": True,
        "sample_sizes": sizes,
        "pairwise": pairs,
        "leading_arm": {"arm": best[0], "avg_views": round(sum(best[1]) / len(best[1]), 1)},
        "honesty": "3 arms = 3 pairwise tests; treat p<0.05 as 'promising', "
                   "re-confirm on the next batch before rewriting the prompt bank.",
    }
