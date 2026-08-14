"""
Demand-queue refresh (2026-08-15): auto-mine LIVE French YouTube
autocomplete demand so search_demand_queue_fr.json never goes stale.

WHY: the original queue was hand-mined once (2026-08-11, 6 entries). Once
consumed by the topic selector it is never refilled — the pipeline silently
falls back to blind catalogue guesses, and every video after that is 100%
guess-based. Real, measured search demand is the strongest *organic* growth
signal available (users actively type these queries → videos answer them →
they surface in YouTube search + suggested → 100% organic traffic).

HOW: seeds come from two proven organic sources —
  1. channel WINNERS (1000+ view phenomena, mined via winner_pillar +
     performance_state so we mine demand around what already works),
  2. evergreen body-glitch catalogue subjects (broad seeds = fresh queries
     outside the winner circle).
Each seed hits the free suggestqueries endpoint (client=firefox, hl/gl=fr,
ds=yt — the same endpoint and client that worked in fr_batch_optimize on CI),
with polite 0.35s spacing and relevance/garbage guards identical to the
repair miner. The refreshed queue is written atomically (temp + rename) with
max 40 entries (queue must stay consumable in weeks, not years).

INVOKED: called from the daily intelligence sync (analytics) and from the
main pipeline before topic selection when the queue is empty or older than
REFRESH_MAX_AGE_DAYS. Never raises — a mining failure must never stop the
pipeline from publishing.
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

QUEUE_PATH = Path("data/search_demand_queue_fr.json")
MAX_ENTRIES = 40
REFRESH_MAX_AGE_DAYS = 4
SEEDS_PER_PASS = 6
MAX_API_CALLS = 40
MIN_CALL_SPACING = 0.35

_DEMAND_RE = re.compile(r"'([^']+)'")

_LEAK_SUFFIX_PATS = [
    r"\s*peut\s+sembler\s+étrange\s*$", r"\s*peut\s+sembler\s*$",
    r"\s*semble\s+soudain\s*$", r"\s*arrive\s*$", r"\s*devient\s*$",
    r"\s*se\s*$", r"\s*la\s*$", r"\s*le\s*$",
]


def _clean_subject(text: str) -> str:
    """Strip LLM leak suffixes and any leading 'Ce qu'il faut comprendre sur '
    framing so the miner seeds are real phenomenon names, not essay titles."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    for framing in ("ce qu'il faut comprendre sur ", "ce que votre corps vous dit quand ",
                    "ce qui se passe quand ", "quand "):
        if t.lower().startswith(framing):
            t = t[len(framing):]
            break
    for pat in _LEAK_SUFFIX_PATS:
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    return t.strip().rstrip(" .?,!")


def _short_core(topic: str) -> str:
    """Derive a natural SEARCH-LIKE core (<=7 words) from an essay-style
    topic. Long awkward phrases get 0 Google suggestions; short natural
    ones get many. E.g. 'le muscle qui tressaille tout seul' -> core stays
    'le muscle qui tressaille tout seul'; 'ce qui se passe quand le ventre
    se serre lors d'une peur' -> 'le ventre se serre lors d'une peur'."""
    t = _clean_subject(topic)
    # strip leftover question/essay framing that _clean_subject missed so
    # the core is a natural search phrase, never 'pourquoi pourquoi ...'
    for prefix in ("pourquoi ", "pourquoi le ", "pourquoi la ", "pourquoi les ",
                   "pourquoi mon ", "pourquoi ma ", "pourquoi on ",
                   "comprendre ", "ce qui se passe quand ", "ce qui se passe ",
                   "ce que la science explique sur ",
                   "ce que votre corps vous dit quand ",
                   "ce qu'il faut comprendre sur ", "quand "):
        if t.lower().startswith(prefix):
            t = t[len(prefix):]
            break
    t = _clean_subject(t)
    toks = [w for w in re.split(r"\s+", t) if w]
    if len(toks) <= 7:
        return " ".join(toks)
    # find the densest 4-7 word span containing the most topic-words
    words = _topic_words(t)
    best, best_score = t, max(1, len(words))
    for width in range(7, 3, -1):
        for i in range(len(toks) - width + 1):
            span = " ".join(toks[i:i + width])
            score = len(_topic_words(span) & words)
            if score > best_score:
                best, best_score = span, score
    return best


# evergreen FR question stems — guarantee a floor of suggestions even
# when no winner/catalogue seed matches real search phrasing
_EVERGREEN_STEMS = [
    "pourquoi le corps fait des choses bizarres",
    "pourquoi on a des sensations bizarres",
    "pourquoi la peau fait des choses bizarres",
    "sensations bizarres dans le corps",
]


def _topic_words(text: str) -> set[str]:
    try:
        from trend_fetcher import _topic_words as _tw
        return _tw(text)
    except Exception:  # pragma: no cover - defensive, same as callers
        stop = {"le", "la", "les", "un", "une", "du", "des", "de", "et", "ou",
                "que", "qui", "quoi", "quand", "sans", "pour", "sur", "dans",
                "par", "a", "au", "aux", "ton", "ta", "tes", "votre", "mon",
                "ma", "mes", "son", "sa", "ses", "ce", "cette", "ces", "il",
                "elle", "je", "tu", "nous", "vous", "ils", "elles", "y", "en",
                "pas", "ne", "n", "est", "sont", "se", "l", "d"}
        toks = [w for w in re.split(r"\s+", (text or "").lower()) if w and len(w) >= 3]
        return {w.strip("'\".,;:!?-") for w in toks} - stop


def _winner_subjects(limit: int = 6) -> list[str]:
    """Subjects of proven winner topics (1000+ views) — demand mining starts
    from what the channel already wins with."""
    try:
        from intelligence.features import WINNER_VIEWS  # standard constants
        _ = WINNER_VIEWS
    except Exception:
        pass
    try:
        state = json.loads(Path("data/performance_state.json")
                           .read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    winners = []
    for item in state.get("top_topics_by_views", []) or []:
        views = item.get("avg_views", 0) or 0
        n = item.get("n", 0) or 0
        if views >= 1000 and n >= 1 and item.get("topic"):
            winners.append(item["topic"])
        if len(winners) >= limit:
            break
    if not winners:
        winners = ["le ventre se serre lors d'une peur",
                   "les genoux qui craquent",
                   "un aliment froid provoque un mal de tête"]
    out = []
    for t in winners:
        core = _short_core(t)
        if core:
            out.append(core)
    # floor of evergreen stems so a queue refresh never returns empty
    if not out:
        out = _EVERGREEN_STEMS[:2]
    return out or ["corps"]


def _catalogue_subjects(limit: int = 4) -> list[str]:
    """Evergreen catalogue subjects as broad seeds (fresh queries outside the
    winner circle). Cheap to compute; failures degrade to []."""
    try:
        from trend_fetcher import get_body_glitch_topics
        pool = get_body_glitch_topics()
    except Exception:
        return []
    try:
        from video_history import load_history  # history shapes vary; best-effort
        history = load_history()
        hist_topics = {(h.get("topic") or h.get("title") or "").lower()
                       for h in (history or [])}
    except Exception:
        hist_topics = set()
    picked = []
    random.seed(42)  # deterministic seed selection — reproducible miners
    for item in random.sample(pool, min(len(pool), 60)):
        topic = (item.get("topic") or item.get("base_phenomenon") or "").lower()
        if not topic or topic in hist_topics or any(t in topic for t in picked):
            continue
        # strip leading pourquoi prefix and essay framing
        topic = _clean_subject(topic)
        core = _short_core(topic)
        if 8 <= len(core) <= 60:
            picked.append(core)
        if len(picked) >= limit:
            break
    return picked + _EVERGREEN_STEMS[:2]


def _mine_seed(seed: str, *, max_calls: int = MAX_API_CALLS) -> tuple[list[str], int]:
    """Mine live FR autocomplete suggestions for one seed. Never raises.
    Returns (queries, actual_api_calls) so the caller can budget fairly."""
    import requests as _rq
    out, seen, calls = [], set(), 0
    ref = _topic_words(seed)
    # never double a leading question word — 'pourquoi pourquoi ...' is
    # dead weight that returns 0 suggestions
    if any(seed.lower().startswith(q) for q in
           ("pourquoi ", "comment ", "que faire ", "quand ", "où ")):
        stems = [f"causes de {seed}", f"que faire quand {seed}", seed]
    else:
        stems = [f"pourquoi {seed}", f"causes de {seed}",
                 f"que faire quand {seed}", seed]
    stems = [s[:60] for s in stems]
    for s in stems:
        if calls >= max_calls:
            break
        calls += 1  # one stem = one HTTP call budgeted
        suggestions = []
        for attempt in range(2):  # one retry on rate-limit (429/403)
            try:
                r = _rq.get("https://suggestqueries.google.com/complete/search",
                            params={"client": "firefox", "hl": "fr", "gl": "fr",
                                    "ds": "yt", "q": s},
                            timeout=6, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code in (429, 403):
                    if attempt == 0:
                        time.sleep(5.0)
                        continue
                    suggestions = []
                else:
                    suggestions = r.json()[1] if r.ok else []
                break
            except Exception:
                suggestions = []
                if attempt == 0:
                    time.sleep(3.0)
                    continue
                break
        time.sleep(MIN_CALL_SPACING)
        for p in suggestions or []:
            p = str(p).strip().lower()
            if not (10 <= len(p) <= 90) or p in seen:
                continue
            toks = [w for w in re.split(r"\s+", p) if w]
            if len(toks) < 3:
                continue  # too short to be a video-worthy demand query
            if len(toks) >= 4 and len(toks) != len(set(toks)) \
                    and any(len(w) >= 4 for w in toks):
                continue  # degenerate repeat ('la peau la peau la peau')
            words = _topic_words(p)
            shared = words & ref
            if not shared:
                continue
            # relevance guard: accept when 2+ shared words, or one long
            # shared word, or the suggestion essentially IS the phenomenon
            # itself (e.g. 'sommeil paradoxal' from a sleep-topic seed —
            # pure demand, not noise). 'shared' is always non-empty here,
            # so the guard is really a strength check.
            strong = (len(shared) >= 2) or (max(len(w) for w in shared) >= 6)
            is_phenomenon = len(words - ref) <= 1
            if not (strong or is_phenomenon):
                continue
            seen.add(p)
            out.append(p)
    return out[:4], calls


def _subject_to_record(topic: str, queries: list[str], *, index: int) -> dict:
    """Build one demand record in the same shape as the original queue."""
    notes = "; ".join(f"autocomplete: '{q}'" for q in queries)
    title = topic[0].upper() + topic[1:]
    return {
        "series_number": f"DEM-{index}",
        "series_title": title if len(title) <= 60 else title[:57] + "...",
        "topic": topic,
        "nominal_phrase": topic,
        "question_phrase": f"pourquoi {topic}",
        "demand_note": notes,
        "pillar": "reflexes_du_corps",
        "mined_at": datetime.now(timezone.utc).isoformat(),
    }


def _queue_is_stale() -> bool:
    try:
        payload = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    topics = payload.get("topics") if isinstance(payload, dict) else payload
    if not isinstance(topics, list) or len(topics) < 2:
        return True
    mined_at = (payload.get("mined_at") or "")
    if not mined_at:
        return True
    try:
        when = datetime.fromisoformat(mined_at)
    except ValueError:
        return True
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now - when).days >= REFRESH_MAX_AGE_DAYS


def refresh_demand_queue() -> bool:
    """Refresh search_demand_queue_fr.json when stale/empty. Idempotent and
    pipeline-safe: returns False (no-op) when the queue is still fresh."""
    if not _queue_is_stale():
        logger.info("Demand queue still fresh — no refresh needed")
        return False
    logger.info("🔎 Refreshing FR search-demand queue from live autocomplete...")
    subjects = []
    try:
        subjects.extend(_winner_subjects(limit=SEEDS_PER_PASS))
    except Exception as exc:
        logger.warning("Winner-subject mining failed: %s", exc)
    try:
        subjects.extend(_catalogue_subjects(limit=SEEDS_PER_PASS))
    except Exception as exc:
        logger.warning("Catalogue-seed mining failed: %s", exc)
    # de-dupe keeping order
    subjects = list(dict.fromkeys(subj.lower().strip() for subj in subjects
                                  if subj and len(subj.strip()) >= 5))

    records, api_calls = [], 0
    for subj in subjects:
        if api_calls >= MAX_API_CALLS:
            break
        try:
            queries, used = _mine_seed(subj, max_calls=max(1, MAX_API_CALLS - api_calls))
        except Exception as exc:
            logger.warning("Seed %r failed: %s", subj, exc)
            continue
        api_calls += used or 1
        if queries:
            records.append(_subject_to_record(subj, queries,
                                              index=len(records) + 1))
        time.sleep(MIN_CALL_SPACING)

    if not records:
        logger.warning("Demand refresh produced 0 records — keeping old queue")
        return False

    payload = {
        "source": "YouTube France autocomplete (suggestqueries, hl=fr gl=fr) "
                  f"mined {datetime.now(timezone.utc):%Y-%m-%d}",
        "mined_at": datetime.now(timezone.utc).isoformat(),
        "topics": records[:MAX_ENTRIES],
    }
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="demand_", dir=QUEUE_PATH.parent,
                               suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, QUEUE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    logger.info("✅ Demand queue refreshed: %d subjects, mined %d queries",
                len(records), sum(1 for r in records for _ in _DEMAND_RE.findall(r.get("demand_note", "") or "")))
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")
    refresh_demand_queue()
