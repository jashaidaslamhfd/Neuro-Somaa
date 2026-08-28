# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-28T17:35:02.797386+00:00_ — n=67 vidéos réelles

## 📊 Data quality
- vues réelles: **67** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **3** · 🔴 figées (2 lectures sans hausse): **64**
  · ⚡ +2.9 vues/j — Corps lourd
  · ⚡ +1.0 vues/j — Pourquoi l'œil distingue plus de nuances de vert ?
  · ⚡ +1.0 vues/j — Pourquoi le hoquet ne s'arrête pas ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=-0.06, n=67) — **consultatif seulement, jamais un gate**
- ✅ `seo_score` (SEO quality): **CALIBRATED** (r=+0.37, n=67) — peut guider des décisions
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.11, n=67) — biais +0.24 (prédit 0.69 vs réel 0.45) — **consultatif seulement, jamais un gate**
- ✅ `predicted_ctr` (CTR): **CALIBRATED** (r=+0.36, n=67) — peut guider des décisions

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = 0.4441 ± 0.1674** (MAE ≈ 378.5 vues) — ✅ fiable
- facteurs dominants: `is_question` (+), `hour_cos` (+), `hour_sin` (-), `title_chars` (-), `has_second_person` (-)
- MLP: MAE ≈ 242.0 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1501, avg 570.2 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUI_SE_PASSE` n= 1 · winner-rate 0% · avg 777.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 1.0
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 394.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi l'estomac gargouille quand on a faim ?** — 1 vues (z=-6.75): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **-109.8 vues/jour^²** · attendu 30j: **99 vues** (bande 0.0–570.8/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **tout / seul / ventre / muscle / s'endort**
- `tout / seul / ventre / muscle / s'endort` — 3 vidéos · avg 1019.7 vues · max 1168
- `cœur / battre / son / nuit / s'emballe` — 4 vidéos · avg 572.8 vues · max 874
- `raison / change / dit / cerveau / vous` — 32 vidéos · avg 572.5 vues · max 1134
- `corps / s'endormant / après / lourd / mentir` — 8 vidéos · avg 484.8 vues · max 986
- `froid / peut / sembler / étrange / frissonne` — 7 vidéos · avg 416.3 vues · max 1241

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 44.0% / 65.6% · **72%** des vidéos perdent le spectateur avant la moitié

## 🪝 Expérience hooks — leader actuel: **pov_reveal** (avg 635.6 vues)
- `pov_reveal` (635.64) vs `question` (369.0) — p=0.2484 (ns)

## 🚀 Winner-cloning fastlane (7 sujets, TTL 96h)
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi des fourmillements apparaissent au moment où tu t'y attends le moins ? » ← cloné de **1055 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1054 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
