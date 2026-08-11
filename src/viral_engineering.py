#!/usr/bin/env python3
"""Viral engineering layer — evidence-based probability raisers (2026-08-12).

Nothing here can GUARANTEE views (only the audience decides); each piece is
one of the mechanics the winning Shorts channels actually engineer:

  1. HOOK ARMS (experiment rotation) — question vs shock-fact vs POV-reveal.
     Deterministic arm per topic (crc32), logged in history, significance via
     the intelligence layer's permutation test. Data, not vibes.
  2. SCORE_HOOK_V2 — a transparent 0-100 hook rubric. The old hook scorer was
     a single opaque number; this one decomposes WHY a hook is weak so the
     retry loop can fix the specific weakness.
  3. LOOP BRIDGE — a last line engineered to make the rewatch natural; on
     Shorts, looped replays count as >100% average retention and are the
     strongest single distribution signal.
  4. SURPRISE BEAT audit — every script needs ≥1 escalation in the middle
     scenes (number, contrast, unexpected turn); flat middles = swipe away.

French-native quality stays enforced upstream (french_quality_gate); this
module never emits medical claims or engagement bait.
"""
from __future__ import annotations

import re
import zlib

HOOK_ARMS = ("question", "shock_fact", "pov_reveal")

_BODY_WORDS = {
    "corps", "cerveau", "cœur", "coeur", "peau", "ventre", "yeux", "œil", "oeil",
    "os", "sang", "sommeil", "paupière", "paupiere", "doigts", "mains", "bouche",
    "langue", "oreilles", "nez", "pieds", "jambes", "muscles", "voix", "souffle",
}
_NOVELTY_WORDS = {
    "jamais", "secret", "personne", "toujours", "soudain", "en fait",
    "contrairement", "incroyable", "bizarre", "étrange", "etrange",
}
_GAP_MARKERS = ("?", "mais", "sauf", "pourtant", "en fait", "et pourtant", "sauf que")
_SECOND_PERSON = re.compile(r"\b(ton|ta|tes|votre|vos|vous|tu|te)\b", re.IGNORECASE)

_LOOP_BRIDGES = (
    "Et tout ça recommence dès la première seconde.",
    "La prochaine fois, ton corps recommencera exactement pareil.",
    "C'est ce cercle qui tourne en boucle dans ton corps.",
    "Et ça repart exactement comme au début de cette vidéo.",
    "Ton corps le refera dès que tu auras fini de regarder.",
    "Maintenant tu ne verras plus jamais ce moment pareil.",
)


def hook_arm_for_topic(topic: str) -> str:
    """Deterministic hook style per topic (stable across runs/machines)."""
    override = __import__("os").environ.get("VIRAL_HOOK_ARM", "").strip().lower()
    if override in HOOK_ARMS:
        return override
    return HOOK_ARMS[zlib.crc32((topic or "").encode("utf-8")) % len(HOOK_ARMS)]


def hook_style_instruction(arm: str) -> str:
    """French instruction injected into the LLM prompt for the given arm."""
    return {
        "question": (
            "HOOK (arme expérience = question) : la vidéo S'OUVRE sur une question "
            "directe à la seconde personne (« Pourquoi ton corps… », « Tu as déjà remarqué que… »). "
            "Une seule question, 5 à 10 mots, avec un verbe."
        ),
        "shock_fact": (
            "HOOK (arme expérience = fait choc) : la PREMIÈRE phrase est un fait "
            "surprenant et vrai, pas une question (« Ton cœur vient de… », "
            "« À cette seconde précise, ton cerveau… »). Reste exact — aucune "
            "promesse médicale, aucun chiffre inventé — mais crée un choc de curiosité."
        ),
        "pov_reveal": (
            "HOOK (arme expérience = POV immersif) : la première scène plonge le "
            "spectateur DANS la situation à la deuxième personne (« Tu te réveilles "
            "et ta main ne répond plus… ») puis promet la révélation scientifique."
        ),
    }.get(arm, "")


def score_hook_v2(hook_text: str) -> dict:
    """Transparent 0-100 hook rubric. Returns score + the 'why' breakdown.

    Deliberately transparent: a low score always names the missing ingredient
    so the retry loop can fix that exact weakness instead of re-rolling dice.
    """
    from french_quality_gate import has_french_verb

    text = " ".join(str(hook_text or "").split())
    words = text.split()
    lower = text.lower()
    breakdown: dict[str, int] = {}
    missing: list[str] = []

    def add(key: str, points: int, ok: bool, reason: str):
        breakdown[key] = points if ok else 0
        if not ok:
            missing.append(reason)

    add("second_person", 18, bool(_SECOND_PERSON.search(lower)), "pas de « ton/vous » (adresser le spectateur)")
    add("verb", 14, has_french_verb(text), "aucun verbe conjugué")
    add("length", 14, 4 <= len(words) <= 12, f"{len(words)} mots (idéal 4-12)")
    add("curiosity_gap", 12, any(m in lower for m in _GAP_MARKERS), "pas d'ouverture de boucle (?, mais, sauf…)")
    add("body_anchor", 12, any(w in lower for w in _BODY_WORDS), "pas d'ancrage corps concret")
    add("novelty", 10, any(w in lower for w in _NOVELTY_WORDS), "aucun marqueur de surprise")
    add("digit", 10, any(c.isdigit() for c in text), "aucun chiffre")
    add("specific", 10, not any(g in lower for g in ("truc", "chose incroyable", "dingue")), "terme générique (« truc »)")

    score = min(100, sum(breakdown.values()))
    return {
        "score": score,
        "grade": "strong" if score >= 70 else ("medium" if score >= 45 else "weak"),
        "breakdown": breakdown,
        "missing": missing,
    }


def loop_bridge_for(topic: str) -> str:
    """Deterministic loop-bridge line (always a full French sentence with a verb)."""
    return _LOOP_BRIDGES[zlib.crc32((topic or "").encode("utf-8")) % len(_LOOP_BRIDGES)]


def looks_like_loop_bridge(caption: str) -> bool:
    """Heuristic: does this caption pull the viewer back to the start?"""
    lower = (caption or "").lower()
    pulls = ("recommence", "repart", "boucle", "début", "premiere seconde",
             "première seconde", "encore une fois", "pareil")
    verbs_hint = any(p in lower for p in pulls)
    return verbs_hint


def surprise_beat_present(scenes: list) -> tuple[bool, str]:
    """Middle scenes need ≥1 escalation: digit, %, contrast turn or question.

    Flat middles are where the 4-9s cliff becomes the 10-20s graveyard.
    """
    middle = scenes[1:-1] if len(scenes) > 2 else scenes
    markers = ("mais", "sauf", "pourtant", "en fait", "contrairement", "soudain")
    for s in middle:
        cap = str(s.get("caption", "")).lower() if isinstance(s, dict) else ""
        if any(m in cap for m in markers) or any(c.isdigit() for c in cap) or "?" in cap or "%" in cap:
            return True, ""
    return False, "aucune scène centrale ne contient d'escalade (chiffre, contraste, question)"


def viral_script_audit(script_data: dict) -> dict:
    """Non-fatal advisory pass on a generated script (does not mutate)."""
    hook = script_data.get("hook") or ""
    hook_eval = score_hook_v2(hook or script_data.get("title", ""))
    scenes = script_data.get("scenes", []) or []
    beat_ok, beat_reason = surprise_beat_present(scenes)
    last_caption = ""
    if scenes and isinstance(scenes[-1], dict):
        last_caption = scenes[-1].get("caption", "")
    loop_ok = looks_like_loop_bridge(last_caption)

    warnings = []
    if hook_eval["grade"] == "weak":
        warnings.append("hook faible: " + ", ".join(hook_eval["missing"][:3]))
    if not beat_ok:
        warnings.append(beat_reason)
    if not loop_ok:
        warnings.append("dernière scène sans pont de boucle (la relecture ne sera pas naturelle)")

    return {
        "hook_arm": script_data.get("hook_arm"),
        "hook_score_v2": hook_eval["score"],
        "hook_grade": hook_eval["grade"],
        "hook_missing": hook_eval["missing"],
        "surprise_beat": beat_ok,
        "loop_bridge_present": loop_ok,
        "warnings": warnings,
    }
