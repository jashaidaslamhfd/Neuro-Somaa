# Neuro-Somaa — French Shorts Engine

Neuro-Somaa is a France-first automation system for producing concise, natural French YouTube Shorts about everyday science, the human body, sleep, emotions, and familiar phenomena. It turns a topic into a French script, narration, vertical video, metadata, and an optional YouTube upload through one deterministic entrypoint.

## Design principles

The system is intentionally small and observable. It prefers a French-native fallback script over a failed slot, uses a 15–30 second target window, keeps upload private when scheduling is enabled, and writes a durable record to `data/video_history.json`. It never prints secret values. It also never treats a dry-run as a published upload.

YouTube's own guidance groups performance into appeal, engagement, and satisfaction. Accordingly, this rebuild prioritizes a clear French title, immediate value in the opening seconds, readable narration, and real post-publication analytics rather than fabricated scores.

## Secret-name mapping

The workflow references the existing GitHub Secret names without requiring any renaming. LLM selection checks `GROQ_API_KEY`, then `OPENROUTER_API_KEY`, then `ALT_LLM_API_KEY`. YouTube upload uses `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `REFRESH_TOKEN`. Optional visual provider secrets are accepted for future adapters: `GEMINI_API_KEY`, `REPLICATE_API_TOKEN`, `HF_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `AI_HORDE_API_KEY`, `DEEPAI_API_KEY`, `MODELSLAB_API_KEY`, and `POLLINATIONS_KEY`. The existing `YOUTUBE_API_KEY`, `FB_ACCESS_TOKEN`, `FB_PAGE_ID`, and `INSTAGRAM_USER_ID` names remain available for later platform adapters.

## Local usage

```bash
cp env.example .env
python scripts/preflight.py
DRY_RUN=true python src/main.py
```

For a live upload, provide at least one LLM secret and the three YouTube OAuth secrets, then set `DRY_RUN=false`. The default YouTube privacy is `private`; scheduled publication must remain private until a publish time is explicitly assigned.

## GitHub Actions

The single workflow `.github/workflows/main.yml` supports manual dry-runs, manual live runs, and two daily scheduled runs. The CI job compiles the code and runs tests. The production job runs preflight, generates the French Short, uploads only when `dry_run=false`, and always stores the generated output as an artifact.

## Preserved state

The rebuild preserves the existing `.git` history, `data/` state and video history, `assets/`, and remote GitHub Secret values. Source code, workflows, tests, and documentation were replaced with the clean implementation above.

## License

MIT.
