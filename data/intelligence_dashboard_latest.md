# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-29T11:46:48.924643+00:00_ — n=67 vidéos réelles

## 📊 Data quality
- vues réelles: **67** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **1** · 🔴 figées (2 lectures sans hausse): **64**
  · ⚡ +1.3 vues/j — Pourquoi le hoquet ne s'arrête pas ?
  · ⚡ +-2.6 vues/j — Comprendre pourquoi le cerveau réclame du sommeil 
  · ⚡ +-7.9 vues/j — Pourquoi les corps flottants visibles dans la lumi

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=-0.06, n=67) — **consultatif seulement, jamais un gate**
- ✅ `seo_score` (SEO quality): **CALIBRATED** (r=+0.62, n=67) — peut guider des décisions
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.11, n=67) — biais +0.23 (prédit 0.69 vs réel 0.46) — **consultatif seulement, jamais un gate**
- ✅ `predicted_ctr` (CTR): **CALIBRATED** (r=+0.62, n=67) — peut guider des décisions

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = 0.2528 ± 0.6374** (MAE ≈ 328.4 vues) — ✅ fiable
- facteurs dominants: `is_question` (+), `seo_score` (+), `predicted_ctr` (+), `title_chars` (-), `phrase_words` (+)
- MLP: MAE ≈ 233.7 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.117, avg 519.7 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUI_SE_PASSE` n= 1 · winner-rate 0% · avg 777.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 1.0
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 3.5

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))

## 📈 Prévision 30 jours (Holt)
- tendance: **-104.2 vues/jour^²** · attendu 30j: **128 vues** (bande 0.0–564.3/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **seul / tout / ventre / muscle / s'endort**
- `seul / tout / ventre / muscle / s'endort` — 3 vidéos · avg 632.7 vues · max 1054
- `cœur / battre / son / nuit / sous` — 4 vidéos · avg 572.8 vues · max 874
- `raison / change / dit / cerveau / vous` — 32 vidéos · avg 547.7 vues · max 1134
- `corps / s'endormant / après / lourd / mentir` — 8 vidéos · avg 473.6 vues · max 986
- `froid / sembler / peut / étrange / frissonne` — 7 vidéos · avg 350.7 vues · max 1241

## ⏱️ Rétention
- P10/P50/P90 = 28.6% / 44.6% / 66.3% · **70%** des vidéos perdent le spectateur avant la moitié

## 🪝 Expérience hooks — leader actuel: **pov_reveal** (avg 635.6 vues)
- `pov_reveal` (635.64) vs `question` (369.2) — p=0.2488 (ns)

## 🚀 Winner-cloning fastlane (6 sujets, TTL 96h)
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi des fourmillements apparaissent au moment où tu t'y attends le moins ? » ← cloné de **1055 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1054 vues**
- « Pourquoi la mâchoire craque quand tu es amoureux ? » ← cloné de **1029 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
