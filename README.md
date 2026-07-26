# SKILLOR — YouTube Shorts France

Pipeline Python **France-first** pour une chaîne YouTube Shorts de science du quotidien :

`Sujet français → script français → voix française → visuels → sous-titres → SEO français → upload privé`

## Positionnement éditorial
- **Audience :** France et francophonie, adultes curieux de science simple.
- **Série :** *Réflexes du corps* — 500 phénomènes familiers (paupière qui saute, déjà-vu, bâillement, sommeil, etc.).
- **Langue :** tous les éléments visibles et audibles sont générés en français naturel.
- **Sécurité :** aucune promesse médicale, aucun engagement artificiel, aucune automatisation de vues/commentaires.

## Réglages France actifs
| Élément | Valeur |
|---|---|
| Recherche de tendances | `FR` |
| Région YouTube | `FR` |
| Fuseau de publication | `Europe/Paris` |
| Créneaux de publication | 12:30 / 19:30 / 21:00 (Paris), un seul Short par créneau |
| Voix de secours/principale | Kokoro français `ff_siwis` |
| Moteur vocal | `TTS_ENGINE=kokoro` |
| Série | `body_glitches_fr` |
| Seuils qualité (production) | `MIN_HOOK_SCORE=85`, `QUALITY_APPROVAL_THRESHOLD=85` |

## Démarrage
```bash
cp env.example .env
# renseignez au minimum GROQ_API_KEY ; ajoutez OAuth YouTube pour publier
python scripts/generate_body_glitch_topics.py
python src/main.py
```

### Deux modes de publication — à choisir en connaissance de cause

| Mode | Réglage | Comportement |
|---|---|---|
| **Revue manuelle** (défaut de `env.example`) | `YT_PRIVACY_STATUS=private` | La vidéo reste privée indéfiniment. Rien n'est publié sans vous. |
| **Automatique** (défaut du workflow) | `YT_PRIVACY_STATUS=public` + `YT_SCHEDULE_PUBLISH=true` | La vidéo est envoyée en privé avec un `publishAt`, puis **YouTube la rend publique automatiquement** au prochain créneau libre. **Aucune relecture humaine n'a lieu entre les deux.** |

`.github/workflows/main.yml` tourne en mode **automatique** : c'est ce qui permet les 3 Shorts/jour sans intervention. Si vous préférez relire chaque vidéo, passez `YT_PRIVACY_STATUS` à `private` dans le workflow.

Les garde-fous qui remplacent la relecture en mode automatique : double contrôle qualité français (script + métadonnées finales), blocage des titres tronqués, blocage des titres en doublon, contrôle du rythme des sous-titres et vérification anti-spam.

## Signaux qui aident YouTube à identifier l'audience française
Le système envoie des signaux cohérents et honnêtes : langue du script, voix FR, titre/description/tags FR, région de tendances `FR`, créneaux Paris et thèmes cohérents. **Aucun réglage ne garantit une recommandation** : l'algorithme apprend surtout des spectateurs qui choisissent et regardent réellement les vidéos.
