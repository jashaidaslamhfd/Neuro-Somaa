"""CTR 60%+ Optimized Topic + Title System for Dark Psychology France.

This module provides:
1. PREMIUM_CTR_TOPICS - Topics ranked by curiosity-gap potential (CTR 60%+)
2. CTR_TITLE_TEMPLATES - Title formulas that maximize click-through
3. THUMBNAIL_TEXT_PAIRS - Bold overlay text for thumbnails
4. COLD_OPEN_HOOKS - First 2-second hooks that lock attention

Each topic has:
- CTR score (0-100, 60+ = guaranteed click magnet)
- Title (optimized for French Shorts feed)
- Thumbnail text (max 4 words, bold, dark psych aesthetic)
- Cold open (first 2 seconds spoken hook)

HOW IT WORKS:
- Topics with CTR 70+ get picked FIRST by the pipeline
- Each topic comes with a pre-optimized title + thumbnail combo
- The LLM prompt is injected with these patterns for consistent high-CTR output
"""

from __future__ import annotations

import re

# ═══════════════════════════════════════════════════════════════
# 1. PREMIUM CTR TOPICS — Dark Psychology France (CTR 60%+)
# ═══════════════════════════════════════════════════════════════

PREMIUM_CTR_TOPICS = [
    # ─── TIER S: CTR 80%+ (Curiosity gap that CANNOT be ignored) ───
    {
        "topic": "Tu mens 200 fois par jour sans le compter",
        "ctr_score": 95,
        "title": "Tu mens 200 fois par jour — voici la preuve",
        "thumbnail": "200 MENSONGES / JOUR",
        "cold_open": "Tu viens de mentir il y a 3 minutes. Et tu ne t'en es même pas rendu compte.",
        "category": "Secrets du Comportement",
        "why_works": "Number shock + personal accusation = impossible to scroll past",
    },
    {
        "topic": "Les gens te manipulent sans que tu le voies",
        "ctr_score": 93,
        "title": "3 personnes te manipulent en ce moment — tu ne le vois pas",
        "thumbnail": "ON TE MANIPULE ?",
        "cold_open": "En ce moment même, quelqu'un utilise cette technique sur toi.",
        "category": "Manipulation",
        "why_works": "Personal threat + right now urgency = instant click",
    },
    {
        "topic": "Ton cerveau invente des souvenirs faux",
        "ctr_score": 92,
        "title": "90% de tes souvenirs sont des mensonges de ton cerveau",
        "thumbnail": "FAUX SOUVENIRS ?",
        "cold_open": "Ce souvenir que tu chéris le plus... ton cerveau l'a inventé.",
        "category": "Biais Cognitifs",
        "why_works": "Attacks personal identity = viewer MUST know more",
    },
    {
        "topic": "Tu dis oui alors que tu veux dire non",
        "ctr_score": 91,
        "title": "Pourquoi tu dis oui alors que tu veux dire non",
        "thumbnail": "OUI = NON ?",
        "cold_open": "La dernière fois qu'on t'a demandé un service, tu as dit oui. Mais tu voulais dire non.",
        "category": "Manipulation",
        "why_works": "Universal pain point = every viewer relates instantly",
    },
    {
        "topic": "Tu tombes toujours amoureux du mauvais type",
        "ctr_score": 90,
        "title": "Tu tombes toujours amoureux du mauvais type — voici pourquoi",
        "thumbnail": "MAUVAIS TYPE ?",
        "cold_open": "Si tu as déjà pleuré pour quelqu'un qui ne le méritait pas, cette vidéo est pour toi.",
        "category": "Relations",
        "why_works": "Emotional trigger + personal identification = immediate hook",
    },
    {
        "topic": "Le silence fait plus de dégâts que les mots",
        "ctr_score": 89,
        "title": "Le silence fait plus de dégâts que n'importe quel mot",
        "thumbnail": "SILENCE = DÉGÂTS",
        "cold_open": "Le dernier silence que tu as subi t'a blessé plus que n'importe quelle insulte.",
        "category": "Relations",
        "why_works": "Counter-intuitive truth = challenges what everyone believes",
    },
    {
        "topic": "Tu obéis à l'autorité sans réfléchir",
        "ctr_score": 88,
        "title": "Tu obéis à l'autorité sans même le savoir — la preuve",
        "thumbnail": "OBEISSANCE ?",
        "cold_open": "Si un homme en blouse blanche te dit de faire quelque chose de dangereux... tu le ferais.",
        "category": "Pouvoir & Société",
        "why_works": "Disrupts self-image = 'I would never!' = must watch",
    },
    {
        "topic": "La jalousie révèle ta peur pas ton amour",
        "ctr_score": 87,
        "title": "La jalousie n'est PAS de l'amour — c'est ta peur qui parle",
        "thumbnail": "JALOUSIE ≠ AMOUR",
        "cold_open": "Si tu es jaloux, ce n'est pas parce que tu aimes. C'est parce que tu as peur.",
        "category": "Relations",
        "why_works": "Challenges universal emotion = viewers defensive = must watch",
    },
    {
        "topic": "Les algorithmes contrôlent ce que tu penses",
        "ctr_score": 86,
        "title": "Les algorithmes contrôlent tes pensées — et tu ne le vois pas",
        "thumbnail": "ALGORITHME = CONTRÔLE",
        "cold_open": "Cette vidéo que tu regardes en ce moment... un algorithme a décidé que tu la verrais.",
        "category": "Société & Contrôle",
        "why_works": "Meta-reality = video about algorithms ON an algorithm platform",
    },
    {
        "topic": "Tu vérifies ton téléphone 100 fois par jour",
        "ctr_score": 85,
        "title": "Tu vérifies ton téléphone 100 fois par jour — c'est une addiction",
        "thumbnail": "100 FOIS / JOUR",
        "cold_open": "Combien de fois as-tu regardé ton téléphone aujourd'hui ? Plus de 50. Et c'est grave.",
        "category": "Addictions Modernes",
        "why_works": "Number shock + viewer does it RIGHT NOW = instant recognition",
    },

    # ─── TIER A: CTR 70-80% ───
    {
        "topic": "Ton cerveau te ment chaque jour",
        "ctr_score": 84,
        "title": "Ton cerveau te ment tous les jours — voici comment",
        "thumbnail": "CERVEAU QUI MENT ?",
        "cold_open": "Ton cerveau vient de te mentir il y a 2 secondes. Et tu l'as cru.",
        "category": "Biais Cognitifs",
    },
    {
        "topic": "Tu fais confiance aux gens qui te mentent",
        "ctr_score": 83,
        "title": "Tu fais le plus confiance aux gens qui te mentent le plus",
        "thumbnail": "CONFIANCE AUX MENTEURS",
        "cold_open": "La personne à qui tu fais le plus confiance... ment probablement en ce moment.",
        "category": "Manipulation",
    },
    {
        "topic": "Le pouvoir change ta personnalité en 7 jours",
        "ctr_score": 82,
        "title": "Le pouvoir te transforme en 7 jours — et pas en bien",
        "thumbnail": "POUVOIR = MONSTRE ?",
        "cold_open": "Donne du pouvoir à n'importe qui. Dans 7 jours, tu ne le reconnaîtras plus.",
        "category": "Pouvoir & Société",
    },
    {
        "topic": "Tu attires dans ta vie ce que tu fuis le plus",
        "ctr_score": 81,
        "title": "Tu attires dans ta vie exactement ce que tu fuis",
        "thumbnail": "TU ATTIRE CE QUE TU FUIS",
        "cold_open": "Cette situation que tu détestes... c'est toi qui l'as attirée.",
        "category": "Relations",
    },
    {
        "topic": "Tu crois être meilleur que la moyenne",
        "ctr_score": 80,
        "title": "Tu crois être meilleur que la moyenne — 99% des gens le croient",
        "thumbnail": "MIEUX QUE TOUS ?",
        "cold_open": "Tu penses être plus intelligent que la plupart des gens. Tu te trompes.",
        "category": "Biais Cognitifs",
    },
    {
        "topic": "Les manipulateurs utilisent ton prénom pour te contrôler",
        "ctr_score": 79,
        "title": "Quand quelqu'un dit ton prénom — c'est une technique de contrôle",
        "thumbnail": "TON PRÉNOM = ARME",
        "cold_open": "Si quelqu'un utilise ton prénom en plein milieu d'une conversation... fais attention.",
        "category": "Manipulation",
    },
    {
        "topic": "Le regard des autres influence tes décisions",
        "ctr_score": 78,
        "title": "Le regard des autres contrôle tes décisions — tu ne le vois pas",
        "thumbnail": "REGARD = CONTRÔLE",
        "cold_open": "Tu crois décider librement. Mais le regard de quelqu'un vient de tout changer.",
        "category": "Influence",
    },
    {
        "topic": "Tu ne vois pas quand quelqu'un t'aime vraiment",
        "ctr_score": 77,
        "title": "Les signes d'amour que tu ne vois jamais — même quand ils sont là",
        "thumbnail": "AMOUR INVISIBLE",
        "cold_open": "Quelqu'un t'aime profondément. Et tu n'as jamais remarqué.",
        "category": "Relations",
    },
    {
        "topic": "Tu repenses toujours à cette humiliation",
        "ctr_score": 76,
        "title": "Ce souvenir gênant qui ne t'quitte jamais — ton cerveau le fait exprès",
        "thumbnail": "SOUVENIR GÊNANT ?",
        "cold_open": "Ce moment gênant que tu repenses en boucle... ton cerveau le fait exprès.",
        "category": "Biais Cognitifs",
    },
    {
        "topic": "Tu fais semblant d'aller bien alors que tu souffres",
        "ctr_score": 75,
        "title": "Tu fais semblant d'aller bien — et ça te détruit de l'intérieur",
        "thumbnail": "MASQUE = SURVIE",
        "cold_open": "Ce sourire que tu portes en ce moment... il cache quoi exactement ?",
        "category": "Émotions Cachées",
    },
    {
        "topic": "Le mensonge le plus courant au monde",
        "ctr_score": 74,
        "title": "Le mensonge le plus courant au monde — tu le dis chaque jour",
        "thumbnail": "MENSONGE QUOTIDIEN",
        "cold_open": "Tu as dit ce mensonge 3 fois aujourd'hui. Et tu ne le comptes même plus.",
        "category": "Manipulation",
    },
    {
        "topic": "Tu ne connais pas ta vraie personnalité cachée",
        "ctr_score": 73,
        "title": "Ta vraie personnalité est cachée — même de toi",
        "thumbnail": "VRAIE PERSONNALITÉ ?",
        "cold_open": "Tu crois te connaître. Mais ta vraie personnalité est une couche que tu ne vois pas.",
        "category": "Inconscient",
    },
    {
        "topic": "Le prix influence ce que tu aimes vraiment",
        "ctr_score": 72,
        "title": "Ce que tu aimes dépend du prix — pas de ton vrai goût",
        "thumbnail": "PRIX = GOÛT ?",
        "cold_open": "Ce vin que tu as adoré ? Si tu avais su qu'il coûtait 3 euros... tu l'aurais détesté.",
        "category": "Biais Cognitifs",
    },
    {
        "topic": "Tu procrastines par peur de réussir",
        "ctr_score": 71,
        "title": "Tu ne procrastines pas par paresse — c'est la peur de réussir",
        "thumbnail": "PEUR DE RÉUSSIR ?",
        "cold_open": "Tu crois que tu es paresseux. Non. Tu as peur de réussir.",
        "category": "Émotions Cachées",
    },
    {
        "topic": "Tu restes dans des situations toxiques par habitude",
        "ctr_score": 70,
        "title": "Tu restes dans des situations toxiques par habitude — pas par amour",
        "thumbnail": "HABITUDE TOXIQUE",
        "cold_open": "Tu sais que c'est toxique. Mais tu restes. Parce que ton cerveau confond habitude et bonheur.",
        "category": "Relations",
    },
]


# ═══════════════════════════════════════════════════════════════
# 2. CTR TITLE TEMPLATES
# ═══════════════════════════════════════════════════════════════

CTR_TITLE_TEMPLATES = [
    "{number} {action} sans le savoir — la preuve",
    "Tu {action} — et c'est plus grave que tu ne crois",
    "{number}% des gens {action} — et tu en fais partie",
    "Ce que {subject} ne te dit JAMAIS sur {topic}",
    "{topic} — la vérité que personne n'ose dire",
    "Pourquoi {topic} — la réponse est troublante",
    "Ce qui se passe quand {topic} est fascinant",
    "Voici pourquoi {topic} est plus courant que tu ne crois",
    "Les signes que {topic} — et tu ne les vois pas",
    "{topic} te contrôle sans que tu le voies",
    "La psychologie explique pourquoi {topic}",
    "Ce que la science dit sur {topic}",
    "Ce qu'il faut comprendre sur {topic}",
    "Le secret derrière {topic}",
]


# ═══════════════════════════════════════════════════════════════
# 3. THUMBNAIL TEXT — Max 4 words, Bold, Dark Psych
# ═══════════════════════════════════════════════════════════════

THUMBNAIL_TEXT_PAIRS = [
    ("200 MENSONGES / JOUR", "HIGH"),
    ("ON TE MANIPULE ?", "HIGH"),
    ("FAUX SOUVENIRS ?", "HIGH"),
    ("OUI = NON ?", "MEDIUM"),
    ("MAUVAIS TYPE ?", "HIGH"),
    ("SILENCE = DÉGÂTS", "MEDIUM"),
    ("OBEISSANCE ?", "MEDIUM"),
    ("JALOUSIE ≠ AMOUR ?", "HIGH"),
    ("ALGORITHME = CONTRÔLE ?", "HIGH"),
    ("100 FOIS / JOUR ?", "HIGH"),
    ("CERVEAU QUI MENT", "HIGH"),
    ("POUVOIR = MONSTRE ?", "MEDIUM"),
    ("TON PRÉNOM = ARME ?", "HIGH"),
    ("REGARD = CONTRÔLE ?", "HIGH"),
    ("AMOUR INVISIBLE ?", "MEDIUM"),
    ("SOUVENIR GÊNANT ?", "MEDIUM"),
    ("MASQUE = SURVIE ?", "HIGH"),
    ("CONFIANCE AUX MENTEURS ?", "HIGH"),
    ("MIEUX QUE TOUS ?", "MEDIUM"),
    ("PEUR DE RÉUSSIR ?", "MEDIUM"),
    ("HABITUDE TOXIQUE ?", "HIGH"),
    ("VRAIE PERSONNALITÉ ?", "MEDIUM"),
    ("PRIX = GOÛT ?", "MEDIUM"),
    ("TU ATTIRE CE QUE TU FUIS", "HIGH"),
    ("MENSONGE QUOTIDIEN", "HIGH"),
]


# ═══════════════════════════════════════════════════════════════
# 4. COLD OPEN HOOKS — First 2 Seconds
# ═══════════════════════════════════════════════════════════════

COLD_OPEN_HOOKS = [
    "En ce moment même, quelqu'un utilise cette technique sur toi.",
    "Tu viens de faire quelque chose sans t'en rendre compte.",
    "Ton cerveau vient de te mentir il y a 2 secondes.",
    "Tu mens. Tout le monde le fait. Mais toi... tu ne le sais même pas.",
    "Tu crois connaître cette personne. Tu te trompes lourdement.",
    "Tu penses être libre de tes choix. Tu te trompes.",
    "Si tu as déjà souffert en silence... cette vidéo va tout changer.",
    "Ce moment que tu repenses en boucle... ton cerveau le fait exprès.",
    "Ce sourire que tu portes en ce moment... il cache quoi ?",
    "90% de ce que tu crois savoir sur toi est faux.",
    "La prochaine fois qu'on te dira ton prénom... tu penseras à cette vidéo.",
    "Si tu penses être à l'abri de la manipulation... regarde cette vidéo.",
    "Tu crois que ça ne t'arrive pas ? Attends.",
    "Regarde autour de toi. Personne ne le voit. Personne sauf toi maintenant.",
]


# ═══════════════════════════════════════════════════════════════
# 5. CTR SCORING ENGINE
# ═══════════════════════════════════════════════════════════════

def score_title_ctr(title: str, topic: str = "") -> dict:
    """Score a French title for CTR potential (0-100)."""
    score = 0
    breakdown = {}
    t = (title or "").lower()

    # Personal Address (15 pts)
    personal = any(w in t for w in ("tu ", "ton ", "ta ", "tes ", "toi "))
    breakdown["personal_address"] = 15 if personal else 0
    score += 15 if personal else 0

    # Curiosity Gap (20 pts)
    gap_markers = ("?", "voici", "la preuve", "comment", "ce qui se passe", "ce que", "la vérité", "le secret")
    gap = any(m in t for m in gap_markers)
    breakdown["curiosity_gap"] = 20 if gap else 0
    score += 20 if gap else 0

    # Number/Specificity (15 pts)
    has_number = bool(re.search(r"\d+", title))
    breakdown["number_specificity"] = 15 if has_number else 0
    score += 15 if has_number else 0

    # Emotional Trigger Words (15 pts)
    emotion_words = ("peur", "aimer", "souffrir", "mal", "mentir", "mensonge",
                     "manipuler", "contrôler", "détruit", "secret", "jamais",
                     "caché", "toxique", "honte", "coupable", "rejet")
    has_emotion = any(w in t for w in emotion_words)
    breakdown["emotional_trigger"] = 15 if has_emotion else 0
    score += 15 if has_emotion else 0

    # Shock/Contrarian (15 pts)
    shock = any(w in t for w in ("pas", "jamais", "toujours", "dangereux", "contrôle"))
    breakdown["shock_contrarian"] = 15 if shock else 0
    score += 15 if shock else 0

    # Optimal Length (10 pts)
    word_count = len(title.split())
    optimal = 5 <= word_count <= 10
    breakdown["optimal_length"] = 10 if optimal else 5
    score += 10 if optimal else 5

    # French Naturalness (10 pts)
    natural = any(w in t for w in ("pourquoi", "voici", "ce que", "c'est", "il y a", "sauf que"))
    breakdown["french_natural"] = 10 if natural else 5
    score += 10 if natural else 5

    score = min(100, score)
    grade = "S" if score >= 85 else ("A" if score >= 70 else ("B" if score >= 60 else "C"))

    return {
        "score": score,
        "grade": grade,
        "ctr_expected": f"{max(60, score)}%+" if score >= 60 else f"{score}%",
        "breakdown": breakdown,
    }


def get_top_ctr_topics(n: int = 10) -> list:
    """Return top N topics sorted by CTR score."""
    sorted_topics = sorted(PREMIUM_CTR_TOPICS, key=lambda x: x["ctr_score"], reverse=True)
    return sorted_topics[:n]


def pick_thumbnail_text(topic_text: str) -> str:
    """Pick the best thumbnail text for a given topic."""
    topic_lower = topic_text.lower()
    keyword_map = {
        "mensonge": "200 MENSONGES / JOUR",
        "manipul": "ON TE MANIPULE ?",
        "souvenir": "FAUX SOUVENIRS ?",
        "oui": "OUI = NON ?",
        "amoureux": "MAUVAIS TYPE ?",
        "silence": "SILENCE DÉTRUIT ?",
        "obéi": "OBEISSANCE ?",
        "jalousie": "JALOUSIE ≠ AMOUR ?",
        "algorithme": "ALGORITHME = CONTRÔLE ?",
        "téléphone": "100 FOIS / JOUR ?",
        "cerveau": "CERVEAU QUI MENT",
        "pouvoir": "POUVOIR = MONSTRE ?",
        "prénom": "TON PRÉNOM = ARME ?",
        "regard": "REGARD = CONTRÔLE ?",
        "sourire": "MASQUE = SURVIE ?",
        "prix": "PRIX = GOÛT ?",
        "procrastine": "PEUR DE RÉUSSIR ?",
        "toxique": "HABITUDE TOXIQUE ?",
        "amour": "AMOUR INVISIBLE ?",
        "personnalité": "VRAIE PERSONNALITÉ ?",
    }
    for keyword, thumb_text in keyword_map.items():
        if keyword in topic_lower:
            return thumb_text
    return "PSYCHOLOGIE SOMBRE"


if __name__ == "__main__":
    print("=" * 60)
    print("CTR 60%+ TOPIC RANKING - Dark Psychology France")
    print("=" * 60)
    for i, t in enumerate(get_top_ctr_topics(25), 1):
        print(f"\n#{i:02d} [{t['ctr_score']}%] {t['title']}")
        print(f"    Thumbnail: {t['thumbnail']}")
        print(f"    Hook: {t['cold_open'][:80]}...")
        print(f"    Category: {t['category']}")
    print(f"\n{'=' * 60}")
    print(f"Total Premium Topics: {len(PREMIUM_CTR_TOPICS)}")
    print(f"Topics with CTR 80%+: {sum(1 for t in PREMIUM_CTR_TOPICS if t['ctr_score'] >= 80)}")
    print(f"Topics with CTR 70%+: {sum(1 for t in PREMIUM_CTR_TOPICS if t['ctr_score'] >= 70)}")
    print(f"Topics with CTR 60%+: {sum(1 for t in PREMIUM_CTR_TOPICS if t['ctr_score'] >= 60)}")
    print("=" * 60)
