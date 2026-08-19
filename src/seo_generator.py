"""SEO français, pensé pour la découverte sur YouTube France et la francophonie."""
import hashlib
import json
import logging
import os
import random
import re

from french_quality_gate import has_french_verb

logger = logging.getLogger(__name__)

TITLE_MAX_LEN = 60          # Shorts feed truncates ~60-70 chars; keep it fully visible
TITLE_MAX_WORDS = 11        # room for a real curiosity/keyword phrase, not just a label
DESCRIPTION_MAX_LEN = 5000
PINNED_COMMENT_MAX_LEN = 200

PLAYLISTS_BY_CATEGORY = {
    "Cerveau": "Cerveau & mémoire",
    "Corps": "Réflexes du corps",
    "Sommeil": "Sommeil expliqué",
    "Science": "Science du quotidien",
}

STOP = {
    "le", "la", "les", "un", "une", "de", "du", "des", "et", "ou", "pourquoi",
    "comment", "dans", "sur", "à", "au", "aux", "ce", "cette", "ces", "votre",
    "vous", "quand", "sans", "cela", "arrive", "peut", "être", "est", "sont",
    "avec", "pour", "que", "qui", "se", "sa", "son", "ses", "on", "il", "elle",
    "ne", "pas", "plus", "quoi", "leur", "leurs", "en", "y", "d", "l",
    # --- Template scaffolding, NOT searchable keywords. ---------------
    # _keywords() turns every long-ish title word into a tag, so the
    # boilerplate of the title templates ("Ce qu'il FAUT COMPRENDRE sur…",
    # "Ce que la science EXPLIQUE sur…") shipped as literal YouTube tags.
    # Live examples on the channel: tags "faut", "qu'il", "comprendre",
    # "explique", "semble", "avant", "moment". Nobody searches those, and
    # they dilute the handful of tags that actually describe the video.
    "faut", "qu'il", "quil", "qu", "comprendre", "explique", "expliquer",
    "science", "derrière", "derriere", "passe", "semble", "sembler",
    "avant", "après", "apres", "moment", "important", "vraiment", "toujours",
    "jamais", "chaque", "aussi", "très", "tres", "bien", "faire", "fait",
    "dit", "dire", "savoir", "voici", "vraie", "vrai", "raison", "chose",
    "choses", "tout", "tous", "toute", "toutes", "autre", "autres", "ainsi",
    "alors", "donc", "mais", "lors", "lorsque", "parfois", "souvent",
    "notre", "nos", "mon", "ma", "mes", "ton", "ta", "tes", "tu", "te",
}

# Words that are legitimate TAGS but useless as HASHTAGS. "science" is a fine
# YouTube tag (people search it) yet as "#science" it is so broad it adds
# nothing to a Short and pushes out a specific one. Kept separate from STOP so
# the tag list is unaffected.
HASHTAG_STOPLIST = {
    "science", "sciences", "corps", "chose", "choses", "facon", "façon",
    "maniere", "manière", "effet", "cause", "raison", "phenomene", "phénomène",
}

# Hard block: this is a France-first channel. English tags were shipped on 11
# live videos ("anatomy", "humanbody", "bodyfacts", "yourbody", …) — on 9 of
# them English outnumbered French tags 10-to-4. That tells YouTube's classifier
# the video targets an English-speaking audience while the audio, captions and
# metadata are French, splitting the very signal the channel depends on.
ENGLISH_TAG_BLOCKLIST = {
    "anatomy", "physiology", "humanbody", "human body", "yourbody", "your body",
    "bodyfacts", "body facts", "bodyparts", "body parts", "bodymystery",
    "bodyawareness", "humanfacts", "humananatomy", "human anatomy",
    "brainfacts", "brain facts", "sciencefacts", "science facts", "didyouknow",
    "facts", "body", "brain", "health", "mindblown", "amazingfacts",
}

CATEGORY_HASHTAGS = {
    "Cerveau": ["#cerveau", "#neurosciences", "#psychologie", "#memoire"],
    "Corps": ["#corpshumain", "#anatomie", "#biologie", "#sante"],
    "Sommeil": ["#sommeil", "#reves", "#insomnie", "#biologie"],
    # "#science" was the lead hashtag here and it is far too broad to help a
    # Short — it competes with every science video on the platform while
    # saying nothing about this channel's niche. Replaced with terms a French
    # viewer of everyday-body-science content actually browses.
    "Science": ["#culturegenerale", "#saviezvous", "#faitsscientifiques", "#corpshumain"],
}

CATEGORY_TAGS = {
    "Cerveau": ["cerveau", "neurosciences", "psychologie", "memoire", "mental"],
    "Corps": ["corps humain", "anatomie", "biologie", "physiologie", "sante"],
    "Sommeil": ["sommeil", "reves", "insomnie", "cycle du sommeil", "repos"],
    "Science": ["science", "culture generale", "faits scientifiques", "curiosites", "phenomenes"],
}

# ---------------------------------------------------------------------------
# Competitor intelligence (optional, public-data based)
# ---------------------------------------------------------------------------
# Premium setup principle: learn patterns from French Shorts that already won
# millions of views, but never clone exact competitor titles/tags wholesale.
# `scripts/competitor_analysis.py` writes this file. If it is absent, SEO falls
# back to the deterministic France-first logic above.
COMPETITOR_INTEL_PATH = os.environ.get("COMPETITOR_INTEL_PATH", "data/competitor_intel_fr.json")
TITLE_BANDIT_PATH = os.environ.get("TITLE_BANDIT_PATH", "data/title_bandit_fr.json")
USE_COMPETITOR_INTEL = os.environ.get("USE_COMPETITOR_INTEL", "true").strip().lower() != "false"
USE_TITLE_BANDIT = os.environ.get("USE_TITLE_BANDIT", "true").strip().lower() != "false"

SAFE_COMPETITOR_TAG_ALLOWLIST = {
    "vulgarisation", "vulgarisation scientifique", "science", "sciences",
    "corps humain", "cerveau", "neurosciences", "psychologie", "anatomie",
    "biologie", "physiologie", "sante", "santé", "sommeil", "memoire",
    "mémoire", "curiosité", "curiosite", "culture generale", "culture générale",
    "faits scientifiques", "france", "français", "francais",
}
LOCALE_TAGS = ["france", "francophonie"]


def _load_competitor_intel() -> dict:
    enabled = os.environ.get("USE_COMPETITOR_INTEL", "true").strip().lower() != "false"
    if not (USE_COMPETITOR_INTEL and enabled):
        return {}
    path = os.environ.get("COMPETITOR_INTEL_PATH", COMPETITOR_INTEL_PATH)
    try:
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _normalised_title_hash(title: str) -> str:
    norm = re.sub(r"[^a-z0-9à-ÿœæ ]", "", (title or "").lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _not_exact_competitor_title(title: str, intel: dict) -> bool:
    hashes = set(intel.get("exact_title_hashes") or [])
    return not hashes or _normalised_title_hash(title) not in hashes


def _safe_competitor_tags(topic: str, category: str, intel: dict, limit: int = 4) -> list[str]:
    """Blend only relevant competitor-derived tags into our tag list.

    We do NOT dump a competitor's entire tag set onto a video. A tag survives
    only if it is a clean French/niche term and either appears in this topic,
    belongs to the category vocabulary, or is a safe broad French-science tag.
    """
    topic_words = set(_keywords(topic, n=12))
    category_words = {t.lower() for t in CATEGORY_TAGS.get(category, [])}
    out: list[str] = []
    for item in intel.get("high_value_tags", []) or []:
        tag = str(item.get("tag", "")).strip().lower()
        if not tag or tag in STOP or tag in ENGLISH_TAG_BLOCKLIST:
            continue
        if tag in out:
            continue
        compact = re.sub(r"\s+", " ", tag)
        overlaps_topic = any(part in topic_words for part in compact.split()) or compact in topic.lower()
        category_safe = compact in category_words or compact in SAFE_COMPETITOR_TAG_ALLOWLIST
        if overlaps_topic or category_safe:
            out.append(compact)
        if len(out) >= limit:
            break
    return out


def _load_title_bandit() -> dict:
    enabled = os.environ.get("USE_TITLE_BANDIT", "true").strip().lower() != "false"
    if not (USE_TITLE_BANDIT and enabled):
        return {}
    path = os.environ.get("TITLE_BANDIT_PATH", TITLE_BANDIT_PATH)
    try:
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _title_pattern_id(title: str) -> str:
    t = (title or "").strip().lower()
    if re.match(r"^pourquoi\b.+\?\s*$", t):
        return "pourquoi-question"
    if t.startswith("pourquoi"):
        return "pourquoi-declarative"
    if t.startswith("ce qui se passe") or t.startswith("ce qui arrive") or t.startswith("ce qui change"):
        return "ce-qui-se-passe"
    if t.startswith("ce que ton corps") or t.startswith("ce que votre corps") or t.startswith("ce que le corps"):
        return "ce-que-corps-revele"
    if t.startswith("ce qu'il faut") or t.startswith("ce qu’il faut"):
        return "ce-quil-faut"
    if t.startswith("la science") or t.startswith("ce que la science"):
        return "la-science"
    if t.startswith("comment"):
        return "comment"
    return "other"


def _candidate_title_ok(title: str) -> bool:
    low = (title or "").lower()
    if "remarque entendre" in low:
        return False
    words = title.split()
    if not words:
        return False
    last = re.sub(r"[^a-zà-ÿœ]", "", words[-1].lower())
    return last not in _DANGLING_ENDINGS


def _load_ml_word_impact() -> dict[str, float]:
    """Load the ML brain's learned per-word view impact.

    `scripts/ml_brain.py` writes data/ml_brain_state.json after training on
    competitor + our own analytics. Positive words (e.g. "serre", "ventre",
    "peur") measurably lifted views on this channel; negative words ("silence",
    "dans", "votre") dragged them down. Ranking candidate titles by the sum of
    their words' learned impact lets the repair/generation layer be driven by
    real data instead of fixed heuristics. Missing file -> empty dict (no-op).
    """
    path = os.environ.get("ML_BRAIN_STATE_PATH", "data/ml_brain_state.json")
    try:
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        impacts = data.get("word_impact") or {}
        return {
            str(k): float(v) for k, v in impacts.items()
            if isinstance(v, (int, float))
        }
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return {}


def _rank_title_options(options: list[str], bandit: dict) -> list[str]:
    """Order candidate titles with the channel-learning bandit + ML word impact.

    Two learned signals combine here:
      * title_bandit  (premium_growth_loop)  -> whole-pattern preference
      * ml_word_impact (ml_brain)            -> per-word view lift
    If both are absent, the SEO generator's deterministic order is preserved.
    """
    if not options:
        return options
    pattern_scores: dict[str, float] = {}
    for row in bandit.get("preferred_patterns", []) or []:
        pattern = row.get("pattern") or row.get("id")
        if pattern:
            try:
                pattern_scores[str(pattern)] = float(row.get("score", 0))
            except (TypeError, ValueError):
                continue

    word_impact = _load_ml_word_impact()
    ml_active = bool(word_impact)
    has_patterns = bool(pattern_scores)
    if not ml_active and not has_patterns:
        return options

    def _word_lift(title: str) -> float:
        if not ml_active:
            return 0.0
        toks = set(_words(title))
        return sum(word_impact.get(w, 0.0) for w in toks if w in word_impact)

    original_index = {title: idx for idx, title in enumerate(options)}
    return sorted(
        options,
        key=lambda title: (
            # A '?' question title ALWAYS outranks everything, including the
            # bandit's favourite pattern. This is the channel's own quality
            # policy: bare/short series labels measured low CTR, and a short
            # 2-3 word label can masquerade as the high-scoring 'other' pattern
            # (e.g. "Chair de poule") — letting it win ships a bad title.
            # Ordering question-ness above the bandit score makes the choice
            # robust no matter what the analytics sync learns.
            1 if title.endswith("?") else 0,
            pattern_scores.get(_title_pattern_id(title), 0.0),
            _word_lift(title),
            -original_index.get(title, 0),
        ),
        reverse=True,
    )


# The `topic` fed into this module is already a fully-formed French angle
# sentence produced upstream (e.g. "Pourquoi une paupière qui tressaille sans
# raison arrive" or "La science derrière le déjà-vu") - see
# scripts/generate_body_glitch_topics.py's ANGLES templates. Re-wrapping it in
# another "Pourquoi {topic}" template would double up ("Pourquoi pourquoi...").
# So variety here comes from re-phrasing/reformatting the angle itself, not
# from stacking a second template on top of it.
_LEADING_STARTERS = (
    "pourquoi", "la science", "ce qui", "ce qu'il", "ce que", "les déclencheurs",
    "le signal", "comprendre", "voici",
)

# 2026-08-19: expanded from 3 to 10 pinned-comment formulas. The channel
# growth play: the pinned comment is the #1 place a French viewer engages
# (reply = comment signal = feed boost). One question-only formula capped
# replies; the new set mixes reply-bait, debate, self-report and tease
# patterns used by the biggest FR Shorts creators — always in tu-register,
# never clickbait, never medical advice.
PINNED_QUESTION_TEMPLATES = [
    # (original set — kept for variety)
    "Ça t'arrive aussi, {topic_short} ? Dis-le en commentaire.",
    "Tu t'es déjà demandé pourquoi {topic_short} ?",
    "Tu veux qu'on explique quel réflexe du corps après {topic_short} ?",
    # Reply-bait: give the tease, make the reply the completion.
    "La vraie raison de {topic_short} est plus bizarre que ça — dis-moi en commentaire si tu l'as déjà vécu.",
    "J'ai lu 3 explications différentes de {topic_short}. Toi, c'est laquelle qui t'a surpris ?",
    # Self-report (viewers love confirming their own body).
    "Réflexe honnête : ça t'est arrivé combien de fois cette semaine, {topic_short} ?",
    # Debate/opinion — the highest reply-density format on FR Shorts.
    "Débat du soir : {topic_short}, réflexe utile ou bug du corps selon toi ? Dis ton choix en commentaire.",
    # Rate-it format — effortless engagement, no typing skill needed.
    "Sur 10, à quel point ça te stress quand {topic_short} ? Note en commentaire.",
    # Tag-a-friend — share signal (shares are the strongest viral weight).
    "Identifie quelqu'un à qui ça arrive TOUT le temps avec {topic_short}.",
    # Tease + next-video pull — keeps the reply + subscribes curiosity.
    "Si tu veux, la prochaine vidéo explore le réflexe OPPOSÉ à {topic_short} — dis-moi si ça t'intéresse.",
]

# 2026-08-19: rotating French growth hashtags. Not stacked on every video
# (broad tags on 100% of videos dilutes them) — a deterministic hash picks 2
# per topic, always AFTER the niche/category hashtags so the algorithm still
# sees a France-first body-science channel, not a generic Shorts farm.
FR_GROWTH_HASHTAGS = [
    "#decouverte", "#apprendre", "#faitssurprenants", "#curiosites", "#savoir", "#cultivetoicerveau", "#expliquesimple", "#shortsfrancais",
]


def _words(v):
    return re.findall(r"[\wÀ-ÿŒœ'-]+", v or "", flags=re.UNICODE)


def _clean_topic(topic: str) -> str:
    """Lowercase the first letter of a mid-sentence topic fragment so it reads
    naturally inside a template like 'Pourquoi <topic>'."""
    t = (topic or "").strip()
    if t and t[0].isupper() and not t[:2].isupper():
        t = t[0].lower() + t[1:]
    return t


# Kept in sync with the templates in scripts/generate_body_glitch_topics.py.
_ANGLE_PREFIXES = (
    "pourquoi ", "la science derrière ", "ce qui se passe quand ",
    "ce qu'il faut comprendre sur ", "ce qui change lorsque ",
    "ce que votre corps vous dit quand ", "ce que la science explique sur ",
    "comprendre pourquoi ", "voici pourquoi ",
)


def _bare_phenomenon(topic: str) -> str:
    """Strip a known angle-starter prefix and trailing ' arrive' so the core
    phenomenon phrase can be dropped into a pinned-comment template without
    duplicating words like 'pourquoi' or 'arrive'."""
    t = _clean_topic(topic)
    low = t.lower()
    for prefix in _ANGLE_PREFIXES:
        if low.startswith(prefix):
            t = t[len(prefix):]
            break
    for suffix in (" arrive", " peut sembler étrange", " semble soudain"):
        if t.lower().endswith(suffix):
            t = t[: -len(suffix)]
            break
    return t.strip() or topic


# Words that must never END a title: cutting here produces visibly broken
# French like "...entendre son cœur battre la" - a real title that shipped.
_DANGLING_ENDINGS = {
    "le", "la", "les", "l", "de", "du", "des", "d", "un", "une",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses",
    "au", "aux", "à", "en", "dans", "sur", "sous", "chez", "avec", "sans",
    "pour", "par", "et", "ou", "ni", "mais", "donc", "car", "que", "qui",
    "quand", "lorsque", "avant", "après", "apres", "si", "ce", "cette", "leur", "leurs", "y",
    # Truncation-safe verbs/adverbs: a title must NEVER end on these — they
    # scream "clipped mid-sentence" in the feed (analytics: dangling verb
    # titles were published live).
    "sembler", "semble", "semblera", "devenir", "devient", "vient", "va",
    "vont", "fait", "faire", "dit", "passe", "se", "est", "sont", "peut",
    "peuvent", "votre", "notre", "vous", "on", "toujours", "souvent",
    "parfois", "soudain", "tout", "tous", "toute", "très", "plus",
    "aussi", "encore", "comment", "pourquoi", "vraiment",
    "arrive", "arrivent", "paraît", "commence", "revient", "reste",
    "deviennent", "semble-t", "donne", "montre", "voit", "entend",
}


# Subordinate-clause openers: cutting BEFORE one of these leaves a head that
# is a complete French phrase, not a mid-sentence chop.
_CLAUSE_BREAKS = (
    " parce que ", " lorsque ", " pendant que ", " pendant ", " quand ",
    " avant ", " après ", " apres ", " sous ", " face à ", " face a ",
    " lors de ", " lors d'", " dans ", " que ",
)

_QUESTION_STARTERS = ("pourquoi", "comment", "combien", "ce qui", "ce qu'")


def _looks_question(head: str) -> bool:
    return head.lower().startswith(_QUESTION_STARTERS)


def _clause_cut(full: str, budget: int) -> str:
    """Try to shorten `full` at a subordinate-clause boundary so the visible
    head remains a complete, natural French phrase.  Returns "" when no clean
    boundary fits the limits."""
    low = full.lower()
    best = ""
    for br in _CLAUSE_BREAKS:
        idx = low.find(br)
        if idx <= 0:
            continue
        head = full[:idx].strip()
        hw = head.split()
        if not (4 <= len(hw) <= TITLE_MAX_WORDS and 20 <= len(head) <= budget):
            continue
        if hw[-1].lower().rstrip("?!.") in _DANGLING_ENDINGS:
            continue
        if len(head) > len(best):
            best = head
    return best


def _truncate_title(text: str, fallback="La science du quotidien") -> str:
    """Shorten a title without ever leaving a visibly broken French fragment.

    Order of preference:
      1. text already fits        -> keep it untouched;
      2. cut at a clause boundary  -> "…quand X" loses the X clause cleanly;
      3. remodel the phenomenon as a short "Pourquoi <phénomène> ?" question;
      4. word-limit truncation + dangling-function-word cleanup (last resort).

    Question-like starters always get their "?" (back)."""
    text = (text or "").strip()
    full = " ".join(_words(text))
    if not full:
        return fallback
    wants_q = text.endswith("?") or _looks_question(full)
    budget = TITLE_MAX_LEN - 2 if wants_q else TITLE_MAX_LEN
    words = full.split()

    def finish(out: str, q: bool) -> str:
        if q and out and not out.endswith("?") and len(out) + 2 <= TITLE_MAX_LEN:
            out += " ?"
        return out or fallback

    # 1) fits already
    if len(words) <= TITLE_MAX_WORDS and len(full) <= budget:
        return finish(full, wants_q)

    # 2) clause-boundary cut
    cut = _clause_cut(full, budget)
    if cut:
        return finish(cut, wants_q and _looks_question(cut))

    # 3) remodel the bare phenomenon as a short question
    bare = _bare_phenomenon(full)
    if bare and bare.lower() != full.lower():
        bwords = bare.split()
        while bwords and (len(" ".join(bwords)) > budget - 9
                          or len(bwords) > TITLE_MAX_WORDS - 2):
            bwords.pop()
        while len(bwords) > 2 and bwords[-1].lower().rstrip("?!.") in _DANGLING_ENDINGS:
            bwords.pop()
        if len(bwords) >= 3:
            return finish("Pourquoi " + " ".join(bwords), True)

    # 4) last resort: word truncation + dangling cleanup
    out = " ".join(words[:TITLE_MAX_WORDS])
    if len(out) > budget:
        out = out[:budget].rsplit(" ", 1)[0]
    parts = out.split()
    while len(parts) > 2 and parts[-1].lower().rstrip("?!.") in _DANGLING_ENDINGS:
        parts.pop()
    out = " ".join(parts).strip()
    return finish(out, bool(parts) and parts[0].lower() == "pourquoi")


def _category(topic):
    x = (topic or "").lower()
    if any(w in x for w in ("sommeil", "rêve", "réveil")):
        return "Sommeil"
    if any(w in x for w in ("cerveau", "mémoire", "déjà-vu", "chanson")):
        return "Cerveau"
    if any(w in x for w in ("corps", "coeur", "cœur", "yeux", "ventre", "main", "muscle", "peau")):
        return "Corps"
    return "Science"


# French elisions that _words() captures as part of a token ("d'une", "l'on",
# "qu'il"). Stripping them turns "d'une" -> "une" (then STOP drops it) instead
# of shipping "d'une" as a literal YouTube tag — a real junk-tag bug on the
# channel. Order in the alternation matters: longer prefixes first.
_ELISION = re.compile(r"^(?:lorsqu|puisqu|jusqu|aujourd|presqu|qu|nous|vous|l|d|j|m|t|s|c|n)'", re.IGNORECASE)


def _keywords(topic, n=8):
    seen, out = set(), []
    for w in _words(topic):
        lw = _ELISION.sub("", w.lower())
        if len(lw) > 3 and lw not in STOP and lw not in seen:
            seen.add(lw)
            out.append(lw)
        if len(out) >= n:
            break
    return out


def _question_title_from_phrase(phrase: str) -> str:
    """Build a natural curiosity title from the catalogue's subject+verb
    phrase (`q` in scripts/generate_body_glitch_topics.py).

    The live channel exposed an end-to-end bug: `_build_title_options()` placed
    a short safe series label first when an angle was long, but the later A/B
    heuristic then promoted the longer secondary angle solely because it had a
    better length score. That produced awkward public titles such as
    "Pourquoi l'apparition soudaine de la chair de poule ?" and
    "Comprendre pourquoi le corps frissonne sous le stress". The catalogue
    already knows the grammatical question form — use it directly.
    """
    p = _clean_topic(phrase or "").strip().rstrip(" .?")
    if not p:
        return ""

    lowered = p.lower()
    if lowered.startswith("comprendre pourquoi "):
        p = p[len("comprendre "):]
    elif lowered.startswith("voici pourquoi "):
        p = p[len("voici "):]

    lowered = p.lower()
    core = p[len("pourquoi "):].strip() if lowered.startswith("pourquoi ") else p

    # Remove catalogue/fluent-angle padding from fallback phrases. The stored
    # `question_phrase` normally has none of this, but user-supplied topics and
    # older data files can still pass the longer angle through this helper.
    for suffix in (" peut sembler étrange", " semble soudain"):
        if core.lower().endswith(suffix):
            core = core[: -len(suffix)].strip()
            break

    if not core:
        return ""
    return _truncate_title(f"Pourquoi {_clean_topic(core)} ?")


def _build_title_options(topic: str, series_title: str, question_phrase: str = "") -> list[str]:
    """Generate real, distinct SEO title candidates from the full French angle
    (topic), not from the already-short branded series title.

    `topic` starts with a phrase like "Pourquoi ...", "La science derrière ...",
    "Ce qui se passe quand ...", etc. When the Body Glitch catalogue supplies
    its grammatical subject+verb form (`question_phrase`), it becomes the first
    candidate so the A/B scorer cannot accidentally promote a clumsy truncated
    noun phrase over a natural French title.
    """
    raw = (topic or "").strip()
    if not raw:
        return [_truncate_title(series_title)] if series_title else []

    capitalized = raw[0].upper() + raw[1:] if raw else raw
    full_angle_text = " ".join(_words(capitalized))
    angle_option = _truncate_title(capitalized)

    # Compare word content, not raw character length: `_truncate_title()` adds
    # a final question mark to question-like titles, and that punctuation alone
    # is not truncation. The old length comparison falsely demoted every clean
    # "Pourquoi ..." angle to the short series label.
    angle_truncated = " ".join(_words(angle_option)).lower() != full_angle_text.lower()
    series_option = _truncate_title(series_title) if series_title else ""

    question_option = _question_title_from_phrase(question_phrase)
    if not question_option and raw.lower().startswith(("comprendre pourquoi ", "voici pourquoi ")):
        question_option = _question_title_from_phrase(raw)

    options = []
    if question_option:
        options.append(question_option)

    if angle_truncated and series_option:
        options.extend([series_option, angle_option])
    else:
        options.append(angle_option)

    starts_with_starter = raw.lower().startswith(_LEADING_STARTERS)

    # A question-mark variant reads naturally only for "Pourquoi ..." / "Ce
    # qui/qu'il ..." style angles, not for noun-phrase statements.
    if raw.lower().startswith(("pourquoi", "ce qui", "ce qu'il")):
        q = capitalized.rstrip(" .") + " ?"
        options.append(_truncate_title(q))

    # If the angle doesn't already open with a curiosity starter, add one -
    # this only fires for topics that came in as a bare phenomenon phrase.
    if not starts_with_starter:
        options.append(_truncate_title(f"Pourquoi {_clean_topic(raw)}"))

    # Short branded series title as a final candidate (dedup keeps the
    # earlier preferred position if it was already promoted above).
    if series_option:
        options.append(series_option)

    return list(dict.fromkeys([o for o in options if o]))[:5]


def _competitor_title_options(topic: str, script_data: dict, intel: dict) -> list[str]:
    """Generate original titles from competitor-winning templates.

    The templates come from `competitor_intel_fr.json`, but the subject phrase
    comes from OUR catalogue/script. Exact title hashes from competitors are
    blocked, so this is pattern transfer, not metadata copying.
    """
    if not intel:
        return []
    question_phrase = script_data.get("question_phrase") or script_data.get("base_question") or ""
    nominal_phrase = (
        script_data.get("nominal_phrase")
        or script_data.get("base_phenomenon")
        or _bare_phenomenon(topic)
    )
    out: list[str] = []
    for item in intel.get("safe_title_templates", []) or []:
        template_id = item.get("id") or item.get("pattern")
        title = ""
        if template_id == "pourquoi-question" and question_phrase:
            title = _question_title_from_phrase(question_phrase)
        elif template_id == "ce-qui-se-passe" and question_phrase:
            title = _truncate_title(f"Ce qui se passe quand {_clean_topic(question_phrase)}")
        elif template_id == "ce-que-corps-revele" and question_phrase:
            title = _truncate_title(f"Ce que ton corps révèle quand {_clean_topic(question_phrase)}")
        elif template_id == "la-science" and nominal_phrase:
            title = _truncate_title(f"La science derrière {_clean_topic(nominal_phrase)}")
        elif template_id == "ce-quil-faut" and nominal_phrase:
            title = _truncate_title(f"Ce qu'il faut savoir sur {_clean_topic(nominal_phrase)}")

        # If competitor intel has no catalogue phrase but the current angle is
        # already a `Pourquoi...` title, we can still produce the safe core
        # question from our own topic.
        if not title and template_id == "pourquoi-question":
            title = _question_title_from_phrase(topic)

        if title and _not_exact_competitor_title(title, intel):
            out.append(title)
    return list(dict.fromkeys(out))[:4]


_LEAK_TOKENS = (
    # description-copy bleed (mirrors metadata_repair._carries_description_text)
    # NOTE: " on e " from the 1XVYcxQqDqo incident is NOT a standalone token —
    # it matched "on entend"/"on est" and false-rejected good titles. The real
    # leak was "Dans ce Short on e ?", which "dans ce short" already catches.
    "dans ce short", "ce short", "abonne", "abonnez", "hashtags",
    "description", "```", "http", "www.",
    # LLM template fragments that reached live titles (2026-07 audits)
    "remarque entendre", "remarque ", "peut sembler ", "peut s",
    "semble soudain", "il faut savoir que", "on va voir",
)
# subordinate-clause openers: a title ending on one is incomplete
_SUBORDINATE_ENDINGS = {"quand", "lorsque", "lorsqu", "si", "que", "qui",
                        "qu'", "parce", "car", "dès", "avant", "après"}


def _title_is_clean(title: str) -> tuple[bool, str]:
    """Prevention gate (FIXED 2026-08-02): reject a FINAL title that carries
    leaked template fragments, description copy, dangling subordinate clauses,
    or is a bare 1-2 word label. Broken titles used to publish and only get
    caught by the repair layer days later — costing CTR the whole time.

    Returns (clean, reason)."""
    low = (title or "").strip().lower()
    if not low:
        return False, "empty title"
    for token in _LEAK_TOKENS:
        if token in low:
            return False, f"leaked fragment '{token.strip()}'"
    words = [w for w in low.split()]
    if len(words) < 3:
        return False, f"bare label ({len(words)} words)"
    # the '?' may be its own token ("...tout seul ?"); resolve to the last real word
    last = words[-1].rstrip("?!.")
    if last == "" and len(words) >= 2:
        last = words[-2].rstrip("?!.")
    # A COMPLETE question ending with '?' legitimately ends on its verb
    # ("Pourquoi le hoquet commence ?" — 'commence' is the verb, not a dangling
    # fragment). The dangling-word check exists for truncated STATEMENTS, so it
    # only applies to titles that do NOT end with a question mark.
    is_question = low.rstrip().endswith("?")
    if not is_question and (last in _DANGLING_ENDINGS
                            or last in _SUBORDINATE_ENDINGS or last == ""):
        return False, f"ends on dangling word '{last}'"
    # a question title must end with '?' — an LLM 'pourquoi...' sentence that
    # got cut before the question mark is a leak signal
    if low.startswith("pourquoi") and not low.rstrip().endswith("?"):
        return False, "pourquoi-title without closing '?'"
    return True, "ok"


def _scrub_leaks(text: str) -> str:
    """Remove known LLM leak fragments from a topic/title so a fallback title
    can never ship the same defect the leak-gate is meant to block."""
    out = text or ""
    for token in ("remarque entendre", "peut sembler", "semble soudain",
                  "remarque", "peut s"):
        out = re.sub(re.escape(token), " ", out, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip(" .?")


def _clean_title_fallback(topic: str, series_title: str, question_phrase: str = "") -> str:
    """Deterministic clean title when every candidate fails the leak gate.

    Tries, in order: the catalogue's grammatical question → a leak-scrubbed
    truncation of the topic → a remodelled 'Pourquoi {phénomène} ?' → the
    series title. Every candidate must pass the leak-gate itself."""
    q = _question_title_from_phrase(question_phrase)
    if q and _title_is_clean(q)[0]:
        return q
    scrubbed = _scrub_leaks(topic or "")
    base = _truncate_title(scrubbed or series_title)
    if _title_is_clean(base)[0]:
        return base
    # last resort: Pourquoi {bare phenomenon} ?
    bare = _bare_phenomenon(scrubbed or "")
    if bare and len(bare.split()) >= 2:
        return _truncate_title(f"Pourquoi {bare} ?")
    return _truncate_title(series_title or "La science du quotidien")


def _question_hook_from_title(title: str, max_len: int = 35) -> str:
    """Build a short interrogative thumbnail hook FROM the final title.

    French Shorts thumbnails must read as a question or promise with a verb —
    never a bare 2-word label ("CŒUR NUIT" shipped and cost CTR). Stripping
    the leading interrogative leaves an informal question a native actually
    reads: "Pourquoi le cœur bat plus vite ?" -> "LE CŒUR BAT PLUS VITE ?".

    A cut window must END on a content word: windows closing on an article /
    preposition / bare auxiliary produce dangling broken French on screen
    ("LE CERVEAU DES FEMMES EST ?" — caught in the 2026-08-11 dry-run).
    Returns "" when no verb-ful hook can be derived.
    """
    from french_quality_gate import _TITLE_DANGLER_WORDS
    _AUX_DANGLERS = {"est", "sont", "était", "etaient", "sera", "seront",
                     "a", "ont", "avait", "avaient", "aura", "auront"}
    # Copular/temporal words that need a complement — a hook must never END on
    # them (screen reads "…plus vite avant ?" / "…latéral devient ?" = broken).
    _COMPLEMENT_VERBS = {"devient", "deviennent", "semble", "semblent", "parait",
                         "paraissent", "reste", "restent", "demeure", "deviens"}
    _TAIL_DANGLERS = {"avant", "après", "apres", "pendant", "dès", "depuis",
                      "lors", "vers", "entre", "contre", "malgré", "sauf", "chez"}
    danglers = _TITLE_DANGLER_WORDS | _AUX_DANGLERS | _COMPLEMENT_VERBS | _TAIL_DANGLERS

    full = " ".join((title or "").split())
    if not full:
        return ""
    body = re.sub(
        r"^(pourquoi|comment|est-ce que|quand|combien de|combien d'|que se passe-t-il quand)\s+",
        "", full, flags=re.IGNORECASE,
    ).rstrip(" ?!.")
    words = body.split()

    def _usable(candidate: str) -> bool:
        if not has_french_verb(candidate):
            return False
        tail = candidate.split()[-1].strip(",.;:!?\"'").lower()
        return tail not in danglers

    # Largest window first, capped by the on-screen width budget: more of the
    # real phrasing survives whenever it fits ("le cerveau des femmes est
    # divisé" beats "le cerveau"), never ending on a dangling auxiliary.
    for count in range(min(len(words), 7), 2, -1):
        candidate = " ".join(words[:count]).strip()
        hook = candidate + " ?"
        if len(hook) <= max_len and _usable(candidate):
            return hook
    # Full body may itself fit (short titles).
    if len(words) > 7 and _usable(body) and len(body) + 2 <= max_len:
        return body + " ?"
    return ""


def _fr_thumbnail_hook(script_data: dict, series_title: str, chosen_title: str, max_len: int = 35) -> str:
    """Decide the on-thumbnail copy. Guarantees a French verb is present.

    Order:  1. the LLM's thumbnail_text, kept ONLY if it carries a verb
               (bare labels are downgraded, not shipped);
            2. a question hook derived deterministically from the final title;
            3. series title / chosen title (previous behaviour, last resort).
    """
    cand = " ".join(str(script_data.get("thumbnail_text") or "").split())
    if cand and has_french_verb(cand):
        return cand.upper()[:max_len]
    if cand:
        logger.info("Thumbnail text %r has no French verb -> downgrading to question hook", cand)
    hook = _question_hook_from_title(script_data.get("title") or chosen_title, max_len=max_len)
    if hook:
        return hook.upper()[:max_len]
    return (series_title or cand or chosen_title).upper()[:max_len]


def generate_seo_package(topic: str, script_data: dict) -> dict:
    series_title = script_data.get("series_title") or script_data.get("title") or ""
    category = _category(topic)
    keys = _keywords(topic)

    question_phrase = script_data.get("question_phrase") or script_data.get("base_question") or ""
    competitor_intel = _load_competitor_intel()
    title_bandit = _load_title_bandit()
    base_title_options = _build_title_options(topic, series_title, question_phrase)
    competitor_title_options = _competitor_title_options(topic, script_data, competitor_intel)
    combined_title_options = list(dict.fromkeys(competitor_title_options + base_title_options))
    combined_title_options = [title for title in combined_title_options if _candidate_title_ok(title)]
    if competitor_intel:
        combined_title_options = [
            title for title in combined_title_options
            if _not_exact_competitor_title(title, competitor_intel)
        ]
    title_options = _rank_title_options(combined_title_options, title_bandit)[:5]
    # FIXED 2026-08-02: leak-gate every candidate BEFORE it can be chosen.
    # Broken titles ("remarque entendre...", "peut s...", bare labels) used to
    # win the A/B ranking and publish — caught only days later by the repair
    # layer. A title that fails the gate is dropped; if none survive, a clean
    # deterministic title is built from the topic instead.
    title_options = [t for t in title_options if _title_is_clean(t)[0]]
    if title_options:
        chosen_title = title_options[0]
    else:
        fallback_title = _truncate_title(series_title or topic)
        chosen_title = fallback_title if _not_exact_competitor_title(fallback_title, competitor_intel) else "Science du quotidien"
    if not _title_is_clean(chosen_title)[0]:
        chosen_title = _clean_title_fallback(topic, series_title, question_phrase)
        logger.warning("SEO title failed leak-gate -> deterministic fallback: %r", chosen_title)

    hook = script_data.get("hook", "").strip()
    desc = script_data.get("description", "").strip()
    # 2026-08-19: rotating reply-bait CTA pool (all tu-register, French
    # spoken style). A fixed CTA on every video reads as a template and caps
    # engagement; rotating CTAs with a reply question lift comment rate,
    # which is the #1 reply-signal weight in the Shorts feed.
    cta_pool = [
        "Abonne-toi pour plus de science simple — et dis-moi : ça t'arrive aussi ?",
        "Abonne-toi si ton corps te fait des trucs bizarres comme ça — ton réflexe préféré en commentaire ?",
        "Tu veux la suite ? Abonne-toi — et raconte-moi la dernière fois que ça t'est arrivé.",
        "Si ça t'a surpris, abonne-toi — et dis-moi : ton corps te joue quel tour bizarre en ce moment ?",
        "Abonne-toi pour comprendre ton corps — toi, c'est arrivé quand la première fois ?",
    ]
    cta_seed = sum(ord(c) for c in (topic or "").lower())
    default_cta = cta_pool[cta_seed % len(cta_pool)]
    cta = script_data.get("cta") or default_cta
    cta = cta.strip()

    cat_hashtags = CATEGORY_HASHTAGS.get(category, CATEGORY_HASHTAGS["Science"])
    # Only turn a keyword into a hashtag if it is a real search term.
    # `keys` comes from _keywords(), which strips STOP words from the topic —
    # but the *hashtag* line was built straight from keys[:3] with no second
    # filter, so template scaffolding still reached the live descriptions as
    # "#quil #faut #comprendre", "#explique", "#passe", "#semble" and
    # "#derrière" (19 junk hashtags across 8 videos, found 2026-07-27).
    # Fixing the tag list alone was not enough: hashtags are a separate path.
    def _hashtag_ok(word: str) -> bool:
        slug = re.sub(r"[^\w]", "", word).lower()
        return (
            len(slug) > 3
            and slug not in STOP
            and slug not in ENGLISH_TAG_BLOCKLIST
            and slug not in HASHTAG_STOPLIST
        )

    keyword_hashtags = ["#" + re.sub(r"[^\w]", "", k) for k in keys if _hashtag_ok(k)][:3]
    # 2026-08-19: niche/category hashtags FIRST (channel identity signal for
    # YouTube's classifier), growth hashtags in the middle (deterministic 2 per
    # topic — stacking all of them on every video would dilute them), #shorts
    # last (broad tag carries the least discovery value).
    growth_pool = FR_GROWTH_HASHTAGS
    topic_hash = sum(ord(c) for c in (topic or "x").lower())
    growth_picks = [growth_pool[topic_hash % len(growth_pool)],
                    growth_pool[(topic_hash // 7) % len(growth_pool)]]
    hashtags = cat_hashtags[:2] + keyword_hashtags + growth_picks + ["#shorts"]
    hashtags = list(dict.fromkeys(hashtags))[:9]

    keyword_intro = _clean_topic(topic)
    keyword_intro = keyword_intro[0].upper() + keyword_intro[1:] if keyword_intro else ""
    # De-duplicate the opening line. `desc` (the LLM summary) very often
    # already restates the topic verbatim, which published descriptions like:
    #   "Ce que votre corps vous dit quand la mâchoire craque en mâchant.
    #    Ce que votre corps vous dit quand la mâchoire craque en mâchant.
    #    Découvrez ce que votre corps vous dit quand votre mâchoire craque…"
    # — the same sentence three times before any real information. That is a
    # duplicate-content signal and wastes the only two lines YouTube shows.
    def _norm(text: str) -> str:
        return re.sub(r"[^a-zà-ÿœ0-9 ]", "", (text or "").lower()).strip()

    intro_norm = _norm(keyword_intro)
    desc_norm = _norm(desc)
    # 2026-08-19: hook-first description structure. Only the first ~100 chars
    # are visible in the Shorts feed overlay before "...plus", so the hook
    # question (the video's actual promise) must be line 1 — not the topic
    # restatement. Structure: hook -> topic + summary -> rotating CTA -> FR
    # hashtag block.
    if hook and _norm(hook) and _norm(hook) not in _norm(desc):
        opening = hook.strip()
    elif intro_norm and desc_norm and (
        desc_norm.startswith(intro_norm) or intro_norm in desc_norm
    ):
        opening = desc.strip()                      # summary already says it
    elif desc.strip():
        # Avoid "…craque en mâchant ?." when the topic already ends in
        # punctuation.
        sep = "" if keyword_intro.rstrip().endswith(("?", "!", ".", "…")) else "."
        opening = f"{keyword_intro.rstrip()}{sep} {desc.strip()}"
    else:
        sep = "" if keyword_intro.rstrip().endswith(("?", "!", ".", "…")) else "."
        opening = f"{keyword_intro.rstrip()}{sep}"

    blocks = [opening]
    # Line 2: topic restatement + real summary (only when it adds new words).
    if desc.strip() and _norm(desc) not in _norm(opening):
        blocks.append(desc.strip())
    if cta:
        blocks.append(cta.strip())
    blocks.append(" ".join(hashtags))
    description = "\n\n".join(b for b in blocks if b).strip()

    cat_tags = CATEGORY_TAGS.get(category, CATEGORY_TAGS["Science"])
    competitor_tags = _safe_competitor_tags(topic, category, competitor_intel)
    locale_tags = LOCALE_TAGS if os.environ.get("FRANCOPHONE_LOCALE_TAGS", "true").lower() == "true" else []
    # French-only guarantee: drop any English tag that slips in from a category
    # list, a topic string or competitor intel, and keep only tags that read as
    # real search terms. Competitor tags are blended, never copied wholesale.
    tags = [
        t for t in dict.fromkeys(keys + competitor_tags + cat_tags + locale_tags + ["français"])
        if t.lower().strip() not in ENGLISH_TAG_BLOCKLIST and len(t.strip()) > 2
    ][:15]

    topic_short = _truncate_title(_bare_phenomenon(topic), fallback=series_title or "ce phénomène")
    pinned_comment = random.choice(PINNED_QUESTION_TEMPLATES).format(
        topic_short=topic_short.lower()
    )[:PINNED_COMMENT_MAX_LEN]

    return {
        "title_options": title_options,
        "title": chosen_title,
        "chosen_title": chosen_title,
        "series_title": series_title,
        "description": description[:DESCRIPTION_MAX_LEN],
        "tags": tags,
        "hashtags": hashtags,
        "thumbnail_text": _fr_thumbnail_hook(script_data, series_title, chosen_title),
        "pinned_comment": pinned_comment,
        "playlist_suggestion": PLAYLISTS_BY_CATEGORY[category],
        # Previously hardcoded to 85 (misleading in logs). Now derived from
        # real signals: title length (30-60 chars reads best on mobile) and
        # tag breadth. Still a heuristic, not a guarantee.
        "seo_score": {
            "scores": {
                "overall_seo_score": min(
                    100,
                    round(
                        0.5 * (100 if 30 <= len(chosen_title) <= 60 else 70)
                        + 0.5 * min(100, 50 + 5 * len(tags))
                    )
                )
            },
            "category": category,
        },
    }


def generate_description(script_data: dict, tags: list[str] | None = None) -> str:
    """Description unique, en français, utilisée par l'upload YouTube."""
    package = generate_seo_package(script_data.get("topic") or script_data.get("title", "science"), script_data)
    description = package["description"]

    # Only append hashtags that are genuinely NEW and genuinely searchable.
    # This used to blindly convert the first 3 tags into hashtags and staple
    # them on, which is how live descriptions ended with the template
    # scaffolding "#quil #faut #comprendre" duplicated after the existing
    # hashtag line.
    existing = {h.lower() for h in re.findall(r"#\w+", description)}
    extra = []
    for tag in (tags or []):
        slug = re.sub(r"[^\w]", "", str(tag)).lower()
        if (
            len(slug) > 3
            and slug not in STOP
            and slug not in ENGLISH_TAG_BLOCKLIST
            and f"#{slug}" not in existing
            and f"#{slug}" not in extra
        ):
            extra.append(f"#{slug}")
        if len(extra) == 3:
            break

    if extra:
        description = f"{description} {' '.join(extra)}"
    return description.strip()[:DESCRIPTION_MAX_LEN]
    
