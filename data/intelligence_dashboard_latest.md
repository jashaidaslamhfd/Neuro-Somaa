# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-09-02T09:50:01.631410+00:00_ — n=67 vidéos réelles

## 📊 Data quality
- vues réelles: **67** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **2** · 🔴 figées (2 lectures sans hausse): **62**
  · ⚡ +7.2 vues/j — Pourquoi le corps gratte après la douche ?
  · ⚡ +2.0 vues/j — Pourquoi le hoquet commence brusquement ?
  · ⚡ +-2.1 vues/j — Pourquoi on entend son cœur battre la nuit ?

## 🧪 Truth Gate (scores internes vs réalité)
- ⛔ `hook_score` (hook quality): **INVERTED** (r=-0.22, n=67) — **consultatif seulement, jamais un gate**
- ✅ `seo_score` (SEO quality): **CALIBRATED** (r=+0.59, n=67) — peut guider des décisions
- ⛔ `predicted_retention` (retention): **INVERTED** (r=-0.25, n=67) — biais +0.26 (prédit 0.69 vs réel 0.43) — **consultatif seulement, jamais un gate**
- ✅ `predicted_ctr` (CTR): **CALIBRATED** (r=+0.59, n=67) — peut guider des décisions

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = 0.2836 ± 0.2328** (MAE ≈ 286.4 vues) — ✅ fiable
- facteurs dominants: `seo_score` (+), `phrase_words` (+), `predicted_ctr` (+), `dow_cos` (+), `is_question` (+)
- MLP: MAE ≈ 199.2 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1001, avg 407.0 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUI_SE_PASSE` n= 1 · winner-rate 0% · avg 1.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 1.0
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 3.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))

## 📈 Prévision 30 jours (Holt)
- tendance: **-89.0 vues/jour^²** · attendu 30j: **239 vues** (bande 0.0–492.8/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **seul / tout / ventre / muscle / pied**
- `seul / tout / ventre / muscle / pied` — 3 vidéos · avg 632.3 vues · max 1054
- `raison / change / dit / cerveau / vous` — 32 vidéos · avg 460.0 vues · max 1134
- `corps / s'endormant / après / lourd / mentir` — 8 vidéos · avg 453.0 vues · max 986
- `cœur / battre / son / nuit / sous` — 4 vidéos · avg 219.5 vues · max 874
- `sur / faim / comprendre / qu'il / faut` — 13 vidéos · avg 175.1 vues · max 1029

## ⏱️ Rétention
- P10/P50/P90 = 10.0% / 44.5% / 69.3% · **69%** des vidéos perdent le spectateur avant la moitié

## 🪝 Expérience hooks — leader actuel: **pov_reveal** (avg 638.5 vues)
- `pov_reveal` (638.45) vs `question` (369.2) — p=0.246 (ns)

## 🚀 Winner-cloning fastlane (5 sujets, TTL 96h)
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi des fourmillements apparaissent au moment où tu t'y attends le moins ? » ← cloné de **1055 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1054 vues**
- « Pourquoi la mâchoire craque quand tu es amoureux ? » ← cloné de **1029 vues**
- « Pourquoi un nœud au ventre apparaît au réveil ? » ← cloné de **1007 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
