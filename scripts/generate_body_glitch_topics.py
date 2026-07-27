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
    ("Paupière qui saute",
     "une paupière tressaille sans raison", "la paupière qui tressaille sans raison", "ŒIL QUI SAUTE ?"),
    ("Ventre qui gargouille",
     "le ventre gargouille sans faim", "le ventre qui gargouille sans faim", "BRUIT DU VENTRE ?"),
    ("Chair de poule",
     "la chair de poule apparaît soudainement", "l'apparition soudaine de la chair de poule", "POURQUOI DES FRISSONS ?"),
    ("Oreilles qui sifflent",
     "les oreilles sifflent dans le silence", "les oreilles qui sifflent dans le silence", "ÇA SIFFLE ?"),
    ("Hoquet soudain",
     "le hoquet commence brusquement", "le hoquet qui commence brusquement", "POURQUOI LE HOQUET ?"),
    ("Nez qui coule",
     "le nez coule quand on pleure", "le nez qui coule quand on pleure", "NEZ QUI COULE ?"),
    ("Mains fripées",
     "les mains se fripent dans l'eau", "les mains qui se fripent dans l'eau", "MAINS FRIPÉES ?"),
    ("Frissons de stress",
     "le corps frissonne sous le stress", "le corps qui frissonne sous le stress", "POURQUOI JE TREMBLE ?"),
    ("Rougir",
     "le visage rougit par gêne", "le visage qui rougit par gêne", "POURQUOI JE ROUGIS ?"),
    ("Bâillement contagieux",
     "le bâillement se transmet aux autres", "le bâillement qui se transmet aux autres", "POURQUOI ON BÂILLE ?"),
    ("Larmes de rire",
     "les yeux pleurent quand on rit", "les larmes qui coulent quand on rit", "LARMES DE RIRE ?"),
    ("Gel du cerveau",
     "un aliment froid provoque un mal de tête", "le mal de tête après un aliment froid", "CERVEAU GELÉ ?"),
    ("Fourmillements",
     "des fourmillements apparaissent après une mauvaise position", "les fourmillements après une mauvaise position", "DES FOURMIS ?"),
    ("Pied endormi",
     "un pied s'endort tout seul", "le pied qui s'endort tout seul", "PIED ENDORMI ?"),
    ("Muscle qui saute",
     "un muscle tressaille tout seul", "le muscle qui tressaille tout seul", "MUSCLE QUI SAUTE ?"),
    ("Sursaut du sommeil",
     "le corps sursaute en s'endormant", "le sursaut du corps en s'endormant", "SURSAUT DU SOMMEIL ?"),
    ("Voix qui tremble",
     "la voix tremble par nervosité", "la voix qui tremble par nervosité", "VOIX QUI TREMBLE ?"),
    ("Mains froides",
     "les mains deviennent froides sous le stress", "les mains froides sous le stress", "MAINS FROIDES ?"),
    ("Oreilles chaudes",
     "les oreilles deviennent chaudes", "les oreilles qui deviennent chaudes", "OREILLES CHAUDES ?"),
    ("Mains moites",
     "les paumes transpirent par nervosité", "les paumes qui transpirent par nervosité", "MAINS MOITES ?"),
    ("Nœud au ventre",
     "un nœud au ventre apparaît avant un moment important", "le nœud au ventre avant un moment important", "NŒUD AU VENTRE ?"),
    ("Boule dans la gorge",
     "une boule dans la gorge apparaît sous l'émotion", "la boule dans la gorge sous l'émotion", "BOULE À LA GORGE ?"),
    ("Bouche sèche",
     "la bouche devient sèche par nervosité", "la bouche sèche par nervosité", "BOUCHE SÈCHE ?"),
    ("Mâchoire qui craque",
     "la mâchoire craque en mâchant", "la mâchoire qui craque en mâchant", "MÂCHOIRE QUI CRAQUE ?"),
    ("Genoux qui craquent",
     "les genoux craquent en bougeant", "les genoux qui craquent en bougeant", "GENOUX QUI CRAQUENT ?"),
    ("Ventre qui se serre",
     "le ventre se serre lors d'une peur", "le ventre qui se serre lors d'une peur", "VENTRE SERRÉ ?"),
    ("Cœur qui s'emballe",
     "le cœur s'emballe sous le stress", "le cœur qui s'emballe sous le stress", "CŒUR QUI S'EMBALLE ?"),
    ("Vertige au lever",
     "un vertige apparaît après s'être levé", "le vertige après s'être levé", "VERTIGE AU LEVER ?"),
    ("Éternuement lumineux",
     "une lumière vive fait éternuer", "l'éternuement face à une lumière vive", "LUMIÈRE = ÉTERNUEMENT ?"),
    ("Corps flottants",
     "des corps flottants apparaissent dans la lumière", "les corps flottants visibles dans la lumière", "TACHES DEVANT LES YEUX ?"),
    ("Vibration fantôme",
     "on sent une vibration de téléphone imaginaire", "la vibration de téléphone imaginaire", "VIBRATION FANTÔME ?"),
    ("Chanson en boucle",
     "une chanson reste coincée dans la tête", "la chanson qui reste dans la tête", "CHANSON BLOQUÉE ?"),
    ("Déjà-vu",
     "un déjà-vu semble étrangement familier", "le déjà-vu qui semble familier", "DÉJÀ-VU ?"),
    ("Trou de mémoire",
     "on oublie pourquoi on entre dans une pièce", "le trou de mémoire en entrant dans une pièce", "POURQUOI SUIS-JE ICI ?"),
    ("Prénom oublié",
     "on oublie un prénom juste après l'avoir entendu", "le prénom oublié juste après l'avoir entendu", "PRÉNOM OUBLIÉ ?"),
    ("Souvenirs nocturnes",
     "les souvenirs gênants reviennent le soir", "les souvenirs gênants qui reviennent le soir", "POURQUOI J'Y REPENSE ?"),
    ("Réveil avant l'alarme",
     "on se réveille juste avant son réveil", "le réveil juste avant l'alarme", "AVANT LE RÉVEIL ?"),
    ("Battements entendus",
     "on entend son cœur battre la nuit", "les battements de cœur entendus la nuit", "J'ENTENDS MON CŒUR ?"),
    ("Horloge de la faim",
     "la faim revient à la même heure chaque jour", "la faim qui revient à la même heure", "FAIM ENCORE ?"),
    ("Musique et humeur",
     "la musique change l'humeur instantanément", "l'effet de la musique sur l'humeur", "MUSIQUE = HUMEUR ?"),
    ("Silence gênant",
     "le silence devient inconfortable", "le silence qui devient inconfortable", "SILENCE GÊNANT ?"),
    ("Entendre son nom",
     "le cerveau repère son propre prénom", "le prénom que le cerveau repère partout", "J'AI ENTENDU MON NOM ?"),
    ("Temps accéléré",
     "le temps semble passer plus vite en vieillissant", "le temps qui semble accélérer en vieillissant", "LE TEMPS ACCÉLÈRE ?"),
    ("Sommeil profond",
     "le cerveau réclame du sommeil profond", "le sommeil profond dont le cerveau a besoin", "SOMMEIL PROFOND ?"),
    ("Nuances de vert",
     "l'œil distingue plus de nuances de vert", "les nuances de vert que l'œil distingue", "POURQUOI LE VERT ?"),
    ("Stress et mémoire",
     "le stress brouille la mémoire", "l'effet du stress sur la mémoire", "STRESS ET MÉMOIRE ?"),
    ("Frisson de froid",
     "on frissonne quand on a froid", "le frisson quand on a froid", "FRISSON DE FROID ?"),
    ("Corps lourd",
     "le corps semble lourd quand on est fatigué", "le corps lourd quand on est fatigué", "CORPS LOURD ?"),
    ("Corps figé",
     "le corps se fige quand on a peur", "le corps qui se fige face à la peur", "CORPS FIGÉ ?"),
    ("Rêve oublié",
     "un rêve disparaît au réveil", "le rêve qui disparaît au réveil", "RÊVE DISPARU ?"),
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
                "topic": n,          # base_phenomenon (forme nominale)
                "angle": angle,      # sujet parlant : phrase française complète
                "thumbnail_text": thumbnail,
                "pillar": "reflexes_du_corps",
            })
    assert len(records) == 500
    return records


if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'data' / 'body_glitch_topics.json'
    target.write_text(json.dumps(build_catalogue(), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"500 sujets français écrits dans {target}")
