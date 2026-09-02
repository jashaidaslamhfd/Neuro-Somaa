# 🔍 TRUTH AUDIT — Neuro-Somaa (2026-08-12)

**Doctrine:** Koi bhi function, file ya config "blind" nahi ho sakti. Har
decision ya to (a) ek verifiable FACT check karta hai (length, grammar,
duplication, silence, pacing), ya (b) MEASURED YouTube outcome data use karta
hai, ya (c) khulaan "advisory / BLIND-PICK" keh kar khud ko declare karta hai.
Koi chhupi hui vibe-score decision nahi.

## Per-unit verdict

| Unit | File | Verdict | Evidence |
|---|---|---|---|
| Script model | `src/script_generator.py` | ✅ MEASURED | gpt-oss-120b live in run 31591671661; chain fallback real |
| Topic pick | `src/trend_fetcher.py` | ✅ MEASURED | `_measured_topic_boost` → similar-video retention ≥ median+3 |
| Search demand | `data/search_demand_queue_fr.json` | ✅ MEASURED | real YouTube FR autocomplete queries |
| Titles (gen) | `src/main.py` | ✅ MEASURED | swap only if CTR-heuristic PROVEN or bandit confident |
| Titles (batch) | `scripts/fr_batch_optimize.py` | ✅ MEASURED | POURQUOI bandit winner (n=37, confident) |
| Tags | `scripts/fr_batch_optimize.py` | ✅ MEASURED | exact autocomplete queries first |
| Hook score | `src/shorts_enhancer.py` | ⚠️ ADVISORY | r=-0.08 NOISE on 50 vids — gates disabled until calibrated |
| CTR predict | `src/seo_analytics.py` | ⚠️ ADVISORY | r=-0.13 NOISE + CTR unservable on Shorts feed |
| Retention predict | `src/seo_analytics.py` | ⚠️ ADVISORY | mean 0.70 vs real 0.39 (2x) — gate disabled |
| SEO score | `src/seo_generator.py` | ⚠️ ADVISORY | r=-0.16 INVERTED — display only |
| Scheduler | `src/scheduler.py` | ✅ MEASURED | dynamic slots from upload_slot_intel_fr.json (confident) |
| Voice | `src/voice_generator.py` | ✅ FACT | hard gates: silence/mixed-engine/too-short; edge-tts FR |
| Visuals | `src/image_generator.py` | ✅ FACT | Pexels-video-first, perceptual-hash dedup ledger |
| Pacing/durations | `src/shorts_enhancer.py` | ✅ FACT | caption pacing + 4-9s cliff window checks |
| Legacy template pickers | `src/niche_strategy.py` | 🔶 DECLARED BLIND | get_random_hook/cta/etc log BLIND-PICK if ever called |
| Workflows | `.github/workflows/*.yml` | ✅ GUARDED | test_no_dead_env_vars_in_main_workflow (CI red on drift) |

## Standing guards (CI turns red if truth regresses)

1. `tests/test_truth_gate.py` — scores must prove predictive validity; NOISE
   scores locked to decision_usable=false on real history.
2. `tests/test_no_fake_decisions.py` — title swap / render vetoes / attempt
   ranking must route through `_score_decision_usable`.
3. `tests/test_measured_truth.py` — topic boost + growth/stall tracking.
4. `tests/test_runtime_config.py::test_no_dead_env_vars_in_main_workflow` —
   every workflow env var must be code-referenced or toolchain.
5. `tests/test_groq_models.py` — retired-model and fallback-chain guards.
