# Neuro-Somaa — YouTube Shorts France

> **English summary:** Neuro-Somaa is a fully automated, French-first YouTube
> Shorts pipeline that runs entirely on GitHub Actions — French topic → French
> script (LLM) → French neural voice → visuals → captions → French SEO →
> scheduled upload (3 Shorts/day at Paris peak times). A daily analytics sync
> feeds real views/retention/CTR back into a learning loop (publish slots,
> title patterns, topic gaps). Safety gates: French-language check, medical
> claim filter, anti-spam checks, synthetic-media disclosure. The French
> documentation below is the operator manual.

Pipeline Python **France-first** pour une chaîne YouTube Shorts de science du quotidien :

`Sujet français → script français → voix française → visuels → sous-titres → SEO français → upload programmé`

## Positionnement éditorial
- **Audience :** France et francophonie, adultes curieux de science simple.
- **Série :** *faits surprenants* — phénomènes familiers du corps (paupière qui saute, déjà-vu, bâillement, sommeil…).
- **Langue :** tous les éléments visibles et audibles sont générés en français naturel.
- **Sécurité :** aucune promesse médicale, aucun engagement artificiel, aucune automatisation de vues/commentaires.

## Réglages France actifs
| Élément | Valeur |
|---|---|
| Recherche de tendances | `FR` |
| Région YouTube | `FR` |
| Fuseau de publication | `Europe/Paris` |
| Créneaux par défaut | 12:30 / 19:30 / 21:00 (Paris), un Short par créneau, **3/jour** |
| Créneaux dynamiques | appris des vues réelles (`data/upload_slot_intel_fr.json`), minimum 5 observations avant adoption |
| Moteur vocal principal | `TTS_ENGINE=edge`, voix `fr-FR-HenriNeural` (repli Remy/Denise puis Kokoro `ff_siwis`) |
| Série | `faits_surprenants_fr` |
| Seuils qualité (production) | `MIN_HOOK_SCORE=70`, `QUALITY_APPROVAL_THRESHOLD=60` (alignés `env.example` ↔ `main.yml` via `tests/test_runtime_config.py`) |

## Démarrage
```bash
cp env.example .env
# renseignez au minimum GROQ_API_KEY ; ajoutez OAuth YouTube pour publier
# (le REFRESH_TOKEN doit aussi porter le scope yt-analytics.readonly pour
#  que les impressions et le CTR réel remontent dans video_history.json)
python scripts/generate_body_glitch_topics.py
python src/main.py
```

### Deux modes de publication — à choisir en connaissance de cause

| Mode | Réglage | Comportement |
|---|---|---|
| **Revue manuelle** (défaut de `env.example`) | `YT_PRIVACY_STATUS=private` | La vidéo reste privée indéfiniment. Rien n'est publié sans vous. |
| **Automatique** (défaut du workflow) | `YT_PRIVACY_STATUS=private` + `YT_SCHEDULE_PUBLISH=true` | La vidéo est envoyée en privé avec un `publishAt` (au prochain créneau Paris appris), puis **YouTube la rend publique automatiquement** à cette minute. **Aucune relecture humaine n'a lieu entre les deux.** |

`.github/workflows/main.yml` tourne en mode **automatique** : c'est ce qui permet les 3 Shorts/jour sans intervention. Si vous préférez relire chaque vidéo, passez `YT_PRIVACY_STATUS` à `private` dans le workflow.

Les garde-fous qui remplacent la relecture en mode automatique : double contrôle qualité français (script + métadonnées finales), blocage des titres tronqués, blocage des titres sans verbe, blocage des titres en doublon, miniatures à accroche verbale (jamais une étiquette nue), contrôle du rythme des sous-titres et vérification anti-spam.

## Workflows principaux (noms réels)
| Workflow | Rôle | Fréquence |
|---|---|---|
| `Neuro-Somaa - French Shorts Automation` | génère + programme 3 Shorts/jour | 10:30 / 17:30 / 19:00 UTC |
| `Neuro-Somaa - YouTube Analytics Sync` | vues/rétention/CTR réels → historique + réapprentissage | quotidien 05:30 UTC |
| `Auto-Apply Verified Metadata Repairs (daily)` | répare les métadonnées défectueuses (cooldown 7 jours par vidéo) | quotidien 08:00 UTC |
| `Monetization Readiness (daily plan)` | tableau de bord monétisation | quotidien |
| `CI - guard tests on push` | 130+ tests hors-ligne | chaque push |

Les autres workflows sont des **outils manuels** (one-shot) : migration de niche, réparation de miniatures, nettoyage… à lancer uniquement via *Run workflow*.

## Signaux qui aident YouTube à identifier l'audience française
Le système envoie des signaux cohérents et honnêtes : langue du script, voix FR, titre/description/tags/miniature FR, région de tendances `FR`, créneaux Paris et thèmes cohérents. **Aucun réglage ne garantit une recommandation** : l'algorithme apprend surtout des spectateurs qui choisissent et regardent réellement les vidéos.

## Couche premium : intelligence concurrentielle française
Le repo peut aussi apprendre des Shorts français déjà gagnants :

1. renseignez `YOUTUBE_API_KEY` ;
2. laissez `COMPETITOR_CHANNEL_IDS` vide si vous voulez l'auto-découverte : le système choisit lui-même les concurrents à partir de requêtes FR à fort volume ;
3. optionnellement, ajoutez des IDs de chaînes dans `COMPETITOR_CHANNEL_IDS` pour forcer certaines références ;
4. lancez le workflow **Neuro-Somaa - French Competitor Repair**.

Le fichier `data/competitor_intel_fr.json` apprend les **patterns** gagnants (ex. formats de titres, tags de niche), puis `seo_generator.py` les mélange aux titres/tags Neuro-Somaa. Par sécurité, le système **ne copie pas mot pour mot** les titres/tags concurrents : il crée des métadonnées originales à partir du sujet Neuro-Somaa et bloque les correspondances exactes.

Pour les vidéos déjà publiées, le workflow **SEO Repair (uploaded videos)** peut reconstruire titre/description/tags avec cette intelligence concurrentielle. Il reste en dry-run par défaut ; choisir `mode=apply` pour écrire sur YouTube.

## Boucle d'apprentissage continue (dans la sync analytique)
La sync quotidienne (`src/analytics_updater.py`) enchaîne après chaque relevé :

- **Dynamic publish slots** : apprend les heures Paris qui génèrent le plus de vues/rétention et écrit `data/upload_slot_intel_fr.json` (adoption seulement après **5 observations minimum**) ; les prochains `publishAt` utilisent ces créneaux (`USE_DYNAMIC_SCHEDULE=true`).
- **Title bandit** : compare les patterns de titres avec les performances réelles et réordonne les futurs titres dans `data/title_bandit_fr.json`.
- **48h auto-repair plan** : repère les vidéos qui sous-performent après 48 h et génère un plan de réparation sans écrire sur YouTube.
- **Topic gaps** : compare les mots-clés concurrents + demandes en commentaires avec le catalogue de sujets.
- **Comments intelligence** : lit les vrais commentaires pour détecter les sujets demandés, sans automatiser les vues/commentaires.
- **ML brain** : réentraîné à chaque sync uniquement sur les vidéos ayant de vraies mesures (`data/ml_brain_state.json`).
- **Francophonie subtile** : tags France/francophonie via `FRANCOPHONE_LOCALE_TAGS=true` sans changer la voix `fr-FR`.

## Hygiène du dépôt
- `data/video_history.json` = historique **cumulatif réel** (source de vérité ML).
- Les instantanés datés (`seo_diag_*`, `premium_growth_dashboard_*`…) sont élagués automatiquement : **7 derniers jours + le plus récent** (`scripts/cleanup_data_snapshots.py`, lancé par la sync analytique).
- Dépendances : `requirements.txt` (génération vidéo, lourd) · `requirements-ops.txt` (réparations/audits, léger) · `requirements-ci.txt` (tests hors-ligne).

## Licence
MIT — voir [LICENSE](LICENSE).
