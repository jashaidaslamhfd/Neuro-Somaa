# Neuro-Somaa — Organic Growth Loop: Final Status (2026-08-15)

## What was broken and what is now fixed

| # | Problem | Status |
|---|---------|--------|
| 1 | `demand_refresh.py` mined only **1 subject per run** (queue went stale → pipeline reverted to blind catalogue guesses) | **Fixed** — now mines **7 subjects / 16 live FR queries** per run |
| 2 | Demand queue never refilled after initial hand-mining | **Fixed** — auto-refreshes every 4 days inside the daily analytics sync and before every main pipeline run |
| 3 | Budget accounting bug: first seed consumed the whole 20-call budget | Fixed |
| 4 | Essay-style seeds (e.g. "Ce qu'il faut comprendre sur...") got 0 Google suggestions | Fixed via `_short_core()` — converts essay titles into natural 4–7 word search phrases |
| 5 | Over-strict junk filter rejected valid phenomenon demand ("sommeil paradoxal") | Fixed with `is_phenomenon` clause + min-3-words floor |
| 6 | Base test suite | **245/245 tests pass** |

## Diagnosis of the earlier manual pipeline failure

The manually dispatched run (`French Shorts Automation`, 21:13 UTC) failed at **upload time** with `invalid_scope` — this is the **YouTube refresh token's Google OAuth scopes**, not the video generation. It ran *before* today's fixes. Today's push (`b4111d0`) added the demand-refresh steps; the next scheduled run (19:30 Paris) will pick topics from the fresh demand queue.

## The growth loop now works end-to-end

1. **Daily 05:30 UTC** — analytics sync pulls real views/retention → updates `performance_state.json` → then refills `search_demand_queue_fr.json` from live YouTube France autocomplete (mined around proven 1000+ view winners + evergreen body-glitch catalogue).
2. **3×/day (12:30/19:30/21:00 Paris)** — main pipeline refreshes the queue first, then topic selection prefers **measured live search demand** over blind guesses.
3. **Winner Fastlane** — videos hitting 1000+ views automatically generate grammar-safe French clone topics (already fixed earlier today).

## Current live demand queue (mined 2026-08-14 21:32 UTC)

| Subject | Live autocomplete demand found |
|---------|-------------------------------|
| les genoux qui craquent en bougeant | les os qui craquent tout le temps, les genoux qui craquent |
| un aliment froid provoque un mal de tête | comment se débarrasser d'un mal de tête |
| le muscle qui tressaille tout seul | muscle qui tremble tout seul, muscle qui se contracte tout seul, pourquoi le muscle bouge tout seul |
| le cerveau est immature à 20 ans | pourquoi dit on que le cerveau est immature, les traumas et leurs conséquences sur le cerveau, comment fonctionne le cerveau d'un hypersensible |
| les yeux bougent pendant le sommeil paradoxal | sommeil paradoxal c'est quoi, les paralysies du sommeil |
| la voix tremble par nervosité | voix qui tremble |
| ce qui change lorsque le cœur s'emballe sous le stress | le coeur qui s'emballe |

## One thing you still must do (I cannot do it)

The `invalid_scope` upload failure means the YouTube refresh token is missing at least one scope. Regenerate it with the full set:
`https://accounts.google.com/o/oauth2/v2/auth?client_id=...&response_type=code&scope=https://www.googleapis.com/auth/youtube.upload%20https://www.googleapis.com/auth/youtube%20https://www.googleapis.com/auth/youtube.readonly`

After regenerating, update the repo secret `REFRESH_TOKEN`. This is the **only remaining blocker** for uploads. Optionally, add `FB_ACCESS_TOKEN`, `FB_PAGE_ID`, `INSTAGRAM_USER_ID` secrets to activate FB/IG Reels cross-posting (already coded, secret-gated).
