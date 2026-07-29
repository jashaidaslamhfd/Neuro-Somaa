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

## Couche premium : intelligence concurrentielle française
Le repo peut aussi apprendre des Shorts français déjà gagnants :

1. renseignez `YOUTUBE_API_KEY` ;
2. laissez `COMPETITOR_CHANNEL_IDS` vide si vous voulez l'auto-découverte : le système choisit lui-même les concurrents à partir de requêtes FR à fort volume ;
3. optionnellement, ajoutez des IDs de chaînes dans `COMPETITOR_CHANNEL_IDS` pour forcer certaines références ;
4. lancez le workflow **SKILLOR - French Competitor Intelligence**.

Le fichier `data/competitor_intel_fr.json` apprend les **patterns** gagnants (ex. formats de titres, tags de niche), puis `seo_generator.py` les mélange aux titres/tags SKILLOR. Par sécurité, le système **ne copie pas mot pour mot** les titres/tags concurrents : il crée des métadonnées originales à partir du sujet SKILLOR et bloque les correspondances exactes.

Pour les vidéos déjà publiées, le workflow **SEO Repair (uploaded videos)** peut reconstruire titre/description/tags avec cette intelligence concurrentielle. Il reste en dry-run par défaut ; choisir `mode=apply` pour écrire sur YouTube.

## Boucle premium de croissance
Le workflow **SKILLOR - Premium Growth Loop** ajoute la couche d'apprentissage continue :

- **Dynamic publish slots** : apprend les heures Paris qui génèrent le plus de vues/rétention et écrit `data/upload_slot_intel_fr.json`; les prochains `publishAt` utilisent ces créneaux automatiquement (`USE_DYNAMIC_SCHEDULE=true`).
- **Title bandit** : compare les patterns de titres avec les performances réelles de la chaîne et réordonne les futurs titres dans `data/title_bandit_fr.json`.
- **48h auto-repair plan** : repère les vidéos qui sous-performent après 48 h et génère un plan de réparation sans écrire sur YouTube.
- **Topic gaps** : compare les mots-clés concurrents + demandes en commentaires avec le catalogue de 500 sujets.
- **Comments intelligence** : lit les vrais commentaires pour détecter les sujets demandés, sans automatiser les vues/commentaires.
- **Final publication audit** : avant upload, le MP4, l'audio, la vignette, les sous-titres et les métadonnées finales sont vérifiés ensemble.
- **Francophonie subtile** : tags France/francophonie activables via `FRANCOPHONE_LOCALE_TAGS=true` sans changer la voix `fr-FR`.
