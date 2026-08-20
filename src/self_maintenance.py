"""
src/self_maintenance.py

Daily self-healing pass for the SKILLOR French channel.

This runs AFTER the analytics sync (see src/analytics_updater.py), once real
YouTube numbers exist for videos that are at least 24-48h old. It is the piece
that makes the channel maintain itself instead of needing a human to notice a
problem and dispatch a one-shot workflow by hand.

Three jobs, in order:

1. SCHEDULE HEALTH — verify the learned publish slots still cover the two
   daily Paris peaks (18:30 + 21:00 CET per 2026-08-21 schedule change) and
   are spaced far enough apart. A broken or collapsed schedule means videos
   pile onto one slot, which is exactly how a day silently drops to zero
   uploads.

2. UPLOADED-VIDEO REPAIR — re-check videos ALREADY on the channel for the
   defects the pipeline now blocks at generation time (truncated titles,
   English tags on a French channel, missing/duplicate descriptions). Older
   uploads were created before those gates existed, so they keep under-
   performing until something rewrites them.

3. PIPELINE HEALTH — record whether the last generation runs actually produced
   videos, so a silent outage (tests failing, quota exhausted) shows up in the
   report instead of being discovered days later by a human noticing low views.

SAFETY: repair is DRY-RUN by default. Nothing on YouTube is rewritten unless
SELF_MAINTENANCE_APPLY=true is set. Every step is individually non-fatal — a
maintenance pass must never take down the analytics job that calls it.

Usage:
    python src/self_maintenance.py            # report only
    SELF_MAINTENANCE_APPLY=true python src/self_maintenance.py
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

logger = logging.getLogger(__name__)

UTC = timezone.utc

HISTORY_PATH = ROOT_DIR / "data" / "video_history.json"
SLOT_INTEL_PATH = ROOT_DIR / "data" / "upload_slot_intel_fr.json"

# 2026-08-21: owner moved the channel to 2 quality videos/day at French peak
# slots (18:30 + 21:00 Paris). A day is healthy when two videos were
# published; below this the channel is losing reach it paid the compute for.
EXPECTED_VIDEOS_PER_DAY = 2
# Two videos landing within this many minutes compete with each other in the
# same Shorts feed refresh instead of covering separate audience peaks.
MIN_SLOT_GAP_MINUTES = 90
# YouTube titles are cut in the Shorts UI well before the API's 100-char cap.
MAX_SAFE_TITLE_CHARS = 70
# Below this a title carries no searchable topic — "Corps lourd" tells a
# scroller nothing and ranks for nothing.
MIN_USEFUL_TITLE_CHARS = 25

# A French title that stops on one of these words was cut off by a length
# budget mid-sentence — the reader never gets the payload. Real examples from
# this channel: "...entendre son cœur battre la", "...quand le silence devient".
# Articles/prepositions/auxiliaries can never legitimately end a French title.
DANGLING_FRENCH_ENDINGS = {
    "le", "la", "les", "l", "un", "une", "des", "du", "de", "d",
    "au", "aux", "à", "et", "ou", "en", "dans", "sur", "sous", "par",
    "pour", "avec", "sans", "que", "qui", "quand", "dont", "où",
    "ce", "cet", "cette", "ces", "son", "sa", "ses", "leur", "leurs",
    "mon", "ma", "mes", "ton", "ta", "tes", "notre", "votre",
    "est", "sont", "être", "avoir", "peut", "semble", "devient", "fait",
    "plus", "moins", "très", "trop", "si", "ne", "se", "on",
}

# "Pourquoi le hoquet commence brusquement ?" is a question. "Pourquoi le
# muscle qui tressaille tout seul ?" is not — it is a noun phrase with a
# question mark bolted on, which reads as broken French. A real question needs
# a conjugated verb, and a relative "qui/que" clause swallowing it is the tell.
INTERROGATIVE_OPENERS = ("pourquoi", "comment", "quand", "où", "qui", "que", "quoi")


def _apply_enabled() -> bool:
    return os.environ.get("SELF_MAINTENANCE_APPLY", "false").strip().lower() == "true"


def _load_history() -> list[dict]:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read video history: %s", exc)
        return []
    if isinstance(data, list):
        return data
    return data.get("videos", []) if isinstance(data, dict) else []


def _parse_dt(value):
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _slot_gap_minutes(a: dict, b: dict) -> int:
    """Smallest wrap-around distance in minutes between two daily slots."""
    minutes_a = int(a.get("hour", 0)) * 60 + int(a.get("minute", 0))
    minutes_b = int(b.get("hour", 0)) * 60 + int(b.get("minute", 0))
    raw = abs(minutes_a - minutes_b)
    return min(raw, 1440 - raw)


def check_schedule_health() -> dict:
    """Confirm the learned slots really deliver three separated daily peaks."""
    problems: list[str] = []
    try:
        intel = json.loads(SLOT_INTEL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "slots": [],
            "problems": [f"upload_slot_intel_fr.json unreadable ({exc}); "
                         "scheduler will fall back to default French peaks"],
        }

    slots = intel.get("recommended_slots") or []
    if len(slots) < EXPECTED_VIDEOS_PER_DAY:
        problems.append(
            f"only {len(slots)} publish slot(s) learned, need {EXPECTED_VIDEOS_PER_DAY} "
            "— some daily runs will have no free peak to claim"
        )

    for i, first in enumerate(slots):
        for second in slots[i + 1:]:
            gap = _slot_gap_minutes(first, second)
            if gap < MIN_SLOT_GAP_MINUTES:
                problems.append(
                    f"slots {first.get('slot')} and {second.get('slot')} are only "
                    f"{gap} min apart (<{MIN_SLOT_GAP_MINUTES}); they compete for the same feed"
                )

    # A slot chosen from a single video is noise, not a learned peak. The
    # blended prior in premium_growth_loop should prevent this, so flag it as a
    # regression if it reappears.
    thin = [s.get("slot") for s in slots if int(s.get("samples") or 0) == 1]
    if thin:
        problems.append(
            f"slot(s) {', '.join(str(t) for t in thin)} rest on a single video; "
            "treat their ranking as provisional"
        )

    return {
        "ok": not problems,
        "slots": [s.get("slot") for s in slots],
        "problems": problems,
    }


def check_publishing_cadence(history: list[dict], days: int = 3) -> dict:
    """Count videos actually scheduled per day over the recent window."""
    now = datetime.now(UTC)
    per_day: dict[str, int] = {}
    for offset in range(days):
        per_day[(now - timedelta(days=offset)).date().isoformat()] = 0

    for entry in history:
        when = _parse_dt(entry.get("publish_at") or entry.get("posted_at"))
        if not when:
            continue
        key = when.astimezone(UTC).date().isoformat()
        if key in per_day:
            per_day[key] += 1

    # Today is still in progress, so only completed days can be judged short.
    today = now.date().isoformat()
    short_days = {
        day: count for day, count in per_day.items()
        if count < EXPECTED_VIDEOS_PER_DAY and day != today
    }
    return {
        "ok": not short_days,
        "per_day": per_day,
        "short_days": short_days,
    }


def _ends_mid_phrase(title: str) -> bool:
    """True when a French title stops before it says anything."""
    cleaned = title.strip().rstrip("?!.…").strip()
    if title.strip().endswith(("...", "…")):
        return True
    if not cleaned:
        return False
    last = cleaned.split()[-1].strip(",;:'\u2019").lower()
    if last in DANGLING_FRENCH_ENDINGS:
        return True
    # A subordinate clause that never resolves. "Ce que votre corps vous dit
    # quand le silence" ends on a real noun, so the dangling-word check above
    # passes it, yet the promise ("quand ... WHAT?") is never paid off. This
    # title was still live after the 2026-07-30 repair run for exactly that
    # reason, so the monitor has to catch it independently.
    padded = f" {cleaned.lower()} "
    for opener in (" quand ", " lorsque ", " lorsqu'", " si "):
        if opener in padded:
            tail = padded.rsplit(opener, 1)[1].strip()
            if len(tail.split()) <= 2:
                return True
    return False


def _carries_description_text(title: str) -> bool:
    """True when description/body copy leaked into the title.

    Real example left live by a repair run: "Pourquoi se réveiller avant son
    réveil Dans ce Short on e ?".
    """
    low = (title or "").lower()
    leaked = (
        "dans ce short", "ce short", "abonne", "abonnez", "hashtags",
        "description", "voici", "```", "#", "http", "www.",
    )
    if any(token in low for token in leaked):
        return True
    # A bare trailing "on e" is the tail of a cut-off "on explique". Matching
    # it as a substring would also hit the perfectly good
    # "Pourquoi on entend son cœur battre ?", so anchor it to the end.
    return low.rstrip("?!. ").endswith(" on e")


def _is_malformed_question(title: str) -> bool:
    """True for 'Pourquoi <noun phrase> ?' with no conjugated verb.

    A relative clause ("qui tressaille", "de la chair de poule") leaves the
    interrogative opener with nothing to ask about, so the title reads as an
    unfinished thought even though it carries a question mark.
    """
    stripped = title.strip()
    if not stripped.endswith("?"):
        return False
    words = stripped.rstrip("? ").split()
    if not words or words[0].lower() not in INTERROGATIVE_OPENERS:
        return False
    # "Pourquoi X qui/de ..." — the opener never reaches a main verb.
    lowered = [w.lower().strip(",;:") for w in words]
    if "qui" in lowered[1:] or "l'apparition" in lowered or "le sursaut" in lowered:
        return True
    return False


def find_uploaded_video_defects(history: list[dict]) -> list[dict]:
    """Scan already-published videos for the defects newer gates would block."""
    defects: list[dict] = []
    seen_titles: dict[str, str] = {}

    for entry in history:
        video_id = entry.get("youtube_video_id")
        if not video_id:
            continue
        title = (entry.get("title") or "").strip()
        issues: list[str] = []

        if not title:
            issues.append("missing title")
        else:
            if len(title) > MAX_SAFE_TITLE_CHARS:
                issues.append(f"title {len(title)} chars — truncated in the Shorts UI")
            if _ends_mid_phrase(title):
                issues.append("title ends mid-phrase — the payload is missing")
            if _carries_description_text(title):
                issues.append("description copy leaked into the title")
            if _is_malformed_question(title):
                issues.append("question mark on a phrase with no conjugated verb")
            if len(title) < MIN_USEFUL_TITLE_CHARS:
                issues.append(f"title only {len(title)} chars — too thin to earn a click")
            previous = seen_titles.get(title.lower())
            if previous:
                issues.append(f"duplicate title of {previous}")
            else:
                seen_titles[title.lower()] = video_id

        if issues:
            defects.append({"video_id": video_id, "title": title, "issues": issues})

    return defects


def run_uploaded_video_repair(apply: bool) -> dict:
    """Delegate the actual YouTube rewrite to the existing repair script.

    scripts/metadata_repair.py already knows how to mint compliant French
    metadata and PATCH it onto YouTube; re-implementing that here would create
    a second, drifting copy of the rules.
    """
    if not all(os.environ.get(var) for var in
               ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REFRESH_TOKEN")):
        return {"ran": False, "reason": "YouTube OAuth secrets absent — repair skipped"}

    command = [sys.executable, str(ROOT_DIR / "scripts" / "metadata_repair.py")]
    if apply:
        command.append("--apply")

    try:
        completed = subprocess.run(
            command, cwd=str(ROOT_DIR), capture_output=True, text=True, timeout=900,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return {"ran": False, "reason": f"repair script could not start: {exc}"}

    return {
        "ran": True,
        "applied": apply,
        "exit_code": completed.returncode,
        "tail": (completed.stdout or completed.stderr or "").strip().splitlines()[-5:],
    }


def build_report(schedule: dict, cadence: dict, defects: list[dict], repair: dict) -> str:
    lines = [
        "# SKILLOR — rapport de maintenance automatique",
        f"_Généré {datetime.now(UTC).isoformat()}_",
        "",
        "## 1. Créneaux de publication",
        f"Créneaux appris : {', '.join(schedule['slots']) or 'aucun'}",
    ]
    if schedule["ok"]:
        lines.append("✅ Les deux pics quotidiens distincts sont couverts.")
    else:
        lines.extend(f"⚠️ {problem}" for problem in schedule["problems"])

    lines += ["", "## 2. Cadence réelle (2 vidéos/jour attendues)"]
    for day, count in sorted(cadence["per_day"].items(), reverse=True):
        mark = "✅" if count >= EXPECTED_VIDEOS_PER_DAY else "⚠️"
        lines.append(f"{mark} {day} : {count}/{EXPECTED_VIDEOS_PER_DAY}")
    if cadence["short_days"]:
        lines.append(
            "⚠️ Journées incomplètes — vérifier les échecs du workflow de génération."
        )

    lines += ["", "## 3. Vidéos déjà publiées à réparer"]
    if defects:
        lines.append(f"{len(defects)} vidéo(s) présentent des défauts :")
        for defect in defects[:20]:
            lines.append(f"- `{defect['video_id']}` — {'; '.join(defect['issues'])}")
    else:
        lines.append("✅ Aucun défaut détecté dans les métadonnées historisées.")

    lines += ["", "## 4. Réparation exécutée"]
    if not repair.get("ran"):
        lines.append(f"⏭️ Ignorée : {repair.get('reason')}")
    else:
        mode = "APPLIQUÉE" if repair.get("applied") else "SIMULATION (dry-run)"
        lines.append(f"Mode : {mode} — code de sortie {repair.get('exit_code')}")
        lines.extend(f"    {line}" for line in repair.get("tail", []))
        if not repair.get("applied"):
            lines.append(
                "ℹ️ Définir SELF_MAINTENANCE_APPLY=true pour écrire réellement sur YouTube."
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    apply = _apply_enabled()
    history = _load_history()

    schedule = check_schedule_health()
    cadence = check_publishing_cadence(history)
    defects = find_uploaded_video_defects(history)
    repair = run_uploaded_video_repair(apply) if defects else {
        "ran": False, "reason": "aucun défaut détecté, rien à réparer"
    }

    report = build_report(schedule, cadence, defects, repair)
    out_dir = ROOT_DIR / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    (out_dir / f"self_maintenance_{stamp}.md").write_text(report, encoding="utf-8")

    logger.info("Maintenance: schedule_ok=%s cadence_ok=%s defects=%d repair_ran=%s",
                schedule["ok"], cadence["ok"], len(defects), repair.get("ran"))
    print(report)
    # Always succeed: this is a monitor, and failing it would mask the
    # analytics sync that runs alongside it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
