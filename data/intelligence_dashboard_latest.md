# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-22T19:23:42.533520+00:00_ — n=72 vidéos réelles

## 📊 Data quality
- vues réelles: **72** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **7** · 🔴 figées (2 lectures sans hausse): **57**
  · ⚡ +6.4 vues/j — Pourquoi le cerveau atténue la douleur en danger ?
  · ⚡ +1.3 vues/j — Pourquoi on pleure quand on bâille ?
  · ⚡ +0.6 vues/j — Pourquoi on sent une vibration de téléphone imagin

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=+0.09, n=72) — **consultatif seulement, jamais un gate**
- 🔴 `seo_score` (SEO quality): **NOISE** (r=+0.12, n=72) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=+0.03, n=72) — biais +0.27 (prédit 0.69 vs réel 0.42) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_ctr` (CTR): **NOISE** (r=+0.08, n=72) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.1688 ± 0.3688** (MAE ≈ 428.9 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `is_question` (+), `predicted_ctr` (-), `dow_cos` (-), `seo_score` (+), `has_second_person` (-)
- MLP: MAE ≈ 270.7 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1802, avg 624.9 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 0% · avg 330.3
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 0% · avg 4.5
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 390.5
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 248.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 877.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi l'estomac gargouille quand on a faim ?** — 1 vues (z=-10.28): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la musique change l'humeur ?** — 36 vues (z=-5.18): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi la faim revient à la même heure ?** — 61 vues (z=-4.28): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le cerveau crée des souvenirs faux ?** — 83 vues (z=-3.75): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **-120.1 vues/jour^²** · attendu 30j: **203 vues** (bande 0.0–564.2/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **raison / mains / paupière / deviennent / tressaille**
- `raison / mains / paupière / deviennent / tressaille` — 4 vidéos · avg 859.0 vues · max 1050
- `réveil / peut / sembler / tout / seul` — 7 vidéos · avg 768.0 vues · max 1456
- `science / explique / sur / yeux / deviennent` — 12 vidéos · avg 705.7 vues · max 1209
- `froid / peau / soudain / frissonne / semble` — 8 vidéos · avg 570.9 vues · max 1241
- `corps / dit / change / vous / comprendre` — 36 vidéos · avg 469.6 vues · max 1134

## ⏱️ Rétention
- P10/P50/P90 = 27.6% / 41.1% / 59.9% · **76%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.16)
- `control_long` avg 680.44 vs `test_short` avg 912.56 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: {'pov_reveal': 11, 'shock_fact': 3, 'question': 4}); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (8 sujets, TTL 96h)
- « Pourquoi le ventre se serre lors d'une peur au réveil ? » ← cloné de **1456 vues**
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi les souvenirs gênants reviennent plus souvent en hiver ? » ← cloné de **1134 vues**
- « Pourquoi un pied s'endort tout seul plus chez certaines personnes ? » ← cloné de **1054 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
