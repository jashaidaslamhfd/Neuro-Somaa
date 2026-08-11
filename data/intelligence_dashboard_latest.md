# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-11T10:01:44.348998+00:00_ — n=47 vidéos réelles

## 📊 Data quality
- vues réelles: **47** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.5232 ± 0.8272** (MAE ≈ 342.1 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `has_second_person` (-), `dow_sin` (+), `hour_cos` (+), `hour_sin` (-), `predicted_ctr` (-)
- MLP: MAE ≈ 146.6 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.2509, avg 708.2 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 875.5

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi votre corps refuse de maigrir ?** — 3 vues (z=-11.59): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi l'œil distingue plus de nuances de vert ?** — 28 vues (z=-7.21): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure chaque jour ?** — 149 vues (z=-3.58): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi un vertige apparaît après s'être levé ?** — 151 vues (z=-3.55): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision — need ≥21 daily points, have 17

## 🗂️ Clusters de sujets (k=5) — gagnant: **ventre / peut / sembler / étrange / avant**
- `ventre / peut / sembler / étrange / avant` — 9 vidéos · avg 837.1 vues · max 1456
- `comprendre / faut / qu'il / par / sur` — 6 vidéos · avg 734.0 vues · max 1512
- `science / sur / explique / derrière / chaudes` — 7 vidéos · avg 733.9 vues · max 1205
- `cœur / passe / battre / son / nuit` — 4 vidéos · avg 619.0 vues · max 797
- `corps / dit / vous / refuse / s'endormant` — 21 vidéos · avg 616.2 vues · max 1241

## ⏱️ Rétention
- P10/P50/P90 = 28.9% / 36.5% / 47.5% · **89%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.163)
- `control_long` avg 680.0 vs `test_short` avg 910.67 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: none yet); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (1 sujets, TTL 96h)
- « Pourquoi le ventre se serre au réveil ? » ← cloné de **1456 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
