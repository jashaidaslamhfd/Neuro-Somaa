# demand_refresh.py — final diagnosis (2026-08-15)

Fixed. Queue went from 1 under-mined subject to 7 subjects / 16 live FR
autocomplete queries in one run.

## Root causes (all in one file)
1. **Long essay-style seeds → 0 Google suggestions.** Autocomplete only
   returns results for natural 4–8 word search phrases. Fixed by
   `_short_core()`: strips essay/question framing and picks the densest
   <=7-word phenomenon span.
2. **Budget accounting bug.** One seed consumed the ENTIRE 20-call budget
   (the accounting line added `MAX_API_CALLS - used`, not `used`), so only
   the FIRST seed ever got mined. Fixed to count actual calls.
3. **Stem collisions.** `pourquoi pourquoi ...` stems returned nothing;
   skipped when the seed already starts with a question word.
4. **Over-strict junk filter.** Single-phenomenon suggestions like
   'sommeil paradoxal' are pure demand, not noise — now accepted via an
   `is_phenomenon` clause. Two-word junk ('l'apparition') dropped by a new
   min-3-words rule.
5. **Budget too small.** 20 calls for 11 subjects × 4 stems was never
   enough; raised to 40 (still ~15s of free HTTP calls).

## Wiring
- `analytics.yml` (daily 05:30 UTC): new "Refresh live French search-demand
  queue" step after the analytics sync (continue-on-error, never blocks).
- `main.yml` (3×/day): same step before topic selection so main.py picks
  from a fresh demand queue every run.
