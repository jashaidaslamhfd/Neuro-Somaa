#!/usr/bin/env python3
"""Channel growth forecasting — Holt double exponential smoothing (pure math).

Daily views series from video_history → 30-day projection.
Honesty rules (this channel is n≈50 videos, median ~760 views):
  * needs ≥21 days of data to emit numbers;
  * returns prediction bands (±1 residual std), not fake point precision;
  * milestones (Tier-1 500 subs...) are stated only when trend actually
    exists — never as marketing.
"""
from __future__ import annotations

from collections import defaultdict


def _daily_views_series(history: list[dict]) -> list[tuple[str, int]]:
    from .features import _parse_dt
    daily: dict[str, int] = defaultdict(int)
    for entry in history or []:
        views = entry.get("views")
        if views is None:
            continue
        dt = _parse_dt(entry.get("publish_at") or entry.get("posted_at"))
        if not dt:
            continue
        try:
            daily[dt.strftime("%Y-%m-%d")] += int(views)
        except (TypeError, ValueError):
            continue
    return sorted(daily.items())


def holt_forecast(series: list[float], horizon: int = 30, alpha: float = 0.4, beta: float = 0.1) -> dict:
    n = len(series)
    if n < 21:
        return {"reliable": False, "reason": f"need ≥21 daily points, have {n}"}
    level = series[0]
    trend = (series[-1] - series[0]) / max(n - 1, 1)
    fitted = [level]
    for x in series[1:]:
        prev_level = level
        level = alpha * x + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        fitted.append(level)
    residuals = [x - f for x, f in zip(series, fitted)]
    sigma = (sum(r * r for r in residuals) / max(len(residuals) - 2, 1)) ** 0.5
    forecast = [max(0.0, level + (h + 1) * trend) for h in range(horizon)]
    return {
        "reliable": True,
        "method": "Holt double exponential smoothing (α=0.4, β=0.1)",
        "last_level": round(level, 1),
        "daily_trend": round(trend, 2),
        "sigma_daily": round(sigma, 1),
        "forecast_daily_views": [round(v, 1) for v in forecast],
        "total_30d_expected": round(sum(forecast), 0),
        "band_30d_low": round(sum(max(0.0, f - sigma) for f in forecast) / max(horizon, 1), 1),
        "band_30d_high": round(sum(f + sigma for f in forecast) / max(horizon, 1), 1),
        "honesty": "trend extrapolation assumes current strategy/format holds; "
                   "a single viral outlier reshapes everything — re-read weekly.",
    }


def forecast_growth(history: list[dict], horizon: int = 30) -> dict:
    series = _daily_views_series(history)
    result = holt_forecast([float(v) for _, v in series], horizon=horizon)
    result["series_days"] = len(series)
    if series:
        result["first_day"], result["last_day"] = series[0][0], series[-1][0]
    return result
