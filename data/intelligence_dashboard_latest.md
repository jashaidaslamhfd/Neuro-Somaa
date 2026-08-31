# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-31T11:45:33.837841+00:00_ — n=67 vidéos réelles

## 📊 Data quality
- vues réelles: **67** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **3** · 🔴 figées (2 lectures sans hausse): **62**
  · ⚡ +4.8 vues/j — Pourquoi le corps gratte après la douche ?
  · ⚡ +1.0 vues/j — Corps lourd
  · ⚡ +1.0 vues/j — Pourquoi l'apparition soudaine de la chair de poul

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=-0.08, n=67) — **consultatif seulement, jamais un gate**
- ✅ `seo_score` (SEO quality): **CALIBRATED** (r=+0.63, n=67) — peut guider des décisions
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.13, n=67) — biais +0.22 (prédit 0.69 vs réel 0.47) — **consultatif seulement, jamais un gate**
- ✅ `predicted_ctr` (CTR): **CALIBRATED** (r=+0.62, n=67) — peut guider des décisions

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = 0.3628 ± 0.3872** (MAE ≈ 290.0 vues) — ✅ fiable
- facteurs dominants: `seo_score` (+), `is_question` (+), `predicted_ctr` (+), `dow_sin` (-), `dow_cos` (+)
- MLP: MAE ≈ 199.6 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1001, avg 459.8 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUI_SE_PASSE` n= 1 · winner-rate 0% · avg 11.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 1.0
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 3.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))

## 📈 Prévision 30 jours (Holt)
- tendance: **-96.2 vues/jour^²** · attendu 30j: **187 vues** (bande 0.0–491.3/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **seul / tout / ventre / muscle / s'endort**
- `seul / tout / ventre / muscle / s'endort` — 3 vidéos · avg 631.0 vues · max 1054
- `raison / change / dit / cerveau / vous` — 32 vidéos · avg 547.7 vues · max 1134
- `corps / s'endormant / après / lourd / mentir` — 8 vidéos · avg 475.1 vues · max 986
- `cœur / battre / son / nuit / s'emballe` — 4 vidéos · avg 222.5 vues · max 874
- `sur / faim / comprendre / qu'il / faut` — 13 vidéos · avg 181.2 vues · max 1029

## ⏱️ Rétention
- P10/P50/P90 = 27.6% / 44.6% / 70.6% · **66%** des vidéos perdent le spectateur avant la moitié

## 🪝 Expérience hooks — leader actuel: **pov_reveal** (avg 636.9 vues)
- `pov_reveal` (636.91) vs `question` (369.2) — p=0.2476 (ns)

## 🚀 Winner-cloning fastlane (5 sujets, TTL 96h)
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi des fourmillements apparaissent au moment où tu t'y attends le moins ? » ← cloné de **1055 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1054 vues**
- « Pourquoi la mâchoire craque quand tu es amoureux ? » ← cloné de **1029 vues**
- « Pourquoi un nœud au ventre apparaît au réveil ? » ← cloné de **1007 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
