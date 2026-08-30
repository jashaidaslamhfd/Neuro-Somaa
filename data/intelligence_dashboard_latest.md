# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-30T10:36:36.812783+00:00_ — n=67 vidéos réelles

## 📊 Data quality
- vues réelles: **67** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **3** · 🔴 figées (2 lectures sans hausse): **63**
  · ⚡ +6.3 vues/j — Pourquoi le corps gratte après la douche ?
  · ⚡ +3.2 vues/j — Pourquoi la main s'engourdit quand on dort dessus 
  · ⚡ +1.1 vues/j — Pourquoi le sursaut du corps en s'endormant ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=-0.07, n=67) — **consultatif seulement, jamais un gate**
- ✅ `seo_score` (SEO quality): **CALIBRATED** (r=+0.66, n=67) — peut guider des décisions
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.12, n=67) — biais +0.23 (prédit 0.69 vs réel 0.47) — **consultatif seulement, jamais un gate**
- ✅ `predicted_ctr` (CTR): **CALIBRATED** (r=+0.66, n=67) — peut guider des décisions

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = 0.3381 ± 0.5248** (MAE ≈ 303.7 vues) — ✅ fiable
- facteurs dominants: `seo_score` (+), `is_question` (+), `predicted_ctr` (+), `dow_sin` (-), `phrase_words` (+)
- MLP: MAE ≈ 212.0 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.117, avg 503.0 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUI_SE_PASSE` n= 1 · winner-rate 0% · avg 41.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 1.0
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 3.5

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))

## 📈 Prévision 30 jours (Holt)
- tendance: **-101.2 vues/jour^²** · attendu 30j: **151 vues** (bande 0.0–520.4/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **seul / tout / ventre / muscle / pied**
- `seul / tout / ventre / muscle / pied` — 3 vidéos · avg 631.0 vues · max 1054
- `raison / change / dit / cerveau / vous` — 32 vidéos · avg 547.7 vues · max 1134
- `corps / s'endormant / après / lourd / refuse` — 8 vidéos · avg 474.5 vues · max 986
- `cœur / battre / son / nuit / s'emballe` — 4 vidéos · avg 388.8 vues · max 874
- `sur / faim / comprendre / qu'il / faut` — 13 vidéos · avg 229.7 vues · max 1029

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 44.6% / 69.3% · **67%** des vidéos perdent le spectateur avant la moitié

## 🪝 Expérience hooks — leader actuel: **pov_reveal** (avg 636.5 vues)
- `pov_reveal` (636.45) vs `question` (369.2) — p=0.2478 (ns)

## 🚀 Winner-cloning fastlane (6 sujets, TTL 96h)
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi des fourmillements apparaissent au moment où tu t'y attends le moins ? » ← cloné de **1055 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1054 vues**
- « Pourquoi la mâchoire craque quand tu es amoureux ? » ← cloné de **1029 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
