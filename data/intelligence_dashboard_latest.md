# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-13T06:55:33.533797+00:00_ — n=54 vidéos réelles

## 📊 Data quality
- vues réelles: **54** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **3** · 🔴 figées (2 lectures sans hausse): **0**
  · ⚡ +252.5 vues/j — Pourquoi un rêve disparaît au réveil ?
  · ⚡ +7.0 vues/j — Pourquoi des corps flottants visibles dans l'œil ?
  · ⚡ +2.0 vues/j — Pourquoi le cerveau semble ralentir le temps en da

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=-0.02, n=54) — **consultatif seulement, jamais un gate**
- ⛔ `seo_score` (SEO quality): **INVERTED** (r=-0.16, n=54) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.09, n=54) — biais +0.31 (prédit 0.70 vs réel 0.39) — **consultatif seulement, jamais un gate**
- ⛔ `predicted_ctr` (CTR): **INVERTED** (r=-0.17, n=54) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.9614 ± 1.082** (MAE ≈ 343.9 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `has_second_person` (-), `hour_sin` (-), `topic_bucket_2` (-), `predicted_ctr` (-), `seo_score` (-)
- MLP: MAE ≈ 213.7 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.2099, avg 686.5 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 875.5

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi le stress brouille la mémoire ?** — 22 vues (z=-8.2): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi l'œil distingue plus de nuances de vert ?** — 31 vues (z=-7.43): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la respiration ralentit en dormant ?** — 37 vues (z=-7.03): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure chaque jour ?** — 150 vues (z=-3.8): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi un vertige apparaît après s'être levé ?** — 165 vues (z=-3.58): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision — need ≥21 daily points, have 20

## 🗂️ Clusters de sujets (k=6) — gagnant: **autres / bâillement / transmet / comprendre**
- `autres / bâillement / transmet / comprendre` — 1 vidéos · avg 810.0 vues · max 810
- `sur / explique / comprendre / science / faut` — 11 vidéos · avg 762.2 vues · max 1512
- `avant / ventre / apparaît / gargouille / vite` — 7 vidéos · avg 761.4 vues · max 1456
- `semble / temps / cœur / son / cerveau` — 10 vidéos · avg 715.4 vues · max 1241
- `change / lorsque / froid / peau / oreilles` — 16 vidéos · avg 700.7 vues · max 1087

## ⏱️ Rétention
- P10/P50/P90 = 28.9% / 37.6% / 52.9% · **89%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.163)
- `control_long` avg 680.0 vs `test_short` avg 910.67 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: none yet); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (1 sujets, TTL 96h)
- « Pourquoi le ventre se serre au réveil ? » ← cloné de **1456 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
