from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from config import Settings

FALLBACK_TOPICS = [
    "Pourquoi le bâillement est contagieux ?",
    "Pourquoi as-tu la chair de poule ?",
    "Pourquoi une odeur réveille un souvenir ?",
    "Pourquoi ton cœur accélère avant de choisir ?",
    "Pourquoi tes jambes tremblent sous le stress ?",
]

NEURO_SOMAA_SYSTEM_PROMPT = r"""
Tu es le directeur éditorial senior de Neuro-Somaa.

MISSION
Créer des YouTube Shorts en français destinés principalement à la France,
avec une capacité naturelle à toucher également la Belgique, la Suisse
romande et les autres audiences francophones européennes.

IDENTITÉ DE LA CHAÎNE

Neuro-Somaa explore :

MYSTÈRES DU CERVEAU
+
PSYCHOLOGIE
+
COMPORTEMENTS HUMAINS
+
PERCEPTION ET ILLUSIONS
+
SOMMEIL, RÊVES ET MÉMOIRE
+
IA ET ESPRIT HUMAIN
+
SCIENCE ÉTONNANTE DU QUOTIDIEN

POSITIONNEMENT CENTRAL :

"Les choses étranges que ton cerveau fait sans que tu t'en rendes compte."

L'IA est une extension éditoriale de Neuro-Somaa.
Ne transforme JAMAIS la chaîne en chaîne de news technologiques génériques.

==================================================
PRIORITÉ ABSOLUE
==================================================

Le contenu doit être conçu dans cet ordre :

1. STOP SCROLL
2. CURIOSITÉ
3. COMPRÉHENSION IMMÉDIATE
4. RÉTENTION
5. PAYOFF
6. SATISFACTION
7. REWATCH POTENTIEL
8. SEO

Le SEO ne doit jamais dégrader le contenu.

==================================================
AUDIENCE
==================================================

Audience primaire :
France métropolitaine.

Audience secondaire :
Belgique francophone
Suisse romande
Europe francophone.

LOCALISATION FRANCE :
- français naturel de France métropolitaine
- tutoiement naturel : tu, ton, ta, tes
- vocabulaire oral moderne utilisé en France
- formulations simples et idiomatiques, jamais traduites littéralement de l'anglais
- évite les tournures québécoises, trop scolaires ou artificielles
- références quotidiennes compréhensibles par un public français
- n'ajoute jamais « en France » artificiellement
- pour l'IA et la technologie, utilise les termes réellement employés par le public français

Le français doit sembler écrit par un créateur français natif.

NE PAS traduire mentalement depuis l'anglais.

Utilise :
- français moderne
- naturel
- oral
- direct
- intelligent
- légèrement mystérieux
- facile à comprendre
- phrases courtes

Évite :
- français scolaire
- vocabulaire inutilement compliqué
- traductions littérales
- formulations américaines traduites
- répétitions
- introductions longues
- ton de manuel scolaire

==================================================
CONTENT PILLARS
==================================================

Répartition éditoriale cible :

30% — mystères du cerveau
25% — psychologie / comportements humains
15% — perception / illusions / sens
15% — sommeil / rêves / mémoire
10% — IA × esprit humain / attention / habitudes numériques
5% — science étonnante liée à la vie quotidienne

Les proportions sont indicatives et peuvent être adaptées selon les
performances observées.

==================================================
AI BRIDGE ENGINE
==================================================

Lorsqu'un sujet concerne l'IA, cherche d'abord son lien avec l'humain.

PRIORITÉ :

AI + CERVEAU
AI + PSYCHOLOGIE
AI + COMPORTEMENT
AI + ÉMOTIONS
AI + MÉMOIRE
AI + ATTENTION
AI + DÉCISION
AI + APPRENTISSAGE
AI + CRÉATIVITÉ
AI + PERCEPTION
AI + RELATION HUMAIN-MACHINE
AI + FUTUR DU TRAVAIL
AI + HABITUDES NUMÉRIQUES

Un sujet purement technique doit être transformé en question humaine
lorsque cela est pertinent.

EXEMPLE :

Sujet :
"Une IA devient meilleure pour reconnaître les visages."

Angle faible :
"Une nouvelle IA reconnaît mieux les visages."

Angle Neuro-Somaa :
"Ton cerveau reconnaît-il vraiment un visage comme une IA ?"

EXEMPLE :

Sujet :
"Les agents IA peuvent accomplir plusieurs tâches."

Angle faible :
"Les agents IA arrivent."

Angle Neuro-Somaa :
"Et si ton cerveau commençait à déléguer ses décisions à une IA ?"

==================================================
TREND BRIDGE
==================================================

Lorsqu'un sujet IA est tendance, ne copie pas le sujet sous forme de news.

Cherche :

TREND
→ CURIOSITÉ HUMAINE
→ QUESTION PSYCHOLOGIQUE
→ EXPLICATION SCIENTIFIQUE

Le sujet doit rester compréhensible même pour quelqu'un qui ne suit
pas quotidiennement l'actualité technologique.

Ne prétends jamais qu'une information est récente ou nouvelle si elle
n'est pas vérifiée.

==================================================
TOPIC SELECTION
==================================================

Avant d'écrire, analyse le sujet.

Cherche au moins une propriété :

- surprise
- contradiction
- mystère
- conséquence personnelle
- comportement étrange
- phénomène quotidien
- peur légère / inquiétude sans sensationnalisme
- découverte
- paradoxe
- expérience mentale
- futur proche
- question que beaucoup de personnes peuvent se poser

Évite les sujets qui demandent trop de contexte avant de devenir intéressants.

==================================================
HOOK ENGINE
==================================================

Le hook est la priorité numéro 1.

Génère mentalement plusieurs hooks avant de choisir le meilleur.

Le hook doit fonctionner immédiatement.

Il peut utiliser :

- une contradiction
- une question personnelle
- une révélation
- une situation familière
- une conséquence inattendue
- une phrase qui force mentalement une question

INTERDIT :

"Dans cette vidéo..."
"Aujourd'hui..."
"Bonjour..."
"Voici 5 choses..."
"Tu savais que..."
"Dans cet épisode..."

Ne commence pas par une introduction.

Ne commence pas systématiquement par :

"Pourquoi..."
"Ton cerveau..."
"Ce qui arrive si..."

La structure du hook doit varier.

==================================================
VOICE-OVER STYLE — PRIORITY
==================================================

La narration doit sonner comme une vraie voix humaine qui explique un phénomène
intéressant à quelqu'un, pas comme une histoire racontée ou un trailer de film.

STYLE OBLIGATOIRE :
- voix naturelle, calme, directe et crédible
- ton de commentaire documentaire moderne
- curiosité légère, sans jouer la peur
- phrases courtes et faciles à dire à voix haute
- rythme conversationnel
- petites variations naturelles de longueur et de rythme
- chaque phrase doit apporter une information
- parle au spectateur comme à une personne, avec "tu" quand c'est naturel

INTERDIT :
- ton de conteur
- narration théâtrale ou dramatique
- voix de bande-annonce
- phrases artificiellement mystérieuses
- "imagine que...", "et puis...", "soudain..." utilisés comme effets de storytelling
- suspense fabriqué qui retarde l'explication
- exagération ou sensationnalisme

RÈGLE SIMPLE :
Si le texte ressemble à une histoire racontée autour d'un feu, réécris-le comme
un créateur scientifique français qui explique simplement quelque chose d'étonnant.

La narration doit être agréable avec une voix TTS naturelle et ne doit jamais
dépendre d'une interprétation théâtrale pour fonctionner.

==================================================
RETENTION ENGINE
==================================================

Ne force PAS un nombre fixe de scènes.

Le nombre de scènes dépend du contenu.

Chaque scène doit avoir une fonction.

Possible progression :

HOOK
→ QUESTION
→ PREMIER INDICE
→ NOUVELLE INFORMATION
→ CONTRADICTION
→ EXPLICATION
→ REVELATION
→ PAYOFF

Mais cette structure n'est PAS obligatoire.

Ne remplis jamais une scène uniquement pour atteindre un nombre.

Chaque nouvelle scène doit apporter une information nouvelle.

==================================================
OPEN LOOP
==================================================

Maintiens une question implicite dans l'esprit du spectateur.

Le spectateur doit naturellement vouloir savoir :

"Mais pourquoi ?"
"Comment ?"
"Qu'est-ce qui se passe ensuite ?"
"Alors, qu'est-ce que ça signifie pour moi ?"

Ne répète pas artificiellement ces formulations.

L'open loop doit venir de l'histoire.

==================================================
PAYOFF
==================================================

La fin doit résoudre ou transformer la question du début.

Le spectateur doit obtenir une vraie réponse.

La fin peut contenir :

- une révélation
- une conséquence
- un paradoxe
- une nouvelle question intelligente
- un détail qui change le sens du début

Évite les CTA génériques.

Ne termine pas automatiquement par :

"Abonne-toi."
"Like et partage."
"Qu'en penses-tu ?"

==================================================
VISUAL ENGINE
==================================================

Chaque scène doit pouvoir devenir une image ou un plan vertical.

Favorise :

- visage
- yeux
- cerveau
- smartphone
- ordinateur
- IA
- robot
- environnement quotidien
- gestes humains
- contraste humain/technologie
- métaphores visuelles
- scènes cinématiques
- objets reconnaissables

Évite les concepts impossibles à visualiser.

==================================================
CAPTIONS
==================================================

Les captions doivent être courtes.

Elles ne doivent pas répéter toute la narration.

Elles doivent renforcer l'idée principale.

Maximum quelques mots par écran lorsque possible.

==================================================
TITLE ENGINE
==================================================

Le titre doit être court, naturel et intrigant.

Ne force pas une question.

Ne force pas "Ton cerveau".

Ne mets pas de hashtags dans le titre.

Évite les titres génériques.

Le titre doit correspondre exactement au contenu.

==================================================
SCIENTIFIC ACCURACY
==================================================

Ne fabrique aucun chiffre.

Ne transforme pas une hypothèse en fait.

Ne prétends pas qu'une étude existe si elle n'est pas connue ou fournie.

Évite les affirmations médicales absolues.

Lorsque la science est complexe, simplifie sans falsifier.

==================================================
ORIGINALITY
==================================================

Ne copie pas la formulation d'un créateur existant.

Ne reproduis pas des hooks identiques.

Ne réutilise pas systématiquement les mêmes structures.

Deux vidéos successives ne doivent pas avoir le même style de hook.

==================================================
FINAL QUALITY CHECK
==================================================

Avant de répondre, vérifie :

[ ] Le sujet est pertinent pour Neuro-Somaa ?
[ ] Si c'est de l'IA, existe-t-il un angle humain ?
[ ] Le hook fonctionne sans contexte ?
[ ] Le premier moment est immédiatement intéressant ?
[ ] Le français est naturel ?
[ ] Aucun remplissage ?
[ ] Chaque scène apporte quelque chose de nouveau ?
[ ] La curiosité reste active ?
[ ] Le payoff répond au hook ?
[ ] Le contenu est scientifiquement prudent ?
[ ] Le titre est naturel ?
[ ] Les captions sont lisibles rapidement ?
[ ] Le contenu ne ressemble pas à une news générique ?
[ ] La structure n'est pas identique aux vidéos précédentes ?
[ ] La durée demandée est respectée ?

Si une réponse est NON, améliore le contenu avant de générer le JSON.

STRUCTURE NARRATIVE ADAPTABLE : selon le sujet, tu peux utiliser une ACCROCHE,
un MYSTÈRE, des INDICES, un REBONDISSEMENT et une RÉVÉLATION claire. Ces repères
sont adaptables et ne représentent jamais une obligation de produire huit scènes.

RÉPONDS UNIQUEMENT AVEC UN JSON VALIDE.
Aucun markdown.
Aucune explication.
"""


NEURO_SOMAA_USER_PROMPT = '\nSUJET :\n{topic}\n\nTYPE DE SUJET :\n{topic_category}\n\nANGLE SUGGÉRÉ :\n{suggested_angle}\n\nDURÉE CIBLE :\n{min_seconds}-{max_seconds} secondes\n\nCrée un YouTube Short original pour Neuro-Somaa.\n\nPUBLIC :\nFrance en priorité.\nBelgique francophone et Suisse romande en audience secondaire.\n\nOBJECTIF :\nCréer une vidéo qui donne immédiatement une raison de rester,\npuis maintenir une curiosité jusqu\'au payoff.\n\nIMPORTANT :\n\nLe sujet peut concerner :\n- cerveau\n- psychologie\n- comportement humain\n- science\n- IA\n- IA × humain\n- technologie × comportement\n- futur\n\nSi le sujet concerne l\'IA, privilégie un angle qui montre ce que cela\nchange pour l\'humain, son cerveau, ses émotions, ses décisions ou son\ncomportement lorsque cela est naturel.\n\nNE TRANSFORME PAS LE CONTENU EN NEWS TECHNIQUE GÉNÉRIQUE.\n\nSTRUCTURE :\n\nNe force pas 8 scènes.\n\nUtilise uniquement le nombre de scènes nécessaire.\n\nChaque scène doit contenir :\n\n{{\n  "caption": "...",\n  "narration": "..."\n}}\n\nLe premier segment doit commencer directement par le hook.\n\nAucune introduction.\n\nLa dernière partie doit produire un payoff clair.\n\nGÉNÈRE :\n\n- title\n- scenes\n- description\n- tags\n\nDESCRIPTION :\ncourte, naturelle, pertinente.\n\nHASHTAGS :\n3 à 5 maximum.\n\nTAGS :\n8 à 12 mots-clés réellement pertinents.\n\nRetourne exactement :\n\n{{\n  "title": "...",\n  "scenes": [\n    {{\n      "caption": "...",\n      "narration": "..."\n    }}\n  ],\n  "description": "...",\n  "tags": ["...", "..."]\n}}\n\nUNIQUEMENT DU JSON VALIDE.\n'

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
_WINNING_TOPIC_KEYWORDS = ("cerveau", "psychologie", "comportement", "sommeil", "stress", "rêve", "reve", "memoire", "mémoire", "attention", "perception", "illusion", "dopamine", "habitude", "téléphone", "notification", "concentration", "peur", "odeur", "vision", "muscle", "ventre")
_LOSING_TOPIC_KEYWORDS = ("e. coli", "ecoli", "bactérie", "vatican", "gaza", "patrimoine", "médiéval")
_TOPIC_LOOKAHEAD = 12
_RUNTIME_TOPIC_BANS = (
    "on lui ", "on leur ", "une personne", "un homme", "une femme",
    "après une ", "après un ", "témoigne", "témoignage", "festival",
    "exposition", "municipalité", "village", "ville", "tumeur", "cancer",
    "maladie", "hôpital", "patient", "patients", "procès", "police",
    "élection", "politique", "guerre", "ukraine", "gaza", "concarneau",
    "bannalec", "quimper", "paris", "lyon", "marseille", "bordeaux",
    "quatre artistes", "jour de mémoire", "leçons politiques",
    "stress, surcharge", "surcharge mentale, perte de sens",
)

def _runtime_topic_fit(title: str) -> bool:
    normalized = " ".join(title.lower().split())
    if any(token in normalized for token in _RUNTIME_TOPIC_BANS):
        return False
    return not (len(normalized) > 110 or normalized.count(",") >= 2)


_TOPIC_PERFORMANCE_KEYWORDS = (
    "cerveau", "psychologie", "comportement", "sommeil", "rêve", "rêves",
    "mémoire", "attention", "perception", "illusion", "dopamine",
    "concentration", "peur", "odeur", "vision", "habitude",
    "notification", "téléphone", "muscle", "cœur", "corps",
    "respiration", "fatigue", "émotion", "stress",
)


def _topic_retention_bonus(title: str, rows: list[dict[str, Any]]) -> float:
    """Use actual watch analytics as a modest tie-breaker for topic choice.

    Only fetched analytics with at least 30 views count. Predicted retention
    and low-sample videos are excluded to avoid reinforcing invented signals.
    """
    keyword_rates: dict[str, list[float]] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("analytics_fetched_at"):
            continue
        historical_topic = _clean_fr(str(row.get("topic") or row.get("title") or ""))
        if not historical_topic or not _runtime_topic_fit(historical_topic):
            continue
        try:
            views = int(row.get("views") or 0)
            average_pct = float(row.get("average_view_percentage") or 0)
        except (TypeError, ValueError):
            continue
        if views < 30 or average_pct <= 0:
            continue
        historical_text = historical_topic.lower()
        for keyword in _TOPIC_PERFORMANCE_KEYWORDS:
            if keyword in historical_text:
                keyword_rates.setdefault(keyword, []).append(min(average_pct, 100.0))

    current = title.lower()
    supported_rates = [
        sum(rates) / len(rates)
        for keyword, rates in keyword_rates.items()
        if len(rates) >= 2 and keyword in current
    ]
    if not supported_rates:
        return 0.0
    # Keep the metric as a small adjustment; content relevance still matters more.
    return max(-4.0, min(4.0, (sum(supported_rates) / len(supported_rates) - 45.0) / 10.0))

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
            rows: list[dict[str, Any]] = []
            if history.exists():
                loaded_rows = json.loads(history.read_text(encoding="utf-8"))
                rows = loaded_rows if isinstance(loaded_rows, list) else []
                used = {_clean_fr(str(row.get("topic", ""))).lower() for row in rows if isinstance(row, dict)}
            pointer_path = settings.data_dir / "queue_index_fr.json"
            try:
                pointer = int(json.loads(pointer_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pointer = 0
            ordered = items[pointer % len(items):] + items[:pointer % len(items)] if items else []
            candidates: list[tuple[float, int, str]] = []
            for offset, item in enumerate(ordered):
                # Queue items (see scripts/fetch_france_trends.py::make_topic) use
                # "angle"/"topic" keys — never "title". Reading "title" here meant
                # this branch NEVER found a candidate, so every run silently fell
                # through to the tiny 5-item FALLBACK_TOPICS list below, and once
                # that list was fully used up (this channel has 69+ videos), the
                # code returned FALLBACK_TOPICS[0] every single time — the same
                # title forever, regardless of the mined queue's real content.
                title = (item.get("angle") or item.get("topic") or item.get("question_phrase") or item.get("title")) if isinstance(item, dict) else str(item)
                clean_title = _clean_fr(str(title))
                if clean_title and clean_title.lower() not in used and _runtime_topic_fit(clean_title):
                    retention_bonus = _topic_retention_bonus(clean_title, rows)
                    combined_score = _topic_cluster_score(clean_title) + retention_bonus
                    candidates.append((combined_score, offset, clean_title))
                if len(candidates) >= _TOPIC_LOOKAHEAD:
                    break
            if candidates:
                # Topic relevance is the primary signal; observed watch retention
                # gives a modest, evidence-based adjustment, then queue order wins.
                _, offset, title = max(candidates, key=lambda candidate: (candidate[0], -candidate[1]))
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
    """Always return 8-12 French SEO tags."""
    words = [
        w for w in re.sub(r"[^\wà-ÿ' ]", " ", topic.lower()).split()
        if len(w) > 2 and w not in _STOPWORDS_FR
    ]
    specific = words[:5] or ["quotidien"]
    base = [
        "science", "corps humain", "cerveau", "psychologie", "neurosciences",
        "curiosité", "france", "shorts français", "comportement", "mémoire",
    ]
    tags = [*specific, *base]
    seen: list[str] = []
    for tag in tags:
        if tag.lower() not in {s.lower() for s in seen}:
            seen.append(tag)
        if len(seen) >= 12:
            break
    for pad in ("attention", "stress", "sommeil", "émotion", "réflexe"):
        if len(seen) >= 8:
            break
        if pad not in {s.lower() for s in seen}:
            seen.append(pad)
    return seen[:12]


def _format_clean_title(clean: str) -> str:
    """Normalize a title without ever cutting it mid-thought."""
    clean = re.sub(r'^[«"]\s*', '', clean)
    clean = re.sub(r'\s*[»"]\s*$', '', clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) > 58:
        clean = clean[:58].rsplit(" ", 1)[0].rstrip(" ,.;:")
    if clean and clean[-1] not in "?!.":
        clean = clean + " ?"
    return clean


def _fallback_script(topic: str) -> dict[str, Any]:
    clean = _clean_fr(topic).rstrip("?")
    title = _format_clean_title(clean)
    tags = _fallback_tags(clean)
    for market_tag in ("france", "shorts français", "science", "cerveau", "psychologie"):
        if market_tag not in tags and len(tags) < 12:
            tags.append(market_tag)
    tags = tags[:12]
    while len(tags) < 8:
        tags.append("neurosciences")
    hook = title.rstrip(" ?") + " ?"
    return {
        "title": title,
        "description": "Un phénomène étonnant expliqué simplement. #shorts #science #france #neurosciences #cerveau",
        "tags": tags,
        "scenes": [
            {"caption": "Regarde ce phénomène.", "narration": hook},
            {"caption": "Ton cerveau intervient.", "narration": "Ton cerveau traite ce phénomène automatiquement sans que tu le remarques."},
            {"caption": "Ce n'est pas un hasard.", "narration": "Ce mécanisme a une fonction précise dans ton comportement quotidien."},
            {"caption": "Les signaux circulent.", "narration": "Des signaux nerveux coordonnent ensuite la réponse du corps très rapidement."},
            {"caption": "La réaction est rapide.", "narration": "La réaction peut arriver avant même que tu y penses consciemment."},
            {"caption": "Voilà le mécanisme.", "narration": "C'est donc surtout une réponse automatique du système nerveux central."},
            {"caption": "Tu le vis chaque jour.", "narration": "Ce réflexe influence tes décisions et tes émotions sans effort."},
            {"caption": "Maintenant tu le sais.", "narration": "Comprendre ce mécanisme change la façon dont tu observes ton corps."},
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
    if len(title) > 60:
        raise ValueError(f"le titre fait {len(title)} caractères; vise 60 maximum")
    title_lower = title.lower()
    banned_title_patterns = (
        "on lui ", "une personne", "un homme", "une femme", "quatre artistes",
        "jour de mémoire", "surcharge mentale", "pourquoi quatre",
        "pourquoi on lui", "pourquoi jour de", "tumeur", "cancer",
        "leçons politiques", "concarneau", "bannalec", "prix nobel",
        "festival", "exposition", "témoignage", "témoigne", "ukraine", "gaza",
        "guerre", "élection",
    )
    if any(pattern in title_lower for pattern in banned_title_patterns):
        raise ValueError("titre article-shaped ou hors ligne éditoriale")
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


_TOPIC_CATEGORY_KEYWORDS = {
    "brain / psychology / behaviour": ("cerveau", "mémoire", "rêve", "stress", "émotion", "attention", "décision", "comportement"),
    "AI × human": ("ia", "intelligence artificielle", "chatgpt", "algorithme", "robot", "agent"),
    "AI / future science": ("technologie", "futur", "machine", "automatisation", "science"),
    "digital life / behaviour": ("téléphone", "écran", "réseau", "internet", "notification", "numérique"),
}


def _topic_category_and_angle(topic: str) -> tuple[str, str]:
    """Map raw queue topics to the prompt's human-first category and angle."""
    normalized = str(topic or "").lower()
    scores = {
        category: sum(1 for keyword in keywords if keyword in normalized)
        for category, keywords in _TOPIC_CATEGORY_KEYWORDS.items()
    }
    category = max(scores, key=scores.get) if max(scores.values(), default=0) else "brain / psychology / behaviour"
    if category == "AI × human":
        angle = "le lien entre cette technologie et le cerveau, les émotions ou les décisions humaines"
    elif category == "digital life / behaviour":
        angle = "la conséquence personnelle et surprenante de ce comportement quotidien"
    elif category == "AI / future science":
        angle = "ce que cette évolution change concrètement pour les humains"
    else:
        angle = "le phénomène personnel et contre-intuitif que le spectateur peut reconnaître"
    return category, angle



class _GeminiAdapter:
    """Lightweight adapter allowing Gemini to be called with OpenAI-compatible chat interface."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, model: str, messages: list[dict[str, str]], **kwargs):
        system_text = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        user_parts = [f"{m['role'].upper()}: {m['content']}" for m in messages if m["role"] != "system"]
        prompt_text = "\n\n".join(user_parts)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.6},
        }
        if system_text:
            body["system_instruction"] = {"parts": [{"text": system_text}]}
        resp = requests.post(url, json=body, timeout=30)
        resp.raise_for_status()
        res_json = resp.json()
        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]

        class _Choice:
            def __init__(self, text):
                self.message = type("Msg", (), {"content": text})()

        return type("Resp", (), {"choices": [_Choice(raw_text)]})()


class _OpenRouterAdapter:
    """Fallback adapter for OpenRouter if openai package is absent."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, model: str, messages: list[dict[str, str]], **kwargs):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jashaidaslamhfd/Neuro-Somaa",
            "X-Title": "Neuro-Somaa French Shorts",
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": 0.6,
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        raw_text = resp.json()["choices"][0]["message"]["content"]

        class _Choice:
            def __init__(self, text):
                self.message = type("Msg", (), {"content": text})()

        return type("Resp", (), {"choices": [_Choice(raw_text)]})()

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

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        gemini_client = _GeminiAdapter(gemini_key)
        providers.append((gemini_client, "gemini-2.0-flash"))
        providers.append((gemini_client, "gemini-1.5-flash"))

    for alt_key in ("OPENROUTER_API_KEY", "ALT_LLM_API_KEY"):
        k = os.getenv(alt_key, "").strip()
        if k:
            alt_model = os.getenv("OPENROUTER_MODEL") or "meta-llama/llama-3.3-70b-instruct"
            try:
                import openai
                providers.append((openai.OpenAI(api_key=k, base_url="https://openrouter.ai/api/v1"), alt_model))
            except Exception:
                providers.append((_OpenRouterAdapter(k), alt_model))
            break

    if not providers:
        return _fallback_script(topic)

    system_prompt = (
        NEURO_SOMAA_SYSTEM_PROMPT
    )
    topic_category, suggested_angle = _topic_category_and_angle(topic)
    user_prompt = NEURO_SOMAA_USER_PROMPT.format(
        topic=topic,
        topic_category=topic_category,
        suggested_angle=suggested_angle,
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
