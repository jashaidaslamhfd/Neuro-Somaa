"""TRUTH GATE (2026-08-11) — "measure, don't assert".

Problem this kills
------------------
The pipeline graded its own work: hook_score, seo_score, predicted_ctr,
predicted_retention were produced by the same heuristics/LLM that made the
content, then used as if they were facts (MIN_HOOK_SCORE even hard-blocked
uploads on them). Live autopsy on 47 real videos (2026-08-11):

  hook_score   vs real views      Spearman r = -0.08   → NOISE
                 score-100 hooks avg 578 vues, score-70 hooks avg 759 vues.
  seo_score    vs real views      Spearman r = -0.16   → INVERTED
  predicted_retention  mean 0.70 vs actual 0.38        → 2x exaggeration

A score that doesn't predict reality is not a score — it's decoration.
The Truth Gate therefore does one thing: every internal metric must PROVE
its predictive validity against real YouTube outcomes before anything in
the pipeline is allowed to trust it. Uncalibrated scores degrade to
honest "advisory only" labels; upload gates fall back to empirical priors
("what did SIMILAR videos actually do?") instead of self-grades.

Verdict bands (Spearman |r| against real views):
  n < MIN_N   → INSUFFICIENT_DATA   (honest "we don't know yet")
  r <= -0.15  → INVERTED            (actively misleading)
  |r| < 0.15  → NOISE               (no signal)
  0.15–0.35   → WEAK                (mild signal — advisory ok)
  >  0.35     → CALIBRATED          (allowed to drive decisions)
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

MIN_N = 12
NOISE_BAND = 0.15
WEAK_BAND = 0.35

STATUS_PATH = Path("data/truth_status.json")

# internal candidate score -> which claim it makes
METRICS = (
    ("hook_score", "hook quality"),
    ("seo_score", "SEO quality"),
    ("predicted_retention", "retention"),
    ("predicted_ctr", "CTR"),
)

_FR_STOP = {
    "le",
    "la",
    "les",
    "de",
    "du",
    "des",
    "un",
    "une",
    "et",
    "ou",
    "en",
    "dans",
    "sur",
    "pour",
    "par",
    "avec",
    "sans",
    "que",
    "qui",
    "quand",
    "pourquoi",
    "comment",
    "ce",
    "se",
    "sa",
    "son",
    "ses",
    "au",
    "aux",
    "on",
    "il",
    "elle",
    "est",
    "a",
    "plus",
    "tout",
    "toute",
    "pas",
    "ne",
    "à",
    "the",
    "ton",
    "ta",
    "tes",
    "mon",
    "ma",
    "mes",
    "notre",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-zàâäæçéèêëîïôöœùûüÿ']+", (text or "").lower())
    return {w.strip("'") for w in words if len(w.strip("'")) >= 4 and w.strip("'") not in _FR_STOP}


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation (ties via midranks). None if n < 3."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=False))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    if not vx or not vy:
        return None
    return cov / (vx * vy)


def _verdict(r: float | None, n: int) -> str:
    if n < MIN_N or r is None:
        return "INSUFFICIENT_DATA"
    if r <= -NOISE_BAND:
        return "INVERTED"
    if abs(r) < NOISE_BAND:
        return "NOISE"
    if r < WEAK_BAND:
        return "WEAK"
    return "CALIBRATED"


def calibrate_scores(history: list[dict]) -> dict:
    """Grade every internal score against real outcomes. Never flatters."""
    usable = [v for v in history if v.get("views") is not None]
    out: dict[str, dict] = {}
    for field, claim in METRICS:
        rows = [
            (v.get(field), v.get("views"), v.get("average_view_percentage"))
            for v in usable
            if isinstance(v.get(field), (int, float))
        ]
        preds = [r[0] for r in rows]
        views = [r[1] for r in rows]
        rets = [r[2] for r in rows if r[2] is not None]
        preds_r = [r[0] for r in rows if r[2] is not None]
        r_views = spearman(preds, views)
        r_ret = spearman(preds_r, rets)
        entry = {
            "claims": claim,
            "n": len(rows),
            "spearman_vs_views": round(r_views, 3) if r_views is not None else None,
            "spearman_vs_retention": round(r_ret, 3) if r_ret is not None else None,
            "verdict": _verdict(r_views, len(rows)),
            "decision_usable": _verdict(r_views, len(rows)) in ("WEAK", "CALIBRATED"),
        }
        # systematic bias for probabilistic predictions (0..1 vs 0..100 scale)
        if field == "predicted_retention" and preds and rets:
            both = [(p, a) for p, a in ((r[0], r[2] / 100) for r in rows) if a is not None]
            if both:
                mp = sum(b[0] for b in both) / len(both)
                ma = sum(b[1] for b in both) / len(both)
                entry["bias"] = round(mp - ma, 3)
                entry["mean_predicted"] = round(mp, 3)
                entry["mean_actual"] = round(ma, 3)
        out[field] = entry
    out["_summary"] = {
        "n_videos": len(usable),
        "message": (
            "An internal score only earns trust by predicting real outcomes. "
            "NOISE/INVERTED scores are advisory-only everywhere in the pipeline."
        ),
    }
    return out


def empirical_prediction(topic: str, history: list[dict], *, min_similar: int = 3) -> dict:
    """Honest expectation for a NEW video: what did SIMILAR videos actually do?

    No model magic — median views/retention of videos sharing a content word
    with the topic, falling back (loudly labelled) to the global median.
    """
    usable = [
        (v, v.get("views"), v.get("average_view_percentage")) for v in history if v.get("views") is not None
    ]
    if not usable:
        return {
            "confidence": "UNKNOWN",
            "basis": "no measured history yet",
            "views_median": None,
            "retention_p50": None,
            "n": 0,
            "similar": [],
        }
    tk = _tokens(topic)
    sims = []
    for v, views, ret in usable:
        words = _tokens((v.get("topic") or "") + " " + (v.get("title") or ""))
        shared = tk & words
        if shared:
            sims.append((views, ret, v.get("title") or "?", sorted(shared)))
    sims.sort(key=lambda s: -len(s[3]))
    strong = [s for s in sims if len(s[3]) >= 1][:8]
    pool = strong if len(strong) >= min_similar else None

    def _median(vals):
        vals = sorted(vals)
        n = len(vals)
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    if pool:
        views_m = _median([s[0] for s in pool])
        rets = [s[1] for s in pool if s[1] is not None]
        return {
            "confidence": "SIMILAR_VIDEOS" if len(pool) >= 5 else "FEW_SIMILAR",
            "basis": f"{len(pool)} measured videos on the same phenomenon",
            "views_median": round(views_m),
            "retention_p50": round(_median(rets), 1) if rets else None,
            "n": len(pool),
            "similar": [s[2] for s in pool[:3]],
        }
    views_m = _median([u[1] for u in usable])
    rets = [u[2] for u in usable if u[2] is not None]
    return {
        "confidence": "GLOBAL_FALLBACK",
        "basis": "no similar video measured — channel-wide median, wide error bars",
        "views_median": round(views_m),
        "retention_p50": round(_median(rets), 1) if rets else None,
        "n": len(usable),
        "similar": [],
    }


def truth_status(calibration: dict) -> dict:
    """Compact status main.py reads: which internal scores may gate decisions."""
    return {
        m: {
            "verdict": calibration[m]["verdict"],
            "decision_usable": calibration[m]["decision_usable"],
            "spearman_vs_views": calibration[m]["spearman_vs_views"],
        }
        for m, _ in METRICS
    }


def render_truth_markdown(calibration: dict) -> list[str]:
    badge = {"CALIBRATED": "✅", "WEAK": "🟡", "NOISE": "🔴", "INVERTED": "⛔", "INSUFFICIENT_DATA": "⚪"}
    lines = ["", "## 🧪 Truth Gate (scores internes vs réalité)"]
    for field, _ in METRICS:
        c = calibration[field]
        r = c["spearman_vs_views"]
        r_s = f"r={r:+.2f}" if r is not None else "r=n/a"
        line = f"- {badge[c['verdict']]} `{field}` ({c['claims']}): **{c['verdict']}** ({r_s}, n={c['n']})"
        if c.get("bias") is not None:
            line += (
                f" — biais {c['bias']:+.2f} (prédit {c['mean_predicted']:.2f} vs réel {c['mean_actual']:.2f})"
            )
        if c["decision_usable"]:
            line += " — peut guider des décisions"
        else:
            line += " — **consultatif seulement, jamais un gate**"
        lines.append(line)
    return lines


def run(history: list[dict], status_path: Path = STATUS_PATH) -> dict:
    """Calibrate everything once per analytics sync; persist the gate status."""
    calibration = calibrate_scores(history)
    status = truth_status(calibration)
    status["_meta"] = {"min_n": MIN_N, "noise_band": NOISE_BAND, "weak_band": WEAK_BAND}
    try:
        status_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{status_path.name}.", suffix=".tmp", dir=status_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(status, handle, indent=2, ensure_ascii=False)
            os.replace(temporary, status_path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise
        logger.info(
            "truth gate: hook_score=%s seo_score=%s (status -> %s)",
            status["hook_score"]["verdict"],
            status["seo_score"]["verdict"],
            status_path,
        )
    except OSError as exc:
        logger.warning("truth status write failed: %s", exc)
    return {"calibration": calibration, "status": status}


def load_status(status_path: Path = STATUS_PATH, *, max_age_hours: int = 72) -> dict | None:
    """main.py side: read the latest gate status. None = treat every internal
    score as advisory-only (never trust a self-grade of unknown validity)."""
    try:
        import datetime as _dt

        data = json.loads(status_path.read_text(encoding="utf-8"))
        mtime = _dt.datetime.fromtimestamp(status_path.stat().st_mtime, tz=_dt.UTC)
        if (_dt.datetime.now(_dt.UTC) - mtime).total_seconds() > max_age_hours * 3600:
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None
