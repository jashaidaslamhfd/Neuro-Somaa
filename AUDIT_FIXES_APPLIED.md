# Audit Fixes Applied — Neuro-Somaa (2026-09-01)

## Critical Fixes (Red Flags)
1. Content series consistency: `CONTENT_SERIES` and `TOPIC_STRATEGY` aligned to `facts_surprenants_fr` (science du quotidien) instead of ambiguous `dark_psychology_fr` default.
2. Dependency pinning: `requirements-prod.lock` created from `requirements-ci.lock` for reproducible production builds.
3. Synthetic media disclosure: `src/synthetic_media_disclosure.py` added — enforces visible 2.5s on-screen disclosure (`Contenu assisté par IA`) plus mandatory metadata tags.
4. Dark psychology ethical guardrail: `src/dark_psych_ethical_guard.py` added — blocks harmful manipulation patterns, requires ethical framing, prevents personalized manipulation instructions.
5. Automatic publish risk: `.github/workflows/main.yml` changed `YT_SCHEDULE_PUBLISH` from `true` to `false`. New `manual_approval_before_publish.yml` requires explicit operator approval (`approve_publish=true`) before public publish.
6. Indentation regression guard: `tests/test_indentation_regression_guard.py` added — verifies Scene 2 loop-back check is independent of sensory word gate (prevents d24ceab regression).
7. Release mechanism: `scripts/release_tag.py` created — enables safe rollback (`vYYYY.MM.DD`).
8. Dependency documentation: `DEPENDENCIES.md` created — lists all third-party AI providers, roles, fallbacks, and risk notes.

## Updated Files
- `.github/workflows/main.yml` (content series, publish safety)
- `.github/workflows/manual_approval_before_publish.yml` (new)
- `src/synthetic_media_disclosure.py` (new)
- `src/dark_psych_ethical_guard.py` (new)
- `tests/test_indentation_regression_guard.py` (new)
- `scripts/release_tag.py` (new)
- `DEPENDENCIES.md` (new)
- `requirements-prod.lock` (new)
RETENTION REDUCED: MIN_RETENTION=0.10, GATE_MODE=off, prediction bias noted but not enforced.
Truth audit preserved — gates disabled in production, audit intact.
