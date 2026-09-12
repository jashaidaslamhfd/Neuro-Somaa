# Neuro-Somaa Production Runbook

## Purpose

Neuro-Somaa is a French-language YouTube Shorts production pipeline. A successful run must mean more than a green process: it must produce a validated French Short, select a unique title, pass media and thumbnail quality gates, upload a YouTube video successfully, and persist the resulting channel state.

## Production contract

| Area | Blocking requirement |
| --- | --- |
| Code | Compilation, Ruff, and the complete pytest suite pass before generation |
| French content | Script, metadata, disclosure, and final publication audit pass the strict French gate |
| Uniqueness | Historical and current-run title/topic collisions are rejected before expensive rendering |
| Video | Valid 9:16 MP4, minimum duration, valid audio, no silent segments, and acceptable retention prediction |
| Visuals | Scene assets satisfy the configured Shorts resolution and stock-clip quality floor |
| Thumbnail | Four bounded variants are rendered; the best mobile-aware variant must meet `MIN_THUMBNAIL_SCORE` |
| YouTube | Upload returns a real `youtube_video_id`; privacy and scheduled publish time are logged |
| State | Durable channel state is persisted only after a successful pipeline result |
| Failure semantics | A missed slot or absent YouTube video ID exits non-zero and turns the workflow red |

## Running modes

A manual dry run uses the `dry_run=true` workflow input. It builds and audits the complete asset pipeline but does not upload to YouTube. A production run uses `dry_run=false`; it may create a private scheduled YouTube upload and should only be launched when the operator accepts that side effect.

The scheduled workflow runs at the configured Paris peak slots. It refreshes the French demand queue, runs the complete test suite, generates the Short, validates all gates, uploads the asset, persists state, and stores artifacts for 14 days.

## Thumbnail policy

The production renderer creates up to four deterministic thumbnail variants. Each variant uses the same French hook and platform-safe geometry but a distinct visual theme. The scorer evaluates the actual headline band, mobile downsample readability, copy length, safe-zone compliance, and secondary colour contrast. The selected variant is written to `output/thumbnail.jpg` and the complete score report is retained in `script_data["thumbnail_variants"]`.

`MIN_THUMBNAIL_SCORE=80` is the production default. This score is an internal deterministic heuristic, not a YouTube CTR guarantee. It must be calibrated against real channel analytics before being treated as a business KPI.

## Recovery procedure

When a run fails, first inspect the workflow log and download the run artifact. Confirm whether the failure occurred before generation, during a quality gate, during YouTube upload, or during state persistence. Do not manually re-upload an ambiguous result until the log and YouTube video ID have been checked; a failed client response may still have created a private video.

If a guard failure exhausts continuity retries, the pipeline records the missed slot and exits with status `2`. The operator may safely re-dispatch the workflow with a controlled topic after confirming that no duplicate private video exists. If a real pipeline exception occurs, the workflow retries up to three times at the shell level, cleaning temporary render files between attempts.

## Release checklist

Before merging production changes, run:

```bash
python -m compileall -q src scripts tests
ruff check src scripts tests
python -m pytest tests/ -q
```

After merging, verify the push-triggered CI run is green. For a production behaviour check, manually dispatch with `dry_run=true` first. Only then run `dry_run=false` when an actual private scheduled upload is intended.
