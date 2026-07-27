"""SEO français, pensé pour la découverte sur YouTube France et la francophonie."""
import random
import re

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

PINNED_QUESTION_TEMPLATES = [
    "Ça vous arrive aussi, {topic_short} ? Dites-le en commentaire.",
    "Vous vous êtes déjà demandé pourquoi {topic_short} ?",
    "Quel autre réflexe du corps voulez-vous voir expliqué après {topic_short} ?",
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
    "quand", "lorsque", "si", "ce", "cette", "leur", "leurs", "y",
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
_CLAUSE_BREAKS = (" parce que ", " lorsque ", " pendant que ", " pendant ",
                  " quand ", " que ")

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


def _build_title_options(topic: str, series_title: str) -> list[str]:
    """Generate real, distinct SEO title candidates from the full French angle
    (topic), not from the already-short branded series title.

    `topic` already starts with a phrase like "Pourquoi ...", "La science
    derrière ...", "Ce qui se passe quand ...", etc. so options are built by
    reformatting that sentence, not by re-wrapping it in another template."""
    raw = (topic or "").strip()
    if not raw:
        return [_truncate_title(series_title)] if series_title else []

    capitalized = raw[0].upper() + raw[1:] if raw else raw
    full_angle_text = " ".join(_words(capitalized))
    angle_option = _truncate_title(capitalized)

    # If the full angle doesn't fit the Shorts title limits, the truncated
    # version may look clipped even after dangling-word cleanup. In that case
    # prefer the short branded series title as the DEFAULT pick (it is always
    # clean and grammatical), and keep the angle as a secondary candidate.
    # This is what prevented "...entendre son cœur battre la" from being the
    # visible title while the catalogue angle was too long.
    angle_truncated = len(angle_option) != len(full_angle_text)
    series_option = _truncate_title(series_title) if series_title else ""

    if angle_truncated and series_option:
        options = [series_option, angle_option]
    else:
        options = [angle_option]

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


def generate_seo_package(topic: str, script_data: dict) -> dict:
    series_title = script_data.get("series_title") or script_data.get("title") or ""
    category = _category(topic)
    keys = _keywords(topic)

    title_options = _build_title_options(topic, series_title)
    chosen_title = title_options[0] if title_options else _truncate_title(series_title or topic)

    hook = script_data.get("hook", "").strip()
    desc = script_data.get("description", "").strip()
    cta = script_data.get("cta", "Abonnez-vous pour plus de science simple.").strip()

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
    hashtags = ["#shorts"] + cat_hashtags[:2] + keyword_hashtags
    hashtags = list(dict.fromkeys(hashtags))[:8]

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
    if intro_norm and desc_norm and (
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

    # Drop the hook line when it merely repeats the opening.
    blocks = [opening]
    if hook and _norm(hook) not in _norm(opening):
        blocks.append(hook.strip())
    if cta:
        blocks.append(cta.strip())
    blocks.append(" ".join(hashtags))
    description = "\n\n".join(b for b in blocks if b).strip()

    cat_tags = CATEGORY_TAGS.get(category, CATEGORY_TAGS["Science"])
    # French-only guarantee: drop any English tag that slips in from a category
    # list or a topic string, and keep only tags that read as real search terms.
    tags = [
        t for t in dict.fromkeys(keys + cat_tags + ["français"])
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
        "thumbnail_text": (script_data.get("thumbnail_text") or series_title or chosen_title).upper()[:35],
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
    
