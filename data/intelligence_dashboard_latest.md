# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-17T05:59:45.367636+00:00_ — n=65 vidéos réelles

## 📊 Data quality
- vues réelles: **65** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 📈 Croissance mesurée (vérité, pas impression)
- 🟢 en croissance: **9** · 🔴 figées (2 lectures sans hausse): **47**
  · ⚡ +136.4 vues/j — Pourquoi la mémoire invente des détails sans le vo
  · ⚡ +96.6 vues/j — Pourquoi les mains deviennent froides sans raison 
  · ⚡ +11.9 vues/j — Pourquoi le cerveau crée des souvenirs faux ?

## 🧪 Truth Gate (scores internes vs réalité)
- 🔴 `hook_score` (hook quality): **NOISE** (r=+0.02, n=65) — **consultatif seulement, jamais un gate**
- ⛔ `seo_score` (SEO quality): **INVERTED** (r=-0.16, n=65) — **consultatif seulement, jamais un gate**
- 🔴 `predicted_retention` (retention): **NOISE** (r=-0.04, n=65) — biais +0.29 (prédit 0.70 vs réel 0.40) — **consultatif seulement, jamais un gate**
- ⛔ `predicted_ctr` (CTR): **INVERTED** (r=-0.17, n=65) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = -0.6631 ± 0.7115** (MAE ≈ 377.0 vues) — ⚠️ bruit, conseils seulement
- facteurs dominants: `has_second_person` (-), `dow_sin` (+), `hour_sin` (-), `predicted_ctr` (-), `topic_bucket_2` (-)
- MLP: MAE ≈ 217.1 vues (advisory)

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.1673, avg 673.2 vues)
  🔬 `CE_QUE_VOTRE_CORPS` n= 3 · winner-rate 33% · avg 449.7
  🔬 `CE_QUIL_FAUT_COMPRENDRE` n= 2 · winner-rate 50% · avg 1071.0
  🔬 `CE_QUI_SE_PASSE` n= 2 · winner-rate 0% · avg 521.5
  🔬 `LA_SCIENCE  ` n= 2 · winner-rate 0% · avg 484.5
  🔬 `OTHER       ` n= 2 · winner-rate 0% · avg 877.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))
- 🔻 **Pourquoi la musique change l'humeur ?** — 10 vues (z=-10.1): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le cerveau crée des souvenirs faux ?** — 62 vues (z=-5.94): _queue metadata+thumbnail repair (hooks, CTR signals)_
- 🔻 **Pourquoi le stress brouille la mémoire ?** — 107 vues (z=-4.65): _queue metadata+thumbnail repair (hooks, CTR signals)_

## 📈 Prévision 30 jours (Holt)
- tendance: **-26.5 vues/jour^²** · attendu 30j: **33817 vues** (bande 612.7–1641.8/j)

## 🗂️ Clusters de sujets (k=6) — gagnant: **froid / derrière / temps / peau / science**
- `froid / derrière / temps / peau / science` — 8 vidéos · avg 874.6 vues · max 1456
- `sur / explique / science / par / faut` — 10 vidéos · avg 759.3 vues · max 1512
- `cœur / réveil / son / passe / avant` — 10 vidéos · avg 627.5 vues · max 928
- `change / lorsque / mémoire / stress / paupière` — 9 vidéos · avg 626.4 vues · max 1007
- `corps / vous / dit / raison / ventre` — 24 vidéos · avg 624.8 vues · max 1087

## ⏱️ Rétention
- P10/P50/P90 = 29.1% / 39.8% / 52.7% · **85%** des vidéos perdent le spectateur avant la moitié

## 🧪 Expérience durée: pas de différence significative encore (p=0.1614)
- `control_long` avg 680.33 vs `test_short` avg 911.78 (n=9/9)

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: {'pov_reveal': 7, 'shock_fact': 2, 'question': 2}); arms start accruing from the first run after 2026-08-12

## 🚀 Winner-cloning fastlane (5 sujets, TTL 96h)
- « Pourquoi le ventre se serre lors d'une peur au réveil ? » ← cloné de **1456 vues**
- « Pourquoi un aliment froid provoque un mal quand tu es stressé ? » ← cloné de **1241 vues**
- « Pourquoi le muscle qui tressaille tout seul au réveil ? » ← cloné de **1168 vues**
- « Pourquoi la mâchoire craque quand tu es amoureux ? » ← cloné de **1029 vues**
- « Pourquoi un nœud au ventre apparaît au réveil ? » ← cloné de **1007 vues**
_Le prochain run de génération pioche D'ABORD dans cette file._

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
