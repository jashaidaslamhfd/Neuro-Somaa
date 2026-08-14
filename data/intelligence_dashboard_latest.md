# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-14T21:52:43.583994+00:00_ — n=59 vidéos réelles

## 📊 Data quality
- vues réelles: **59** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **11** · 🔴 figées (2 lectures sans hausse): **2**
  · ⚡ +98.5 vues/j — Pourquoi la respiration ralentit en dormant ?
  · ⚡ +53.3 vues/j — Pourquoi le stress brouille la mémoire ?
  · ⚡ +18.8 vues/j — Pourquoi un rêve disparaît au réveil ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=+0.02, n=59) — **consultatif seulement, jamais un gate**
- 🔴 `seo_score` (SEO quality): **NOISE** (r=-0.14, n=59) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.05, n=59) — biais +0.30 (prédit 0.70 vs réel 0.40) — **consultatif seulement, jamais un gate**
- ⛔ `predicted_ctr` (CTR): **INVERTED** (r=-0.15, n=59) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.3785 ± 0.676** (MAE ≈ 348.2 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `has_second_person` (-), `hour_sin` (-), `dow_sin` (+), `predicted_ctr` (-), `hour_cos` (+)
- MLP: MAE ≈ 176.0 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1881, avg 695.1 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 876.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi l'œil distingue plus de nuances de vert ?** — 33 vues (z=-7.56): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le stress brouille la mémoire ?** — 107 vues (z=-4.75): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure chaque jour ?** — 152 vues (z=-3.91): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi un vertige apparaît après s'être levé ?** — 165 vues (z=-3.71): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **+5.8 vues/jour^²** · attendu 30j: **56975 vues** (bande 1375.4–2422.9/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **ventre / faim / serre / lors / d'une**
- `ventre / faim / serre / lors / d'une` — 5 vidéos · avg 886.6 vues · max 1456
- `change / lorsque / mémoire / stress / paupière` — 6 vidéos · avg 747.7 vues · max 985
- `sur / explique / comprendre / science / qu'il` — 10 vidéos · avg 726.4 vues · max 1512
- `corps / raison / seul / tout / réveil` — 18 vidéos · avg 702.8 vues · max 1168
- `semble / temps / derrière / ralentit / science` — 10 vidéos · avg 618.5 vues · max 1241

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 38.8% / 49.8% · **90%** des vidéos perdent le spectateur avant la moitié

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: {'pov_reveal': 3, 'shock_fact': 2}); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (5 sujets, TTL 96h)
- « Pourquoi le ventre se serre lors d'une peur au réveil ? » ← cloné de **1456 vues**
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi la mâchoire craque quand tu es amoureux ? » ← cloné de **1060 vues**
- « Pourquoi un nœud au ventre apparaît au réveil ? » ← cloné de **1007 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
