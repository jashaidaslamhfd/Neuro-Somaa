# Weekly Francophone Market Experiment

## Purpose

The Neuro-Somaa channel is France-first: France represents 41.5% of the current audience, while Haiti and other smaller Francophone markets are treated as controlled expansion cohorts. The weekly experiment must never dilute the daily France-first pipeline or mix its performance attribution.

## Workflow

The workflow is `.github/workflows/francophone_market_weekly.yml`. It runs every Sunday at **15:30 UTC**. During the current daylight period this is approximately 11:30 in America/Port-au-Prince and 17:30 in Europe/Paris. The workflow generates exactly one French Short and uploads it as **private**, not public.

The initial cohort is `haiti` with experiment ID `haiti_weekly_v1`. A manual dispatch can select `francophone_expansion` for a broader smaller-market cohort, but the implementation remains French-language and must not claim country-specific causality from aggregate data alone.

## Safety and attribution

The weekly workflow shares the production concurrency lock, so it cannot overlap with the daily France-first publisher. It disables scheduled publishing and keeps `YT_PRIVACY_STATUS=private`. It uses the existing French quality gates, first-three-second gate, minimum thumbnail score of 80, minimum retention threshold of 50%, duplicate protection, and French Edge TTS fallback.

`MARKET_EXPERIMENT_ID` is appended to the generated YouTube tags and persisted in the local history. This supports cohort filtering in the repository and later comparison in YouTube Studio. It is an attribution label, not a guarantee that YouTube will expose country-filtered causal metrics.

## Review protocol

After the private upload is reviewed, collect the first 48–72 hours of views, engaged views, average percentage viewed, retention curve, likes, comments, shares, and geography. Compare the experiment against the France-first median and record the result before publishing it publicly. If the Short fails the hook, French-quality, thumbnail, or media audit, the workflow must fail without making the video public.

The default experiment is intentionally one video per week. Do not add a second weekly market video until at least four comparable experiments exist or the analytics show that the first cohort is materially outperforming its baseline.

## Manual dry run

Use GitHub Actions **Run workflow** with `dry_run=true` to render and audit without a YouTube upload. Use `dry_run=false` only when the operator accepts a private upload for review. Public publishing remains a separate human decision.

## Current audience context

The supplied YouTube Studio geography snapshot covers 25 July–21 August 2026 and shows France at 41.5%, Algeria at 6.7%, Côte d’Ivoire at 5.7%, Senegal at 5.4%, Burkina Faso at 3.5%, Belgium at 2.4%, Haiti at 2.3%, Morocco at 2.2%, Togo at 2.0%, and Congo–Kinshasa at 1.7%. These shares justify a small weekly Haiti/expansion test while keeping France as the primary optimization target.

## Rollback

To pause the experiment, disable the workflow in GitHub Actions or remove its `schedule` trigger. The daily France-first workflow is independent and must remain enabled. Existing private experiment uploads can be left private or deleted manually after the review decision; the weekly workflow does not automatically publish or delete them.
