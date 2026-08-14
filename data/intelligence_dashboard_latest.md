# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-14T06:53:00.600433+00:00_ — n=56 vidéos réelles

## 📊 Data quality
- vues réelles: **56** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **6** · 🔴 figées (2 lectures sans hausse): **0**
  · ⚡ +252.5 vues/j — Pourquoi un rêve disparaît au réveil ?
  · ⚡ +7.0 vues/j — Pourquoi des corps flottants visibles dans l'œil ?
  · ⚡ +2.0 vues/j — Pourquoi le cerveau semble ralentir le temps en da

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=-0.01, n=56) — **consultatif seulement, jamais un gate**
- 🔴 `seo_score` (SEO quality): **NOISE** (r=-0.14, n=56) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.08, n=56) — biais +0.31 (prédit 0.70 vs réel 0.39) — **consultatif seulement, jamais un gate**
- ⛔ `predicted_ctr` (CTR): **INVERTED** (r=-0.16, n=56) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.6305 ± 0.7752** (MAE ≈ 353.7 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `has_second_person` (-), `hour_sin` (-), `topic_bucket_2` (-), `predicted_ctr` (-), `seo_score` (-)
- MLP: MAE ≈ 211.9 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.2005, avg 691.9 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 876.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi le stress brouille la mémoire ?** — 22 vues (z=-8.55): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi l'œil distingue plus de nuances de vert ?** — 33 vues (z=-7.6): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la respiration ralentit en dormant ?** — 37 vues (z=-7.33): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure chaque jour ?** — 150 vues (z=-3.96): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi un vertige apparaît après s'être levé ?** — 165 vues (z=-3.73): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision — need ≥21 daily points, have 20

## 🗂️ Clusters de sujets (k=6) — gagnant: **tout / seul / tressaille / raison / paupière**
- `tout / seul / tressaille / raison / paupière` — 4 vidéos · avg 991.5 vues · max 1168
- `comprendre / qu'il / faut / par / sur` — 6 vidéos · avg 734.7 vues · max 1512
- `cerveau / réveil / cœur / yeux / avant` — 13 vidéos · avg 721.0 vues · max 1456
- `froid / semble / frissonne / peau / passer` — 6 vidéos · avg 691.5 vues · max 1241
- `lorsque / change / faim / ventre / mémoire` — 7 vidéos · avg 637.0 vues · max 1007

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 38.3% / 53.2% · **88%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.1634)
- `control_long` avg 680.11 vs `test_short` avg 910.67 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: {'pov_reveal': 1, 'shock_fact': 1}); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (1 sujets, TTL 96h)
- « Pourquoi le ventre se serre au réveil ? » ← cloné de **1456 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
