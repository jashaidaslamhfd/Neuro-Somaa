# Musiques de fond — provenance et licences

## ✅ ORIGINALES (sécurisées pour la monétisation — aucune risque Content ID)

Les pistes `own_*.ogg` sont **générées dans ce dépôt** (scripts/generate_own_music.py,
synthèse procédurale originale). Elles sont 100% originales : aucune réclamation
Content ID possible. **La pipeline les utilise PAR DÉFAUT depuis 2026-08-02**
(`MUSIC_SOURCE=own`).

| Fichier | Origine | Licence | Vérifié |
|---|---|---|---|
| `own_dark_drone.ogg` | générée (scripts/generate_own_music.py) | Originale (ce dépôt) | ✅ |
| `own_suspense_thrum.ogg` | générée (scripts/generate_own_music.py) | Originale (ce dépôt) | ✅ |

## 🚫 TIERCES — QUARANTAISÉES (2026-08-15)

Les pistes suivantes ont été déplacées vers `assets/music/quarantine/`, hors
du chemin de scan de la pipeline. Elles ne sont **plus jamais sélectionnées**
par `_get_music_track()` : seuls les morceaux originaux (`own_*.ogg`/`own_*.wav`)
et le lit ambient synthétique original restent actifs. Aucune réclamation
Content ID possible sur les vidéos produites. Pour les réutiliser après avoir
vérifié leur licence Pixabay (voir instructions ci-dessous), remettez-les
dans `assets/music/`.

| Fichier | Auteur présumé | Source | Licence | Vérifié |
|---|---|---|---|---|
| `lnplusmusic-science-space-technology-music-362831.mp3` | lnplusmusic | Pixabay ? (id 362831) | à confirmer | ❌ |
| `mfcc-science-space-technology-music-328258.mp3` | mfcc | Pixabay ? (id 328258) | à confirmer | ❌ |
| `paulyudin-suspense-513011.mp3` | paulyudin | Pixabay ? (id 513011) | à confirmer | ❌ |
| `the_mountain-brain-science-136923.mp3` | the_mountain | Pixabay ? (id 136923) | à confirmer | ❌ |

## Comment vérifier
1. Ouvre la page Pixabay Music du fichier (cherche l'ID dans le nom).
2. Confirme la licence "Pixabay Content License" (usage commercial autorisé).
3. Colle le lien + la licence dans ce tableau et passe ✅.

**Recommandation 2026-08-02:** supprime les 4 fichiers tiers — les pistes
originales suffisent et éliminent tout risque.
