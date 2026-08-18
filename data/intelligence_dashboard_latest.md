# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-18T05:53:48.636861+00:00_ — n=67 vidéos réelles

## 📊 Data quality
- vues réelles: **67** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **9** · 🔴 figées (2 lectures sans hausse): **47**
  · ⚡ +136.4 vues/j — Pourquoi la mémoire invente des détails sans le vo
  · ⚡ +96.6 vues/j — Pourquoi les mains deviennent froides sans raison 
  · ⚡ +11.9 vues/j — Pourquoi le cerveau crée des souvenirs faux ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=+0.04, n=67) — **consultatif seulement, jamais un gate**
- ⛔ `seo_score` (SEO quality): **INVERTED** (r=-0.16, n=67) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.02, n=67) — biais +0.29 (prédit 0.70 vs réel 0.40) — **consultatif seulement, jamais un gate**
- ⛔ `predicted_ctr` (CTR): **INVERTED** (r=-0.17, n=67) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.4555 ± 0.6468** (MAE ≈ 323.3 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `has_second_person` (-), `predicted_ctr` (-), `dow_sin` (+), `hour_sin` (-), `topic_bucket_2` (-)
- MLP: MAE ≈ 219.6 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1613, avg 675.3 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.5
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 877.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi la musique change l'humeur ?** — 10 vues (z=-10.57): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le cerveau crée des souvenirs faux ?** — 62 vues (z=-6.21): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le stress brouille la mémoire ?** — 107 vues (z=-4.86): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **-27.6 vues/jour^²** · attendu 30j: **31913 vues** (bande 560.9–1566.7/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **ventre / seul / tout / serre / d'une**
- `ventre / seul / tout / serre / d'une` — 7 vidéos · avg 1052.4 vues · max 1456
- `cœur / réveil / son / avant / battre` — 7 vidéos · avg 678.6 vues · max 928
- `corps / vous / dit / raison / deviennent` — 30 vidéos · avg 642.1 vues · max 1512
- `semble / froid / frissonne / temps / soudain` — 8 vidéos · avg 615.0 vues · max 1241
- `change / lorsque / corps / visibles / flottants` — 10 vidéos · avg 573.2 vues · max 985

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 39.5% / 51.9% · **85%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.1614)
- `control_long` avg 680.33 vs `test_short` avg 911.78 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: {'pov_reveal': 8, 'shock_fact': 2, 'question': 3}); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (5 sujets, TTL 96h)
- « Pourquoi le ventre se serre lors d'une peur au réveil ? » ← cloné de **1456 vues**
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi la mâchoire craque quand tu es amoureux ? » ← cloné de **1029 vues**
- « Pourquoi un nœud au ventre apparaît au réveil ? » ← cloné de **1007 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
