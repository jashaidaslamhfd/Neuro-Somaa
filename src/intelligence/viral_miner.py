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


def _phenomenon_core(title: str, max_words: int = 7) -> str:
    """'Pourquoi le cœur bat plus vite avant de parler en public ?'
       -> 'le cœur bat plus vite'   (the stable, clonable core).

    Cut at the first context marker (avant/quand/pendant/…) — the context is
    exactly what the variant bank REPLACES, so it must not ride along.

    2026-08-15 audit fix: markers like "en/même/des" were cutting INSIDE a
    noun phrase ("un aliment froid provoque un mal de tête" -> "...provocque
    un", broken French). Determiners/adverbs that continue a noun are now
    skipped: the cut only fires on true context markers followed by a
    non-determiner word.
    """
    body = _INTERROGATIVE.sub("", (title or "").strip()).rstrip(" ?!.")
    words = body.split()
    # Context markers that INTRODUCE a new situation (the variant bank swaps
    # these): en <gerund>, avant de, quand, pendant, après, chez, lors (de),
    # parce que, si. Everything from the first complete marker phrase onward
    # is stripped — otherwise the clone reads "…craque en mâchant quand tu
    # es amoureux" (double context = broken French).
    # "lors d'une peur" stays inside the core ONLY when the fear IS the
    # phenomenon ("ventre se serre lors d'une peur"): here "lors" is followed
    # by a full noun phrase that defines the event itself.
    # Two classes of markers:
    #  - TEMPORAL/CIRCUMSTANTIAL markers ALWAYS start a new situation that the
    #    variant bank must replace ("pendant la nuit" → "au réveil"). They can
    #    never be part of the phenomenon's own name.
    #  - NOUN-PHRASE markers (lors, chez) ONLY attach to a phenomenon when the
    #    following phrase names the event itself ("ventre se serre lors d'une
    #    peur"). "lors d'une peur" is the phenomenon; "lors de la nuit" is not.
    temporal_markers = {"quand", "pendant", "après", "apres", "avant",
                        "après", "si", "lorsque", "lorsque"}
    noun_markers = {"lors", "chez", "parce", "car"}
    strict_markers = temporal_markers | noun_markers
    functional = {"un", "une", "le", "la", "les", "du", "de", "des", "en",
                  "ton", "ta", "tes", "votre", "vos", "même", "meme", "d",
                  "l", "que", "quoi", "ne", "pas", "plus", "tout", "très",
                  "tres", "juste", "seul", "seule", "soudain", "soudainement",
                  "souvent", "jamais", "toujours", "déjà", "deja", "bien"}

    def rest_is_phenomenon_name(rest_words: list[str]) -> bool:
        """True only for noun-phrase markers (lors/chez/parce/car): the rest is
        the event that defines the phenomenon itself ("lors d'une peur").
        Temporal/circumstantial markers can never pass — "pendant la nuit" is
        always replaceable context, never the phenomenon's name."""
        if not rest_words:
            return False
        toks = [t for t in rest_words if t.lower() not in functional]
        from french_quality_gate import has_french_verb
        return (1 <= len(toks) <= 3 and not has_french_verb(" ".join(rest_words)))

    cut = len(words)
    i = 0
    while i < len(words):
        w = words[i].lower()
        if w in strict_markers:
            # consume the marker + its phrase tokens
            phrase = []
            j = i + 1
            while j < len(words) and words[j].lower() in functional:
                phrase.append(words[j])
                j += 1
            if w in noun_markers and rest_is_phenomenon_name(phrase + words[j:j+2]):
                # noun-phrase marker whose object IS the phenomenon — keep,
                # BUT only when no temporal/circumstantial marker follows
                # right after ("lors d'une peur pendant la nuit": the
                # phenomenon ends at "peur", the "pendant" phrase is the
                # swappable context and must NOT ride along).
                following_temporal = next((k for k in range(j, min(j + 4, len(words)))
                                           if words[k].lower() in temporal_markers), None)
                if following_temporal is not None:
                    cut = following_temporal if following_temporal >= 3 else len(words)
                    break
                i = j
                continue
            # temporal/circumstantial marker, or noun-marker without a
            # phenomenon object: strip everything from here onward
            cut = i if i >= 3 else len(words)
            break
        i += 1
    # When an explicit context cut fired, keep everything up to it
    # untruncated ("le ventre se serre lors d'une peur" is the full
    # phenomenon — cutting to max_words drops its defining event).
    core_words = words if cut == len(words) else words[:cut]
    if cut == len(words):
        core_words = core_words[:max_words]  # cap only when whole body kept
    # The cap can land mid-phrase ("un aliment froid provoque un mal de").
    # Trim dangling determiners/prepositions off the CAPPED end so the core
    # always ends on a content word.
    # "sans" and "moment" are included because a core ending on them is
    # always a phrase half-cut ("tout seul sans…", "au moment de…").
    _dangling = {"un", "une", "le", "la", "les", "du", "des", "de", "en",
                 "ton", "ta", "tes", "votre", "vos", "tout", "soudain",
                 "d", "l", "à", "a", "au", "aux", "et", "ou", "sans",
                 "moment", "temps", "raison", "cause"}
    while core_words and core_words[-1].lower() in _dangling:
        core_words.pop()
    core = " ".join(core_words).strip()
    # An explicit context cut is kept untruncated — "le ventre se serre lors
    # d'une peur" is the full phenomenon; a generic cap would drop it.
    # Drop a trailing gerund context ("la mâchoire craque en mâchant" →
    # "la mâchoire craque"): the variant bank supplies the new context and a
    # clone like "…craque en mâchant quand tu es amoureux" is broken French.
    parts = core.split()
    if len(parts) >= 3 and parts[-2] == "en" and parts[-1].endswith("ant"):
        core = " ".join(parts[:-2])
    return core


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
    """Build the cloning fastlane.

    Winner sources (union, deduped, sorted by views desc):
      1. anomaly layer "over" outliers (statistically significant over-performance);
      2. channel-scale winners: any video at or above WINNER_VIEWS views — on a
         small channel the 1000-view bar IS the viral signal, and waiting for a
         statistical outlier (z>3.5) can leave the fastlane empty for months
         (that is exactly what happened in the 2026-08-15 audit: 11 videos over
         1000 views and zero fastlane entries because no anomaly fired);
      3. top-decile backup so a brand-new winner without a flag still clones.
    """
    from intelligence.features import WINNER_VIEWS  # channel-scale winner bar
    winners = []
    seen_ids = set()
    for a in anomalies.get("anomalies", []):
        if a.get("direction") == "over":
            winners.append((a["views"], a["title"], a["video_id"]))
            seen_ids.add(a["video_id"])
    scored = [(int(e.get("views", 0)), str(e.get("title") or ""), e.get("youtube_video_id"))
              for e in history or [] if isinstance(e.get("views"), int)]
    if scored:
        scored.sort(reverse=True)
        # Channel-scale winners: the proven-viral clones the algorithm is
        # actively looking for more of — priority over generic top-decile.
        for views, title, vid in scored:
            if vid in seen_ids or not title:
                continue
            if views >= WINNER_VIEWS:
                winners.append((views, title, vid))
                seen_ids.add(vid)
        # top-decile backup so a rising video near the bar still clones
        cutoff = max(3, len(scored) // 10)
        for views, title, vid in scored[:cutoff]:
            if vid not in seen_ids and title:
                winners.append((views, title, vid))
                seen_ids.add(vid)

    recent_norm = [_norm(str(e.get("topic") or e.get("title") or ""))
                   for e in (history or [])[-recent_n:]]
    # 2026-08-15 audit: the near-dupe guard (4 shared words vs ALL 90 recent
    # topics) blocked every clone of every winner — a body-parts channel
    # inevitably reuses "corps/le/ton/ton" everywhere. Compare only against
    # the WINNER's own immediate neighbourhood (30 topics) so adjacent
    # proven-viral territory stays open. Duplicates of already-published
    # topics are still fully blocked below (exact _norm match + threshold).
    guard_window = max(recent_n // 3, 30)

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
        neighbourhood = recent_norm[-guard_window:]
        neighbours = [r for r in neighbourhood if r != source_norm]
        for i in range(len(_VARIANTS)):
            variant = _VARIANTS[(start + i) % len(_VARIANTS)]
            candidate = f"Pourquoi {core} {variant} ?"
            cand_norm = _norm(candidate)
            if cand_norm == source_norm or cand_norm in others or _too_similar(candidate, neighbours):
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
