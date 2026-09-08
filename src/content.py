from __future__ import annotations

import json
import os
import re
from typing import Any

from config import Settings

FALLBACK_TOPICS = [
    "Pourquoi votre cerveau bâille-t-il quand quelqu’un bâille ?",
    "Pourquoi la peau se couvre-t-elle de chair de poule ?",
    "Pourquoi un souvenir revient-il avec une odeur ?",
    "Pourquoi le cœur accélère-t-il avant une décision ?",
    "Pourquoi les jambes tremblent-elles sous le stress ?",
]

FRANCE_COPY_RULES = (
    "Écris en français de France métropolitaine, naturel et actuel. Utilise le tutoiement "
    "(tu, ton, ta, tes) pour parler directement au spectateur. Évite les calques de l’anglais, "
    "les tournures québécoises ou belges non nécessaires, le jargon administratif et les formulations "
    "trop littérales. Préfère des phrases courtes, fluides et orales, sans exagération médicale."
)

# This mirrors score_hook() / score_script_quality() below line for line, so the
# model is optimizing for exactly what the gate checks — not guessing at it.
HOOK_SCORING_RUBRIC = """RÈGLES DE NOTATION DU HOOK — ton texte est noté automatiquement, vise le score maximum.

1) LE TITRE (doit finir par un point d'interrogation) :
   - Termine par "?" → +15 points. Un titre qui n'est pas une question perd 15 points ailleurs, alors termine TOUJOURS par "?".
   - Contient un mot de curiosité — "pourquoi", "comment", "et si", "ce que" — → +10 points.
   - Fait 70 caractères ou moins → +10 points. Au-delà de 70 caractères → -15 points. Reste COURT.
   - Ne révèle jamais la réponse dans le titre : pose la question, ne donne pas le mécanisme.

2) LA PREMIÈRE SCÈNE (caption) — c'est elle qui décide si le spectateur reste ou skip :
   - Contient "tu", "ton", "ta", "tes" ou "toi" (adresse directe) → +10 points.
   - Fait entre 3 et 7 mots → +10 points. Plus de 12 mots → -15 points.
   - N'utilise JAMAIS une formule générique du type "Dans cette vidéo…", "Aujourd'hui on va parler de…",
     "Bonjour à tous", "Salut tout le monde", "On va voir ensemble", "Dans cet épisode", "Bienvenue dans",
     "Je vais vous expliquer" → chacune de ces formules fait perdre 25 points. INTERDITES.

3) CHAQUE SCÈNE (les 8, pas seulement la première) — le rythme doit rester serré du début à la fin :
   - Toutes les captions doivent faire entre 3 et 8 mots idéalement (jamais plus de 12 mots).
   - Aucune formule générique de la liste interdite ci-dessus, dans AUCUNE scène.
   - Chaque caption doit apporter une info concrète et courte, pas une transition vide.

EXEMPLE QUI OBTIENT LE SCORE MAXIMUM (titre 100/100, rythme 90/100) :
{
  "title": "Pourquoi ton cerveau rêve-t-il ?",
  "scenes": [
    {"caption": "ATTENDS—ton cerveau fait ça.", "narration": "..."},
    {"caption": "La réponse commence dans ton cerveau.", "narration": "..."},
    {"caption": "Il repère d'abord un signal.", "narration": "..."}
  ]
}
Remarque pourquoi ça marche : titre = question courte + "pourquoi" + "ton" (adresse directe) ;
scène 1 = 5 mots, commence par une accroche ("ATTENDS—"), pas de formule générique."""

# "Point par point" mystery/investigation arc: each scene reveals exactly one
# new clue, nothing is repeated, and a mid-video twist re-hooks the viewer at
# the exact moment YouTube's retention curve typically dips.
MYSTERY_STRUCTURE_GUIDE = """STRUCTURE NARRATIVE "POINT PAR POINT" (mystère façon enquête) — 8 scènes, dans cet ordre EXACT :

Scène 1 — L'ACCROCHE : pose l'énigme sans la résoudre. Le spectateur doit penser "attends, quoi ?!".
Scène 2 — LE MYSTÈRE : formule clairement la question à laquelle la vidéo va répondre. Zéro indice encore.
Scène 3 — INDICE 1 : un premier élément concret, qui seul ne suffit pas à comprendre.
Scène 4 — INDICE 2 : une deuxième pièce du puzzle. Le spectateur commence à deviner, sans être sûr.
Scène 5 — REBONDISSEMENT : un fait surprenant qui bouscule ce que le spectateur croyait avoir compris.
   C'est le point de la vidéo où l'attention décroche le plus souvent — cette scène DOIT relancer la curiosité.
Scène 6 — INDICE 3 : la pièce qui relie tout. Les points commencent à se connecter entre eux.
Scène 7 — RÉVÉLATION : la réponse complète, simple, qui relie tous les indices précédents en une seule idée claire.
Scène 8 — LA CHUTE : une phrase courte qui donne envie de vérifier par soi-même, de commenter ou de partager —
   jamais une formule de conclusion générique ("voilà", "et voilà pourquoi", "j'espère que ça t'a plu").

RÈGLE D'OR : chaque scène apporte UNE SEULE information nouvelle (un "point"), jamais deux à la fois,
et ne répète JAMAIS une information déjà donnée dans une scène précédente. Le spectateur doit sentir
qu'il résout une enquête scène après scène, jusqu'à ce que tous les points se relient à la scène 7."""

# Generic openers that waste the first watch-time seconds instead of hooking
# the viewer — a Short that starts here is far more likely to be skipped.
_FILLER_OPENERS = (
    "dans cette vidéo", "aujourd’hui on va parler de", "aujourd'hui on va parler de",
    "bonjour à tous", "salut tout le monde", "on va voir ensemble", "dans cet épisode",
    "bienvenue dans", "je vais vous expliquer",
)
_DIRECT_ADDRESS_RE = re.compile(r"\b(tu|ton|ta|tes|toi)\b", re.IGNORECASE)
_CURIOSITY_WORDS = ("pourquoi", "comment", "et si", "ce que")


def score_hook(title: str, first_caption: str) -> int:
    """Heuristic 0-100 score for the opening hook (title + first caption).

    A Short's watch-time survival is decided in its first seconds, so this
    rewards the things that keep a viewer from skipping: an open curiosity
    gap, direct address, and a title/caption short enough to land instantly.
    It penalizes generic openers that burn that window without payoff.
    """
    title = title.strip()
    caption = first_caption.strip()
    title_lower = title.lower()
    caption_lower = caption.lower()
    score = 50
    if title.endswith("?"):
        score += 15
    if any(word in title_lower for word in _CURIOSITY_WORDS):
        score += 10
    if _DIRECT_ADDRESS_RE.search(title_lower) or _DIRECT_ADDRESS_RE.search(caption_lower):
        score += 10
    score += 10 if len(title) <= 70 else -15
    word_count = len(caption.split())
    if 3 <= word_count <= 7:
        score += 10
    elif word_count > 12:
        score -= 15
    if any(opener in caption_lower for opener in _FILLER_OPENERS):
        score -= 25
    return max(0, min(100, score))


def _scene_pace_score(caption: str) -> int:
    """Heuristic 0-100 score for a single scene's caption pacing."""
    words = caption.split()
    score = 70
    word_count = len(words)
    if 3 <= word_count <= 8:
        score += 20
    elif word_count > 12:
        score -= 30
    elif word_count == 0:
        return 0
    if any(opener in caption.lower() for opener in _FILLER_OPENERS):
        score -= 25
    return max(0, min(100, score))


def score_script_quality(scenes: list[dict[str, Any]]) -> int:
    """Average per-scene pacing score — a proxy for retention across the whole Short."""
    if not scenes:
        return 0
    scores = [_scene_pace_score(str(scene.get("caption", ""))) for scene in scenes]
    return round(sum(scores) / len(scores))


def _clean_fr(text: str) -> str:
    text = re.sub(r"\s+([?!:;…])", r"\1", text.strip())
    text = re.sub(r"\s{2,}", " ", text)
    return text


def load_topic(settings: Settings) -> str:
    if settings.topic:
        return _clean_fr(settings.topic)
    queue = settings.data_dir / "search_demand_queue_fr.json"
    if queue.exists():
        try:
            payload = json.loads(queue.read_text(encoding="utf-8"))
            items = payload if isinstance(payload, list) else payload.get("topics", [])
            history = settings.data_dir / "video_history.json"
            used = set()
            if history.exists():
                rows = json.loads(history.read_text(encoding="utf-8"))
                used = {_clean_fr(str(row.get("topic", ""))).lower() for row in rows if isinstance(row, dict)}
            pointer_path = settings.data_dir / "queue_index_fr.json"
            try:
                pointer = int(json.loads(pointer_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pointer = 0
            ordered = items[pointer % len(items):] + items[:pointer % len(items)] if items else []
            for offset, item in enumerate(ordered):
                title = item.get("title") if isinstance(item, dict) else str(item)
                if title and _clean_fr(str(title)).lower() not in used:
                    pointer_path.write_text(json.dumps(pointer + offset + 1), encoding="utf-8")
                    return _clean_fr(str(title))
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    history = settings.data_dir / "video_history.json"
    used = set()
    if history.exists():
        try:
            rows = json.loads(history.read_text(encoding="utf-8"))
            used = {_clean_fr(str(row.get("topic", ""))).lower() for row in rows if isinstance(row, dict)}
        except (OSError, json.JSONDecodeError):
            pass
    return next((topic for topic in FALLBACK_TOPICS if _clean_fr(topic).lower() not in used), FALLBACK_TOPICS[0])


def _fallback_script(topic: str) -> dict[str, Any]:
    # Mirrors MYSTERY_STRUCTURE_GUIDE's 8 roles: hook, mystery, clue x2,
    # twist, final clue, reveal, payoff — kept in sync by hand since this
    # path never calls the LLM.
    clean = _clean_fr(topic).rstrip("?")
    return {
        "title": _clean_fr(clean + " ?"),
        "description": f"Tu vas comprendre pourquoi {clean.lower()}. Une explication claire en quelques secondes. #shorts #science",
        "tags": ["science", "cerveau", "corps humain", "curiosité", "shorts français"],
        "scenes": [
            {"caption": "ATTENDS—ton cerveau fait ça.", "narration": clean + " ?"},
            {"caption": "La réponse commence dans ton cerveau.", "narration": "La réponse commence dans ton cerveau."},
            {"caption": "Il repère d’abord un signal.", "narration": "Il repère d’abord un signal."},
            {"caption": "Puis il cherche un souvenir lié.", "narration": "Puis il cherche un souvenir lié."},
            {"caption": "Une odeur peut réveiller une émotion.", "narration": "Une odeur peut réveiller une émotion."},
            {"caption": "Le cerveau associe les deux très vite.", "narration": "Le cerveau associe les deux très vite."},
            {"caption": "C’est pourquoi le souvenir semble soudain.", "narration": "C’est pourquoi le souvenir semble soudain."},
            {"caption": "Observe-le la prochaine fois.", "narration": "Observe-le la prochaine fois."},
        ],
    }


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM returned no JSON object")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict) or not payload.get("scenes"):
        raise ValueError("LLM JSON has no scenes")
    payload["title"] = _clean_fr(str(payload.get("title", "")))
    payload["description"] = _clean_fr(str(payload.get("description", "")))
    for scene in payload["scenes"]:
        scene["caption"] = _clean_fr(str(scene.get("caption", "")))
        scene["narration"] = _clean_fr(str(scene.get("narration", "")))
    return payload


def generate_script(topic: str, settings: Settings) -> dict[str, Any]:
    if settings.dry_run or not settings.llm_keys:
        return _fallback_script(topic)
    api_key = os.getenv(settings.llm_keys[0], "")
    if settings.llm_keys[0] != "GROQ_API_KEY":
        return _fallback_script(topic)
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
    except Exception:
        return _fallback_script(topic)

    system_prompt = (
        f"{FRANCE_COPY_RULES}\n\n{HOOK_SCORING_RUBRIC}\n\n{MYSTERY_STRUCTURE_GUIDE}\n\n"
        "Réponds uniquement en JSON valide."
    )
    user_prompt = (
        f"Sujet: {topic}\nCrée un titre de moins de 70 caractères et EXACTEMENT 8 scènes très courtes, "
        "en suivant précisément les 8 rôles de la structure point par point ci-dessus (scène 1 = accroche, "
        "scène 2 = mystère, scène 3-4 = indices, scène 5 = rebondissement, scène 6 = indice final, "
        "scène 7 = révélation, scène 8 = chute). Chaque scène doit contenir caption et narration en "
        f"français de France. Durée cible {settings.min_seconds:g}-{settings.max_seconds:g}s. "
        "Applique STRICTEMENT les règles de notation ET la structure narrative ci-dessus avant de répondre."
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                temperature=0.6,
                response_format={"type": "json_object"},
                messages=messages,
            )
            raw = response.choices[0].message.content or ""
            result = _extract_json(raw)
            scenes = result.get("scenes", [])
            if len(scenes) != 8:
                raise ValueError(f"il faut exactement 8 scènes (reçu {len(scenes)})")
            hook_score = score_hook(str(result.get("title", "")), str(scenes[0].get("caption", "")))
            quality_score = score_script_quality(scenes)
            if hook_score >= settings.min_hook_score and quality_score >= settings.quality_approval_threshold:
                return result
            reason = (
                f"score du hook = {hook_score} (minimum requis {settings.min_hook_score}), "
                f"score de rythme = {quality_score} (minimum requis {settings.quality_approval_threshold})."
            )
        except (ValueError, KeyError, TypeError) as exc:
            reason = str(exc)
        except Exception:
            # Network/API-level failures are not worth retrying against the same prompt.
            return _fallback_script(topic)
        if attempt == max_attempts:
            break
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": (
            f"Ta réponse a échoué la validation : {reason} Relis attentivement les règles de notation "
            "et la structure narrative point par point, et renvoie un JSON complet et corrigé "
            "(titre + 8 scènes, une scène par rôle de l'enquête) qui respecte STRICTEMENT chaque règle."
        )})
    return _fallback_script(topic)
