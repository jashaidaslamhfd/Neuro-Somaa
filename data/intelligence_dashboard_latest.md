# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-16T05:52:41.912357+00:00_ — n=62 vidéos réelles

## 📊 Data quality
- vues réelles: **62** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **9** · 🔴 figées (2 lectures sans hausse): **42**
  · ⚡ +298.2 vues/j — Pourquoi les mains deviennent froides sans raison 
  · ⚡ +19.8 vues/j — Pourquoi on se réveille à 3h du matin sans raison 
  · ⚡ +11.0 vues/j — Pourquoi un rêve disparaît au réveil ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=-0.04, n=62) — **consultatif seulement, jamais un gate**
- 🔴 `seo_score` (SEO quality): **NOISE** (r=-0.15, n=62) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.11, n=62) — biais +0.30 (prédit 0.70 vs réel 0.40) — **consultatif seulement, jamais un gate**
- ⛔ `predicted_ctr` (CTR): **INVERTED** (r=-0.16, n=62) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.6778 ± 0.8513** (MAE ≈ 374.7 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `has_second_person` (-), `hour_sin` (-), `topic_bucket_2` (-), `predicted_ctr` (-), `dow_sin` (+)
- MLP: MAE ≈ 184.6 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1773, avg 686.7 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 876.5

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi le cerveau crée des souvenirs faux ?** — 50 vues (z=-6.38): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le stress brouille la mémoire ?** — 107 vues (z=-4.6): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure chaque jour ?** — 152 vues (z=-3.77): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **-4.2 vues/jour^²** · attendu 30j: **50380 vues** (bande 1161.7–2197.0/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **froid / sembler / peut / étrange / frissonne**
- `froid / sembler / peut / étrange / frissonne` — 7 vidéos · avg 795.4 vues · max 1456
- `cœur / son / battre / nuit / vite` — 5 vidéos · avg 733.4 vues · max 878
- `raison / deviennent / science / lorsque / change` — 26 vidéos · avg 705.0 vues · max 1205
- `cerveau / comprendre / qu'il / faut / immature` — 7 vidéos · avg 694.4 vues · max 1512
- `corps / refuse / s'endormant / flottants / visibles` — 8 vidéos · avg 614.2 vues · max 1031

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 38.9% / 52.9% · **89%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.1636)
- `control_long` avg 680.22 vs `test_short` avg 910.67 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: {'pov_reveal': 4, 'shock_fact': 2, 'question': 2}); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (5 sujets, TTL 96h)
- « Pourquoi le ventre se serre lors d'une peur au réveil ? » ← cloné de **1456 vues**
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi la mâchoire craque quand tu es amoureux ? » ← cloné de **1029 vues**
- « Pourquoi un nœud au ventre apparaît au réveil ? » ← cloné de **1007 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
