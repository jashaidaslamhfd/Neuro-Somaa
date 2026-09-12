#!/usr/bin/env python3
"""Premium growth loop for the French SKILLOR channel.

Daily/weekly offline brain that turns public competitor data + our real channel
analytics into actionable state:

1. title-bandit weights (`data/title_bandit_fr.json`) used by seo_generator;
2. 48h auto-repair plan for underperforming already-uploaded videos;
3. topic-gap recommendations from competitor winners and real comments;
4. dashboard markdown/json for the owner.

It never writes to YouTube. Repair application stays in `seo_repair.yml` and is
still dry-run by default.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

LOG = logging.getLogger("premium-growth-loop")
TODAY = datetime.now(UTC).date()

PATTERN_ALIASES = {
    "CE_QUE_VOTRE_CORPS": "ce-que-corps-revele",
    "CE_QUIL_FAUT_COMPRENDRE": "ce-quil-faut",
    "CE_QUI_SE_PASSE": "ce-qui-se-passe",
    "LA_SCIENCE": "la-science",
    "POURQUOI": "pourquoi-question",
    "pourquoi-question": "pourquoi-question",
    "pourquoi-declarative": "pourquoi-declarative",
    "ce-que-corps-dit": "ce-que-corps-revele",
    "ce-qu-il-faut": "ce-quil-faut",
    "ce-qui-se-passe": "ce-qui-se-passe",
    "la-science": "la-science",
}
DEFAULT_PATTERN_PRIOR = {
    "pourquoi-question": 2.0,
    "ce-que-corps-revele": 1.6,
    "ce-qui-se-passe": 1.25,
    "la-science": 0.9,
    "ce-quil-faut": 0.8,
}
DEFAULT_UPLOAD_SLOT_PRIOR = {
    "12:30": 2.2,
    "19:30": 2.8,
    "21:00": 2.6,
}
# How many real videos a slot needs before its measured score is trusted at
# full weight, and how many videos the French default priors are worth. These
# stop a single lucky (or unlucky) upload from redefining the daily schedule.
# 5 matches the duration-experiment per-arm minimum: below that, a slot is
# eligible for the ranking table but must NEVER be handed a daily publish
# slot while prior-backed defaults are still available.
MIN_CONFIDENT_SLOT_SAMPLES = 5
PRIOR_STRENGTH_VIDEOS = 4
PARIS_TZ = ZoneInfo("Europe/Paris")


def _global_average_score(groups: dict[str, list[float]]) -> float:
    """Mean score across every measured video — the neutral expectation for a
    slot the channel knows nothing about."""
    values = [score for scores in groups.values() for score in scores]
    return sum(values) / len(values) if values else 0.0


def _prior_on_observed_scale(slot: str, groups: dict[str, list[float]]) -> float:
    """Express a French default prior on the same scale as measured scores.

    The raw priors (2.2-2.8) are hand-set preferences, while measured scores
    are log10(views+10) + 1.2*retention and sit near 3.5 for any slot with a
    single ordinary video. Comparing the two directly meant every prior lost
    to every one-off upload. Only the priors' RELATIVE ordering is meaningful,
    so re-centre them on the channel's own average score.
    """
    prior = DEFAULT_UPLOAD_SLOT_PRIOR.get(slot)
    if prior is None:
        return 0.0
    baseline = _global_average_score(groups)
    if not baseline:
        return prior
    prior_mean = sum(DEFAULT_UPLOAD_SLOT_PRIOR.values()) / len(DEFAULT_UPLOAD_SLOT_PRIOR)
    return baseline + (prior - prior_mean)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _age_hours(entry: dict) -> float | None:
    dt = _parse_dt(entry.get("posted_at") or entry.get("publish_at"))
    if not dt:
        return None
    return (datetime.now(UTC) - dt.astimezone(UTC)).total_seconds() / 3600


def classify_title(title: str) -> str:
    t = (title or "").strip().lower()
    if re.match(r"^pourquoi\b.+\?\s*$", t):
        return "pourquoi-question"
    if t.startswith("pourquoi"):
        return "pourquoi-declarative"
    if t.startswith(("ce qui se passe", "ce qui change", "ce qui arrive")):
        return "ce-qui-se-passe"
    if t.startswith(("ce que ton corps", "ce que votre corps", "ce que le corps")):
        return "ce-que-corps-revele"
    if t.startswith(("ce qu'il faut", "ce qu’il faut")):
        return "ce-quil-faut"
    if t.startswith(("la science", "ce que la science")):
        return "la-science"
    return "other"


def build_title_bandit(history: list[dict], competitor: dict) -> dict:
    groups: dict[str, list[float]] = defaultdict(list)
    for entry in history:
        age = _age_hours(entry)
        # wait for early analytics to settle; very fresh 0-view videos add noise
        if age is not None and age < 96:
            continue
        title = entry.get("title") or ""
        pattern = classify_title(title)
        views = int(entry.get("views") or 0)
        retention = entry.get("average_view_percentage")
        if retention is None:
            retention = entry.get("predicted_retention")
        retention_val = float(retention or 0)
        if retention_val > 2:  # sometimes stored as percentage not fraction
            retention_val = retention_val / 100
        hook = float(entry.get("hook_score") or 0) / 100
        seo = float(entry.get("seo_score") or 0) / 100
        score = math.log10(max(views, 1) + 10) + 1.8 * retention_val + 0.4 * hook + 0.2 * seo
        if views or retention_val or hook or seo:
            groups[pattern].append(score)

    # Competitor winners are a prior, not the final truth. Our channel analytics
    # dominates once enough samples exist.
    competitor_prior: dict[str, float] = dict(DEFAULT_PATTERN_PRIOR)
    for row in competitor.get("patterns", []) or []:
        pattern = PATTERN_ALIASES.get(row.get("pattern"), row.get("pattern"))
        if not pattern:
            continue
        competitor_prior[pattern] = competitor_prior.get(pattern, 0.0) + float(row.get("score") or 0) * 0.08

    preferred = []
    all_patterns = set(competitor_prior) | set(groups)
    for pattern in sorted(all_patterns):
        observed = groups.get(pattern, [])
        observed_avg = sum(observed) / len(observed) if observed else 0.0
        # prior weight equals roughly two synthetic samples; fades as history grows
        prior = competitor_prior.get(pattern, 0.0)
        score = (observed_avg * len(observed) + prior * 2) / max(len(observed) + 2, 1)
        preferred.append(
            {
                "pattern": pattern,
                "score": round(score, 4),
                "observed_samples": len(observed),
                "observed_avg": round(observed_avg, 4),
                "competitor_prior": round(prior, 4),
            }
        )
    preferred.sort(key=lambda item: item["score"], reverse=True)
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "policy": "Competitor patterns are only priors; channel analytics re-ranks future titles.",
        "preferred_patterns": preferred,
    }


def _catalogue_text() -> str:
    records = _load_json(DATA / "body_glitch_topics.json", [])
    parts = []
    for item in records if isinstance(records, list) else []:
        parts.extend(str(item.get(key, "")) for key in ("topic", "angle", "series_title", "question_phrase"))
    return "\n".join(parts).lower()


def _round_to_half_hour(dt: datetime) -> tuple[int, int]:
    minute = 30 if dt.minute >= 15 and dt.minute < 45 else 0
    hour = dt.hour
    if dt.minute >= 45:
        hour = (hour + 1) % 24
    return hour, minute


def _slot_key(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _slot_distance_minutes(a: str, b: str) -> int:
    ah, am = map(int, a.split(":"))
    bh, bm = map(int, b.split(":"))
    av = ah * 60 + am
    bv = bh * 60 + bm
    diff = abs(av - bv)
    return min(diff, 24 * 60 - diff)


def build_upload_slot_intel(history: list[dict], max_slots: int = 3, min_gap_minutes: int = 90) -> dict:
    """Learn the Paris publish slots that produce the most views/retention.

    Uses each video's scheduled `publish_at` when available, otherwise
    `posted_at`, converts to Europe/Paris, rounds to a half-hour bucket, and
    ranks buckets by real views + retention. Default French peak slots are
    blended as priors so a tiny sample never jumps to a weird one-off time.
    """
    groups: dict[str, list[float]] = defaultdict(list)
    examples: dict[str, list[dict]] = defaultdict(list)

    for entry in history:
        ts = entry.get("publish_at") or entry.get("posted_at")
        dt = _parse_dt(ts)
        if not dt:
            continue
        views = entry.get("views")
        if views is None:
            continue
        try:
            views_i = int(views)
        except (TypeError, ValueError):
            continue
        paris_dt = dt.astimezone(PARIS_TZ)
        hour, minute = _round_to_half_hour(paris_dt)
        key = _slot_key(hour, minute)
        retention = entry.get("average_view_percentage") or entry.get("predicted_retention") or 0
        try:
            retention_f = float(retention)
        except (TypeError, ValueError):
            retention_f = 0.0
        if retention_f > 2:
            retention_f /= 100
        score = math.log10(max(views_i, 1) + 10) + 1.2 * retention_f
        groups[key].append(score)
        examples[key].append(
            {
                "video_id": entry.get("youtube_video_id"),
                "title": entry.get("title"),
                "views": views_i,
                "published_paris": paris_dt.strftime("%Y-%m-%d %H:%M"),
            }
        )

    rows = []
    all_slots = set(groups) | set(DEFAULT_UPLOAD_SLOT_PRIOR)
    for key in sorted(all_slots):
        values = groups.get(key, [])
        observed_avg = sum(values) / len(values) if values else 0.0
        prior = _prior_on_observed_scale(key, groups)
        # The score floor is log10(0 views + 10) = 1.0, so EVERY slot that ever
        # hosted a single video scored ~3.5 and outranked the proven French
        # priors (2.2-2.8). One accidental upload could therefore capture a
        # daily slot forever. Two corrections keep this honest:
        #   1. Priors are weighted like a real sample of videos, not like 2
        #      points of a differently-scaled scale.
        #   2. Slots the channel has barely tested are shrunk toward the
        #      global average instead of being trusted at face value.
        prior_samples = PRIOR_STRENGTH_VIDEOS if prior else 0
        blended = (observed_avg * len(values) + prior * prior_samples) / max(len(values) + prior_samples, 1)
        if 0 < len(values) < MIN_CONFIDENT_SLOT_SAMPLES:
            # Linear shrink: 1 sample keeps 1/5 of its deviation at MIN=5.
            confidence = len(values) / MIN_CONFIDENT_SLOT_SAMPLES
            baseline = prior or _global_average_score(groups)
            blended = baseline + (blended - baseline) * confidence
        hour, minute = map(int, key.split(":"))
        rows.append(
            {
                "slot": key,
                "hour": hour,
                "minute": minute,
                "score": round(blended, 4),
                "observed_samples": len(values),
                "observed_avg": round(observed_avg, 4),
                "prior": round(prior, 4),
                "examples": sorted(
                    examples.get(key, []), key=lambda item: item.get("views", 0), reverse=True
                )[:3],
            }
        )
    rows.sort(key=lambda item: item["score"], reverse=True)

    # A slot is CONFIDENT when it either earned enough real evidence or is
    # backed by a French default prior. A 1-4 sample observation (whatever its
    # score) must never capture a daily publish slot while confident choices
    # exist — this is what let a single 06:00 video displace the proven 12:30
    # lunch slot on 2026-08-11 (shrinkage alone was too weak a correction).
    def _is_confident(row: dict) -> bool:
        return (
            row["observed_samples"] >= MIN_CONFIDENT_SLOT_SAMPLES or row["slot"] in DEFAULT_UPLOAD_SLOT_PRIOR
        )

    def _try_select(pool, min_samples_required: bool) -> list:
        chosen = []
        for row in pool:
            if min_samples_required and not _is_confident(row):
                continue
            if all(_slot_distance_minutes(row["slot"], other["slot"]) >= min_gap_minutes for other in chosen):
                chosen.append(row)
            if len(chosen) >= max_slots:
                break
        return chosen

    # Pass 1 — confident rows only, best score first.
    selected = _try_select(rows, min_samples_required=True)

    # Pass 2 — guarantee three daily slots with the remaining default priors
    # (trusted on no-data repos, and safer than any tiny-sample slot).
    if len(selected) < max_slots:
        for key in DEFAULT_UPLOAD_SLOT_PRIOR:
            if any(row["slot"] == key for row in selected):
                continue
            hour, minute = map(int, key.split(":"))
            selected.append(
                {
                    "slot": key,
                    "hour": hour,
                    "minute": minute,
                    "score": DEFAULT_UPLOAD_SLOT_PRIOR[key],
                    "observed_samples": 0,
                    "observed_avg": 0.0,
                    "prior": DEFAULT_UPLOAD_SLOT_PRIOR[key],
                    "examples": [],
                }
            )
            if len(selected) >= max_slots:
                break

    # Pass 3 — absolute last resort (edge cases where defaults were all
    # consumed by overlapping confident slots): allow tiny-sample rows.
    if len(selected) < max_slots:
        for row in _try_select(rows, min_samples_required=False):
            if not any(row["slot"] == s["slot"] for s in selected) and all(
                _slot_distance_minutes(row["slot"], other["slot"]) >= min_gap_minutes for other in selected
            ):
                selected.append(row)
            if len(selected) >= max_slots:
                break

    score_order = {
        row["slot"]: r
        for r, row in enumerate(sorted(selected, key=lambda item: item["score"], reverse=True), start=1)
    }
    recommended = []
    for rank, row in enumerate(sorted(selected, key=lambda item: (item["hour"], item["minute"])), start=1):
        recommended.append(
            {
                "rank": rank,  # chronological publish order of the day
                "score_rank": score_order[row["slot"]],  # where this slot truly ranks by evidence
                "slot": row["slot"],
                "hour": row["hour"],
                "minute": row["minute"],
                "name": f"Dynamique {row['slot']}",
                "score": row["score"],
                "samples": row["observed_samples"],
                "confident": _is_confident(row),
                "prior": row["prior"],
            }
        )

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "timezone": "Europe/Paris",
        "policy": "PublishAt slots learned from real channel views/retention; defaults are used as priors.",
        "recommended_slots": recommended,
        "ranked_slots": rows[:12],
    }


def build_topic_gaps(competitor: dict, comments: dict, limit: int = 30) -> list[dict]:
    catalogue = _catalogue_text()
    candidates: dict[str, dict[str, Any]] = {}

    def add(term: str, source: str, score: float) -> None:
        clean = re.sub(r"\s+", " ", (term or "").strip().lower())
        if len(clean) < 4 or clean in {"shorts", "science", "français", "francais"}:
            return
        if clean not in candidates:
            candidates[clean] = {
                "term": clean,
                "score": 0.0,
                "sources": set(),
                "in_catalogue": clean in catalogue,
            }
        candidates[clean]["score"] += score
        candidates[clean]["sources"].add(source)

    for item in competitor.get("title_keywords", []) or []:
        add(str(item.get("keyword", "")), "competitor_title", float(item.get("score") or 0))
    for item in competitor.get("high_value_tags", []) or []:
        add(str(item.get("tag", "")), "competitor_tag", float(item.get("score") or 0) * 0.6)
    for item in comments.get("topic_requests", []) or []:
        add(str(item.get("topic", "")), "audience_comment", float(item.get("count") or 1) * 2.0)

    rows = []
    for data in candidates.values():
        rows.append(
            {
                "term": data["term"],
                "score": round(data["score"], 3),
                "sources": sorted(data["sources"]),
                "in_catalogue": bool(data["in_catalogue"]),
                "recommendation": "cover/refresh" if data["in_catalogue"] else "consider adding to catalogue",
            }
        )
    rows.sort(key=lambda item: (item["in_catalogue"], -item["score"]))
    return rows[:limit]


def build_auto_repair_plan(history: list[dict], min_age_hours: int, low_views: int) -> dict:
    try:
        from channel_seo_audit import analyze_title, build_repair_package
    except Exception as exc:
        return {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "error": f"channel_seo_audit import failed: {exc}",
            "repairs": [],
        }

    repairs = []
    for entry in history:
        vid = entry.get("youtube_video_id")
        if not vid:
            continue
        age = _age_hours(entry)
        if age is None or age < min_age_hours:
            continue
        title = entry.get("title") or ""
        views = int(entry.get("views") or 0)
        retention = entry.get("average_view_percentage")
        retention_val = float(retention or 0)
        if retention_val > 2:
            retention_val /= 100
        title_issues = analyze_title(title)
        reasons = []
        if title_issues:
            reasons.extend(title_issues[:3])
        if views and views < low_views:
            reasons.append(f"low views after {age:.0f}h: {views} < {low_views}")
        if retention_val and retention_val < 0.30:
            reasons.append(f"low retention: {retention_val:.1%}")
        if not reasons:
            continue
        row = {
            "id": vid,
            "title": title,
            "topic": entry.get("topic") or title,
            "series_title": entry.get("series_title") or "",
            "base_phenomenon": entry.get("base_phenomenon") or "",
            "nominal_phrase": entry.get("nominal_phrase") or "",
            "question_phrase": entry.get("question_phrase") or "",
            "views": views,
            "title_issues": title_issues,
        }
        pkg = build_repair_package(row, None)
        repairs.append(
            {
                "id": vid,
                "url": f"https://youtu.be/{vid}",
                "age_hours": round(age, 1),
                "views": views,
                "current_title": title,
                "reasons": reasons,
                "proposed_title": pkg.get("title"),
                "proposed_description": pkg.get("description"),
                "proposed_tags": pkg.get("tags", []),
            }
        )
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "policy": "Plan only. Apply via SEO Repair workflow after review.",
        "min_age_hours": min_age_hours,
        "low_view_threshold": low_views,
        "repairs": repairs,
    }


def build_dashboard(
    history: list[dict],
    bandit: dict,
    repairs: dict,
    gaps: list[dict],
    comments: dict,
    slot_intel: dict,
) -> str:
    uploaded = [v for v in history if v.get("youtube_video_id")]
    recent = uploaded[-10:]
    lines = [
        "# SKILLOR — Premium Growth Dashboard\n",
        f"_Generated {datetime.now(UTC).isoformat()}_\n",
        "## Executive summary\n",
        f"- Videos in history: **{len(uploaded)}**\n",
        f"- 48h repair candidates: **{len(repairs.get('repairs', []))}**\n",
        f"- Topic-gap ideas: **{len(gaps)}**\n",
        "- Dynamic publish slots: "
        + ", ".join(s["slot"] for s in slot_intel.get("recommended_slots", []))
        + "\n",
    ]
    if slot_intel.get("recommended_slots"):
        lines.append("\n## Dynamic publish-time learning\n")
        lines.append("| Paris slot | Score | Samples | Prior |\n|---|---:|---:|---:|\n")
        for row in slot_intel.get("recommended_slots", []):
            lines.append(f"| `{row['slot']}` | {row['score']} | {row['samples']} | {row['prior']} |\n")

    top_patterns = bandit.get("preferred_patterns", [])[:5]
    if top_patterns:
        lines.append("\n## Title-pattern bandit\n")
        lines.append("| Pattern | Score | Samples | Competitor prior |\n|---|---:|---:|---:|\n")
        for row in top_patterns:
            lines.append(
                f"| `{row['pattern']}` | {row['score']} | {row['observed_samples']} | {row['competitor_prior']} |\n"
            )
    if repairs.get("repairs"):
        lines.append("\n## 48h auto-repair plan\n")
        for item in repairs["repairs"][:10]:
            lines.append(
                f"- [{item['current_title']}](https://youtu.be/{item['id']}) → "
                f"**{item['proposed_title']}** (`{'; '.join(item['reasons'][:2])}`)\n"
            )
    if gaps:
        lines.append("\n## Topic gaps / demand signals\n")
        for item in gaps[:15]:
            status = "in catalogue" if item["in_catalogue"] else "new gap"
            lines.append(
                f"- **{item['term']}** — {status}, score {item['score']} ({', '.join(item['sources'])})\n"
            )
    if comments.get("topic_requests"):
        lines.append("\n## Audience comment requests\n")
        for item in comments["topic_requests"][:10]:
            lines.append(f"- {item['topic']} ×{item['count']}\n")
    if recent:
        lines.append("\n## Latest uploads\n")
        for item in reversed(recent):
            lines.append(
                f"- {item.get('posted_at') or item.get('publish_at')}: "
                f"{item.get('title')} ({item.get('views', 'n/a')} views)\n"
            )
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--history", default=str(DATA / "video_history.json"))
    parser.add_argument("--competitor", default=str(DATA / "competitor_intel_fr.json"))
    parser.add_argument("--comments", default=str(DATA / "comments_intel_fr.json"))
    parser.add_argument(
        "--min-age-hours", type=int, default=int(os.environ.get("AUTO_REPAIR_MIN_AGE_HOURS", "48"))
    )
    parser.add_argument(
        "--low-views", type=int, default=int(os.environ.get("AUTO_REPAIR_LOW_VIEW_THRESHOLD", "200"))
    )
    args = parser.parse_args(argv)

    history = _load_json(Path(args.history), [])
    history = history if isinstance(history, list) else []
    competitor = _load_json(Path(args.competitor), {})
    comments = _load_json(Path(args.comments), {})

    competitor_data = competitor if isinstance(competitor, dict) else {}
    comments_data = comments if isinstance(comments, dict) else {}
    bandit = build_title_bandit(history, competitor_data)
    slot_intel = build_upload_slot_intel(history)
    gaps = build_topic_gaps(competitor_data, comments_data)
    repairs = build_auto_repair_plan(history, args.min_age_hours, args.low_views)

    bandit_path = DATA / "title_bandit_fr.json"
    slot_path = DATA / "upload_slot_intel_fr.json"
    gaps_path = DATA / f"topic_gap_recommendations_{TODAY.strftime('%Y%m%d')}.json"
    repair_path = DATA / f"auto_repair_plan_{TODAY.strftime('%Y%m%d')}.json"
    dashboard_path = DATA / f"premium_growth_dashboard_{TODAY.strftime('%Y%m%d')}.md"

    _write_json(bandit_path, bandit)
    _write_json(slot_path, slot_intel)
    _write_json(gaps_path, {"generated_at_utc": datetime.now(UTC).isoformat(), "gaps": gaps})
    _write_json(repair_path, repairs)
    dashboard = build_dashboard(history, bandit, repairs, gaps, comments_data, slot_intel)
    dashboard_path.write_text(dashboard, encoding="utf-8")

    LOG.info("Wrote title bandit: %s", bandit_path)
    LOG.info("Wrote upload slot intelligence: %s", slot_path)
    LOG.info("Wrote topic gaps: %s", gaps_path)
    LOG.info("Wrote auto-repair plan: %s", repair_path)
    LOG.info("Wrote dashboard: %s", dashboard_path)
    print(dashboard)
    return 0


if __name__ == "__main__":
    sys.exit(main())
