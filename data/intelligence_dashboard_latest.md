# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-19T05:55:25.023970+00:00_ — n=68 vidéos réelles

## 📊 Data quality
- vues réelles: **68** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **12** · 🔴 figées (2 lectures sans hausse): **49**
  · ⚡ +323.8 vues/j — Pourquoi des fourmillements apparaissent sans rais
  · ⚡ +233.9 vues/j — Pourquoi le corps résiste à la perte de poids ?
  · ⚡ +163.8 vues/j — Pourquoi les souvenirs gênants reviennent ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=+0.02, n=68) — **consultatif seulement, jamais un gate**
- 🔴 `seo_score` (SEO quality): **NOISE** (r=-0.06, n=68) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.04, n=68) — biais +0.29 (prédit 0.70 vs réel 0.41) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_ctr` (CTR): **NOISE** (r=-0.07, n=68) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = 0.0195 ± 0.4786** (MAE ≈ 352.5 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `caps_ratio` (-), `has_second_person` (-), `dow_sin` (+), `hour_sin` (-), `topic_bucket_2` (-)
- MLP: MAE ≈ 222.4 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1929, avg 693.5 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.5
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 877.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi la musique change l'humeur ?** — 36 vues (z=-7.13): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le cerveau crée des souvenirs faux ?** — 83 vues (z=-5.2): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le stress brouille la mémoire ?** — 105 vues (z=-4.66): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **-29.8 vues/jour^²** · attendu 30j: **28710 vues** (bande 381.9–1534.6/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **ventre / faim / serre / lors / d'une**
- `ventre / faim / serre / lors / d'une` — 6 vidéos · avg 878.2 vues · max 1456
- `raison / deviennent / science / froid / semble` — 24 vidéos · avg 770.7 vues · max 1241
- `cerveau / comprendre / souvenirs / immature / qu'il` — 8 vidéos · avg 727.0 vues · max 1512
- `son / cœur / avant / battre / nuit` — 5 vidéos · avg 585.2 vues · max 874
- `change / mémoire / stress / lorsque / sifflent` — 8 vidéos · avg 536.9 vues · max 985

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 40.5% / 52.1% · **82%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.16)
- `control_long` avg 680.33 vs `test_short` avg 912.33 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: {'pov_reveal': 9, 'shock_fact': 2, 'question': 3}); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (8 sujets, TTL 96h)
- « Pourquoi le ventre se serre lors d'une peur au réveil ? » ← cloné de **1456 vues**
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1052 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
