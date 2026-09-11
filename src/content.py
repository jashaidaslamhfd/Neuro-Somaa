from __future__ import annotations

import json
import os
import re
from typing import Any

from config import Settings

FALLBACK_TOPICS = [
    "Pourquoi le bâillement est contagieux ?",
    "Pourquoi as-tu la chair de poule ?",
    "Pourquoi une odeur réveille un souvenir ?",
    "Pourquoi ton cœur accélère avant de choisir ?",
    "Pourquoi tes jambes tremblent sous le stress ?",
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

1) LE TITRE — PLUS C'EST COURT, PLUS ÇA MARCHE. Deux styles acceptés, à égalité de points :
   STYLE QUESTION : termine par "?" → +15 points. Contient un mot de curiosité — "pourquoi", "comment",
     "et si", "ce que" — → +10 points bonus.
   STYLE RÉVÉLATION (POV-reveal) : pas de "?", mais la scène 1 commence par une interjection qui capte
     l'attention ("ATTENDS", "STOP", "REGARDE", "VOICI", "ÉCOUTE", "IMAGINE") ou un mot en MAJUSCULES →
     +15 points, autant qu'une question. Les données de la chaîne montrent que ce style fonctionne AU MOINS
     aussi bien qu'une question — n'hésite pas à l'utiliser pour varier.
   Un titre qui n'est NI une question NI accompagné d'une accroche-révélation perd 15 points. Choisis toujours
   l'un des deux styles.
   LONGUEUR (notée par palier, vise le plus court possible) : ≤35 caractères → +15 points ; ≤50 → +10 ;
     ≤70 → +5 ; au-delà de 70 → -15. Un titre court, unique et clair se lit d'un coup d'œil sur un flux
     Shorts et se démarque — c'est ce qui le rend partageable. Ne révèle jamais la réponse dans le titre.
   UNICITÉ : n'ouvre pas ton titre par le même premier mot que tes dernières vidéos (ex. pas toujours
     "Pourquoi…") — varie l'angle et la formulation pour que chaque titre ait sa propre identité.

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

EXEMPLE STYLE QUESTION (score maximum, titre 100/100) :
{
  "title": "Pourquoi ton cerveau rêve-t-il ?",
  "scenes": [
    {"caption": "ATTENDS—ton cerveau fait ça.", "narration": "..."},
    {"caption": "La réponse commence dans ton cerveau.", "narration": "..."},
    {"caption": "Il repère d'abord un signal.", "narration": "..."}
  ]
}

EXEMPLE STYLE RÉVÉLATION — sans "?", même score maximum grâce à l'accroche "ATTENDS" :
{
  "title": "Ton cerveau efface tes rêves en quelques secondes",
  "scenes": [
    {"caption": "ATTENDS—ça se passe chaque nuit.", "narration": "..."},
    {"caption": "Ton cerveau trie ce qu'il garde.", "narration": "..."}
  ]
}
Remarque : les deux exemples marchent parce que chacun choisit UN style clairement (question OU
révélation), utilise l'adresse directe ("ton"), reste court, et évite toute formule générique."""

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

# Previously the prompt never asked for tags/hashtags at all, so real
# generations uploaded with empty tags most of the time. This makes
# topic-specific metadata a required, validated part of the JSON contract,
# the same way the hook and structure are.
METADATA_RULES = """MÉTADONNÉES SEO — obligatoires dans le JSON, en plus du titre et des scènes :

"description" : 1 à 2 phrases en français qui reformulent le hook du titre SANS donner la
réponse, suivies d'exactement 3 à 5 hashtags français pertinents au sujet PRÉCIS de la
vidéo (jamais génériques comme "#shorts" seul) — ex. "#cerveau #neurosciences #saistu
#shorts #france". Longueur totale max 400 caractères.

"tags" : liste de 8 à 12 mots-clés français EN RAPPORT DIRECT avec le sujet exact de cette
vidéo (jamais une liste générique répétée à chaque vidéo). Mélange obligatoire :
- 2-3 mots-clés larges (ex. "science", "corps humain")
- 3-4 mots-clés spécifiques au sujet exact de cette vidéo
- 2-3 variantes de longue traîne en style recherche (ex. "pourquoi on bâille")
- 1-2 tags de marché : "france", "shorts français"
Ne réutilise jamais mot pour mot la liste de tags d'une vidéo précédente."""

# Generic openers that waste the first watch-time seconds instead of hooking
# the viewer — a Short that starts here is far more likely to be skipped.
_FILLER_OPENERS = (
    "dans cette vidéo", "aujourd’hui on va parler de", "aujourd'hui on va parler de",
    "bonjour à tous", "salut tout le monde", "on va voir ensemble", "dans cet épisode",
    "bienvenue dans", "je vais vous expliquer",
)
_DIRECT_ADDRESS_RE = re.compile(r"\b(tu|ton|ta|tes|toi)\b", re.IGNORECASE)
_CURIOSITY_WORDS = ("pourquoi", "comment", "et si", "ce que")
# A caption opening on a punchy interjection or an ALL-CAPS attention-grab
# word signals a "POV-reveal" style hook — the channel's own analytics
# (hook_arms, growth_state.hook_weights) show this style outperforming plain
# questions, so it earns the same credit as a question instead of a penalty.
_REVEAL_INTERJECTIONS = ("attends", "stop", "regarde", "voici", "écoute", "alerte", "imagine")


_LEADING_WORD_RE = re.compile(r"^([A-ZÀ-Ü][A-ZÀ-Üa-zà-ÿ']*)")


def _has_reveal_opener(caption: str) -> bool:
    match = _LEADING_WORD_RE.match(caption.strip())
    if not match:
        return False
    word = match.group(1)
    return word.lower() in _REVEAL_INTERJECTIONS or word.isupper()


def score_hook(title: str, first_caption: str) -> int:
    """Heuristic 0-100 score for the opening hook (title + first caption).

    A Short's watch-time survival is decided in its first seconds. Two hook
    styles are credited equally here because the channel's own data shows
    both working: a curiosity-gap question, or a punchy declarative
    "POV-reveal" opener (e.g. "ATTENDS—..."). Only a flat title that is
    neither is penalized.
    """
    title = title.strip()
    caption = first_caption.strip()
    title_lower = title.lower()
    caption_lower = caption.lower()
    score = 50
    is_question = title.endswith("?")
    if is_question:
        score += 15
        if any(word in title_lower for word in _CURIOSITY_WORDS):
            score += 10
    elif _has_reveal_opener(caption):
        score += 15
    else:
        score -= 15
    if _DIRECT_ADDRESS_RE.search(title_lower) or _DIRECT_ADDRESS_RE.search(caption_lower):
        score += 10
    # Tiered, not a flat cutoff: the shorter the title, the more it earns —
    # a short title reads instantly on a thumbnail/feed and is what the
    # channel's own data associates with stronger performance.
    length = len(title)
    if length <= 35:
        score += 15
    elif length <= 50:
        score += 10
    elif length <= 70:
        score += 5
    else:
        score -= 15
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


_STOPWORDS_FR = frozenset((
    "le", "la", "les", "un", "une", "des", "de", "du", "ton", "ta", "tes", "tu", "toi",
    "ce", "que", "qui", "et", "ou", "à", "en", "au", "aux", "il", "elle", "on", "pourquoi",
    "comment", "quand",
))


def _title_words(title: str) -> set[str]:
    return {w for w in re.sub(r"[^\wà-ÿ' ]", " ", title.lower()).split() if w not in _STOPWORDS_FR}


def title_is_fresh(title: str, settings: Settings, lookback: int = 8, similarity_threshold: float = 0.55) -> bool:
    """Reject titles that are near word-for-word duplicates of a recent upload.

    This only catches genuine repeats (same topic, reworded) — it does not
    enforce opening-word variety as a hard gate, since a channel whose whole
    history already shares one opener (as this one's does) would otherwise
    fail every single attempt and burn the retry budget for nothing. Opener
    variety is instead a soft instruction in HOOK_SCORING_RUBRIC.
    """
    history = settings.data_dir / "video_history.json"
    if not history.exists():
        return True
    try:
        rows = json.loads(history.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    recent_titles = [str(row.get("title", "")) for row in rows[-lookback:] if isinstance(row, dict) and row.get("title")]
    candidate_words = _title_words(title)
    if not candidate_words:
        return True
    for past_title in recent_titles:
        past_words = _title_words(past_title)
        if not past_words:
            continue
        overlap = len(candidate_words & past_words) / len(candidate_words | past_words)
        if overlap >= similarity_threshold:
            return False
    return True


def _clean_fr(text: str) -> str:
    text = re.sub(r"\s+([?!:;…])", r"\1", text.strip())
    text = re.sub(r"\s{2,}", " ", text)
    return text


# The channel's own historical analytics (topic_weights, before that data was
# untracked from git) showed involuntary-movement/digestive body topics
# consistently outperforming, and eye/heart topics underperforming. This is a
# soft nudge, not a hard filter — it only picks among the next few unused
# queue entries so topic rotation and freshness are still respected.
_WINNING_TOPIC_KEYWORDS = ("muscle", "ventre", "intestin", "pied", "estomac", "digestion")
_LOSING_TOPIC_KEYWORDS = ("œil", "oeil", "yeux", "cœur", "coeur")
_TOPIC_LOOKAHEAD = 12


def _topic_cluster_score(title: str) -> int:
    normalized = title.lower()
    score = sum(1 for kw in _WINNING_TOPIC_KEYWORDS if kw in normalized)
    score -= sum(1 for kw in _LOSING_TOPIC_KEYWORDS if kw in normalized)
    return score


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
            candidates: list[tuple[int, str]] = []
            for offset, item in enumerate(ordered):
                title = item.get("title") if isinstance(item, dict) else str(item)
                if title and _clean_fr(str(title)).lower() not in used:
                    candidates.append((offset, _clean_fr(str(title))))
                if len(candidates) >= _TOPIC_LOOKAHEAD:
                    break
            if candidates:
                # Highest cluster score wins; ties broken by queue order
                # (earliest offset) to keep rotation predictable.
                offset, title = max(candidates, key=lambda c: (_topic_cluster_score(c[1]), -c[0]))
                pointer_path.write_text(json.dumps(pointer + offset + 1), encoding="utf-8")
                return title
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


def _fallback_tags(topic: str) -> list[str]:
    """Derive tags from the topic instead of a fixed list, so if the LLM
    path is ever unavailable the channel doesn't upload the same 5 generic
    tags on every video."""
    words = [
        w for w in re.sub(r"[^\wà-ÿ' ]", " ", topic.lower()).split()
        if len(w) > 2 and w not in _STOPWORDS_FR
    ]
    specific = words[:4] or ["quotidien"]
    tags = ["science", "corps humain", *specific, "curiosité", "france", "shorts français"]
    seen: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.append(tag)
    return seen[:10]


def _fallback_script(topic: str) -> dict[str, Any]:
    # Mirrors MYSTERY_STRUCTURE_GUIDE's 8 roles: hook, mystery, clue x2,
    # twist, final clue, reveal, payoff — kept in sync by hand since this
    # path never calls the LLM.
    clean = _clean_fr(topic).rstrip("?")
    return {
        "title": _clean_fr(clean + " ?"),
        "description": f"Tu vas comprendre pourquoi {clean.lower()}. Une explication claire en quelques secondes. #shorts #science #france",
        "tags": _fallback_tags(clean),
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
    # Metadata is now a required part of the contract (see METADATA_RULES) —
    # previously nothing enforced this, so real generations often uploaded
    # with empty tags and a generic/no-hashtag description.
    tags = payload.get("tags")
    if not isinstance(tags, list) or not (8 <= len(tags) <= 12):
        raise ValueError("il faut 8 à 12 tags SEO spécifiques au sujet (voir MÉTADONNÉES SEO)")
    description = str(payload.get("description", ""))
    if not description or description.count("#") < 3:
        raise ValueError("la description doit inclure 3 à 5 hashtags pertinents au sujet")
    payload["title"] = _clean_fr(str(payload.get("title", "")))
    payload["description"] = _clean_fr(description)
    payload["tags"] = [_clean_fr(str(tag)) for tag in tags][:12]
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
        f"{METADATA_RULES}\n\nRéponds uniquement en JSON valide."
    )
    user_prompt = (
        f"Sujet: {topic}\nCrée un titre le plus court possible (idéalement 35-50 caractères, jamais plus de 70) "
        "et EXACTEMENT 8 scènes très courtes, en suivant précisément les 8 rôles de la structure point par "
        "point ci-dessus (scène 1 = accroche, scène 2 = mystère, scène 3-4 = indices, scène 5 = rebondissement, "
        "scène 6 = indice final, scène 7 = révélation, scène 8 = chute). Chaque scène doit contenir caption et "
        f"narration en français de France. Durée cible {settings.min_seconds:g}-{settings.max_seconds:g}s. "
        "N'oublie pas les champs \"description\" (avec 3-5 hashtags) et \"tags\" (8-12 mots-clés "
        "spécifiques au sujet), voir MÉTADONNÉES SEO. Applique STRICTEMENT les règles de notation, "
        "la structure narrative ET les métadonnées SEO ci-dessus avant de répondre."
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
            fresh = title_is_fresh(str(result.get("title", "")), settings)
            if hook_score >= settings.min_hook_score and quality_score >= settings.quality_approval_threshold and fresh:
                return result
            reasons = []
            if hook_score < settings.min_hook_score:
                reasons.append(f"score du hook = {hook_score} (minimum requis {settings.min_hook_score})")
            if quality_score < settings.quality_approval_threshold:
                reasons.append(f"score de rythme = {quality_score} (minimum requis {settings.quality_approval_threshold})")
            if not fresh:
                reasons.append(
                    "le titre ressemble trop à une vidéo récente (mêmes mots-clés ou même mot de départ) — "
                    "choisis un angle et un premier mot différents"
                )
            reason = "; ".join(reasons)
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
