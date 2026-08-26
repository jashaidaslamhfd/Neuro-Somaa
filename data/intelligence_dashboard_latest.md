# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-26T06:00:32.338873+00:00_ — n=67 vidéos réelles

## 📊 Data quality
- vues réelles: **67** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **2** · 🔴 figées (2 lectures sans hausse): **61**
  · ⚡ +33.0 vues/j — Pourquoi le hoquet ne s'arrête pas ?
  · ⚡ +1.0 vues/j — Pourquoi le cerveau remarque entendre son cœur bat
  · ⚡ +-1.0 vues/j — Ce qu'il faut comprendre sur les genoux qui craque

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=-0.05, n=67) — **consultatif seulement, jamais un gate**
- 🟡 `seo_score` (SEO quality): **WEAK** (r=+0.19, n=67) — peut guider des décisions
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.11, n=67) — biais +0.24 (prédit 0.69 vs réel 0.45) — **consultatif seulement, jamais un gate**
- 🟡 `predicted_ctr` (CTR): **WEAK** (r=+0.18, n=67) — peut guider des décisions

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = 0.428 ± 0.1709** (MAE ≈ 419.5 vues) — ✅ fiable
- facteurs dominants: `is_question` (+), `hour_sin` (-), `has_second_person` (-), `hour_cos` (+), `phrase_words` (-)
- MLP: MAE ≈ 259.7 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1668, avg 605.0 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 1 · winner-rate 0% · avg 2.0
  🔬 `CE_QUI_SE_PASSE` n= 1 · winner-rate 0% · avg 777.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 1.0
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 877.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi l'estomac gargouille quand on a faim ?** — 1 vues (z=-10.43): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la musique change l'humeur ?** — 36 vues (z=-5.26): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure ?** — 60 vues (z=-4.38): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le cerveau crée des souvenirs faux ?** — 83 vues (z=-3.81): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **-113.6 vues/jour^²** · attendu 30j: **86 vues** (bande 0.0–565.1/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **tout / seul / ventre / muscle / s'endort**
- `tout / seul / ventre / muscle / s'endort` — 3 vidéos · avg 1019.7 vues · max 1168
- `corps / s'endormant / après / lourd / mentir` — 8 vidéos · avg 601.9 vues · max 1031
- `raison / change / dit / cerveau / vous` — 32 vidéos · avg 601.8 vues · max 1134
- `cœur / battre / son / nuit / s'emballe` — 4 vidéos · avg 572.8 vues · max 874
- `froid / peut / sembler / étrange / frissonne` — 7 vidéos · avg 416.3 vues · max 1241

## ⏱️ Rétention
- P10/P50/P90 = 29.3% / 43.3% / 65.6% · **73%** des vidéos perdent le spectateur avant la moitié

## 🪝 Expérience hooks — leader actuel: **pov_reveal** (avg 635.7 vues)
- `pov_reveal` (635.73) vs `question` (368.4) — p=0.248 (ns)

## 🚀 Winner-cloning fastlane (7 sujets, TTL 96h)
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi des fourmillements apparaissent au moment où tu t'y attends le moins ? » ← cloné de **1055 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1054 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
