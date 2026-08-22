# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-22T05:52:27.940942+00:00_ — n=71 vidéos réelles

## 📊 Data quality
- vues réelles: **71** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **6** · 🔴 figées (2 lectures sans hausse): **57**
  · ⚡ +10.0 vues/j — Pourquoi des fourmillements apparaissent sans rais
  · ⚡ +4.0 vues/j — Pourquoi une lumière vive fait éternuer ?
  · ⚡ +2.0 vues/j — Pourquoi le hoquet commence brusquement ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=+0.07, n=71) — **consultatif seulement, jamais un gate**
- 🔴 `seo_score` (SEO quality): **NOISE** (r=+0.10, n=71) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=+0.01, n=71) — biais +0.28 (prédit 0.69 vs réel 0.42) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_ctr` (CTR): **NOISE** (r=+0.06, n=71) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.2091 ± 0.2918** (MAE ≈ 399.2 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `is_question` (+), `predicted_ctr` (-), `dow_cos` (-), `caps_ratio` (-), `has_second_person` (-)
- MLP: MAE ≈ 234.2 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1833, avg 638.6 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 409.3
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 0% · avg 9.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 422.5
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 482.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 877.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi la musique change l'humeur ?** — 36 vues (z=-5.32): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure ?** — 60 vues (z=-4.42): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le cerveau crée des souvenirs faux ?** — 83 vues (z=-3.85): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **-102.5 vues/jour^²** · attendu 30j: **1290 vues** (bande 0.0–610.6/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **seul / tout / réveil / sembler / peut**
- `seul / tout / réveil / sembler / peut` — 7 vidéos · avg 852.3 vues · max 1456
- `raison / deviennent / yeux / oreilles / mains` — 7 vidéos · avg 758.9 vues · max 841
- `froid / frissonne / par / soudain / peau` — 4 vidéos · avg 678.8 vues · max 1241
- `corps / vous / dit / après / refuse` — 20 vidéos · avg 560.8 vues · max 1134
- `cerveau / cœur / son / battre / danger` — 10 vidéos · avg 508.7 vues · max 874

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 40.5% / 52.9% · **80%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.16)
- `control_long` avg 680.33 vs `test_short` avg 912.33 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: {'pov_reveal': 11, 'shock_fact': 3, 'question': 3}); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (8 sujets, TTL 96h)
- « Pourquoi le ventre se serre lors d'une peur au réveil ? » ← cloné de **1456 vues**
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1054 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
