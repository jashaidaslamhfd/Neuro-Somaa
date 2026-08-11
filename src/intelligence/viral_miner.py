#!/usr/bin/env python3
"""Winner cloning — the fastest honest growth mechanic on Shorts.

When a video over-performs the channel baseline, the biggest EV move is not
optimization of what exists — it is shipping 2-3 ADJACENT videos within days,
while the algorithm is actively looking for more of that pattern.

This miner:
  1. finds over-performers (the anomaly layer's 'over' anomalies + top decile),
  2. extracts each winner's core phenomenon (first content words after the
     interrogative — the stable part),
  3. builds adjacent French question topics from a contextual variant bank,
  4. filters near-duplicates of anything published in the last N topics,
  5. writes data/winner_fastlane.json (rolling, TTL 4 days) which
     trend_fetcher consumes with FIRST priority at the next generation runs.

All variants are grammatical French questions with a verb — they pass the
same french_quality_gate as catalogue topics before ever uploading.
"""
from __future__ import annotations

import json
import re
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FASTLANE_PATH = ROOT / "data" / "winner_fastlane.json"
FASTLANE_TTL_HOURS = 96  # 4 days — clone while the algorithm still cares

# Context variants that stay grammatical after "Pourquoi <phénomène au présent>"
_VARIANTS = (
    "quand tu es stressé",
    "la nuit pendant ton sommeil",
    "plus chez certaines personnes",
    "quand tu vieillis",
    "après un effort soudain",
    "au réveil",
    "chez les sportifs",
    "au moment où tu t'y attends le moins",
    "quand tu es amoureux",
    "plus souvent en hiver",
)

_INTERROGATIVE = re.compile(r"^(pourquoi|comment|est-ce que|quand|combien de)\s+", re.IGNORECASE)


def _phenomenon_core(title: str, max_words: int = 5) -> str:
    """'Pourquoi le cœur bat plus vite avant de parler en public ?'
       -> 'le cœur bat plus vite'   (the stable, clonable core).

    Cut at the first context marker (avant/quand/pendant/…) — the context is
    exactly what the variant bank REPLACES, so it must not ride along.
    """
    body = _INTERROGATIVE.sub("", (title or "").strip()).rstrip(" ?!.")
    words = body.split()
    cut_markers = {"avant", "quand", "pendant", "après", "apres", "chez", "sans",
                   "avec", "dès", "des", "lors", "parce", "car", "en", "si"}
    cut = next((i for i, w in enumerate(words) if w.lower() in cut_markers), len(words))
    return " ".join(words[:min(cut, max_words)]).strip()


def _norm(text: str) -> str:
    return re.sub(r"[^a-zà-ÿœæ ]", "", (text or "").lower()).strip()


def _too_similar(candidate: str, recent_norm: list[str], shared_threshold: int = 4) -> bool:
    cand_words = set(_norm(candidate).split()) - {"le", "la", "les", "de", "du", "des", "se", "en", "un", "une"}
    for old in recent_norm:
        old_words = set(old.split()) - {"le", "la", "les", "de", "du", "des", "se", "en", "un", "une"}
        if cand_words and len(cand_words & old_words) >= shared_threshold:
            return True
    return False


def mine_winner_fastlane(history: list[dict], anomalies: dict,
                         max_entries: int = 9, recent_n: int = 90) -> dict:
    """Build the cloning fastlane. Empty-but-valid when no over-performer exists."""
    winners = []
    seen_ids = set()
    for a in anomalies.get("anomalies", []):
        if a.get("direction") == "over":
            winners.append((a["views"], a["title"], a["video_id"]))
            seen_ids.add(a["video_id"])
    # top-decile backup so a brand-new winner without anomaly-flag still clones
    scored = [(int(e.get("views", 0)), str(e.get("title") or ""), e.get("youtube_video_id"))
              for e in history or [] if isinstance(e.get("views"), int)]
    if scored:
        scored.sort(reverse=True)
        cutoff = max(3, len(scored) // 10)
        for views, title, vid in scored[:cutoff]:
            if vid not in seen_ids and title:
                winners.append((views, title, vid))
                seen_ids.add(vid)

    recent_norm = [_norm(str(e.get("topic") or e.get("title") or ""))
                   for e in (history or [])[-recent_n:]]

    fastlane: list[dict] = []
    for views, title, vid in sorted(winners, reverse=True):
        core = _phenomenon_core(title)
        if len(core.split()) < 3:
            continue
        # Verbal cores only: "le ventre se serre" + variant = valid question;
        # nominal cores ("l'apparition soudaine de la chair") + adverbial
        # variant produce broken French — skip them, deterministic templates
        # can't safely re-engineer a noun phrase.
        from french_quality_gate import has_french_verb
        if not has_french_verb(core):
            continue
        # Near-dupe guard compares against every recent topic EXCEPT the
        # winner itself (clones necessarily share their parent's core words).
        source_norm = _norm(title)
        others = [r for r in recent_norm if r != source_norm]
        start = zlib.crc32(title.encode()) % len(_VARIANTS)
        for i in range(len(_VARIANTS)):
            variant = _VARIANTS[(start + i) % len(_VARIANTS)]
            candidate = f"Pourquoi {core} {variant} ?"
            if _norm(candidate) == source_norm or _too_similar(candidate, others):
                continue
            fastlane.append({
                "topic": candidate,
                "series_number": f"W{len(fastlane)+1:02d}",
                "cloned_from": {"video_id": vid, "views": views, "title": title[:70]},
            })
            break  # one clone per winner — variety beats volume
        if len(fastlane) >= max_entries:
            break

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ttl_hours": FASTLANE_TTL_HOURS,
        "policy": "ship adjacent clones of over-performers while the algorithm seeks more",
        "fastlane": fastlane,
    }
    FASTLANE_PATH.parent.mkdir(exist_ok=True)
    FASTLANE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def load_fresh_fastlane(path: Path | None = None) -> list[dict]:
    """trend_fetcher-facing reader. Returns [] when absent/stale."""
    p = path or Path(__import__("os").environ.get("VIRAL_FASTLANE_PATH", str(FASTLANE_PATH)))
    try:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(data["generated_at"])
        if datetime.now(timezone.utc) - generated > timedelta(hours=FASTLANE_TTL_HOURS):
            return []
        return [e for e in data.get("fastlane", []) if e.get("topic")]
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return []
