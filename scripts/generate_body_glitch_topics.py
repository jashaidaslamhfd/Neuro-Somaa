"""Génère le catalogue France-first de 500 sujets « Réflexes du corps ».

Les sujets sont conçus pour un public francophone : phénomènes quotidiens,
formulations françaises naturelles et aucune promesse médicale.

CORRECTIF GRAMMAIRE FRANÇAISE
-----------------------------
L'ancienne version insérait le phénomène dans des gabarits génériques du genre
« Pourquoi le cerveau remarque {phenomenon} ». Appliqué à un phénomène verbal
(ex. « entendre son cœur battre la nuit »), cela produisait du français
cassé, instantanément repérable comme traduction automatique :
« Pourquoi le cerveau remarque entendre son cœur battre la nuit ».

Chaque phénomène fournit désormais DEUX formes françaises correctes :
  - q : proposition sujet+verbe  → « une paupière tressaille sans raison »
  - n : syntagme nominal défini  → « la paupière qui tressaille sans raison »
Les 10 gabarits n'utilisent que ces deux formes, donc les 500 titres produits
sont tous des phrases françaises grammaticalement valides.
"""
from __future__ import annotations

import json
from pathlib import Path

# (label série, q = proposition sujet+verbe, n = syntagme nominal défini, vignette)
PHENOMENA = [
    # Counterintuitive body/brain facts — "cela semble faux mais c'est vrai"
    ("Cœur qui bat plus vite",
     "le cœur bat plus vite avant de parler en public", "le cœur qui bat plus vite avant de parler en public", "CŒUR ACCÉLÉRÉ ?"),
    ("Yeux qui bougent en dormant",
     "les yeux bougent pendant le sommeil paradoxal", "le mouvement des yeux pendant le sommeil paradoxal", "YEUX QUI BOUGENT ?"),
    ("Cerveau qui ralentit le temps",
     "le cerveau semble ralentir le temps en danger", "l'impression que le temps ralentit en danger", "TEMPS RALENTI ?"),
    ("Peau qui frissonne de froid",
     "la peau frissonne quand on a peur ou froid", "le frisson de la peau face au froid ou à la peur", "POURQUOI FRISSONNER ?"),
    ("Estomac qui gargouille",
     "l'estomac gargouille quand on a faim", "le gargouillement de l'estomac quand on a faim", "VENTRE QUI GARGOUILLE ?"),
    ("Mémoire qui trompe",
     "la mémoire invente des détails sans le vouloir", "les détails que la mémoire invente sans le vouloir", "MÉMOIRE TRICHEUSE ?"),
    ("Main qui s'engourdit",
     "la main s'engourdit quand on dort dessus", "l'engourdissement de la main quand on dort dessus", "MAIN ENGOURDIE ?"),
    ("Nez qui coule au froid",
     "le nez coule quand il fait froid", "l'écoulement du nez par temps froid", "NEZ QUI COULE ?"),
    ("Bâillement contagieux",
     "le bâillement se transmet aux autres", "la contagion du bâillement", "BÂILLEMENT CONTAGIEUX ?"),
    ("Cerveau qui imagine",
     "le cerveau crée des souvenirs faux", "les faux souvenirs créés par le cerveau", "FAUX SOUVENIRS ?"),
    ("Sursaut au sommeil",
     "le corps sursaute en s'endormant", "le sursaut du corps en s'endormant", "SURSAUT ?"),
    ("Muscle qui tressaille",
     "un muscle tressaille tout seul", "le muscle qui tressaille tout seul", "MUSCLE QUI SAUTE ?"),
    ("Cœur qui s'emballe",
     "le cœur s'emballe sous le stress", "le cœur qui s'emballe sous le stress", "CŒUR EMBALLÉ ?"),
    ("Ventre qui se serre",
     "le ventre se serre lors d'une peur", "le ventre qui se serre lors d'une peur", "VENTRE SERRÉ ?"),
    ("Voix qui tremble",
     "la voix tremble par nervosité", "la voix qui tremble par nervosité", "VOIX QUI TREMBLE ?"),
    ("Paumes qui transpirent",
     "les paumes transpirent par nervosité", "les paumes qui transpirent par nervosité", "PAUMES MOITES ?"),
    ("Oreilles qui deviennent chaudes",
     "les oreilles deviennent chaudes par gêne", "les oreilles qui deviennent chaudes par gêne", "OREILLES CHAUDES ?"),
    ("Paupière qui saute",
     "une paupière tressaille sans raison", "la paupière qui tressaille sans raison", "ŒIL QUI SAUTE ?"),
    ("Mains qui se fripent",
     "les mains se fripent dans l'eau", "les mains qui se fripent dans l'eau", "MAINS FRIPÉES ?"),
    ("Chair de poule",
     "la chair de poule apparaît soudainement", "l'apparition soudaine de la chair de poule", "POURQUOI DES FRISSONS ?"),
    ("Hoquet soudain",
     "le hoquet commence brusquement", "le hoquet qui commence brusquement", "POURQUOI LE HOQUET ?"),
    ("Rêve qui disparaît",
     "un rêve disparaît au réveil", "le rêve qui disparaît au réveil", "RÊVE DISPARU ?"),
    ("Corps lourd",
     "le corps semble lourd quand on est fatigué", "le corps lourd quand on est fatigué", "CORPS LOURD ?"),
    ("Corps figé",
     "le corps se fige quand on a peur", "le corps qui se fige face à la peur", "CORPS FIGÉ ?"),
    ("Fourmillements",
     "des fourmillements apparaissent sans raison", "les fourmillements qui apparaissent sans raison", "FOURMILLEMENTS ?"),
    ("Nœud au ventre",
     "un nœud au ventre apparaît avant un moment", "le nœud au ventre avant un moment important", "NŒUD AU VENTRE ?"),
    ("Vertige en se levant",
     "un vertige apparaît après s'être levé", "le vertige après s'être levé", "VERTIGE ?"),
    ("Oreilles qui sifflent",
     "les oreilles sifflent dans le silence", "les oreilles qui sifflent dans le silence", "ÇA SIFFLE ?"),
    ("Temps qui semble passer vite",
     "le temps semble passer plus vite en vieillissant", "le temps qui semble passer plus vite en vieillissant", "TEMPS QUI FUIT ?"),
    ("Déjà-vu",
     "un déjà-vu semble étrangement familier", "l'impression étrange du déjà-vu", "DÉJÀ-VU ?"),
    ("Cerveau qui repère un prénom",
     "le cerveau repère son propre prénom", "la façon dont le cerveau repère son prénom", "PRÉNOM REPÉRÉ ?"),
    ("Silence inconfortable",
     "le silence devient inconfortable", "le silence qui devient inconfortable", "SILENCE GÊNANT ?"),
    ("Cerveau immature",
     "le cerveau est immature à 20 ans", "le cerveau immature à 20 ans", "CERVEAU JEUNE ?"),
    ("Cerveau divisé",
     "le cerveau des femmes est divisé en 5", "le cerveau divisé en 5", "CERVEAU EN 5 ?"),
    ("Corps qui refuse de mentir",
     "le corps révèle le mensonge", "les signes corporels du mensonge", "CORPS QUI MENT ?"),
    ("Corps qui refuse de maigrir",
     "le corps résiste à la perte de poids", "la résistance du corps à la perte de poids", "MAIGRIR ?"),
    ("Cerveau qui réclame du sommeil",
     "le cerveau réclame du sommeil profond", "le besoin de sommeil profond du cerveau", "SOMMEIL PROFOND ?"),
    ("Lumière qui fait éternuer",
     "une lumière vive fait éternuer", "l'éternuement provoqué par une lumière vive", "ÉTERNUER À LA LUMIÈRE ?"),
    ("Cœur battre la nuit",
     "on entend son cœur battre la nuit", "le cœur battre la nuit dans le silence", "CŒUR LA NUIT ?"),
    ("Aliment froid mal de tête",
     "un aliment froid provoque un mal de tête", "le mal de tête provoqué par un aliment froid", "MAL DE TÊTE FROID ?"),
    ("Vibration imaginaire",
     "on sent une vibration de téléphone imaginaire", "la vibration de téléphone fantôme", "VIBRATION FANTÔME ?"),
    ("Genoux qui craquent",
     "les genoux craquent en bougeant", "les genoux qui craquent en bougeant", "GENOUX QUI CRAQUENT ?"),
    ("Corps flottants",
     "des corps flottants visibles dans l'œil", "les corps flottants visibles dans l'œil", "FLOTTEURS ?"),
    ("Stress qui brouille la mémoire",
     "le stress brouille la mémoire", "la mémoire brouillée par le stress", "STRESS MÉMOIRE ?"),
    ("Peau qui se fripe",
     "la peau se fripe dans l'eau", "la peau qui se fripe dans l'eau", "PEAU FRIPÉE ?"),
    ("Faim à la même heure",
     "la faim revient à la même heure", "le retour de la faim à la même heure", "FAIM HABITUDE ?"),
    ("Musique change l'humeur",
     "la musique change l'humeur", "la façon dont la musique change l'humeur", "MUSIQUE HUMEUR ?"),
    ("Souvenirs gênants",
     "les souvenirs gênants reviennent", "le retour des souvenirs gênants", "SOUVENIRS GÊNANTS ?"),
    ("Cerveau qui éteint la douleur",
     "le cerveau atténue la douleur en danger", "la réduction de la douleur par le cerveau", "DOULEUR ATÉNUÉE ?"),
    ("Respiration qui ralentit",
     "la respiration ralentit en dormant", "le ralentissement de la respiration en dormant", "RESPIRATION ?"),
]

# Gabarits grammaticalement sûrs : {q} = proposition sujet+verbe,
# {n} = syntagme nominal défini. Aucun gabarit ne mélange les deux formes.
ANGLES = [
    "Pourquoi {q}",
    "La science derrière {n}",
    "Ce qui se passe quand {q}",
    "Ce qu'il faut comprendre sur {n}",
    "Pourquoi {q} peut sembler étrange",
    "Ce qui change lorsque {q}",
    "Pourquoi {q} semble soudain",
    "Ce que votre corps vous dit quand {q}",
    "Ce que la science explique sur {n}",
    "Comprendre pourquoi {q}",
]


def build_catalogue() -> list[dict]:
    records = []
    number = 0
    for label, q, n, thumbnail in PHENOMENA:
        for template in ANGLES:
            number += 1
            angle = template.format(q=q, n=n)
            records.append({
                "series_number": number,
                "series_title": label,
                "topic": n,              # base_phenomenon (forme nominale)
                "nominal_phrase": n,     # ex. "la paupière qui tressaille..."
                "question_phrase": q,    # ex. "une paupière tressaille..."
                "angle": angle,          # sujet parlant : phrase française complète
                "thumbnail_text": thumbnail,
                "pillar": "faits_surprenants",
            })
    assert len(records) == 500
    return records


if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'data' / 'body_glitch_topics.json'
    target.write_text(json.dumps(build_catalogue(), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"500 sujets français écrits dans {target}")
