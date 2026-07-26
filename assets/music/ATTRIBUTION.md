# Musiques de fond — provenance et licences

Les pistes de `assets/music/` sont mixées à faible volume (`MUSIC_VOLUME=0.07`)
sous la narration de chaque Short. Elles sont **committées dans un dépôt public**,
il faut donc que leur licence autorise à la fois la redistribution et l'usage
commercial (monétisation YouTube).

⚠️ **À COMPLÉTER PAR LE PROPRIÉTAIRE DU DÉPÔT.** Les noms de fichiers suivent la
convention Pixabay Music (`<auteur>-<titre>-<id>.mp3`), mais l'origine exacte n'a
jamais été documentée. Tant que ce tableau n'est pas rempli et vérifié, chaque
piste est un risque de réclamation Content ID sur toutes les vidéos concernées.

| Fichier | Auteur présumé | Source | Licence | Vérifié |
|---|---|---|---|---|
| `lnplusmusic-science-space-technology-music-362831.mp3` | lnplusmusic | Pixabay ? (id 362831) | à confirmer | ❌ |
| `mfcc-science-space-technology-music-328258.mp3` | mfcc | Pixabay ? (id 328258) | à confirmer | ❌ |
| `paulyudin-suspense-513011.mp3` | paulyudin | Pixabay ? (id 513011) | à confirmer | ❌ |
| `the_mountain-brain-science-136923.mp3` | the_mountain | Pixabay ? (id 136923) | à confirmer | ❌ |

## Comment vérifier

1. Ouvrir `https://pixabay.com/music/search/?q=` et rechercher l'identifiant numérique.
2. Confirmer l'auteur et la licence (la **Pixabay Content License** autorise
   l'usage commercial sans attribution, mais interdit la redistribution du
   fichier « tel quel » — ici les pistes sont mixées dans une vidéo, ce qui est
   conforme ; les committer dans un dépôt public est la zone grise).
3. Renseigner l'URL exacte et cocher ✅.

Si une piste ne peut pas être tracée, la remplacer par une source clairement
licenciée (YouTube Audio Library, Kevin MacLeod / CC-BY avec crédit en
description, ou une bibliothèque payante) plutôt que de la conserver « au cas où ».

## Règle pour toute nouvelle piste

Aucun fichier n'est ajouté à `assets/music/` sans une ligne correspondante,
vérifiée, dans le tableau ci-dessus.
