# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-24T06:01:46.764303+00:00_ — n=73 vidéos réelles

## 📊 Data quality
- vues réelles: **73** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **4** · 🔴 figées (2 lectures sans hausse): **68**
  · ⚡ +9.8 vues/j — Pourquoi la main s'engourdit quand on dort dessus 
  · ⚡ +4.9 vues/j — Pourquoi des fourmillements apparaissent sans rais
  · ⚡ +1.0 vues/j — Pourquoi les oreilles sifflent dans le silence ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=+0.07, n=73) — **consultatif seulement, jamais un gate**
- 🟡 `seo_score` (SEO quality): **WEAK** (r=+0.24, n=73) — peut guider des décisions
- 🔴 `predicted_retention` (retention): **NOISE** (r=+0.01, n=73) — biais +0.27 (prédit 0.69 vs réel 0.42) — **consultatif seulement, jamais un gate**
- 🟡 `predicted_ctr` (CTR): **WEAK** (r=+0.20, n=73) — peut guider des décisions

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = 0.2378 ± 0.2873** (MAE ≈ 401.2 vues) — ✅ fiable
- facteurs dominants: `is_question` (+), `predicted_ctr` (-), `has_second_person` (-), `seo_score` (+), `caps_ratio` (-)
- MLP: MAE ≈ 231.5 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1613, avg 588.6 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 0% · avg 192.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 0% · avg 4.5
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 390.5
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 109.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 877.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi l'estomac gargouille quand on a faim ?** — 1 vues (z=-7.72): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la musique change l'humeur ?** — 36 vues (z=-3.81): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **-117.6 vues/jour^²** · attendu 30j: **51 vues** (bande 0.0–540.3/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **yeux / deviennent / rit / pleurent**
- `yeux / deviennent / rit / pleurent` — 2 vidéos · avg 680.5 vues · max 710
- `change / cerveau / raison / lorsque / peut` — 28 vidéos · avg 563.5 vues · max 1054
- `semble / temps / vite / par / soudain` — 7 vidéos · avg 537.9 vues · max 1241
- `corps / dit / vous / après / refuse` — 20 vidéos · avg 523.6 vues · max 1134
- `sur / science / explique / faut / qu'il` — 14 vidéos · avg 474.9 vues · max 1209

## ⏱️ Rétention
- P10/P50/P90 = 27.6% / 41.2% / 59.2% · **77%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.16)
- `control_long` avg 680.56 vs `test_short` avg 912.56 (n=9/9)

## 🪝 Expérience hooks — leader actuel: **pov_reveal** (avg 635.2 vues)
- `pov_reveal` (635.18) vs `question` (354.4) — p=0.2284 (ns)

## 🚀 Winner-cloning fastlane (7 sujets, TTL 96h)
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi des fourmillements apparaissent au moment où tu t'y attends le moins ? » ← cloné de **1055 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1054 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
