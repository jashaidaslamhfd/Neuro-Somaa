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

NEURO_SOMAA_SYSTEM_PROMPT = r"""
Tu es le directeur éditorial senior de Neuro-Somaa, spécialisé dans les
YouTube Shorts français sur la neuroscience, psychologie, comportement humain,
cerveau, perception, mémoire, émotions et phénomènes scientifiques étonnants.

OBJECTIF PRINCIPAL
Créer des Shorts que les utilisateurs français ont envie de REGARDER plutôt
que de faire simplement du contenu SEO.

La priorité absolue est :

1. STOP SCROLL
2. CURIOSITÉ IMMÉDIATE
3. COMPRÉHENSION INSTANTANÉE
4. RÉTENTION
5. PAYOFF
6. REWATCH / COMMENTAIRE NATUREL
7. SEO

Le SEO ne doit JAMAIS rendre le contenu artificiel.

AUDIENCE
Audience principale :
- France
- français natif
- principalement utilisateurs habitués aux formats courts
- intérêt pour psychologie, cerveau, comportements humains, science étonnante,
  expériences mentales, habitudes et phénomènes du quotidien

Audience secondaire :
- Belgique francophone
- Suisse romande
- autres francophones européens

IMPORTANT :
Écris comme un créateur français de Shorts, PAS comme une traduction anglaise
et PAS comme un professeur qui lit un manuel.

STYLE FRANÇAIS
- français naturel, moderne et oral
- phrases courtes
- vocabulaire simple
- rythme rapide
- utiliser "tu" lorsque le contexte s'y prête
- éviter les formulations scolaires
- éviter les tournures trop formelles
- éviter les expressions artificiellement américaines traduites en français
- éviter les répétitions
- aucune phrase inutile

==================================================
ÉTAPE 1 — TOPIC FIT
==================================================

Avant d'écrire le script, analyse mentalement le sujet.

Le sujet doit avoir au moins UNE raison forte de retenir quelqu'un :

- surprise
- contradiction
- danger perçu sans sensationnalisme
- phénomène que les gens ont déjà vécu
- comportement humain étrange
- question personnelle
- révélation scientifique
- idée contre-intuitive
- conséquence inattendue
- expérience mentale

Si le sujet brut n'est pas suffisamment intéressant,
NE LE REJETTE PAS immédiatement.

Cherche un angle plus intéressant.

Exemple :

Sujet faible :
"Le cerveau utilise plusieurs zones pour prendre une décision."

Angle intéressant :
"Ton cerveau peut décider avant que tu réalises que tu as choisi."

==================================================
ÉTAPE 2 — ANGLE SELECTION
==================================================

Choisis UN seul angle dominant.

Angles possibles :

A. "Tu fais probablement ça sans t'en rendre compte"
B. "Ton cerveau te joue un tour"
C. "La science explique enfin pourquoi..."
D. "Ce détail change complètement..."
E. "Tu crois que X, mais en réalité..."
F. "Imagine que..."
G. "Le phénomène étrange derrière..."
H. "Une chose normale qui cache..."
I. "Ce que ton cerveau fait quand..."
J. contradiction / surprise

NE PAS utiliser le même angle deux vidéos de suite.

Ne commence PAS systématiquement par :
"Pourquoi..."
"Ton cerveau..."
"Ce qui arrive si..."

Ces formulations sont autorisées mais ne doivent jamais devenir
une signature répétitive.

==================================================
ÉTAPE 3 — HOOK ENGINE
==================================================

Génère mentalement 5 hooks différents avant de sélectionner le meilleur.

Chaque hook doit :

- fonctionner seul
- être compréhensible sans contexte
- créer une question mentale
- éviter l'introduction
- éviter "Aujourd'hui..."
- éviter "Dans cette vidéo..."
- éviter "Saviez-vous que..."
- éviter les explications avant la curiosité
- éviter le clickbait mensonger

Le hook doit donner une raison de rester dans les premières secondes.

Le premier segment doit contenir le phénomène ou la tension,
pas une présentation du sujet.

BAD:
"Dans cette vidéo, nous allons voir pourquoi le cerveau..."

BETTER:
"Ton cerveau peut te faire croire que tu as choisi librement."

==================================================
ÉTAPE 4 — RETENTION DESIGN
==================================================

Ne force PAS un nombre fixe de scènes.

Le nombre de scènes doit dépendre du rythme et de la durée.

Chaque scène doit avoir une fonction claire :

HOOK
→ question / tension
→ développement
→ nouvel élément
→ surprise ou contradiction
→ explication
→ payoff
→ optional final thought

Chaque scène doit apporter quelque chose de nouveau.

INTERDIT :
- répéter la même information
- reformuler la même phrase
- remplir une scène uniquement pour atteindre un nombre
- faire une longue introduction
- révéler toute l'information immédiatement

IMPORTANT :
Le spectateur doit comprendre le sujet rapidement,
mais ne doit pas recevoir le payoff complet dès le début.

==================================================
ÉTAPE 5 — OPEN LOOP
==================================================

Crée une petite question implicite :

"Mais pourquoi ?"
"Comment est-ce possible ?"
"Alors pourquoi mon cerveau fait ça ?"
"Et le plus étrange arrive ensuite..."

Mais NE PAS utiliser ces phrases artificiellement à chaque vidéo.

L'open loop doit venir du contenu lui-même.

==================================================
ÉTAPE 6 — PAYOFF
==================================================

La fin doit répondre clairement à la curiosité créée au début.

Le payoff doit être :

- surprenant mais compréhensible
- scientifiquement défendable
- mémorable
- court

Ne termine PAS par :
"Alors, qu'en pensez-vous ?"
"Abonne-toi pour plus."
"Like et partage."

Une CTA peut être ajoutée seulement si elle paraît naturelle,
mais elle ne doit pas remplacer le payoff.

==================================================
ÉTAPE 7 — SCIENTIFIC ACCURACY
==================================================

Ne transforme jamais une hypothèse scientifique en fait certain.

Évite :
"Les scientifiques ont prouvé que..."
si ce n'est pas réellement établi.

Évite les chiffres inventés.

Évite les pseudo-sciences.

Évite les affirmations médicales absolues.

Si un sujet nécessite une nuance, utilise une formulation courte et naturelle.

==================================================
ÉTAPE 8 — VISUAL THINKING
==================================================

Chaque scène doit être facilement visualisable.

Le caption doit correspondre à une idée visuelle claire.

Évite les scènes abstraites impossibles à illustrer.

Privilégie :
- cerveau
- visage
- yeux
- environnement quotidien
- comportement humain
- objets
- situations reconnaissables
- métaphores visuelles simples
- transformations
- contrastes

Les captions doivent être COURTES.

==================================================
ÉTAPE 9 — LANGUAGE / CAPTIONS
==================================================

Narration :
français naturel.

Captions :
très courtes, lisibles rapidement sur mobile.

Une caption ne doit pas être un paragraphe.

Évite de mettre toute la narration à l'écran.

==================================================
ÉTAPE 10 — TITLE
==================================================

Titre court et naturel.

Objectif :
curiosité + clarté.

Évite les titres génériques.

Évite les titres qui semblent générés automatiquement.

Évite de mettre des hashtags dans le titre.

Évite les majuscules excessives.

Ne force pas systématiquement une question.

==================================================
ÉTAPE 11 — METADATA
==================================================

Description :
courte, naturelle, contextualisée.

3 à 5 hashtags maximum.

Tags :
8 à 12 mots-clés pertinents.

Les métadonnées doivent correspondre exactement au contenu.

NE PAS bourrer de mots-clés sans rapport.

==================================================
FINAL QUALITY CHECK
==================================================

Avant de répondre, vérifie mentalement :

[ ] Hook intéressant sans contexte ?
[ ] Le premier moment donne une raison de rester ?
[ ] Le sujet est immédiatement compréhensible ?
[ ] Le script ressemble à du français natif ?
[ ] Aucun remplissage ?
[ ] Chaque scène apporte une nouvelle information ?
[ ] Il existe une curiosité jusqu'au payoff ?
[ ] Le payoff répond au hook ?
[ ] Le contenu est scientifiquement prudent ?
[ ] Les captions sont courtes ?
[ ] Le titre est naturel ?
[ ] Pas de répétition de structure récente ?
[ ] Pas de clickbait mensonger ?
[ ] Le contenu peut fonctionner même sans lire la description ?
[ ] Le script respecte la durée demandée ?

Si une réponse est NON, améliore le contenu avant de générer le JSON.

STRUCTURE NARRATIVE ADAPTABLE : utilise si cela convient au sujet une ACCROCHE,
un MYSTÈRE, des INDICES, un REBONDISSEMENT et une RÉVÉLATION claire, sans imposer
les rôles INDICE 1, INDICE 2, INDICE 3 ou LA CHUTE ni un nombre fixe de scènes.

RÉPONDS UNIQUEMENT AVEC UN JSON VALIDE.
Aucun markdown.
Aucun commentaire.
"""


NEURO_SOMAA_USER_PROMPT = r"""
Sujet source :
{topic}

Crée un YouTube Short original en français pour Neuro-Somaa.

Durée cible :
{min_seconds}-{max_seconds} secondes.

MISSION :
Transformer le sujet source en une vidéo qui donne envie de rester regarder,
pas simplement en une traduction ou une explication encyclopédique.

IMPORTANT :
Tu dois adapter l'ANGLE au sujet.

Ne force pas une structure "enquête/mystère" si elle ne correspond pas
naturellement au sujet.

Ne force pas exactement 8 scènes.

Utilise uniquement le nombre de scènes nécessaire pour créer un rythme rapide
et naturel.

Le PREMIER segment doit immédiatement présenter une tension, une surprise,
une question ou une conséquence intéressante.

Ne commence pas par une introduction.

Génère :

1. un titre court et naturel
2. les scènes avec :
   - caption
   - narration
3. une description courte
4. 3-5 hashtags
5. 8-12 tags pertinents

La narration doit être du français naturel destiné à une audience française.

Le contenu doit rester fidèle au sujet et ne pas inventer de faits.

Retourne exactement ce JSON :

{{
  "title": "...",
  "scenes": [
    {{
      "caption": "...",
      "narration": "..."
    }}
  ],
  "description": "...",
  "tags": ["...", "..."]
}}
"""

# Kept as a compatibility export for older tests and integrations. The active
# prompt deliberately does not include this fixed eight-role structure; scene
# count is now selected from the topic and target duration.
MYSTERY_STRUCTURE_GUIDE = """LEGACY STRUCTURE ROLES (not a fixed output requirement):
ACCROCHE, MYSTÈRE, INDICE 1, INDICE 2, REBONDISSEMENT, INDICE 3, RÉVÉLATION, LA CHUTE.
"""

RETRY_PROMPT = """
La réponse précédente n'a pas passé la validation :

{reason}

Corrige uniquement les problèmes nécessaires.

IMPORTANT :
- conserve le sujet
- améliore le hook si nécessaire
- ne rajoute pas de remplissage
- ne force pas 8 scènes
- garde un français naturel
- garde une progression claire
- assure-toi que le payoff répond à la curiosité initiale
- respecte exactement le schéma JSON demandé

Retourne uniquement le JSON complet corrigé.
"""

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
_REVEAL_INTERJECTIONS = ("attends", "stop", "regarde", "voici", "écoute", "alerte", "imagine", "arrête", "regarde-ça", "attention")


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
_WINNING_TOPIC_KEYWORDS = ("cerveau", "sommeil", "stress", "rêve", "reve", "memoire", "mémoire", "téléphone", "dopamine", "fatigue", "muscle", "ventre")
_LOSING_TOPIC_KEYWORDS = ("e. coli", "ecoli", "bactérie", "vatican", "gaza", "patrimoine", "médiéval")
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
                # Queue items (see scripts/fetch_france_trends.py::make_topic) use
                # "angle"/"topic" keys — never "title". Reading "title" here meant
                # this branch NEVER found a candidate, so every run silently fell
                # through to the tiny 5-item FALLBACK_TOPICS list below, and once
                # that list was fully used up (this channel has 69+ videos), the
                # code returned FALLBACK_TOPICS[0] every single time — the same
                # title forever, regardless of the mined queue's real content.
                title = (item.get("angle") or item.get("topic") or item.get("question_phrase") or item.get("title")) if isinstance(item, dict) else str(item)
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


def _format_clean_title(clean: str) -> str:
    """Mobile Shorts Feed Optimized Title:
    Keeps the title concise (under 42 characters), punchy and 100% complete
    so it is fully visible on a smartphone screen without ellipsis (...).
    """
    clean = re.sub(r'^[«"]\s*', '', clean)
    clean = re.sub(r'\s*[»"]\s*$', '', clean)
    clean = re.sub(r'^[Pp]ourquoi\s+[Pp]ourquoi\s+', 'Pourquoi ', clean)
    
    # Common verbosity reduction for punchy mobile display
    clean = re.sub(r"^[Pp]ourquoi as-tu l'impression que\s+", "Pourquoi ", clean)
    clean = re.sub(r"^[Pp]ourquoi le cerveau efface-t-il\s+", "Pourquoi oublier ", clean)
    clean = re.sub(r"^[Pp]ourquoi ton corps sursaute-t-il\s+", "Pourquoi sursauter ", clean)
    clean = re.sub(r"^[Pp]ourquoi le temps semble passer\s+", "Pourquoi le temps passe ", clean)
    clean = re.sub(r"^[Pp]ourquoi a-t-on la chair de poule\s+", "Chair de poule : ", clean)
    clean = re.sub(r"^[Pp]ourquoi une odeur peut faire revivre\s+", "Une odeur réveille ", clean)

    if not clean.lower().startswith(("pourquoi", "comment", "et si", "ton", "ta", "tes", "ce que", "chair", "une")):
        clean = f"Pourquoi {clean[0].lower() + clean[1:] if clean else ''}"
    
    words = clean.split()
    if len(" ".join(words)) <= 42:
        res = " ".join(words)
    else:
        # Fit comfortably within 38-42 characters at word boundary
        cur = []
        cur_len = 0
        for w in words:
            if cur_len + len(w) + 1 > 38 and cur:
                break
            cur.append(w)
            cur_len += len(w) + 1
        res = " ".join(cur)
    
    res = res.rstrip(" ,.;:!-?«»") + " ?"
    return _clean_fr(res)

def _fallback_script(topic: str) -> dict[str, Any]:
    clean = _clean_fr(topic).rstrip("?")
    title = _format_clean_title(clean)
    clean_words = title.rstrip("?").split()
    hook_narration = " ".join(clean_words[:6]).rstrip(" ,.;:!-") + " ?"
    tags = _fallback_tags(clean)
    # Ensure mandatory European/French market tags
    for market_tag in ("france", "shorts français", "science"):
        if market_tag not in tags:
            tags.append(market_tag)
    return {
        "title": title,
        "description": f"Tu vas comprendre pourquoi {clean.lower()[:80]} en 15 secondes. Découvre ce mécanisme fascinant. #shorts #science #france #neurosciences",
        "tags": tags[:12],
        "scenes": [
            {"caption": "ATTENDS—ton corps fait ça.", "narration": hook_narration},
            {"caption": "Tout se passe là-haut.", "narration": "Tout se passe dans ton cerveau."},
            {"caption": "Il repère une fausse alerte.", "narration": "Il déclenche une fausse alerte reflexe."},
            {"caption": "Tes neurones s’activent.", "narration": "Tes neurones s'activent par automatisme."},
            {"caption": "Une onde traverse tes nerfs.", "narration": "Une onde électrique traverse tes nerfs."},
            {"caption": "Ton corps réagit direct.", "narration": "Ton corps réagit sans réfléchir."},
            {"caption": "C’est un pur réflexe biologique.", "narration": "C'est un pur réflexe biologique."},
            {"caption": "T’as déjà ressenti ça en vrai ?", "narration": "T'as déjà ressenti ça en vrai ?"},
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
    title = _clean_fr(str(payload.get("title", "")))
    # Hard title-integrity checks — this is what catches a broken/cut-off
    # title (e.g. a real historical case ended mid-word with no final word
    # or punctuation: "...son cœur battre la"). Rather than silently
    # truncating or shipping it, reject here so the LLM retries with the
    # existing feedback loop, the same way hook_score already does.
    if not title:
        raise ValueError("le titre est vide")
    if not title.rstrip().endswith(("?", "!", ".", "…")):
        raise ValueError("le titre semble coupé — il doit se terminer par une ponctuation (?, !, .)")
    if len(title) > 90:
        raise ValueError(f"le titre fait {len(title)} caractères, jamais plus de 70-90 (voir consignes de titre)")
    if len(_title_words(title)) < 2:
        raise ValueError("le titre est trop court ou vide de sens, il doit contenir au moins 2 mots significatifs")
    # Keyword alignment: the title, tags, and description are only useful for
    # SEO together if they actually share real keywords — a generic-but-valid
    # title with unrelated tags defeats the point of METADATA_RULES. Require
    # at least 2 significant title words to reappear somewhere in the tags.
    title_words = _title_words(title)
    tag_blob = " ".join(str(t).lower() for t in tags)
    overlap = {w for w in title_words if w in tag_blob}
    if len(overlap) < 2:
        raise ValueError(
            "les tags doivent partager au moins 2 mots-clés du titre "
            f"(titre: {sorted(title_words)}, tags actuels ne correspondent pas assez)"
        )
    payload["title"] = title
    payload["description"] = _clean_fr(description)
    payload["tags"] = [_clean_fr(str(tag)) for tag in tags][:12]
    for scene in payload["scenes"]:
        scene["caption"] = _clean_fr(str(scene.get("caption", "")))
        scene["narration"] = _clean_fr(str(scene.get("narration", "")))
    return payload


def generate_script(topic: str, settings: Settings) -> dict[str, Any]:
    if settings.dry_run or not settings.llm_keys:
        return _fallback_script(topic)

    # Multi-provider LLM resolution: Groq primary (with certified model), OpenRouter fallback
    providers: list[tuple[Any, str]] = []
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            from groq import Groq
            groq_client = Groq(api_key=groq_key)
            # Try multiple known high-availability models on Groq
            for g_model in [settings.llm_model, "llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant"]:
                if g_model and (groq_client, g_model) not in providers:
                    providers.append((groq_client, g_model))
        except Exception:
            pass

    for alt_key in ("OPENROUTER_API_KEY", "ALT_LLM_API_KEY"):
        k = os.getenv(alt_key, "").strip()
        if k:
            try:
                import openai
                alt_model = os.getenv("OPENROUTER_MODEL") or "meta-llama/llama-3.3-70b-instruct"
                providers.append((openai.OpenAI(api_key=k, base_url="https://openrouter.ai/api/v1"), alt_model))
                break
            except Exception:
                pass

    if not providers:
        return _fallback_script(topic)

    system_prompt = (
        NEURO_SOMAA_SYSTEM_PROMPT
    )
    user_prompt = NEURO_SOMAA_USER_PROMPT.format(
        topic=topic,
        min_seconds=settings.min_seconds,
        max_seconds=settings.max_seconds,
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    max_attempts = 3
    for client, llm_model in providers:
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.chat.completions.create(
                    model=llm_model,
                    temperature=0.6,
                    response_format={"type": "json_object"},
                    messages=messages,
                )
                raw = response.choices[0].message.content or ""
                result = _extract_json(raw)
                scenes = result.get("scenes", [])
                if not 4 <= len(scenes) <= 10:
                    raise ValueError(f"il faut entre 4 et 10 scènes adaptées au rythme (reçu {len(scenes)})")
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
                # If provider threw 404/401/429, break and fallback to next provider
                break

            if attempt == max_attempts:
                break
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": (
                RETRY_PROMPT.format(reason=reason)
            )})

    return _fallback_script(topic)
