# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-15T07:45:48.601541+00:00_ — n=59 vidéos réelles

## 📊 Data quality
- vues réelles: **59** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **13** · 🔴 figées (2 lectures sans hausse): **41**
  · ⚡ +98.5 vues/j — Pourquoi la respiration ralentit en dormant ?
  · ⚡ +53.3 vues/j — Pourquoi le stress brouille la mémoire ?
  · ⚡ +18.8 vues/j — Pourquoi un rêve disparaît au réveil ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=+0.03, n=59) — **consultatif seulement, jamais un gate**
- 🔴 `seo_score` (SEO quality): **NOISE** (r=-0.15, n=59) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.04, n=59) — biais +0.30 (prédit 0.70 vs réel 0.40) — **consultatif seulement, jamais un gate**
- ⛔ `predicted_ctr` (CTR): **INVERTED** (r=-0.16, n=59) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.3824 ± 0.6845** (MAE ≈ 346.5 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `has_second_person` (-), `hour_sin` (-), `dow_sin` (+), `predicted_ctr` (-), `hour_cos` (+)
- MLP: MAE ≈ 174.8 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1881, avg 692.1 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.0
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 876.5

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi l'œil distingue plus de nuances de vert ?** — 34 vues (z=-7.34): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le stress brouille la mémoire ?** — 107 vues (z=-4.65): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure chaque jour ?** — 152 vues (z=-3.82): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi un vertige apparaît après s'être levé ?** — 166 vues (z=-3.61): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **+6.6 vues/jour^²** · attendu 30j: **57346 vues** (bande 1394.7–2428.3/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **ventre / faim / serre / d'une / lors**
- `ventre / faim / serre / d'une / lors` — 5 vidéos · avg 886.6 vues · max 1456
- `change / lorsque / mémoire / stress / paupière` — 6 vidéos · avg 744.8 vues · max 985
- `sur / explique / comprendre / science / faut` — 10 vidéos · avg 722.8 vues · max 1512
- `corps / raison / seul / tout / réveil` — 18 vidéos · avg 699.4 vues · max 1168
- `semble / temps / derrière / ralentit / science` — 10 vidéos · avg 616.1 vues · max 1241

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 38.8% / 49.8% · **90%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.1636)
- `control_long` avg 680.22 vs `test_short` avg 910.67 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: {'pov_reveal': 3, 'shock_fact': 2}); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (5 sujets, TTL 96h)
- « Pourquoi le ventre se serre lors d'une peur au réveil ? » ← cloné de **1456 vues**
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi la mâchoire craque quand tu es amoureux ? » ← cloné de **1029 vues**
- « Pourquoi un nœud au ventre apparaît au réveil ? » ← cloné de **1007 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
