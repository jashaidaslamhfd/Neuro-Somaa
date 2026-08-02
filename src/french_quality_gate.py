"""
French quality and policy gate for SKILLOR.

Purpose:
- keep every public-facing field French-first
- block risky medical/YMYL claims before video generation/upload
- enforce Shorts-friendly metadata and scene structure

This gate cannot guarantee virality, but it prevents the most common reasons
faceless health/science Shorts get low trust signals: mixed language, repeated
metadata, exaggerated medical claims, weak structure, and unreadable captions.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

FRENCH_MARKERS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "ce", "cet", "cette",
    "ton", "ta", "tes", "tu", "toi", "te", "se", "son", "sa", "ses", "dans",
    "pour", "avec", "sans", "mais", "et", "ou", "donc", "car", "quand", "comme",
    "pourquoi", "voici", "vraiment", "corps", "cerveau", "sommeil", "cœur",
    "santé", "mémoire", "stress", "ventre", "microbiote", "après", "nuit", "science", "secret",
}

ENGLISH_MARKERS = {
    "your", "you", "the", "this", "that", "why", "how", "what", "when", "body",
    "brain", "heart", "sleep", "blood", "health", "truth", "doctors",
    "actually", "never", "always", "people",
}

# Hard blocks: medical diagnosis/cure/guarantee language.
FORBIDDEN_MEDICAL_PATTERNS = [
    r"\bgu[eé]rit\b", r"\bgu[eé]rison garantie\b", r"\brem[eè]de miracle\b",
    r"\bdiagnostique\b", r"\btu as (un|une|la|le)\b", r"\btu souffres de\b",
    r"\barr[eê]te (ton|tes|le|la) traitement\b", r"\bremplace ton traitement\b",
    r"\bpas besoin de m[eé]decin\b", r"\bignore ton m[eé]decin\b",
    r"\b100\s*%\s*(garanti|efficace|vrai)\b", r"\bpreuve absolue\b",
    # English slips
    r"\bcures?\b", r"\bdiagnos(e|is)\b", r"\bguaranteed\b", r"\bdoctor[s]? don't want\b",
]

SAFE_DISCLAIMER = (
    "Contenu éducatif, pas un avis médical. Si un symptôme persiste, parle à un professionnel de santé."
)

# Fact-safety / lightweight RAG gate. We do not require citations in a 40s
# Short, but we block patterns that usually mean the model invented authority
# ("une étude prouve", exact percentages, named research without a source) or
# overstates weak body-science explanations.
UNSUPPORTED_AUTHORITY_PATTERNS = [
    r"\b(une|des) [ée]tudes? (prouve|prouvent|confirme|confirment|montre|montrent)\b",
    r"\bdes chercheurs (ont )?(prouv[ée]|d[ée]couvert|confirm[ée])\b",
    r"\bselon (une|des) [ée]tudes?\b",
    r"\b\d+(?:[,.]\d+)?\s*%\b",
    r"\b\d+\s*(fois|secondes|minutes|heures|jours)\b.*\b(prouve|garantit|explique tout)\b",
]

# ---------------------------------------------------------------------------
# Broken-French detectors. Two real artifacts shipped to the public channel:
#   1. "...mais votre cerveau. Et écoute les sons..." - a sentence cut by a
#      period and continued with a conjunction (scene captions joined naively).
#   2. A caption ending on a dangling connector ("...son cœur batte la") -
#      truncation artifacts in spoken/audio text sound instantly robotic.
# ---------------------------------------------------------------------------
# Only "et/ou/ni" are treated as broken continuations: in French, starting a
# sentence with "Et"/"Ou"/"Ni" after a full stop is incorrect (that is the
# exact artifact that shipped), whereas scene-openers like "Mais", "Donc" or
# "Alors" are normal discourse markers and must NOT be flagged.
BROKEN_CONTINUATION = re.compile(
    r"[.!?…]\s+(et|ou|ni)\b", re.IGNORECASE
)
_CONTINUATION_START = re.compile(r"^(et|ou|ni)\b", re.IGNORECASE)
_DANGLING_CAPTION_END = {
    "le", "la", "les", "de", "du", "des", "un", "une", "son", "sa", "ses",
    "mon", "ma", "mes", "ton", "ta", "tes", "au", "aux", "en", "dans", "sur",
    "sous", "avec", "sans", "pour", "par", "et", "ou", "ni", "que", "qui",
    "ce", "cette", "votre", "notre", "leur", "leurs",
}


def _broken_narration_issues(scenes: list) -> list[str]:
    """Detect sentence fragments produced when scene captions are joined."""
    captions = [str(s.get("caption", "")).strip() for s in scenes if isinstance(s, dict)]
    issues: list[str] = []
    joined = " ".join(captions)
    match = BROKEN_CONTINUATION.search(joined)
    if match:
        issues.append(
            "Broken French continuation after a full stop: %r" % joined[max(0, match.start() - 25):match.end() + 25]
        )
    for index, caption in enumerate(captions, start=1):
        words = caption.split()
        if not words:
            issues.append(f"Scene {index} caption is empty")
            continue
        last = re.sub(r"[^a-zà-ÿœ]", "", words[-1].lower())
        if last in _DANGLING_CAPTION_END:
            issues.append(f"Scene {index} caption ends on a dangling connector: %r" % caption[-40:])
        if _CONTINUATION_START.match(caption) and index > 1:
            prev = captions[index - 2]
            if prev.rstrip().endswith((".", "!", "?", "…")):
                issues.append(
                    f"Scene {index} starts with a conjunction right after a full stop: %r" %
                    (prev[-25:] + " / " + caption[:25])
                )
    return issues


def _all_public_text(script_data: dict) -> str:
    parts: list[str] = []
    for key in ("title", "hook", "cta", "description", "topic"):
        if script_data.get(key):
            parts.append(str(script_data[key]))
    for scene in script_data.get("scenes", []) or []:
        if isinstance(scene, dict):
            parts.append(str(scene.get("caption", "")))
            parts.append(str(scene.get("visual", "")))
    for seq_key in ("tags", "hashtags"):
        val = script_data.get(seq_key)
        if isinstance(val, list):
            parts.extend(map(str, val))
    return "\n".join(parts)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-ZÀ-ÿ']+", text.lower())


def language_score(text: str) -> dict:
    tokens = _tokens(text)
    if not tokens:
        return {"french_hits": 0, "english_hits": 0, "english_ratio": 0.0, "ok": False}
    french_hits = sum(1 for t in tokens if t in FRENCH_MARKERS)
    english_hits = sum(1 for t in tokens if t in ENGLISH_MARKERS)
    english_ratio = english_hits / max(len(tokens), 1)
    # French text can include universal words like science/shorts; allow small ratio.
    ok = french_hits >= 8 and english_ratio <= 0.035
    return {
        "french_hits": french_hits,
        "english_hits": english_hits,
        "english_ratio": round(english_ratio, 4),
        "ok": ok,
    }


def medical_policy_flags(text: str) -> list[str]:
    flags: list[str] = []
    lowered = text.lower()
    for pat in FORBIDDEN_MEDICAL_PATTERNS:
        if re.search(pat, lowered, flags=re.IGNORECASE):
            flags.append(pat)
    return flags


def unsupported_fact_flags(text: str) -> list[str]:
    flags: list[str] = []
    lowered = text.lower()
    for pat in UNSUPPORTED_AUTHORITY_PATTERNS:
        if re.search(pat, lowered, flags=re.IGNORECASE):
            flags.append(pat)
    return flags


def ensure_safe_disclaimer(script_data: dict) -> dict:
    desc = script_data.get("description", "") or ""
    cta = script_data.get("cta", "") or ""
    if SAFE_DISCLAIMER.lower() not in (desc + " " + cta).lower():
        script_data["description"] = (desc.strip() + "\n\n" + SAFE_DISCLAIMER).strip()
        script_data["safety_disclaimer_added"] = True
    return script_data


# Last-word markers of a cut-off title: French articles, prepositions,
# demonstratives and auxiliaries that can never end a real sentence.
_TITLE_DANGLER_WORDS = frozenset({
    "le", "la", "les", "un", "une", "de", "des", "du", "au", "aux", "en",
    "et", "ou", "pour", "sur", "dans", "avec", "sans", "sous", "chez",
    "que", "qui", "quand", "où", "dont", "ce", "cet", "cette", "ces",
    "votre", "vos", "notre", "nos", "leur", "leurs", "son", "sa", "ses",
    "mon", "ma", "mes", "ton", "ta", "tes", "se", "ne", "si", "car",
    "vers", "entre", "très", "trop", "plus", "moins", "peu", "bien",
    "mal", "même", "comme", "être", "avoir", "fait", "faire", "peut",
    "doit", "veut", "va", "à",
})


def validate_publication_quality(script_data: dict) -> tuple[bool, dict]:
    """Return (ok, report). Does not mutate except adding a safe disclaimer."""
    issues: list[str] = []
    warnings: list[str] = []

    scenes = script_data.get("scenes", []) or []
    # FIXED 2026-08-02: the channel moved to the SHORT format (20-26s,
    # 6 scenes x 7-10 words) after the 40-55s format measured 27-38% AVP.
    # Accept BOTH: short format 4-8 scenes OR legacy long format 8-12.
    n = len(scenes)
    if not (4 <= n <= 12):
        issues.append(f"Scene count should be 4-12 for Shorts; got {n}")
    elif n > 8:
        # legacy long format is still allowed to pass the gate (already live
        # videos), but warn so it isn't silently re-produced.
        warnings.append(f"Scene count {n} = legacy long format (short format is 4-8)")

    # Spoken French must never contain cut sentences - viewers hear these
    # instantly (retention and channel-trust killers).
    issues.extend(_broken_narration_issues(scenes)[:5])

    for i, scene in enumerate(scenes, start=1):
        caption = scene.get("caption", "") if isinstance(scene, dict) else ""
        wc = len(caption.split())
        # Short format: 6-12 words/scene. Long format: 12-24.
        if wc < 6 or wc > 24:
            warnings.append(f"Scene {i} caption has {wc} words; target 7-16 (short) / 12-20 (long)")

    title = script_data.get("title", "") or ""
    if len(title) > 70:
        warnings.append("Title is longer than 70 chars; mobile truncation risk")
    if title.isupper() and len(title) > 10:
        issues.append("Title is all caps; spam/clickbait risk")
    # Hard block: a title ending on a French article/preposition/auxiliary is
    # a TRUNCATED title (the "...battre la" incident — the language gate alone
    # cannot catch it because every word is valid French). It looks broken to
    # viewers and murders CTR.
    last_word = ""
    for word in title.lower().replace("’", " ").replace("'", " ").split():
        last_word = word.strip(",.:;…!?«»\"()")
    if last_word in _TITLE_DANGLER_WORDS:
        issues.append(
            f"Title appears truncated (ends with dangling '{last_word}'); "
            "finish the sentence or shorten earlier words"
        )

    text = _all_public_text(script_data)
    lang = language_score(text)
    if not lang["ok"]:
        issues.append(
            f"French language gate failed: french_hits={lang['french_hits']}, "
            f"english_ratio={lang['english_ratio']}"
        )

    med_flags = medical_policy_flags(text)
    if med_flags:
        issues.append("Risky medical/guarantee language detected: " + ", ".join(med_flags[:5]))

    fact_flags = unsupported_fact_flags(text)
    if fact_flags:
        issues.append("Unsupported authority/statistical claim detected: " + ", ".join(fact_flags[:5]))

    # Always add educational disclaimer for body/health science content.
    ensure_safe_disclaimer(script_data)

    report = {
        "approved": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "language": lang,
        "medical_flags": med_flags,
        "fact_flags": fact_flags,
        "disclaimer": SAFE_DISCLAIMER,
    }

    if report["approved"]:
        logger.info("French quality gate approved publication")
    else:
        logger.error(f"French quality gate blocked publication: {issues}")

    return report["approved"], report
    
