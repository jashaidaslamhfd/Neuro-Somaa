# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-12T06:52:50.352128+00:00_ — n=50 vidéos réelles

## 📊 Data quality
- vues réelles: **50** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.3975 ± 0.4474** (MAE ≈ 307.1 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `has_second_person` (-), `dow_sin` (+), `predicted_ctr` (-), `hour_cos` (+), `title_words` (+)
- MLP: MAE ≈ 155.3 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.2324, avg 719.2 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 875.5

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi votre corps refuse de maigrir ?** — 3 vues (z=-12.74): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi l'œil distingue plus de nuances de vert ?** — 28 vues (z=-7.93): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure chaque jour ?** — 150 vues (z=-3.93): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi un vertige apparaît après s'être levé ?** — 151 vues (z=-3.91): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision — need ≥21 daily points, have 18

## 🗂️ Clusters de sujets (k=6) — gagnant: **poule / chair / soudainement / soudaine / l'apparition**
- `poule / chair / soudainement / soudaine / l'apparition` — 2 vidéos · avg 1076.0 vues · max 1205
- `ventre / faim / serre / lors / d'une` — 5 vidéos · avg 886.2 vues · max 1456
- `cerveau / réveil / son / passe / semble` — 22 vidéos · avg 732.1 vues · max 1241
- `comprendre / faut / qu'il / par / sur` — 5 vidéos · avg 727.8 vues · max 1512
- `corps / science / refuse / s'endormant / sur` — 12 vidéos · avg 626.8 vues · max 1168

## ⏱️ Rétention
- P10/P50/P90 = 28.9% / 36.6% / 50.1% · **88%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.163)
- `control_long` avg 680.0 vs `test_short` avg 910.67 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: none yet); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (1 sujets, TTL 96h)
- « Pourquoi le ventre se serre au réveil ? » ← cloné de **1456 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
