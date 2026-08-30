"""Measured CTR experiment registry for title, hook, and thumbnail variants."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

REGISTRY_PATH = os.environ.get("CTR_EXPERIMENTS_PATH", "data/ctr_experiments.json")
MIN_IMPRESSIONS = int(os.environ.get("CTR_MIN_IMPRESSIONS", "1000"))
MIN_CLICKS = int(os.environ.get("CTR_MIN_CLICKS", "30"))


def experiment_id(topic: str, variants: list[dict], video_id: str = "") -> str:
    material = json.dumps({"topic": topic, "variants": variants, "video_id": video_id}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _load() -> list[dict]:
    path = Path(REGISTRY_PATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save(rows: list[dict]) -> None:
    path = Path(REGISTRY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(rows[-1000:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def register(topic: str, variants: list[dict], video_id: str = "") -> str:
    eid = experiment_id(topic, variants, video_id)
    rows = _load()
    if not any(row.get("experiment_id") == eid for row in rows):
        rows.append({
            "experiment_id": eid,
            "created_at": datetime.now(UTC).isoformat(),
            "topic": topic,
            "video_id": video_id or None,
            "variants": variants,
            "status": "maturing",
        })
        _save(rows)
    return eid


def update_metrics(experiment_id_value: str, variant_id: str, impressions: int, clicks: int, views: int | None = None) -> bool:
    rows = _load()
    changed = False
    for row in rows:
        if row.get("experiment_id") != experiment_id_value:
            continue
        for variant in row.get("variants", []):
            if variant.get("variant_id") != variant_id:
                continue
            variant.update({"impressions": int(impressions), "clicks": int(clicks), "views": views})
            changed = True
        if changed:
            row["status"] = "matured" if winner(row) else "maturing"
    if changed:
        _save(rows)
    return changed


def winner(row: dict) -> dict | None:
    eligible = []
    for variant in row.get("variants", []):
        impressions = int(variant.get("impressions") or 0)
        clicks = int(variant.get("clicks") or 0)
        if impressions < MIN_IMPRESSIONS or clicks < MIN_CLICKS:
            continue
        ctr = clicks / impressions
        # Wilson lower bound: select only a measured winner with uncertainty margin.
        z = 1.96
        denominator = 1 + z * z / impressions
        centre = ctr + z * z / (2 * impressions)
        spread = z * math.sqrt((ctr * (1 - ctr) + z * z / (4 * impressions)) / impressions)
        lower = (centre - spread) / denominator
        eligible.append({**variant, "ctr": ctr, "ctr_lower_bound": lower})
    if not eligible:
        return None
    return max(eligible, key=lambda item: item["ctr_lower_bound"])
