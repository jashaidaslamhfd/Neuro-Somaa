#!/usr/bin/env python3
"""FRANÇAIS PARLÉ — humanizer post-pass for the Neuro-Somaa pipeline (2026-08-11).

Why this exists
---------------
LLM voiceovers come out in *written* French: systematic « vous », full
negations (« ce n'est pas »), zero contractions, and sentence chains with no
terminal punctuation. Read aloud by TTS that sounds exactly like what it is —
a machine reading an essay. Native French speakers talk differently:

  écrit  : « Vous avez déjà remarqué que votre cœur s'emballe la nuit ?
             Il n'y a pas de danger. Cela vous arrive quand vous dormez. »
  parlé  : « T'as déjà remarqué que ton cœur s'emballe la nuit ?
             Y a pas de danger. Ça t'arrive quand tu dors. »

This module rewrites only *safe, mechanical* registers — never meaning:

  1. AI-cliché sweep          (« il est important de noter que » → ∅)
  2. vouvoiement → tutoiement (verb-address whitelist + gendered possessives)
  3. nous → on                (spoken French almost never says « nous »)
  4. spoken contractions      (« il y a » → « y a », « cela » → « ça »,
                               « ce n'est pas » → « c'est pas », …)
  5. sentence-boundary repair (the TTS reads punctuation, not line breaks —
     a missing period between two captions is heard as one endless drone)
  6. end-truncation guard     (a voiceover never ends mid-word like « …Al »)

Everything is idempotent: running it on already-spoken French is a no-op.
The caller logs the change list; nothing here ever blocks a script.
"""

from __future__ import annotations

import re

# ── 1. AI-cliché sweep (soft — validation hard-blocks the worst already) ──
_CLICHE_DROPS = (
    r"[Ii]l est important de noter que\s+",
    r"[Ii]l convient de noter que\s+",
    r"[Ii]l est à noter que\s+",
    r"[ÀA] noter que\s+",
    r"[Ee]n conclusion\s*,?\s*",
    r"[Ee]n définitive\s*,?\s*",
)

# ── 2/3/4. Register rewrite tables (longest match first) ─────────────────
# Each tuple: (regex, replacement). Capitalisation of the replacement is
# matched to the original automatically by _matchcase.
_REGISTER: tuple[tuple[str, str], ...] = (
    # classic AI/formal tail-question → spoken one
    (r",?\s*n'est-ce pas\s*\?", " non ?"),
    # full negations → spoken (« ne » drop, only in frozen safe patterns)
    (r"\bil n'y a plus\b", "y a plus"),
    (r"\bil n'y a pas\b", "y a pas"),
    (r"\bce n'est plus\b", "c'est plus"),
    (r"\bce n'est pas\b", "c'est pas"),
    (r"\bce n'est qu'", "c'est qu'"),
    (r"\btu n'as pas\b", "t'as pas"),
    (r"\bon ne sait pas\b", "on sait pas"),
    (r"\bje ne sais pas\b", "je sais pas"),
    (r"\b(?:ne|n') t'inquiètes? pas\b", "t'inquiète pas"),
    # nous → on (spoken French)
    (r"\bnous allons\b", "on va"),
    (r"\bnous avons\b", "on a"),
    (r"\bnous sommes\b", "on est"),
    (r"\bnous devons\b", "on doit"),
    (r"\bnous pouvons\b", "on peut"),
    (r"\bnous savons\b", "on sait"),
    (r"\bnous nous\b", "on se"),
    # vouvoiement → tutoiement (whitelisted verb forms only — guessing the
    # tu-conjugation of arbitrary vous-verbs would corrupt grammar).
    # Reflexive chains FIRST (pronoun + verb must convert together —
    # « vous vous réveillez » → « tu te réveilles », never « tu te
    # réveillez »), then single-verb forms, then the generic fallback.
    (r"\b[Vv]ous vous réveillez\b", "tu te réveilles"),
    (r"\b[Vv]ous vous endormez\b", "tu t'endors"),
    (r"\b[Vv]ous vous demandez\b", "tu te demandes"),
    (r"\b[Vv]ous vous souvenez\b", "tu te souviens"),
    (r"\b[Vv]ous vous sentez\b", "tu te sens"),
    (r"\b[Vv]ous vous levez\b", "tu te lèves"),
    (r"\b[Vv]ous vous rappelez\b", "tu te rappelles"),
    (r"\b[Vv]ous vous êtes\b", "tu t'es"),
    (r"\b[Vv]ous avez\b", "t'as"),
    (r"\b[Vv]ous êtes\b", "t'es"),
    (r"\b[Vv]ous vous\b", "tu te"),
    (r"\b[Vv]ous faites\b", "tu fais"),
    (r"\b[Vv]ous savez\b", "tu sais"),
    (r"\b[Vv]ous sentez\b", "tu sens"),
    (r"\b[Vv]ous entendez\b", "t'entends"),
    (r"\b[Vv]ous dormez\b", "tu dors"),
    (r"\b[Vv]ous réveillez\b", "tu réveilles"),
    (r"\b[Vv]ous ressentez\b", "tu ressens"),
    (r"\b[Vv]ous arrive\b", "t'arrive"),
    (r"\b[Vv]ous aussi\b", "toi aussi"),
    (r"\bchez vous\b", "chez toi"),
    (r"\bpour vous\b", "pour toi"),
    (r"\bcomme vous\b", "comme toi"),
    # imperatives viewers actually hear (CTA / hook style)
    (r"\b[Aa]bonnez-vous\b", "abonne-toi"),
    (r"\b[Ii]maginez\b", "imagine"),
    (r"\b[Rr]egardez\b", "regarde"),
    (r"\b[ÉEe]coutez\b", "écoute"),
    (r"\b[Rr]emarquez\b", "remarque"),
    (r"\b[Rr]etenez\b", "retiens"),
    (r"\b[Ss]achez\b", "sache"),
    (r"\b[Rr]estez\b", "reste"),
    # demonstrative & existential contractions
    (r"\b[Cc]ela est\b", "c'est"),
    (r"\b[Cc]ela\b", "ça"),
    (r"\b[Ii]l y a\b", "y a"),
)

# possessives need gender: « votre peau » → « ta peau » but « votre corps » → « ton corps »
_FEM_NOUNS = {
    "peau",
    "voix",
    "tête",
    "mémoire",
    "respiration",
    "bouche",
    "main",
    "mains",
    "jambe",
    "jambes",
    "gorge",
    "paupière",
    "mâchoire",
    "oreille",
    "oreilles",
    "faim",
    "peur",
    "température",
    "lumière",
    "douleur",
    "nuque",
    "langue",
    "sueur",
    "chair",
    "larme",
    "larmes",
    "poitrine",
    "vision",
    "ouïe",
    "fatigue",
    "alarme",
    "nuit",
    "journée",
    "semaine",
    "santé",
    "vie",
    "famille",
    "envie",
    "horloge",
    "routine",
    "raison",
    "question",
    "pompe",
    "minute",
    "heure",
    "seconde",
}
_MASC_NOUNS = {
    "corps",
    "cerveau",
    "cœur",
    "coeur",
    "ventre",
    "dos",
    "sommeil",
    "stress",
    "système",
    "rythme",
    "réflexe",
    "nez",
    "visage",
    "hoquet",
    "souffle",
    "muscle",
    "muscles",
    "sang",
    "pied",
    "pieds",
    "vertige",
    "frisson",
    "sourire",
    "regard",
    "doigt",
    "doigts",
    "genou",
    "genoux",
    "bâillement",
    "spasme",
    "sanglot",
    "soupir",
    "cri",
    "bruit",
    "réveil",
    "matin",
    "soir",
    "déjeuner",
    "dîner",
    "travail",
    "téléphone",
    "écran",
    "lit",
    "bureau",
}

# ── 5. sentence-boundary repair ───────────────────────────────────────────
# Capitalised words that can open a French sentence in this channel's
# register. A capital straight after a lowercase word + space, with no
# punctuation, means two sentences were glued — the TTS then reads one
# endless drone ("…fatigué C'est dû au fait…" real production example).
_OPENERS = (
    "Le",
    "La",
    "Les",
    "Il",
    "Ils",
    "Elle",
    "Elles",
    "On",
    "Un",
    "Une",
    "Des",
    "Ce",
    "Ces",
    "Cela",
    "Ça",
    "Son",
    "Sa",
    "Ses",
    "Ton",
    "Ta",
    "Tes",
    "Quand",
    "Lorsque",
    "Mais",
    "Et",
    "En",
    "Si",
    "Alors",
    "Résultat",
    "Surtout",
    "Pourtant",
    "Parfois",
    "Voilà",
    "Voici",
    "Pourquoi",
    "Parce",
    "Tout",
    "Toute",
    "C'est",
    "Chaque",
    "Puis",
    "Car",
    "Donc",
)
_BOUNDARY_RE = re.compile(r"(?<=[a-zàâäæçéèêëîïôöœùûüÿ'’])\s+(?=(?:" + "|".join(_OPENERS) + r")(?:\s|'|$))")

# ── 6. dangling-tail guard (cut words like « …de lourdeur Al ») ──────────
_DANGLING_TAIL = {
    "et",
    "mais",
    "que",
    "qui",
    "quoi",
    "de",
    "du",
    "des",
    "à",
    "au",
    "aux",
    "en",
    "dans",
    "sur",
    "par",
    "pour",
    "avec",
    "sans",
    "ce",
    "cet",
    "cette",
    "ces",
    "un",
    "une",
    "le",
    "la",
    "les",
    "il",
    "elle",
    "on",
    "ton",
    "ta",
    "tes",
    "son",
    "sa",
    "ses",
    "votre",
    "vos",
    "mon",
    "ma",
    "mes",
    "si",
    "car",
    "ni",
    "ou",
    "donc",
    "or",
    "alors",
    "comme",
    "quand",
    "lors",
    "afin",
    "al",
    "lorsq",
    "parce",
}
# NOTE: words that CAN legitimately close a spoken sentence (« …ton corps
# aussi. », « …et bien plus. », « …c'est très rare. ») must never be in this
# set — only articles/prepositions/conjunctions that dangle in French.


def _matchcase(original: str, replacement: str) -> str:
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def humanize_spoken_fr(text: str) -> tuple[str, list[str]]:
    """Rewrite written/LLM French into natural spoken French.

    Returns ``(new_text, changes)`` — ``changes`` lists the rule names that
    fired, purely for the pipeline logs. Never raises; worst case it gives
    the input back unchanged.
    """
    original = text or ""
    out = " ".join(original.split())  # normalise whitespace first
    changes: list[str] = []

    def _sub(pattern: str, repl: str, label: str, flags: int = 0) -> None:
        nonlocal out
        new = re.sub(pattern, repl, out, flags=flags)
        if new != out:
            out = new
            if label not in changes:
                changes.append(label)

    # 1. clichés
    for pat in _CLICHE_DROPS:
        _sub(pat, "", "cliché:drop")
    # tidy ", / ;" spacing artefacts — but NEVER eat the French space before
    # « ? » or « ! » (typography: « la nuit ? » keeps its espace).
    out = re.sub(r"\s+([,;:.])(?=\s|$)", r"\1", out)

    # 2. glued-sentence repair FIRST — register rules lowercase « Cela »→« ça »
    #    and company, which would destroy the capital-letter signal the
    #    boundary detector relies on ("…ralentit Cela reste…" real case).
    new = _BOUNDARY_RE.sub(". ", out)
    if new != out:
        out = new
        changes.append("frontière:phrase")

    # 2–4. register tables (case-insensitive; case restored from the match)
    for pat, repl in _REGISTER:

        def _do(m: re.Match[str], r: str = repl) -> str:
            return _matchcase(m.group(0), r)

        new = re.sub(pat, _do, out, flags=re.IGNORECASE)
        if new != out:
            out = new
            if "register:parlé" not in changes:
                changes.append("register:parlé")

    # possessives with gender lookup
    def _poss(m: re.Match[str]) -> str:
        art, noun = m.group(1), m.group(2)
        if art.lower() == "vos":
            fixed = "tes"
        elif noun.lower() in _FEM_NOUNS:
            fixed = "ta"
        elif noun.lower() in _MASC_NOUNS:
            fixed = "ton"
        else:
            return m.group(0)  # unknown gender — leave it, never guess
        _poss.changed = True
        return _matchcase(art, fixed) + " " + noun

    _poss.changed = False
    out = re.sub(r"\b([Vv]otre|[Vv]os)\s+([A-Za-zÀ-ÿŒœ'’-]+)", _poss, out)
    if _poss.changed and "possessif:ton/ta" not in changes:
        changes.append("possessif:ton/ta")

    # 6. dangling tail + complete ending
    words = out.split()
    while len(words) > 4 and words[-1].lower().strip(".,!?…«»\"'") in _DANGLING_TAIL:
        words.pop()
        changes_added = "fin:pendante" not in changes
        if changes_added:
            changes.append("fin:pendante")
    out = " ".join(words)
    if out and not out.endswith((".", "!", "?", "…", "»", '"')):
        # Never truncate back to an earlier sentence: the tail may be real
        # content missing only its final mark (dangling words were already
        # popped above). Truncating erased « Ça reste normal » in tests.
        out = out.rstrip(",;:—–-") + "."
        if "fin:complète" not in changes:
            changes.append("fin:complète")

    # capitalise after any ". x" lowercase start introduced by cliché drops,
    # and at the very start of the text (« il est important de… » drop can
    # leave a lowercase opener).
    out = re.sub(r"([.!?…]\s+)([a-zàâäæçéèêëîïôöœùûüÿ])", lambda m: m.group(1) + m.group(2).upper(), out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    if out and out != original.strip() and not changes:
        changes.append("nettoyage")
    return out, changes


def formality_leftovers(text: str) -> int:
    """Count remaining formal-register markers (vous/votre/imperative -ez).
    Used by the pipeline logger to watch the humanization coverage — a
    healthy script trends to 0. Never blocks anything."""
    t = " " + (text or "").lower() + " "
    return len(re.findall(r"\bvous\b", t)) + len(re.findall(r"\bvotre\b|\bvos\b", t))
