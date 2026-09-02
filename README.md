# Neuro-Somaa

> **Pipeline automatisé de Shorts YouTube en français**, conçu pour produire des vidéos courtes de science du quotidien avec des garde-fous éditoriaux, un contrôle qualité strict et une boucle d’apprentissage fondée sur les données réellement disponibles.

## Promesse

Neuro-Somaa transforme un sujet français en Short prêt à publier :

`Sujet → script français → voix française → visuels → sous-titres → SEO → publication planifiée`

Le projet vise la **France et la francophonie**. Son positionnement éditorial repose sur des faits surprenants liés au corps, au sommeil, aux émotions et aux phénomènes familiers. Il ne promet ni viralité ni recommandation algorithmique et bloque les formulations médicales trompeuses, le spam et les doublons.

## Vue d’ensemble

| Étape | Composant principal | Résultat |
|---|---|---|
| Recherche | `src/trend_fetcher.py`, `src/trend_research.py` | Sujets et signaux francophones |
| Écriture | `src/script_generator.py`, `src/french_humanizer.py` | Script court, naturel et contrôlé |
| Audio | `src/voice_generator.py` | Voix française avec replis configurables |
| Média | `src/image_generator.py`, `src/video_editor.py` | Vidéo verticale et sous-titres |
| Contrôle | `src/french_quality_gate.py`, `src/strict_quality_gate.py` | Validation langue, sécurité, rythme et SEO |
| Publication | `src/uploader.py`, `src/scheduler.py` | Upload YouTube et créneau Paris |
| Apprentissage | `src/analytics_updater.py`, `src/intelligence/` | Historique réel, diagnostics et recommandations |

## Démarrage local

```bash
cp env.example .env
# Renseigner au minimum GROQ_API_KEY.
# Ajouter les identifiants YouTube uniquement pour publier ou synchroniser les données.
python scripts/generate_body_glitch_topics.py
python src/main.py
```

Pour les contrôles légers et les opérations de maintenance, utiliser `requirements-ops.txt`. Les dépendances de génération vidéo sont regroupées dans `requirements.txt`; les dépendances CI sont décrites par `requirements-ci.txt` et verrouillées dans `requirements-ci.lock`.

## Publication et sécurité

Le workflow de production utilise une vidéo privée avec publication planifiée (`YT_PRIVACY_STATUS=private` et `YT_SCHEDULE_PUBLISH=true`). Pour une revue humaine, désactiver la publication planifiée. Une vidéo ne doit être considérée comme prête qu’après le passage des contrôles français, anti-spam, anti-doublon, média, miniature et métadonnées.

Les créneaux par défaut sont **12:30, 19:30 et 21:00**, dans le fuseau `Europe/Paris`. Le système peut produire des recommandations dynamiques, mais leur adoption doit rester une décision explicite après revue des observations.

## Workflows GitHub Actions

| Workflow | Fonction |
|---|---|
| `Neuro-Somaa - French Shorts Automation` | Génère et programme les Shorts |
| `Neuro-Somaa - YouTube Analytics Sync` | Synchronise vues, rétention et métriques disponibles |
| `Auto-Apply Verified Metadata Repairs (daily)` | Applique les réparations validées avec délai de sécurité |
| `Monetization Readiness (daily plan)` | Prépare le suivi de maturité de la chaîne |
| `CI - guard tests on push` | Exécute les tests hors ligne |
| `Ops Console` | Regroupe les opérations manuelles en mode simulation par défaut |

## Organisation du dépôt

```text
.github/workflows/   Automatisation CI/CD et opérations YouTube
src/                 Pipeline de production et intelligence
scripts/             Commandes opérationnelles et analyses ponctuelles
assets/              Musique et médias sources
data/                État durable, historiques et rapports générés
docs/                Runbooks, spécifications et archives de décisions
tests/               Tests de régression et garde-fous
```

Les rapports générés et historiques restent dans `data/`. Les analyses ponctuelles sont dans `scripts/analysis/`; les procédures actives sont dans `docs/operations/`; les audits et migrations historiques sont conservés dans `docs/archive/` afin de ne pas encombrer le parcours principal.

## Documentation utile

Commencer par le [runbook de production](docs/PRODUCTION_RUNBOOK.md), puis consulter l’[expérience de marché francophone](docs/FRANCOPHONE_MARKET_EXPERIMENT.md). Les procédures d’exploitation se trouvent dans [docs/operations](docs/operations/), et les décisions historiques dans [docs/archive](docs/archive/).

## Principes éditoriaux

Le contenu visible et audible est en français naturel. Les titres doivent contenir un verbe conjugué et une question ou une accroche compréhensible. Les affirmations médicales non vérifiables sont bloquées. Les titres, tags et miniatures concurrents servent uniquement à apprendre des formats : ils ne sont pas copiés mot pour mot.

> **Règle centrale :** une métrique indisponible reste indisponible. Le pipeline ne fabrique pas de CTR, de rétention ou de causalité à partir de données manquantes.

## Licence

MIT — voir [LICENSE](LICENSE).
