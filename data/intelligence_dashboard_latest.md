# 🧠 Neuro-Somaa — Intelligence Dashboard
_2026-08-19T11:25:01.143897+00:00_ — n=25 vidéos réelles

## 📊 Data quality
- vues réelles: **25** · couverture CTR: **0%** · rétention: **100%**
- ⚠️ 0 coverage → YouTube Analytics scope/ metric must be fixed (see 2026-08-11 audit fix; token needs yt-analytics.readonly)

## 🧪 Truth Gate (scores internes vs réalité)
- ⚪ `hook_score` (hook quality): **INSUFFICIENT_DATA** (r=n/a, n=25) — **consultatif seulement, jamais un gate**
- ⚪ `seo_score` (SEO quality): **INSUFFICIENT_DATA** (r=n/a, n=25) — **consultatif seulement, jamais un gate**
- ⚪ `predicted_retention` (retention): **INSUFFICIENT_DATA** (r=n/a, n=25) — biais +0.00 (prédit 0.40 vs réel 0.40) — **consultatif seulement, jamais un gate**
- ⚪ `predicted_ctr` (CTR): **INSUFFICIENT_DATA** (r=n/a, n=25) — **consultatif seulement, jamais un gate**

## 🤖 Modèles (ridge + MLP, validation croisée)
- ridge log-vues: **R²_cv = 0.3562 ± 0.3286** (MAE ≈ 171.2 vues) — ✅ fiable
- facteurs dominants: `title_chars` (+), `topic_bucket_2` (+), `dow_cos` (-), `topic_bucket_1` (-), `topic_bucket_3` (-)
- MLP: n<40 — deep model withheld to avoid memorization

## 🎰 Bandit de titres (Thompson sampling)
- ✅ pattern recommandé: **POURQUOI** (winner-rate 0.4795, avg 980.0 vues)
  ✅ `POURQUOI    ` n=25 · winner-rate 48% · avg 980.0

## 🚨 Anomalies (modified z-score (median/MAD, Iglewicz-Hoaglin >3.5))

## 📈 Prévision 30 jours (Holt)
- tendance: **+40.0 vues/jour^²** · attendu 30j: **62400 vues** (bande 2080.0–2080.0/j)

## 🗂️ Clusters de sujets (k=3) — gagnant: **surprend / sujet**
- `surprend / sujet` — 25 vidéos · avg 980.0 vues · max 1460

## ⏱️ Rétention
- P10/P50/P90 = 40.0% / 40.0% / 40.0% · **100%** des vidéos perdent le spectateur avant la moitié

## 🪝 Expérience hooks — hook-arm experiment needs ≥5 real-view videos per arm (have: none yet); arms start accruing from the first run after 2026-08-12

_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._
