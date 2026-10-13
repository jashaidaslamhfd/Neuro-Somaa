# Neuro-Somaa — French Shorts Engine

Neuro-Somaa is a France-first automation system for producing concise, natural French YouTube Shorts about everyday science, the human body, sleep, emotions, and familiar phenomena. It turns a topic into a French script, narration, vertical video, metadata, and an optional YouTube upload through one deterministic entrypoint.

## Design principles

The system is intentionally small and observable. It prefers a French-native fallback script over a failed slot, uses an 18–30 second production target window, keeps upload private when scheduling is enabled, and writes a durable record to `data/video_history.json`. It never prints secret values. It also never treats a dry-run as a published upload.

YouTube's own guidance groups performance into appeal, engagement, and satisfaction. Accordingly, the engine prioritizes a clear French title, immediate value in the opening seconds, readable narration, and observed post-publication analytics. Topic ranking uses average view percentage only when analytics were fetched and the video has a meaningful view sample. Script-audit scores are heuristics, not actual retention or swipe-rate measurements.

## Secret-name mapping

The workflow references the existing GitHub Secret names without requiring any renaming. LLM selection checks `GROQ_API_KEY`, then `OPENROUTER_API_KEY`, then `ALT_LLM_API_KEY`. YouTube upload uses `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `REFRESH_TOKEN`. Optional visual provider secrets are accepted for future adapters: `GEMINI_API_KEY`, `REPLICATE_API_TOKEN`, `HF_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `AI_HORDE_API_KEY`, `DEEPAI_API_KEY`, `MODELSLAB_API_KEY`, and `POLLINATIONS_KEY`. The existing `YOUTUBE_API_KEY`, `FB_ACCESS_TOKEN`, `FB_PAGE_ID`, and `INSTAGRAM_USER_ID` names remain available for later platform adapters.

## Local usage

```bash
cp env.example .env
python scripts/preflight.py
DRY_RUN=true python src/main.py
```

For a live upload, provide at least one LLM secret and the three YouTube OAuth secrets, then set `DRY_RUN=false`. The default YouTube privacy is `public` for immediate Shorts distribution. If `YT_SCHEDULE_PUBLISH=true`, privacy must be `private` and a future publication time is assigned.

## GitHub Actions

The single workflow `.github/workflows/main.yml` supports manual dry-runs, manual live runs, and three daily scheduled runs. Manual dispatch defaults to dry-run to prevent accidental uploads; explicitly disable it only when a live upload is intended. The GitHub token is read-only by default, with write permission limited to production state persistence. Cron runs are scheduled before the Europe/Paris publish slots, and late jobs fall forward to the next same-day slot where possible. The CI job compiles the code and runs tests. The production job runs preflight, generates the French Short, uploads only when `dry_run=false`, and always stores the generated output as an artifact.

## Publishing behavior

The pipeline defaults to immediate public uploads when `DRY_RUN=false` (`YT_PRIVACY_STATUS=public`, `YT_SCHEDULE_PUBLISH=false`). If scheduled publishing is explicitly enabled, YouTube requires the video to remain private until its assigned `publishAt` time. Manual workflow dispatch defaults to `dry_run=true`, so a live upload requires deliberately turning dry-run off.

## License

MIT.
