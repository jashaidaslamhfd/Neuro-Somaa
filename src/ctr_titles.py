"""CTR booster for FR YouTube Shorts titles (Neuro-Somaa).

Adds an LLM-generated layer of high-CTR French title candidates on top of
the existing rule-based French angles in ``seo_generator._build_title_options()``.

Why: the rule-based angles ("Pourquoi ...") are grammatically safe but
template-heavy; 2026 Shorts feeds suppress template output and French
viewers respond to novelty. Viral FR Shorts CTR patterns that outperform
plain "Pourquoi ..." frames: (1) numbers/specificity ("7 signes...",
"4 raisons..."), (2) authority constructions ("Ce que les médecins ne
vous disent pas..."), (3) personal second-person stakes ("Votre corps
essaie de..."), (4) unresolved curiosity gaps ("Ce qui arrive vraiment
à..."). This module generates up to 4 such candidates per video via
OpenRouter (free tier) and falls back to rule-based patterns if the LLM
fails - a title drop must never stop a run.

2026-08-21: first implementation. Toggle: ``CTR_TITLES=false`` disables
the LLM layer entirely (rule-based only, pre-change behaviour).
"""

import os
import re

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:  # pragma: no cover - requests is a core dep
    _HAS_REQUESTS = False

from seo_generator import _truncate_title

CTR_TITLE_MAX_CHARS = 55
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CTR_TIMEOUT = 45

# Common phenomenon phrases per Body Glitch topic, normalised into a clean
# French noun phrase. "pourquoi vos genoux craquent" -> "vos genoux craquent".
_STARTER_RE = re.compile(
    r"^(pourquoi|voici pourquoi|comprendre pourquoi|la science derrière|"
    r"ce qui se passe quand|ce qui arrive quand)\s+(votre|votre corps|vos|le|la|les|l')?\s*",
)


def _fr_phrase(topic: str) -> str:
    low = (topic or "").strip().rstrip(".")
    phrase = _STARTER_RE.sub("", low).strip()
    if not phrase:
        return (topic or "").strip()
    return phrase


def _cap(s: str) -> str:
    """Keep a French fragment lowercase for mid-sentence slots.
    ``.title()`` produced "Sur Genoux Craquent" — broken French casing —
    and capitalising the fragment itself produced "sur Hoquet" mid-sentence,
    which is equally wrong. Titles that start a pattern get capitalisation
    from the fixed prefix already."""
    s = s.strip()
    if not s:
        return s
    return s[0].lower() + s[1:] if s[0].isupper() else s


def _rule_patterns(topic: str) -> list:
    """Deterministic high-CTR French constructions built from the topic."""
    p = _fr_phrase(topic)
    if not p:
        return []
    p_cap = _cap(p)
    patterns = [
        f"Ce que les médecins ne vous disent pas sur {_cap(p)}",
        f"7 signes que {p_cap} est normal ?",
        f"Voici ce qui arrive vraiment quand {p}",
        f"Votre corps essaie de vous avertir : {p}",
        f"La vraie raison pour laquelle {p}",
        f"99% des gens ne savent pas que {p}",
    ]
    return list(dict.fromkeys(
        t for t in patterns
        if t and len(t.encode("utf-8")) <= CTR_TITLE_MAX_CHARS
    ))[:4]


def _llm_patterns(topic: str, seed_title: str) -> list:
    """Ask a free-tier LLM for 4 novel viral French title angles."""
    if not _HAS_REQUESTS:
        return []
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return []
    model = os.environ.get("CTR_TITLE_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    prompt = (
        f"Tu es un rédacteur de titres YouTube Shorts en français pour une "
        f"chaîne de faits scientifiques sur le corps humain. Sujet : "
        f"\"{topic}\". Titre actuel : \"{seed_title}\". Écris exactement 4 "
        f"nouveaux titres à fort taux de clics pour le feed Shorts français. "
        f"Utilise ces modèles éprouvés : nombres et spécificité "
        f"(\"7 signes...\"), autorité (\"Ce que les médecins ne vous disent "
        f"pas...\"), enjeu personnel (\"Votre corps essaie de...\"), curiosité "
        f"inachevée (\"Ce qui arrive vraiment quand...\"). Aucun emoji, aucun "
        f"clickbait mensonger, pas de MAJUSCULES intégrales, maximum "
        f"{CTR_TITLE_MAX_CHARS} caractères chacun. Réponds UNIQUEMENT avec un "
        f"tableau JSON de 4 chaînes, rien d'autre."
    )
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.8},
            timeout=CTR_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        text = resp.json()["choices"][0]["message"]["content"].strip()
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return []
        items = [s.strip().strip('"').strip("'") for s in
                 m.group(0)[1:-1].split(",")]
        return [t.strip() for t in items if t and 10 <= len(t.strip())]
    except Exception:  # noqa: BLE001 - LLM layer is advisory
        return []


def get_ctr_title_options(topic: str, seed_title: str) -> list:
    """Return high-CTR French title candidates. LLM first (novelty), then
    rule-based patterns so a fully-degraded LLM still adds value."""
    off = os.environ.get("CTR_TITLES", "true").strip().lower() in (
        "false", "0", "no", "off",
    )
    if off:
        return []
    try:
        options = _llm_patterns(topic, seed_title)
    except Exception:  # noqa: BLE001 - must never break a run
        options = []
    options.extend(_rule_patterns(topic))
    seen, unique = set(), []
    for opt in options:
        key = opt.lower()
        if key not in seen:
            seen.add(key)
            unique.append(opt)
    # FR channels keep titles under the mobile display budget (title is
    # overlaid in the Shorts feed); longer LLM output is clipped by words.
    clipped = []
    for opt in unique[:6]:
        if len(opt.encode("utf-8")) > CTR_TITLE_MAX_CHARS:
            opt = _truncate_title(opt)
        clipped.append(opt)
    return clipped[:5]
