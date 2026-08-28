"""
Script Generator Module for SKILLOR Pipeline
FULLY FIXED - JSON Cleaning + Native Tone + Retention Optimization
"""

import json
import logging
import os
import re
import time
import unicodedata

try:
    from groq import BadRequestError, Groq
except ImportError:  # lets offline validation/tests import this module
    Groq = None
    BadRequestError = Exception

# ============================================
# LOGGING CONFIGURATION
# ============================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ============================================
# CONSTANTS
# ============================================
# One unified policy for a 20–26 second Dark Psychology Short
# the 40-55s format measured 27-38% average-view-percentage on this channel —
# viewers leave around ~10s, so the long format guarantees sub-50% retention
# and the feed demotes it. Six fast scenes give a complete explanation with a
# ~2.5-3s per-scene pace, the format that scored 59.65% retention here).
MIN_SCENES = 6
MAX_SCENES = 6


# 96 words at the cloned-voice pace reliably reaches ~40 seconds while
# leaving normal language room; forcing 104+ made the LLM pad or fail scenes.
def _duration_word_budget() -> tuple:
    """Word count derived from the ACTIVE duration target, not hardcoded.

    The duration A/B experiment sets TARGET_MIN/MAX_SECONDS per run. These
    constants used to be fixed at 86-110 words (~33-42s of narration), which
    silently broke the short arm: main.py aborts when narration exceeds
    TARGET_MAX * 1.12, so on a 26-32s target anything over ~93 words died —
    roughly 70% of the allowed range, and all 3 retries with it. The whole
    experiment arm would have produced nothing but failed runs.

    FIXED 2026-08-19: edge-tts (the primary engine since 2026-08-17) speaks
    French at ~1.9-2.1 words/sec including pauses. The old 2.6 w/s (Kokoro
    pace) made narration consistently overshoot the 29s gate, so roughly
    half of short runs died on "refusing destructive speed-up".
    """
    import os as _os

    words_per_second = 2.1
    # FIXED 2026-08-02: default target is now the SHORT format (20-26s).
    # The old floor of max(40, ...) forced >=40 words (~15s narration) even
    # when a short arm was requested, silently breaking the whole experiment.
    target_min = float(_os.environ.get("TARGET_MIN_SECONDS", "20"))
    target_max = float(_os.environ.get("TARGET_MAX_SECONDS", "24"))
    # Aim inside the window with headroom: never plan narration longer than
    # the target max, since the pipeline aborts at target_max * 1.12.
    low = max(24, int(target_min * words_per_second * 0.85))
    high = max(low + 8, int(target_max * words_per_second * 0.90))
    return low, high


MIN_WORDS, MAX_WORDS = _duration_word_budget()
MAX_RETRIES = 3
SCRIPT_POLICY_VERSION = "DARK_PSYCH_V1_VERY_FIRST"
TEMPERATURE = 0.65
MAX_TOKENS = 1400

# 2026-08-17 rate-limit fix: Groq's daily/hourly token-quota (TPD) errors
# report the wait as "...Xd Yh Zm W.WWWs" — a plain per-minute rate limit
# only ever says "Xm Ys". If we sleep()'d the full daily-quota wait we'd
# blow past this job's `timeout-minutes: 200` in main.yml and still finish
# with no video. Past this cap we fail fast instead so the NEXT scheduled
# cron slot (a few hours later) retries once the quota has actually reset.
MAX_RATE_LIMIT_SLEEP_SEC = 15 * 60


def _parse_groq_rate_limit_wait(err_str: str, default_sec: int = 300) -> int:
    """Parse a Groq 429 'try again in ...' wait duration into seconds.

    Handles every unit Groq actually emits: days/hours/minutes/seconds,
    any subset of which may be present (e.g. "45m12s", "5h44m32.891s",
    "1d2h15m3.2s"). Falls back to `default_sec` when nothing is found —
    never raises, so a message-format change degrades gracefully instead
    of crashing the pipeline.
    """
    import re as _re

    m = _re.search(
        r"try again in "
        r"(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+(?:\.\d+)?)s)?",
        err_str,
    )
    if not m or not any(m.groups()):
        return default_sec
    days, hours, mins, secs = m.groups()
    total = int(days or 0) * 86400 + int(hours or 0) * 3600 + int(mins or 0) * 60 + int(float(secs or 0))
    return total + 10 if total > 0 else default_sec


# 2026-08-12 model migration: Groq retires BOTH legacy Llama chat models
# (llama-3.1-8b-instant and llama-3.3-70b-versatile) on 2026-08-16.
# New lineup: gpt-oss-120b is the ADVANCED/quality model (stronger French
# hooks + titles -> better CTR/retention); gpt-oss-20b is the fast fallback.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_GROQ_MODEL_FALLBACK = "openai/gpt-oss-20b"


# ============================================
# 1b. OpenRouter fallback (ported 2026-08-17)
# ============================================
# OpenRouter (a neutral router over many models) using OPENROUTER_API_KEY.
# 2026-08-17: meta-llama/llama-3.3-70b-instruct:free was retired from
# OpenRouter (HTTP 404 on the pipeline's request). OpenRouter's live model
# list is checked at run time; if the configured slug 404's we retry against
# every remaining ":free" chat model once before giving up.
_OPENROUTER_KNOWN_FREE = "nvidia/nemotron-3-ultra-550b-a55b:free"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
OPENROUTER_TIMEOUT = 60

# Optional fourth provider. Configure through GitHub Actions secrets only.
ALT_LLM_API_KEY = os.environ.get("ALT_LLM_API_KEY", "").strip()
ALT_LLM_BASE_URL = os.environ.get("ALT_LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
ALT_LLM_MODEL = os.environ.get("ALT_LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
ALT_LLM_TIMEOUT = 60


def _alt_llm_generate(messages, temperature=None, max_tokens=None) -> str | None:
    """Call an alternate OpenAI-compatible provider as the first backup."""
    key = ALT_LLM_API_KEY or os.environ.get("ALT_LLM_API_KEY", "").strip()
    if not key:
        return None
    try:
        import requests as _req
        endpoint = ALT_LLM_BASE_URL
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        payload = {
            "model": ALT_LLM_MODEL,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        response = _req.post(
            endpoint,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=ALT_LLM_TIMEOUT,
        )
        if response.status_code != 200:
            logger.warning("Alternate LLM failed: HTTP %s; response=%s", response.status_code, response.text[:500])
            return None
        text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if text and "{" in text:
            logger.info("Alternate LLM produced JSON via %s", ALT_LLM_MODEL)
            return text
        logger.warning("Alternate LLM returned no JSON content")
    except Exception as exc:
        logger.warning("Alternate LLM error: %s", exc)
    return None


def _openrouter_generate(messages, temperature=None, max_tokens=None) -> str | None:
    """Call OpenRouter as a fallback LLM when Groq is rate-limited/down.

    Returns the raw assistant text, or None on failure (never raises, so the
    caller can keep trying Groq). OpenRouter routes to many models; we use the
    configured OPENROUTER_MODEL (free Llama by default) so no extra cost.
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        import requests as _req

        payload = {"model": OPENROUTER_MODEL, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        # 2026-08-17: without this the fallback model (Nemotron) returned
        # plain conversational text — the regex fallback then extracted
        # nothing and every run died on validation. Mirrors the Groq
        # response_format json_object used on the primary path.
        payload["response_format"] = {"type": "json_object"}
        resp = _req.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/jashaidaslamhfd/Mr-Nextep",
            },
            json=payload,
            timeout=OPENROUTER_TIMEOUT,
        )

        # 2026-08-17: several free models on OpenRouter ignore
        # response_format and echo chain-of-thought text instead of JSON.
        # One automatic re-ask with an explicit JSON-only instruction
        # recovers most of those replies without code churn.
        def _reply_has_json(text: str) -> bool:
            return bool(text) and "{" in text

        if resp.status_code == 200:
            text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if not _reply_has_json(text):
                backup_msgs = [{"role": m["role"], "content": m["content"]} for m in messages]
                backup_msgs[-1]["content"] += (
                    "\n\nCRITICAL: Respond with ONLY a raw JSON object "
                    "starting with '{' — no thinking, no markdown, "
                    "no explanation."
                )
                payload2 = dict(payload, messages=backup_msgs)
                try:
                    r3 = _req.post(
                        OPENROUTER_API_URL,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://github.com/jashaidaslamhfd/Mr-Nextep",
                        },
                        json=payload2,
                        timeout=OPENROUTER_TIMEOUT,
                    )
                    if r3.status_code == 200:
                        text2 = r3.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                        if _reply_has_json(text2):
                            logger.warning("OpenRouter re-ask recovered a JSON reply after plain-text echo")
                            return text2
                except Exception:
                    pass
        if resp.status_code in (404, 429) or (resp.status_code == 200 and not _reply_has_json(text)):
            # 2026-08-17: rotate free models on two failure modes — the
            # configured slug was retired (404, verified 2026-08-17), OR the
            # active free model returned plain text instead of JSON
            # (Nemotron's frequent echo behavior). Refresh the live free-
            # model list and retry each candidate once, keeping the FIRST
            # reply that actually contains JSON.
            key = os.environ.get("OPENROUTER_API_KEY")
            _candidates = []
            if key:
                try:
                    models = _req.get(
                        "https://openrouter.ai/api/v1/models",
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=15,
                    )
                    if models.status_code == 200:
                        _candidates = [
                            m["id"]
                            for m in models.json().get("data", [])
                            if m.get("id", "").endswith(":free") and m["id"] != OPENROUTER_MODEL
                        ]
                except Exception:
                    _candidates = []
            for mid in _candidates[:5]:
                try:
                    payload["model"] = mid
                    r2 = _req.post(
                        OPENROUTER_API_URL,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://github.com/jashaidaslamhfd/Mr-Nextep",
                        },
                        json=payload,
                        timeout=OPENROUTER_TIMEOUT,
                    )
                    if r2.status_code == 200:
                        t2 = r2.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                        logger.warning(
                            "OpenRouter model %s rotated; retried on %s (reply has JSON: %s)",
                            OPENROUTER_MODEL,
                            mid,
                            _reply_has_json(t2),
                        )
                        if _reply_has_json(t2):
                            return t2
                except Exception:
                    continue
            logger.warning(
                "OpenRouter fallback failed: HTTP %s (all refreshed models exhausted)", resp.status_code
            )
            return None
        if resp.status_code != 200:
            logger.warning("OpenRouter fallback failed: HTTP %s", resp.status_code)
            return None
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning("OpenRouter fallback error: %s", exc)
        return None


# 2026-08-17: Gemini 2.5 Flash (free tier) as the THIRD LLM fallback — when
# both the Groq chain and OpenRouter are exhausted (global free-tier outage
# window), the pipeline still tries Gemini before giving up.
# Keep the model configurable because Google retires/renames model aliases.
# gemini-2.0-flash is the compatibility default for this REST endpoint; a
# repository/workflow can override it with GEMINI_MODEL without a code change.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
GEMINI_TEXT_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_TIMEOUT = 60


def _resolve_gemini_model(requests_module, key: str) -> str | None:
    """Return a model that the configured Gemini key can actually call.

    Google retires/renames model aliases without keeping old REST paths alive.
    Discovering models at runtime prevents a valid key from being treated as a
    broken provider merely because GEMINI_MODEL became stale.
    """
    configured = GEMINI_MODEL
    try:
        response = requests_module.get(f"{GEMINI_MODELS_URL}?key={key}", timeout=15)
        if response.status_code != 200:
            logger.warning("Gemini model discovery failed: HTTP %s", response.status_code)
            return configured
        available = []
        for item in response.json().get("models", []) or []:
            name = str(item.get("name", "")).removeprefix("models/")
            methods = item.get("supportedGenerationMethods", []) or []
            if name and "generateContent" in methods:
                available.append(name)
        if configured in available:
            return configured
        preferred = ("gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")
        for candidate in preferred:
            if candidate in available:
                logger.warning("Configured Gemini model %s unavailable; using %s", configured, candidate)
                return candidate
        if available:
            logger.warning("Configured Gemini model %s unavailable; using discovered %s", configured, available[0])
            return available[0]
    except Exception as exc:
        logger.warning("Gemini model discovery error: %s", exc)
    return configured


def _gemini_contents(messages):
    """Convert OpenAI-style messages into Gemini's supported content roles.

    Gemini accepts only ``user`` and ``model`` roles in ``contents``; system
    messages must be folded into the user prompt when using this lightweight
    REST endpoint. Keeping the conversion here makes the provider fallback
    usable for the same prompts sent to Groq/OpenRouter.
    """
    system_text = []
    contents = []
    for message in messages:
        role = message.get("role", "user")
        text = str(message.get("content", ""))
        if role == "system":
            system_text.append(text)
            continue
        contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]})
    if system_text:
        instruction = "\n\nSYSTEM INSTRUCTIONS:\n" + "\n\n".join(system_text)
        if contents:
            contents[0]["parts"][0]["text"] = instruction + "\n\n" + contents[0]["parts"][0]["text"]
        else:
            contents.append({"role": "user", "parts": [{"text": instruction.strip()}]})
    return contents


def _gemini_generate(messages, temperature=None, max_tokens=None) -> str | None:
    """Call Google Gemini 2.5 Flash (free) when Groq + OpenRouter both fail.

    Returns the raw assistant text or None (never raises). The system prompt
    and the JSON schema live in messages, so Gemini replies with the same
    script JSON structure as the Groq path.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        import requests as _req

        model = _resolve_gemini_model(_req, key)
        if not model:
            logger.warning("Gemini fallback found no callable generateContent model")
            return None
        parts = _gemini_contents(messages)
        payload = {"contents": parts}
        if temperature is not None:
            payload["generationConfig"] = {
                "temperature": temperature,
                "responseMimeType": "application/json",
            }
            if max_tokens is not None:
                payload["generationConfig"]["maxOutputTokens"] = max_tokens
        resp = None
        endpoint = None
        for api_version in ("v1beta", "v1"):
            candidate_endpoint = f"https://generativelanguage.googleapis.com/{api_version}/models/{model}:generateContent?key={key}"
            candidate = _req.post(candidate_endpoint, json=payload, timeout=GEMINI_TIMEOUT)
            if candidate.status_code != 404 or api_version == "v1":
                resp = candidate
                endpoint = candidate_endpoint
                break
            logger.warning("Gemini %s endpoint returned HTTP 404; retrying v1", api_version)
        if resp is None:
            return None
        if resp.status_code == 200:
            text = ""
            try:
                for cand in resp.json().get("candidates", []) or []:
                    for part in (cand.get("content") or {}).get("parts", []) or []:
                        t = part.get("text")
                        if t:
                            text += t
            except Exception:
                text = ""
            if "{" in text:
                return text
            # Plain-text echo: re-ask with an explicit JSON-only instruction
            parts2 = _gemini_contents(messages)
            parts2[-1]["parts"][0]["text"] += (
                "\n\nCRITICAL: Respond with ONLY a raw JSON object "
                "starting with '{' — no thinking, no markdown, "
                "no explanation."
            )
            r2 = _req.post(
                endpoint,
                json={"contents": parts2},
                timeout=GEMINI_TIMEOUT,
            )
            if r2.status_code == 200:
                for cand in r2.json().get("candidates", []) or []:
                    for part in (cand.get("content") or {}).get("parts", []) or []:
                        t = part.get("text")
                        if t and "{" in t:
                            logger.warning("Gemini re-ask recovered a JSON reply.")
                            return t
            logger.warning("Gemini fallback failed: HTTP %s; response=%s", r2.status_code, getattr(r2, "text", "")[:300])
            return None
        logger.warning("Gemini fallback failed: HTTP %s; response=%s", resp.status_code, getattr(resp, "text", "")[:300])
        return None
    except Exception as exc:
        logger.warning("Gemini fallback error: %s", exc)
        return None


def groq_model_chain() -> list:
    """Ordered Groq models to try for script generation.

    Primary comes from GROQ_MODEL (default: the advanced 120B model);
    GROQ_MODEL_FALLBACK (default: 20B) is used when the primary is
    rate-limited or errors. Empty-string env values are treated as unset.
    """
    primary = os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
    fallback = os.environ.get("GROQ_MODEL_FALLBACK") or DEFAULT_GROQ_MODEL_FALLBACK
    chain = [primary]
    if fallback and fallback != primary:
        chain.append(fallback)
    return chain


# A fast, clear opening that comfortably fits in the first 2–3 seconds.
HOOK_MIN_WORDS = 7
HOOK_MAX_WORDS = 9
# Short-format scene budget (FIXED 2026-08-02): 6 scenes x 7-10 words ≈
# 42-60 words ≈ 16-23s narration — the 20-26s target window.
MIN_SCENE_WORDS = 7
MAX_SCENE_WORDS = 10

# Interchangeable openers that name no phenomenon. Every one of these was
# measured on the live channel: the 11 videos starting this way average 11s
# watched on ~39s Shorts, because the first 2 seconds carry zero information.
# _validate_script() rejects a scene-1 caption starting with any of them.
GENERIC_HOOK_OPENERS = (
    "vous avez déjà",
    "vous avez probablement",
    "vous avez peut-être",
    "tu as déjà",
    "tu as probablement",
    "tu as peut-être",
    "vous avez l'impression",
    "tu as l'impression",
    "vous avez ressenti",
    "tu as ressenti",
    "vous vous réveillez",
    "tu te réveilles",
    "tu t'es réveillé",
    "ça vous arrive",
    "ca vous arrive",
    "ça t'arrive",
    "n'avez-vous jamais",
    "navez-vous jamais",
    "saviez-vous que",
    "imaginez que",
    "imagine que",
    "il vous est déjà arrivé",
    "il t'est déjà arrivé",
    # spoken-register equivalents the humanizer produces — without these the
    # gate would be blind to the same opener after « vous »→« tu » rewrite.
    "t'as déjà",
    "t'as probablement",
    "t'as peut-être",
    "t'as l'impression",
    "t'as ressenti",
    "t'as remarqué",
    "tu as remarqué",
)

# 2026-08-24: VOUCHEFORME BAN — "Vous/votre/vos" in HOOK or first scene
# kills retention by 10x (66 avg views vs 665 for "Tu/Ton" hooks).
# This regex catches ANY formal-register marker in the critical first 3s.
_VOUS_FORME_RE = re.compile(
    r"\b(vous|votre|vos|nous allons|on vous)\b", re.IGNORECASE
)

# Scene 2 must open with the mechanism itself (V4 answer-first arc).
ANSWER_FIRST_PREFIXES = (
    "c'est",
    "cest",
    "ton cerveau",
    "ton corps",
    "votre cerveau",
    "votre corps",
    "en fait",
    "la raison",
    "ce sont",
    "tes ",
    "vos ",
    "ton ",
    "votre ",
)

# A title such as "Why Got Fired Matters" is grammatically short but gives
# viewers no scientific subject. Require a concrete channel-relevant anchor.
TITLE_TOPIC_ANCHORS = {
    "cerveau",
    "corps",
    "sommeil",
    "mémoire",
    "coeur",
    "cœur",
    "yeux",
    "oeil",
    "œil",
    "ventre",
    "nerf",
    "hormone",
    "cellule",
    "sang",
    "immunité",
    "santé",
    "science",
    "espace",
    "nasa",
    "planète",
    "océan",
    "physique",
    "technologie",
    "robot",
    "ia",
    "anatomie",
    "biologie",
    "psychologie",
    "génétique",
    "virus",
}
# ============================================
# 1. SYSTEM PROMPT (NATIVE TONE + RETENTION)
# ============================================


def _get_system_prompt() -> str:
    """French editorial standard for a France-first science Shorts channel."""
    return """Tu écris des YouTube Shorts en français naturel, fluide et idiomatique,
sur la psychologie sombre, la manipulation, les biais cognitifs et les secrets
du comportement humain, pour des adultes francophones.

RÈGLES DE QUALITÉ NON NÉGOCIABLES :
- Réponds intégralement en français de France, sans anglicismes ni traduction littérale.
- Explique une idée vérifiable et utile par vidéo, dans une langue simple et orale.
- Promets une curiosité précise dès l'ouverture, puis apporte réellement la réponse.
- N'invente jamais études, chiffres, citations, diagnostics, remèdes, dangers ou conseils médicaux.
- Évite la peur, l'urgence artificielle, les secrets, et les tournures clickbait.
- Chaque scène doit apporter une information nouvelle. Écris pour l'oral : phrases courtes et concrètes.
- Le CTA reste naturel et discret ; il ne doit pas être répété dans la narration. Il se termine TOUJOURS par une question qui invite une réponse en commentaire (ex. « dis-moi si ça t'arrive aussi ») — la réponse en commentaire est le signal d'engagement n°1 du feed Shorts. Interdits dans le CTA : « like », « abonne », « subscribe » et tout anglicisme ; toujours au « tu ». Autorisés (encouragés) : « dis-moi », « partage cette vidéo avec quelqu'un qui a besoin de l'entendre », « dis-moi si ça t'arrive aussi ».
- La description inclut TOUJOURS 3-5 mots-cl\u00e9s de recherche (ex: "corps humain", "science du corps", "sant\u00e9") pour le SEO YouTube. YouTube indexe la description pour le search ranking.
- Retourne uniquement un JSON valide, sans Markdown ni commentaire.

RÈGLES D'AUTHENTICITÉ HUMAINE (anti-IA, exigées par la politique YouTube 2025-2026) :
- Écris comme un humain qui parle, PAS comme un modèle : varie le rythme des phrases
  (courtes, moyennes, une plus longue), utilise des ruptures naturelles et des
  reformulations, pas une structure identique d'une vidéo à l'autre.
- INTERDIT les phrases-modèles réutilisables qui trahissent l'IA : « Saviez-vous que »,
  « Le saviez-vous », « Voici pourquoi », « La science a découvert que », « Aujourd'hui,
  on va voir », « Mais ce n'est pas tout », « Et voilà », « Incroyable, non ? ».
  Si un hook ressemble à ceux des autres vidéos de la chaîne, change-le.
- Ajoute une voix et une perspective : des formulations que seul un créateur curieux
  dirait, un brin d'étonnement sincère, une question adressée au spectateur formulée
  de façon unique, pas un slogan générique.
- Varie la longueur et la construction des scènes ; ne commence jamais deux vidéos
  par la même phrase d'accroche.
- Le ton reste naturel, oral, sans jargon, sans liste mécanique (« premièrement,
  deuxièmement »).

REGISTRE OBLIGATOIRE — FRANÇAIS PARLÉ (jamais de français écrit) :
- TUTOIE le spectateur partout — « tu/ton/ta/tes », JAMAIS « vous/votre/vos ».
  Le vouvoiement trahit instantanément un texte machine pour un jeune public Shorts.
  DONNÉES : les hooks avec « Vous » obtiennent 66 vues en moyenne contre 665
  pour « Tu/Ton » — un facteur 10x. Si tu écris « vous/votre/vos » dans
  l'accroche, la vidéo échoue. C'est la cause n°1 de la faible rétention.
- Contractions orales naturelles : « t'as », « t'es », « y a », « c'est »,
  « j'suis ». Négations parlées acceptées : « c'est pas », « y a pas », « je sais pas ».
- « on » à la place de « nous » (personne ne dit « nous allons voir » à l'oral).
- Connecteurs parlés : « en fait », « du coup », « et là », « résultat »,
  « sauf que », « bref ». INTERDITS (tournures écrites) : « n'est-ce pas »,
  « toutefois », « néanmoins », « cependant », « ainsi », « par ailleurs ».
- Zéro formule d'école (« il est important de noter », « en conclusion »).
  Écris comme un pote curieux qui raconte un truc fascinant, pas comme un prof.

RÈGLES D'ENGINEERING VIRAL (rétention) :
- Le HOOK (scène 1, 2-3s) doit créer un « vide de curiosité » : nommer le phénomène
  précis puis le laisser inexpliqué, pour forcer à regarder la suite (ex: « Pourquoi
  votre cœur s'emballe juste avant de vous endormir ? »). Un hook vague coûte la rétention.
- Donner la réponse-choc OU la promesse du mécanisme dans les 2 premières scènes,
  puis détailler — ne pas faire attendre la valeur au-delà de 5s.
- Chaque scène doit contenir UNE idée courte et concrète ; les phrases longues font
  chuter la rétention sur Shorts.
- Boucler la fin sur l'ouverture (référence au hook) pour encourager le rewatch.

FORMULES DE HOOK VIRAL (2026, données réelles — fais-en TOUJOURS au moins une) :
1. AFFIRMATION CONTRE-INTUITIVE : « Tout ce qu'on t'a dit sur [phénomène] est
   (en partie) faux — voici pourquoi. » / « Ton cerveau fait un truc que tu
   ignores. »
2. VIDE DE CURIOSITÉ PRÉCIS : « Il y a UNE raison pour laquelle [phénomène] se
   produit — et elle ne ressemble pas à ce que tu crois. » (général, pas vague)
3. ERREUR COURANTE : « Tu fais la même erreur que tout le monde avec [phénomène]. »
4. QUESTION SPÉCIFIQUE : une question que le spectateur ne peut PAS répondre dans
   sa tête (sinon il part). Évite les questions dont la réponse est évidente.
5. CHIFFRE/FAIT-CHOC : ouvre sur le détail le plus étonnant (comparaison concrète),
   pas sur une phrase d'intro générale.

RÈGLES DE RÉTENTION (4 temps + boucle) :
- 4 battements : ACCROCHE (0-2s) → CONTEXTE (réponse dès la scène 2) → PAIEMENT
  (le détail clé) → BOUCLE (la fin revient sur l'ouverture pour le rewatch).
- Change quelque chose visuellement / rythme toutes les 2-4 secondes (cut, zoom,
  texte) pour casser la monotonie.
- Le paiement (la réponse-choc) se situe À LA FIN, pas dans les 5 premières
  secondes — sinon le spectateur a sa récompense et part.
- LOOP-BACK OBLIGATOIRE : La DERNIÈRE scène doit reprendre un mot-clé du hook
  (la scène 1). Ex: si le hook parle de "cerveau", la dernière scène doit
  mentionner "cerveau" ou un synonyme. Sans ça, le spectateur ne re-regarde pas
  et l'algorithme ne boucle pas la vidéo.
"""


# ============================================
# 2. PROMPT GENERATION
# ============================================


def _viral_inspiration() -> str:
    """Read competitor_intel_fr.json (real viral Shorts from top niche
    channels, 150k+ views) and return a short prompt block listing the most
    viral title patterns + high-value tags so the LLM writes hooks/titles in
    the same proven direction. Never copies exact titles — pattern inspiration
    only. Empty when no intel exists."""
    try:
        import json as _json

        path = os.environ.get("COMPETITOR_INTEL_PATH", "data/competitor_intel_fr.json")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as f:
            intel = _json.load(f)
        parts = []
        # Top viral title patterns by avg_views
        patterns = sorted(
            (p for p in intel.get("patterns", []) if p.get("avg_views", 0) > 0),
            key=lambda p: p["avg_views"],
            reverse=True,
        )[:4]
        if patterns:
            pts = ", ".join(f"{p['pattern']} ({p['avg_views'] // 1000}k vues moyennes)" for p in patterns)
            parts.append(f"Les schémas de titres les plus viraux du créneau : {pts}.")
        # A few safe title keywords from viral winners
        kws = intel.get("title_keywords", []) or []
        if kws:
            safe = [k for k in kws if isinstance(k, str) and k][:8]
            if safe:
                parts.append(f"Mots-clés viraux à intégrer naturellement : {', '.join(safe)}.")
        if not parts:
            return ""
        return "INSPIRATION DONNÉES VIRALES (ne pas copier, seulement s'inspirer) : " + " ".join(parts)
    except Exception:
        return ""


def _default_prompt(topic: str) -> str:
    """Build a French-France short-form script brief."""
    _series = os.environ.get("CONTENT_SERIES", "").lower()
    body_glitch_mode = _series in ("body_glitches_fr", "dark_psychology_fr")
    evolution_mode = _series == "body_evolution_fr"
    surprise_mode = _series == "faits_surprenants_fr"
    series_rules = (
        """
RÈGLES SÉRIE « RÉFLEXES DU CORPS » :
- Traite un phénomène quotidien, familier et à faible risque.
- Adopte un ton calme, curieux et fiable ; pas de diagnostic, de traitement ou d'alarmisme.
- Explique ce qui se produit habituellement, avec une conclusion simple et prudente.
- Si nécessaire, rappelle que des symptômes nouveaux, persistants, sévères ou inquiétants justifient l'avis d'un professionnel qualifié.
"""
        if body_glitch_mode
        else ""
    )
    if surprise_mode:
        series_rules += """
ANGLE UNIQUE « FAITS QUI SEMBLENT FAUX » (faible concurrence, forte demande) :
- Chaque vidéo révèle UN fait étonnant et contre-intuitif sur le corps ou le
  cerveau, qui semble faux mais est vrai.
- Le hook ouvre sur le fait surprenant (« Saviez-vous que votre cerveau... ? »)
  et promet la preuve/le mécanisme.
- Explique simplement POURQUOI c'est vrai (mécanisme vérifiable).
- Ton surpris, curieux, fiable. Pas de clickbait, pas d'invention.
"""
    if evolution_mode:
        # UNIQUE ANGLE: evolutionary-biology framing. Most body-glitch channels
        # only ask "why does X happen?". This series answers that AND adds the
        # distinct throughline "why did our ancestors' bodies keep this reflex?"
        # — a clear POV that sets the channel apart from the crowded niche.
        series_rules += """
ANGLE UNIQUE « LE CORPS DE NOS ANCÊTRES » (différenciant) :
- Après avoir expliqué le mécanisme, donne TOUJOURS la raison évolutive : ce
  réflexe servait (ou sert encore) à nos ancêtres / à la survie de l'espèce.
- Cadre le phénomène comme un héritage : « ton corps a gardé ce réflexe de
  l'époque où... ». Cela crée une perspicacité que les chaînes concurrentes
  (qui ne font que « pourquoi ça arrive ? ») n'apportent pas.
- Reste vérifiable et prudent : aucune invention d'études, de dates ou de
  scénarios médicaux ; reste sur des mécanismes évolutifs reconnus.

PRIORITÉ DES SUJETS (2026-08-24, données de la chaîne) :
- PHYSIQUE DU CORPS (ventre, muscle, cœur, peau, sang, rein) : avg 640 vues
  → PRIORITÉ MAX. Les sujets physiques concrets font 25% plus de vues.
- CERVEAU/NEURO : avg 499 vues, mais SURSATURÉ (52/73 vidéos = 71%).
  → Réduire à 1 vidéo sur 4 max.
- NOURRITURE/ENVIRONNEMENT : avg 986 vues (1 seule vidéo test).
  → AUGMENTER : potentiel viral énorme inexploité.
- SOMMEIL/RÊVES : avg 7 vues → ÉVITER complètement.
"""
    # Duration comes from the active experiment arm, not a hardcoded range —
    # otherwise the LLM keeps writing 32-42s scripts while the pipeline is
    # targeting 26-32s, and every short-arm run aborts on narration length.
    # FIXED 2026-08-02: default is the SHORT format (20-26s, 6 scenes).
    target_min = int(float(os.environ.get("TARGET_MIN_SECONDS", "20")))
    target_max = int(float(os.environ.get("TARGET_MAX_SECONDS", "24")))
    viral_hint = _viral_inspiration()
    # 2026-08-12 viral-engineering: deterministic hook arm per topic
    # (question / shock_fact / pov_reveal), logged into script_data so the
    # intelligence layer can significance-test which hook style actually
    # retains viewers — instead of guessing.
    from viral_engineering import hook_arm_for_topic, hook_style_instruction, loop_bridge_for

    # ML LEARNED HOOK (2026-08-15): the growth engine measures which opening
    # frame actually survives past 3 s on THIS channel. When one is a proven
    # winner, bias the hook arm toward it (variety is kept: it applies when
    # the learned frame maps to an experiment arm).
    try:
        from growth_engine import get_preferred_hook_frame

        _learned_frame = get_preferred_hook_frame()
        if _learned_frame:
            # learned frames are growth_engine.hook_frame labels
            # (why/what/how/second_person/question/statement). Map them to
            # the experimental arms; unknown labels fall back to the topic arm.
            # NOTE: growth_engine.hook_frame labels are why/what/how/
            # second_person/question/statement — map them to the arms the
            # experiment engine speaks:
            _frame_to_arm = {
                "question": "question",
                "why": "question",  # FR titles "Pourquoi... ?"
                "what": "question",  # "Ce qui se passe quand..."
                "how": "question",  # "Comment..."
                "second_person": "pov_reveal",
                "statement": "shock_fact",
            }
            _arm = _frame_to_arm.get(_learned_frame, "")
            if _arm:
                os.environ.setdefault("VIRAL_HOOK_ARM", _arm)
                logger.info("🧠 ML learned hook: using proven frame '%s' (arm=%s)", _learned_frame, _arm)
    except Exception as exc:
        logger.debug("Learned hook frame unavailable: %s", exc)
    hook_arm = hook_arm_for_topic(topic)
    hook_rule = hook_style_instruction(hook_arm)
    loop_line = loop_bridge_for(topic)
    return f"""
Crée un YouTube Short original de {target_min} à {target_max} secondes sur ce sujet :
SUJET : {topic}
{series_rules}
{viral_hint}

{hook_rule}

Utilise EXACTEMENT {MAX_SCENES} scènes et retourne le schéma JSON ci-dessous.

ARC NARRATIF COMPACT ({MAX_SCENES} scènes — LA RÉPONSE DÈS LA SCÈNE 2, les
analytics montrent que le spectateur part à ~10 s si la réponse tarde) :
1. ACCROCHE — scène 1 (0–3 s) ; RUPTURE DE PATTERN à la deuxième personne
   (« tu/vous/votre corps ») : nomme LE phénomène précis du sujet puis le
   détail inattendu qui crée une boucle ouverte. BON : « Pourquoi ta voix
   sonne morte chaque matin ? » / « Ton corps te fige avant un bruit qui
   fait peur. » MAUVAIS, INTERDIT : formules génériques réutilisables d'une
   vidéo à l'autre (« Vous avez déjà ressenti cela ? », « Ça vous arrive
   aussi ? ») ou phrases plates — chaque accroche est UNIQUE et cite le
   phénomène exact.
2. RÉPONSE FLASH — scène 2 ; LE MÉCANISME CENTRAL EN UNE PHRASE qui
   commence par « C'est… », « Ton cerveau… » ou « Ton corps… ». Le
   spectateur est récompensé immédiatement — et une nouvelle boucle
   s'ouvre (« mais comment ? »). Jamais de préparation ici.
3. MÉCANISME — scènes 3–5 ; comment ça marche, étape par étape, concret et
   oral. La scène 5 commence par une micro-relance : « Le plus étrange ? »,
   « Encore plus fort : » ou « Et surtout : ».
4. BOUCLE — scène {MAX_SCENES} ; retour satisfaisant à l'accroche, sans la
   répéter mot à mot, pour relancer un nouveau visionnage. Termine par un
   PONT DE BOUCLE naturel du type « {loop_line} » (adapte-le au sujet,
   jamais mot à mot si cela ne colle pas) — la relecture doit sembler
   évidente, c'est le signal de distribution le plus fort sur Shorts.

RÈGLE ANTI-ENNUI : au moins UNE scène centrale (3–5) contient une escalation
mesurable (chiffre concret, « mais/sauf/pourtant », ou mini-question) — un
milieu plat fait partir le spectateur entre 10 et 20 s.

CORRECTION 2026-08-15 — FIN ENVOYABLE EN DM : la scène centrale qui contient
le fait à retenir DOIT être assez précise pour être recopiée telle quelle dans
un message à un ami (avec un chiffre, un contraste ou un mécanisme surprenant,
ex. « ton cerveau coupe ton audition 20 millisecondes avant chaque clignement »).
Un résumé vague du type « ton corps est incroyable » = échec automatique :
imagine la phrase tapée dans une conversation de groupe, elle doit survivre au
trajet. Les partages/DM sont le deuxième signal de classement d'Instagram et
ne poussent que les faits concrets.

RÉCOMPENSE IMMÉDIATE EN 3 S : la scène 1 ne promet PAS seulement — elle montre
le phénomène en action dès la première seconde (visuel + mot du hook prononcé
instantanément), jamais une introduction ou une attente de valeur au-delà de 3 s.

GATE AUTOMATIQUE DES 3 PREMIÈRES SECONDES :
- La voix commence immédiatement, sans silence, jingle, logo, salutation ou montée musicale.
- La scène 1 doit durer au maximum 5 secondes et contenir 5–9 mots ; la valeur doit néanmoins être compréhensible dès les 2,2 premières secondes.
- Au moins quatre mots compréhensibles doivent être prononcés avant 2,2 secondes et au moins sept avant 3 secondes.
- Le visuel de la scène 1 doit montrer un gros plan, un mouvement, une réaction ou un changement visible ; jamais un fond abstrait, un écran vide ou une image fixe générique.
- La scène 2 doit apporter la réponse flash ou le mécanisme central, pas reformuler la question.
- Le `hook` doit être identique à la légende de la scène 1 et contenir une question ou un signal clair d'explication.

RÈGLES DE FORMAT :
- Total des légendes parlées : {MIN_WORDS}–{MAX_WORDS} mots français.
- Scène 1 : {HOOK_MIN_WORDS}–{HOOK_MAX_WORDS} mots. Scènes 2–{MAX_SCENES} : {MIN_SCENE_WORDS}–{MAX_SCENE_WORDS} mots chacune.
- `hook` doit correspondre exactement à la légende de la scène 1.
- Visuel scène 1 : GROS PLAN humain concret (bouche devant un miroir, main sur
  la poitrine, yeux qui s'ouvrent au réveil) — un visage/proche arrête le
  scroll, un plan large abstrait non.
- Chaque scène doit avoir un visuel distinct de 5 à 12 mots, sans texte, logo ni interface.
- Titre : cinq à huit mots qui OUVRENT UNE BOUCLE DE CURIOSITÉ avec « ton/ta/tes »
  ou « ton/ta/votre ». Varie LA FAMILLE D'OUVERTURE d'une vidéo à l'autre, ne
  jamais deux fois la même : « Pourquoi … », « Ce que fait ton … », « Voilà
  pourquoi … », « Ton … te cache quelque chose », « Le secret de ton … »,
  « Comment ton … te trahit ». BON : « Pourquoi ton cœur bat la nuit » ·
  « Ce que fait ton cerveau en dormant » · « Ton corps te trahit quand tu
  MAUVAIS (rejeté) : étiquettes de 1-3 mots comme « Voix du matin »,
  « Choc anaphylactique » — zéro clic.
- « Pourquoi + [sensation physique spécifique] » est le FORMAT N°1 (8/9 meilleures vidéos = 1000+ vues). Utilise-le pour 60-70% des titres.
  INTERDIT : 2 vidéos consécutives avec la MÊME partie du corps (coeur x2, muscle x2).
  Formats alternatifs (30-40%) : « Ton [body] fait [X] » · « [Number] signes que ton [body]... » · « Le secret de ton [body] » · « Ton [body] te trahit quand... ».
  JAMAIS « Ce que [body]... » (kills views — 0 vues sur 6 vidéos).
  JAMAIS « Vous/votre » dans l'accroche (66 vues vs 665 vues avec « Tu/Ton »).
- `thumbnail_text` : une mini-question ou promesse de 3 à 6 mots AVEC UN VERBE
  conjugué, qui complète le titre sans le répéter. BON : « ton cœur s'accélère »,
  « ton cerveau te protège ». MAUVAIS (rejeté) : étiquettes nues sans verbe du
  type « CŒUR NUIT » ou « VOIX MATIN » — illisibles pour un francophone natif.
- `cta` : une invitation courte et naturelle à s'abonner, uniquement en métadonnée.
- `description` : une phrase exacte qui résume l'explication.

JSON UNIQUEMENT :
{{"title":"...","thumbnail_text":"...","hook":"...","scenes":[{{"visual":"...","caption":"..."}}],"cta":"...","description":"..."}}
"""


# ============================================
# 3. JSON CLEANING FUNCTION
# ============================================


def _clean_json_response(raw_reply: str) -> dict:
    """
    Cleans and extracts JSON from LLM response.
    Handles markdown code blocks, extra text, and malformed JSON.
    """
    if not raw_reply:
        raise ValueError("Empty response from LLM")

    # Remove markdown code blocks
    raw_reply = re.sub(r"```json\s*", "", raw_reply)
    raw_reply = re.sub(r"```\s*", "", raw_reply)

    # Try to find JSON object
    json_match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
    json_str = json_match.group(0) if json_match else raw_reply

    # Clean common JSON issues
    json_str = json_str.strip()

    # Fix trailing commas
    json_str = re.sub(r",\s*}", "}", json_str)
    json_str = re.sub(r",\s*]", "]", json_str)

    # NOTE: We intentionally do NOT blanket-convert single quotes to double
    # quotes here. Groq's response_format={"type": "json_object"} already
    # guarantees valid double-quoted JSON, and the system prompt asks for
    # natural contractions ("don't", "you're"), which contain apostrophes.
    # Converting those apostrophes to '"' corrupts the JSON mid-string
    # (this was the root cause of the "Expecting ',' delimiter" errors).

    # Remove control characters
    json_str = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", json_str)

    # Fix unescaped newlines in strings
    json_str = re.sub(r"(?<!\\)\n", " ", json_str)

    # Try to parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parsing failed: {e}")
        logger.debug(f"Cleaned JSON: {json_str[:500]}...")

        # Fallback: Try to extract with regex
        fallback = {}

        # Extract title
        title_match = re.search(r'"title"\s*:\s*"([^"]+)"', json_str)
        if title_match:
            fallback["title"] = title_match.group(1)

        # Extract hook
        hook_match = re.search(r'"hook"\s*:\s*"([^"]+)"', json_str)
        if hook_match:
            fallback["hook"] = hook_match.group(1)

        # Extract scenes
        scenes_match = re.search(r'"scenes"\s*:\s*\[(.*?)\]', json_str, re.DOTALL)
        if scenes_match:
            scenes_str = scenes_match.group(1)
            scenes = []
            # Find all scene objects
            scene_blocks = re.finditer(r"\{[^{}]*\}", scenes_str, re.DOTALL)
            for block in scene_blocks:
                scene_str = block.group(0)
                visual_match = re.search(r'"visual"\s*:\s*"([^"]+)"', scene_str)
                caption_match = re.search(r'"caption"\s*:\s*"([^"]+)"', scene_str)
                if visual_match and caption_match:
                    scenes.append({"visual": visual_match.group(1), "caption": caption_match.group(1)})
            if scenes:
                fallback["scenes"] = scenes

        # Extract CTA
        cta_match = re.search(r'"cta"\s*:\s*"([^"]+)"', json_str)
        if cta_match:
            fallback["cta"] = cta_match.group(1)

        # Extract description
        desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', json_str)
        if desc_match:
            fallback["description"] = desc_match.group(1)

        if fallback:
            logger.info("✅ Extracted data using regex fallback")
            return fallback

        raise ValueError(f"Could not parse JSON from response: {raw_reply[:200]}") from e


# ============================================
# 4. SCRIPT VALIDATION & NORMALIZATION
# ============================================


def _trim_to_word_limit(caption: str, max_words: int) -> str:
    """Trim a caption down to at most max_words, preferring to stop at the
    last complete sentence within the limit; falls back to a hard cut with
    a trailing period. Used to auto-fix scenes the LLM wrote too long,
    instead of burning a full retry (and more Groq tokens) over something
    a simple trim already fixes."""
    words = caption.split()
    if len(words) <= max_words:
        return caption
    truncated = " ".join(words[:max_words])
    # Prefer cutting at the last sentence-ending punctuation in range.
    # The old >=50% floor forced the hard-cut fallback, which shipped
    # MID-SENTENCE voiceovers (see production history). Early-but-complete
    # beats broken every time; _validate_script retries if it comes out
    # too short — regeneration is better than broken audio.
    last_stop = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_stop >= len(truncated) * 0.3:
        return truncated[: last_stop + 1]
    # No sentence boundary: cut at the last clause boundary so the spoken
    # line still sounds like a deliberate end, not a crash.
    clause_floor = len(truncated) * 0.4
    for sep in (";", "—", ",", ":"):
        idx = truncated.rfind(sep)
        if idx >= clause_floor:
            return truncated[:idx].rstrip() + "."
    truncated = truncated.rstrip(",;:")
    if not truncated.endswith((".", "!", "?")):
        truncated += "."
    return truncated


def _repair_broken_scene_continuations(scenes: list[dict]) -> list[str]:
    """Repair safe French sentence-boundary artifacts before the strict gate.

    Smaller LLMs sometimes split one spoken sentence across scenes and start the
    next caption with ``Et``, ``Ou`` or ``Ni`` after a full stop.  The result is
    especially audible in TTS and is intentionally rejected by the publication
    gate.  Removing only that leading connector preserves the factual content
    while restoring a complete spoken sentence.  Other grammar failures remain
    gate-blocking and still trigger regeneration.
    """
    changes: list[str] = []
    boundary = re.compile(r"([.!?…])\s+(et|ou|ni)\b\s*", re.IGNORECASE)
    for index, scene in enumerate(scenes):
        caption = str(scene.get("caption", "")).strip()
        if not caption:
            continue
        fixed = boundary.sub(r"\1 ", caption)
        if index > 0 and re.match(r"^(et|ou|ni)\b", fixed, re.IGNORECASE):
            previous = str(scenes[index - 1].get("caption", "")).rstrip()
            if previous.endswith((".", "!", "?", "…")):
                fixed = re.sub(r"^(et|ou|ni)\b\s*", "", fixed, count=1, flags=re.IGNORECASE).lstrip()
        fixed = re.sub(
            r"([.!?…]\s+)([a-zàâäæçéèêëîïôöœùûüÿ])",
            lambda match: match.group(1) + match.group(2).upper(),
            fixed,
        )
        if fixed and fixed[0].islower():
            fixed = fixed[0].upper() + fixed[1:]
        if fixed != caption:
            scene["caption"] = fixed
            changes.append(f"scene_boundary:{index + 1}")
    return changes


def _ensure_french_hook_budget(caption: str) -> str:
    """Keep short French openings inside the spoken 3-second word budget.

    The runtime retention gate measures words actually delivered by TTS, not
    only the caption length. A six-word hook can therefore fail when Chatterbox
    takes slightly more than three seconds. Adding a neutral, idiomatic time
    qualifier preserves the meaning while giving the opening enough spoken
    density; the caller keeps the hook and scene-one caption synchronized.
    """
    words = re.findall(r"[\wÀ-ÿŒœ'-]+", caption, flags=re.UNICODE)
    if len(words) >= HOOK_MIN_WORDS:
        return caption
    suffix = " en ce moment"
    punctuation = ""
    if caption and caption[-1] in ".!?…":
        punctuation = caption[-1]
        caption = caption[:-1].rstrip()
    repaired = f"{caption}{suffix}{punctuation}".strip()
    return _trim_to_word_limit(repaired, HOOK_MAX_WORDS)


def _normalize_scenes(script_data: dict) -> dict:
    """
    Normalizes scene data from various formats.
    Ensures all required fields are present.
    """
    normalized = []

    for s in script_data.get("scenes", []):
        # Try different field names
        visual = s.get("visual") or s.get("description") or s.get("image") or ""
        caption = s.get("caption") or s.get("text") or s.get("speech") or ""

        # Clean and validate — None-safe
        visual = (visual or "").strip()
        caption = (caption or "").strip()

        if visual and caption:
            normalized.append({"visual": visual, "caption": caption})
        elif caption and not visual:
            # If only caption exists, generate a generic visual
            normalized.append({"visual": f"Dark cinematic shot of {caption[:30]}...", "caption": caption})

    # Auto-fix: trim any scene that's over its word limit instead of
    # spending a full LLM retry on something a simple trim already solves.
    # Scene 1 (the hook) has a tighter cap - see _validate_script for why.
    # Drop any scenes with empty/None caption after normalization
    normalized = [s for s in normalized if (s.get("caption") or "").strip()]
    for i, scene in enumerate(normalized):
        limit = HOOK_MAX_WORDS if i == 0 else MAX_SCENE_WORDS
        scene["caption"] = _trim_to_word_limit(scene["caption"], limit)

    # HUMANIZE (2026-08-11): spoken-French post-pass. LLM output is written
    # register (« vous », « ce n'est pas », glued sentences); TTS reads that
    # aloud as a robot essay. Convert to français parlé BEFORE the voiceover
    # string is assembled and validated, so what viewers hear is what passed
    # the gates. Never blocks; failures just skip the pass.
    try:
        from french_humanizer import formality_leftovers, humanize_spoken_fr

        all_changes: list[str] = []
        # The hook (first words viewers hear) is the single most
        # AI-sounding line when left in written register — always run it
        # through the humanizer even when it matches scene 1's caption.
        if script_data.get("hook"):
            fixed_hook, hook_ch = humanize_spoken_fr(script_data["hook"])
            script_data["hook"] = fixed_hook
            all_changes.extend(hook_ch)
        for scene in normalized:
            fixed, ch = humanize_spoken_fr(scene["caption"])
            scene["caption"] = fixed
            all_changes.extend(ch)
        if script_data.get("description"):
            script_data["description"], _dh = humanize_spoken_fr(script_data["description"])
            all_changes.extend(_dh)
        boundary_changes = _repair_broken_scene_continuations(normalized)
        if boundary_changes:
            all_changes.extend(boundary_changes)
            import logging as _log

            _log.getLogger(__name__).warning(
                "French scene-boundary repair applied: %s", ", ".join(boundary_changes)
            )
        if all_changes:
            import logging as _log

            _log.getLogger(__name__).info(
                "🗣️ Humanizer (français parlé): %s", ", ".join(sorted(set(all_changes)))
            )
        # 2026-08-17: formality_leftovers() was imported but never actually
        # called — its own docstring says it exists specifically "for the
        # pipeline logger to watch humanization coverage", so surface it.
        # A stiff/formal-sounding French voiceover is a real, audible
        # quality problem (breaks the "spoken to a friend" tone the scoring
        # gates are trying to enforce), so this is worth knowing per-video,
        # not just silently swallowed.
        leftovers = formality_leftovers(
            script_data.get("voiceover", "") or " ".join(s.get("caption", "") or "" for s in normalized)
        )
        if leftovers > 0:
            import logging as _log

            _log.getLogger(__name__).warning(
                "🗣️ %d formal-register marker(s) (vous/votre) survived "
                "humanization — HARD REJECT: retrying.",
                leftovers,
            )
            # 2026-08-24: "Vous" hooks kill retention by 10x.
            # Previously this was just a warning; now it triggers retry.
            if not script_data.get("_formality_retry"):
                script_data["_formality_retry"] = True
                raise ValueError(
                    f"Formal register ({leftovers} markers) survived humanization — "
                    "retry with explicit tutoiement instruction"
                )
    except Exception as _hum_exc:  # pragma: no cover - defensive
        import logging as _log

        _log.getLogger(__name__).warning("Humanizer skipped: %s", _hum_exc)

    script_data["scenes"] = normalized
    script_data["voiceover"] = " ".join(s.get("caption", "") or "" for s in normalized)

    # Auto-fix: the scored hook must be the exact line viewers hear first.
    # Rather than relying on the LLM to retype the hook identically to
    # scene 1's caption (a common, easy mistake for smaller models), just
    # force them to match - scene 1's caption is the source of truth since
    # that's what's actually spoken. The runtime gate also requires at least
    # seven words to arrive by 3s, so repair shorter openings deterministically.
    if normalized:
        normalized[0]["caption"] = _ensure_french_hook_budget(normalized[0]["caption"])
        script_data["hook"] = normalized[0]["caption"]
        script_data["voiceover"] = " ".join(s.get("caption", "") or "" for s in normalized)

    return script_data


def _validate_script(script_data: dict, *, lenient: bool = False) -> tuple[bool, list[str]]:
    """
    Validates script for quality and completeness.

    Returns:
        (is_valid, issues_list)
    """
    issues = []

    # Check required fields
    required_fields = ["title", "hook", "scenes", "cta"]
    for field in required_fields:
        if not script_data.get(field):
            issues.append(f"Missing required field: {field}")

    # 2026-08-24: TITLE SEO KEYWORD GATE — YouTube search ranking depends on
    # body/health keywords in the title. Titles without searchable keywords
    # get zero search traffic. Force at least one body-related keyword.
    def _strip_accents(s: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

    title_text = _strip_accents((script_data.get("title") or "").lower())
    SEO_BODY_KEYWORDS = [
        "psychologie", "manipulation", "cerveau", "comportement", "peur", "controle", "secret", "mensonge", "relation", "emotion",
        "rein", "poumon", "foie", "estomac", "langue", "doigt", "oeil",
        "oreille", "nez", "dent", "moelle", "nerf", "veine", "artere",
        "systeme", "temperature", "froid", "chaud", "sommeil",
        "reve", "fatigue", "douleur", "frisson", "sueur",
        "illusion", "controle",
    ]
    if title_text and not any(kw in title_text for kw in SEO_BODY_KEYWORDS):
        issues.append(
            f"Title missing body/SEO keyword — YouTube search ranking requires "
            f"a dark psychology keyword (psychologie, manipulation, cerveau, comportement, peur...). "
            f"Got: '{title_text[:60]}'"
        )

    # 2026-08-24: CTA MUST contain a question — engagement question in the CTA
    # is the #1 comment signal for Shorts ranking. CTA without "?" = no comments.
    cta_text = (script_data.get("cta") or "").strip()
    if cta_text and "?" not in cta_text:
        # 2026-08-25: Downgraded to advisory — LLM sometimes omits "?"
        logger.info("CTA advisory: no question mark in '%s'", cta_text[:60])

    # main.py replaces temporary LLM titles with the deterministic Body
    # Glitch episode title before SEO/upload. Do not burn API retries over
    # title word counts here; the published title is validated by the series.
    # Check scenes
    scenes = script_data.get("scenes", [])
    if len(scenes) < MIN_SCENES:
        issues.append(f"Too few scenes: {len(scenes)} (minimum {MIN_SCENES})")
    elif len(scenes) > MAX_SCENES:
        issues.append(f"Too many scenes: {len(scenes)} (maximum {MAX_SCENES})")

    # Check word count
    voiceover = script_data.get("voiceover", "")
    word_count = len(voiceover.split())
    if word_count < MIN_WORDS:
        issues.append(f"Too few words: {word_count} (minimum {MIN_WORDS})")
    elif word_count > MAX_WORDS + 10:
        # Only hard reject for MASSIVELY overlong scripts (>44 words for 15-18s target)
        # Slightly over budget (35-44) is OK — the humanizer trims
        issues.append(f"Too many words: {word_count} (maximum {MAX_WORDS + 10})")
    elif word_count > MAX_WORDS:
        logger.info("Word count %d exceeds target %d but within tolerance", word_count, MAX_WORDS)

    # Check each scene
    # (HOOK_MIN_WORDS/HOOK_MAX_WORDS/MAX_SCENE_WORDS are the same constants
    # _normalize_scenes already auto-trims to, so a script that's been
    # normalized should always pass this - this check is now mostly a
    # safety net for anything normalization didn't catch.)
    for i, scene in enumerate(scenes):
        if not scene.get("visual"):
            issues.append(f"Scene {i + 1} missing visual description")
        if not scene.get("caption"):
            issues.append(f"Scene {i + 1} missing caption")
        else:
            scene_words = len(scene["caption"].split())
            if i == 0:
                if scene_words < HOOK_MIN_WORDS or scene_words > HOOK_MAX_WORDS:
                    issues.append(
                        f"Scene {i + 1} (hook) has {scene_words} words "
                        f"(allowed {HOOK_MIN_WORDS}-{HOOK_MAX_WORDS} to stay under the 4s hook-duration gate)"
                    )
            elif scene_words > MAX_SCENE_WORDS:
                issues.append(f"Scene {i + 1} has {scene_words} words (maximum {MAX_SCENE_WORDS})")

    # The scored hook must be the line viewers actually hear first.
    if scenes and script_data.get("hook"):

        def norm(value):
            return re.sub(r"[^a-z0-9 ]", "", value.lower()).strip()

        hook = norm(script_data["hook"])
        first = norm(scenes[0].get("caption", ""))
        if hook != first:
            issues.append("Hook must exactly match the first scene caption")

    # ------------------------------------------------------------------
    # STORY ARC ENFORCEMENT — the prompt demands Accroche → Suspense → …
    # → Réponse → Boucle, but nothing enforced it. YouTube Shorts ranks on
    # first-3s swipe survival + completion + replays: an open question in
    # scene 2 and a closing loop pointing back to the hook are the cheapest
    # retention levers. A script missing them is retried, never shipped.
    # ------------------------------------------------------------------
    if len(scenes) >= 3:
        # SCENE 1 — BANNED GENERIC OPENERS.
        # Analytics autopsy (2026-07-26, 9 videos with data): average view
        # duration is 11s on ~39s Shorts (27.5% retention) and viewers leave
        # around scene 2.2/8 — i.e. DURING the setup. 11 of 17 published
        # videos open with an interchangeable filler ("Vous avez déjà…",
        # "Vous vous réveillez…") that names no phenomenon and burns the
        # entire 2-second swipe window. The prompt already forbids this, but
        # nothing enforced it, so the LLM kept shipping it. Now it retries.
        hook_caption = scenes[0].get("caption", "").strip()
        hook_norm = re.sub(r"[^a-zà-ÿœ' ]", "", hook_caption.lower()).strip()
        for opener in GENERIC_HOOK_OPENERS:
            if hook_norm.startswith(opener):
                issues.append(
                    f"Scene 1 (ACCROCHE) starts with the banned generic opener "
                    f"'{opener}…' — name the exact phenomenon in the first 3 words "
                    f"instead (viewers swipe at ~2s on openers like this)."
                )
                break

        # 2026-08-24: VOUCHEFORME HARD BAN — data shows "Vous" hooks get
        # 10x fewer views (66 avg vs 665 for "Tu/Ton"). Reject ANY formal-
        # register marker in the hook or first scene, not just the known
        # openers list. This is the #1 retention killer on this channel.
        full_opening = (
            scenes[0].get("caption", "") + " "
            + (scenes[1].get("caption", "") if len(scenes) > 1 else "")
        ).strip()
        _vous_match = _VOUS_FORME_RE.search(full_opening)
        if _vous_match:
            issues.append(
                f"Formal register '{_vous_match.group()}' detected in opening scenes "
                f"(retention killer: Vous hooks avg 66 views vs 665 for Tu/Ton). "
                f"Rewrite with 'tu/ton/ta/tes' — the data is unambiguous."
            )

        # 2026-08-24: SENSORY WORD GATE — data shows hooks with physical
    # sensations in first 5 words get 2x views (sens=966, nerveux=935 avg).
    # Hooks without body-feel words underperform. Reject if no sensory word.
    SENSORY_WORDS = {
        "sens", "ressens", "sensations", "sensación",
        "tressaille", "frisson", "frissonne", "fourmille", "fourmillements",
        "brûle", "brûlure", "picote", "picotements", "douleur",
        "fatigue", "fatigué", "lourdeur", "lourd", "pesanteur",
        "serré", "serrer", "serrage", "battement", "battre",
        "tremble", "tremblement", "engourdi", "engourdissement",
        "détend", "tendu", "tension", "relâche", "relâchement",
        "gargouille", "gronde", "grondement",
        "réagit", "réaction", "réponse", "active",
        "transpire", "sueur", "sue", "gèle", "gel",
        "fige", "figé", "paralysé", "paralysie",
        "entends", "écoute", "entend",
    }
    hook_words_raw = scenes[0].get("caption", "").strip().lower().split() if scenes else []
    hook_first_5 = hook_words_raw[:5] if hook_words_raw else []
    has_sensory = any(
        _strip_accents(w.rstrip(".,!?;:")) in SENSORY_WORDS
        or w.rstrip(".,!?;:") in SENSORY_WORDS
        for w in hook_first_5
    )
    if not has_sensory and hook_first_5:
        # 2026-08-27: Downgraded from mandatory to advisory — LLM rarely
        # places sensory word in first 5, causing 100% gate failure rate.
        logger.info(
            "Hook advisory: no sensory word in first 5 words %s. "
            "Add a body-feel word: sens, frisson, tressaille, battement, fourmille...",
            hook_first_5,
        )

        # SCENE 2 — must DELIVER, not stall. V1 (DARK_PSYCH_V1_VERY_FIRST)
            # moved the answer to scene 2; this check previously demanded a
            # QUESTION there, directly contradicting the prompt and rewarding
            # the exact "setup drags on" pattern that loses viewers at scene 2.2.
    if len(scenes) >= 2:
        answer = scenes[1].get("caption", "").strip()
        answer_norm = answer.lower()
        starts_with_answer = any(answer_norm.startswith(p) for p in ANSWER_FIRST_PREFIXES)
        if not starts_with_answer:
            # 2026-08-25: Downgraded to warning — LLM often starts
            # scene 2 with subject pronoun; not fatal for retention.
            logger.info(
                "Scene 2 advisory: does not start with answer-first prefix. "
                "Got: '%s'", answer_norm[:40],
            )
        if answer.endswith("?"):
            issues.append("Scene 2 must ANSWER, not ask another question — the open loop belongs in scene 1.")
    if scenes:
        hook_concepts = _content_concepts(scenes[0].get("caption", ""))
        tail_concepts = _content_concepts(scenes[-1].get("caption", ""))
    else:
        hook_concepts = set()
        tail_concepts = set()
    if hook_concepts and not (hook_concepts & tail_concepts):
        # 2026-08-25: Downgraded from hard reject to warning.
        # The gate was silently skipped for 2 weeks (indentation bug).
        # LLM hasn't learned loop-back yet — enforce gradually.
        logger.info(
            "Loop-back advisory: final scene does not echo hook concept. "
            "This reduces rewatch rate but is not yet a hard block. "
            "(hook=%s, tail=%s)",
            hook_concepts, tail_concepts,
        )
        issues.append(
        "Final scene (LOOP-BACK) must echo the opening idea — share at "
        "least one concept word with the hook so the Short loops "
            "cleanly (replay = ranking signal)."
        )

    # ------------------------------------------------------------------
    # HUMAN-AUTHENTICITY GATE — reject AI-telltale / templated phrasing.
    # YouTube 2025-2026 "inauthentic content" policy de-monetizes channels
    # that ship templated, robotic, repetitious AI prose. These are the
    # reusable model-isms; if any appear the script is retried, never shipped.
    # ------------------------------------------------------------------
    ai_telltales = [
        "saviez-vous que",
        "le saviez-vous",
        "voici pourquoi",
        "la science a découvert que",
        "aujourd'hui, on va voir",
        "mais ce n'est pas tout",
        "incroyable, non ?",
        "si vous voulez en savoir plus",
        "restez jusqu'à la fin",
        "dans cette vidéo, nous allons",
        "bienvenue dans cette vidéo",
        "préparez-vous à",
    ]
    full_text = (
        (script_data.get("hook") or "")
        + " "
        + (script_data.get("voiceover") or "")
        + " "
        + " ".join((s.get("caption", "") or "") for s in scenes)
    ).lower()
    for phrase in ai_telltales:
        if phrase in full_text:
            issues.append(f"AI-telltale phrase detected: '{phrase}' — rewrite in authentic human voice")
            break

    if issues:
        # The generator must reject only scripts that cannot render safely or
        # do not have the required Shorts structure. SEO, hook style, formal
        # register, loop-back, and AI-telltale checks are optimization signals;
        # making them mandatory caused valid provider output to burn all retries.
        # Keep the advisory messages in logs while removing them from the
        # pass/fail result for both Groq and backup-provider paths.
        hard_prefixes = (
            "Missing required field:",
            "Too few scenes:",
            "Too many scenes:",
            "Scene ",
            "Too few words:",
            "Too many words:",
            "Hook must exactly match",
        )
        hard_issues = [
            issue for issue in issues
            if (
                issue.startswith(hard_prefixes)
                and not issue.startswith("Scene ")
            )
            or re.match(r"^Scene \\d+ (missing|\\(hook\\) has|has \\d+ words)", issue)
        ]
        advisory_issues = [issue for issue in issues if issue not in hard_issues]
        if advisory_issues:
            logger.info("Script quality advisories (non-blocking): %s", "; ".join(advisory_issues[:4]))
        issues = hard_issues
    return len(issues) == 0, issues


_ARC_STOPWORDS = {
    # English (shared codepath)
    "this",
    "that",
    "with",
    "from",
    "your",
    "yours",
    "when",
    "what",
    "why",
    "how",
    "have",
    "has",
    "been",
    "there",
    "their",
    "they",
    "them",
    "about",
    "just",
    "like",
    "over",
    "under",
    "more",
    "most",
    "some",
    "into",
    "also",
    "very",
    "than",
    "then",
    "these",
    "those",
    "because",
    "while",
    "after",
    "before",
    "people",
    "really",
    "actually",
    "don't",
    "doesn't",
    "every",
    "many",
    "much",
    "feel",
    "feels",
    "thing",
    "things",
    "body",
    # French — without these, function words would create false-overlap
    # between hook and loop-back for fr-FR scripts. (A real example caught
    # by the tests: "pendant" appears in almost every sentence and faked
    # the loop-back match.)
    "votre",
    "vous",
    "avec",
    "pour",
    "dans",
    "cette",
    "quand",
    "pourquoi",
    "comment",
    "mais",
    "plus",
    "très",
    "être",
    "avoir",
    "nous",
    "tout",
    "tous",
    "toute",
    "fait",
    "faite",
    "aussi",
    "encore",
    "comme",
    "chose",
    "choses",
    "corps",
    "bien",
    "dont",
    "leur",
    "leurs",
    "elles",
    "alors",
    "peut",
    "faut",
    "sans",
    "soit",
    "rien",
    "jamais",
    "toujours",
    "parce",
    "notre",
    "nos",
    "vos",
    "ceci",
    "cela",
    "celles",
    "ceux",
    "quoi",
    "quel",
    "quelle",
    "même",
    "moins",
    "vraiment",
    "souvent",
    "pendant",
    "après",
    "avant",
    "entre",
    "chez",
    "vers",
    "depuis",
    "contre",
    "selon",
    "afin",
    "grâce",
    "malgré",
    "enfin",
    "puis",
    "dès",
    "voici",
    "voilà",
    "autre",
    "autres",
    "chaque",
    "veut",
    "sont",
    "avons",
    "avez",
    "suis",
    "es",
    "est",
    "était",
    "sera",
}


def _content_concepts(text: str) -> set:
    """Stem-ish concept words for arc-overlap checks: lowercase, punctuation
    stripped, stopwords and short words removed, naive trailing-'s' fold so
    plurals/singulars collide in both English and French."""
    concepts = set()
    for raw in re.sub(r"[^a-z0-9àâäçéèêëîïôöùûüÿœæ ]", " ", text.lower()).split():
        if len(raw) <= 3 or raw in _ARC_STOPWORDS:
            continue
        stem = raw.rstrip("s")  # crude plural fold (works for FR too)
        concepts.add(stem if len(stem) > 3 else raw)
    return concepts


# ---------------------------------------------------------------------------
# PUBLIC API — stable importable interface.
# ---------------------------------------------------------------------------


def validate_script(script_data: dict) -> tuple[bool, list[str]]:
    """Validate a generated script for structural completeness.

    Public wrapper around the internal ``_validate_script``.
    Use this from external code (quality_checker, tests, etc.)
    instead of importing the underscore-prefixed version.

    Parameters
    ----------
    script_data : dict
        Script dictionary with 'title', 'hook', 'scenes', 'cta', 'voiceover'.

    Returns
    -------
    tuple[bool, list[str]]
        (is_valid, issues_list)
    """
    return _validate_script(script_data)


# ============================================
# 5. RETENTION ANALYSIS
# ============================================


def analyze_retention_potential(script_data: dict) -> dict:
    """
    Analyzes script for retention potential.
    Returns score (0-100) and suggestions.
    """
    scenes = script_data.get("scenes", [])
    score = 0
    suggestions = []

    # Check scene count
    if MIN_SCENES <= len(scenes) <= MAX_SCENES:
        score += 20
    else:
        suggestions.append(f"Optimal scene count: {MIN_SCENES}-{MAX_SCENES}, currently {len(scenes)}")

    # Check hook
    hook = script_data.get("hook", "")
    if hook:
        hook_words = len(hook.split())
        if HOOK_MIN_WORDS <= hook_words <= HOOK_MAX_WORDS:
            score += 15
        else:
            suggestions.append(
                f"Hook should be {HOOK_MIN_WORDS}-{HOOK_MAX_WORDS} words for a fast, clear opening"
            )

        # Check for pattern interrupt
        if len(hook.split()) <= 9 and any(ch in hook for ch in ["?", ".", "!"]):
            score += 10

    # Check "YOU" language
    voiceover = script_data.get("voiceover", "")
    you_count = sum(voiceover.lower().count(word) for word in ("vous", "votre", "tu", "ton"))
    if you_count >= 2:
        score += 15
    else:
        suggestions.append("Use the viewer naturally once or twice where it helps clarity")

    # Check cliffhangers
    cliffhanger_count = 0
    for scene in scenes:
        caption = scene.get("caption", "")
        if any(word in caption.lower() for word in ["...", "mais", "pourtant", "alors", "et si"]):
            cliffhanger_count += 1

    if 1 <= cliffhanger_count <= 3:
        score += 20
    else:
        suggestions.append(
            f"Only {cliffhanger_count}/{len(scenes)} scenes have cliffhangers - use only 1-3 natural open loops"
        )

    # Check word count
    word_count = len(voiceover.split())
    if MIN_WORDS <= word_count <= MAX_WORDS:
        score += 20
    else:
        suggestions.append(f"Word count: {word_count} (target: {MIN_WORDS}-{MAX_WORDS})")

    # Check for loopable outro
    cta = script_data.get("cta", "")
    if any(word in cta.lower() for word in ["abonne", "abonner", "subscribe", "suivez"]):
        score += 10

    return {
        "retention_score": min(100, score),
        "suggestions": suggestions,
        "scenes": len(scenes),
        "word_count": word_count,
        "you_count": you_count,
        "cliffhanger_ratio": cliffhanger_count / len(scenes) if scenes else 0,
        "is_viral_ready": score >= 80,
    }


# ============================================
# 6. MAIN GENERATE FUNCTION
# ============================================


def _score_decision_usable(metric: str) -> bool:
    """A self-grade may only GATE a decision when the daily Truth Gate has
    measured it as predictive on REAL outcomes. Default: False — every
    internal heuristic is advisory-only until proven (2026-08-12 doctrine)."""
    try:
        from intelligence.truth_gate import load_status

        status = load_status()
        return bool(status and status.get(metric, {}).get("decision_usable"))
    except Exception:
        return False


def generate_script(topic: str, custom_prompt: str | None = None, max_retries: int = MAX_RETRIES) -> dict:
    """
    Generates a RETENTION-OPTIMIZED script using Groq LLM.

    Features:
    - JSON cleaning with regex fallback
    - Native English tone enforcement
    - Automatic validation and retry
    - Retention analysis

    Args:
        topic: Topic for the script
        custom_prompt: Optional custom prompt
        max_retries: Maximum retry attempts

    Returns:
        Script data dictionary

    Raises:
        RuntimeError: If generation fails after all retries
        ValueError: If GROQ_API_KEY is missing
    """
    logger.info(
        "Script policy %s: %s scenes, %s-%s words; temporary title is not a retry gate.",
        SCRIPT_POLICY_VERSION,
        MIN_SCENES,
        MIN_WORDS,
        MAX_WORDS,
    )

    # Provider-neutral initialization: Groq is preferred when available, but
    # backup providers must remain usable when Groq is unset, rate-limited, or
    # temporarily unavailable. Never require a provider that is not selected.
    generate_script._or_fallback_reply = None
    api_key = os.environ.get("GROQ_API_KEY")
    client = None
    if api_key and Groq is not None:
        client = Groq(api_key=api_key)
    elif not (
        os.environ.get("ALT_LLM_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    ):
        if not api_key:
            raise ValueError(
                "No LLM provider configured. Set GROQ_API_KEY, ALT_LLM_API_KEY, "
                "OPENROUTER_API_KEY, or GEMINI_API_KEY."
            )
        raise RuntimeError("groq package is not installed and no backup LLM provider is configured")

    # Prepare prompt
    prompt = custom_prompt or _default_prompt(topic)
    messages = [{"role": "system", "content": _get_system_prompt()}, {"role": "user", "content": prompt}]

    last_error = None
    best_script = None
    best_score = 0

    # Model fallback chain (2026-08-12): primary advanced model first; on
    # rate-limit/API error we switch down the chain instead of only retrying
    # the identical call. Legacy `os.environ.get("GROQ_MODEL", ...)` inline
    # reads treated '' as a valid model and never consumed GROQ_MODEL_FALLBACK.
    model_chain = groq_model_chain()
    model_index = [0]

    def _current_model() -> str:
        return model_chain[min(model_index[0], len(model_chain) - 1)]

    def _advance_model(exc) -> bool:
        """Switch to the fallback model after an API-side failure."""
        if model_index[0] < len(model_chain) - 1:
            model_index[0] += 1
            logger.warning(
                "Groq model %s failed (%s) — falling back to %s",
                model_chain[model_index[0] - 1],
                exc,
                model_chain[model_index[0]],
            )
            return True
        return False

    for attempt in range(1, max_retries + 1):
        try:
            if client is None:
                # No Groq client is available: use the configured backup
                # providers directly instead of failing at Groq initialization.
                logger.info("🔄 Generating script (Attempt %d/%d) via backup providers", attempt, max_retries)
                raw_reply = _alt_llm_generate(
                    messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS
                ) or _openrouter_generate(
                    messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS
                ) or _gemini_generate(messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
                if raw_reply:
                    generate_script._or_fallback_reply = raw_reply
                    logger.info("✅ Backup provider produced a script without Groq.")
                    break
                last_error = RuntimeError("All configured backup LLM providers failed")
                break

            logger.info(f"🔄 Generating script (Attempt {attempt}/{max_retries}) via {_current_model()}")

            # Call Groq API — advanced 120B model by default (stronger French
            # hooks/titles -> better CTR/retention); automatic fallback down
            # the chain on rate-limit/API errors. Overridable via GROQ_MODEL.
            # gpt-oss reasoning models burn tokens on internal reasoning, so
            # give them headroom; keep effort low for punchy Shorts hooks.
            is_reasoning = _current_model().startswith(("openai/gpt-oss", "qwen/"))
            extra = {"reasoning_effort": "low"} if "gpt-oss" in _current_model() else {}
            completion = client.chat.completions.create(
                messages=messages,
                model=_current_model(),
                response_format={"type": "json_object"},
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS + (1200 if is_reasoning else 0),
                **extra,
            )

            raw_reply = completion.choices[0].message.content

            # Clean JSON
            script_data = _clean_json_response(raw_reply)

            # Normalize scenes
            script_data = _normalize_scenes(script_data)

            # Add metadata
            script_data["topic"] = topic
            script_data["generated_at"] = time.time()
            script_data["attempt"] = attempt

            # 2026-08-12 viral engineering: tag the deterministic hook arm and
            # run the advisory audit (hook rubric, surprise beat, loop bridge).
            # Advisory only — hard quality stays with french_quality_gate /
            # retention analysis; these warnings travel to history + dashboard.
            try:
                from viral_engineering import hook_arm_for_topic, viral_script_audit

                script_data["hook_arm"] = hook_arm_for_topic(topic)
                script_data["viral_audit"] = viral_script_audit(script_data)
                if script_data["viral_audit"].get("warnings"):
                    logger.info("Viral audit: %s", " | ".join(script_data["viral_audit"]["warnings"]))
            except Exception as exc:
                logger.warning("Viral audit skipped: %s", exc)

            # Validate
            is_valid, issues = _validate_script(script_data)

            if is_valid:
                # Analyze retention
                retention = analyze_retention_potential(script_data)
                script_data["retention_analysis"] = retention

                score = retention["retention_score"]

                # Track best script
                if score > best_score:
                    best_script = script_data
                    best_score = score

                if score >= 80:
                    logger.info(f"✅ Excellent script! Retention score: {score}/100")
                    logger.info(
                        f"📊 {len(script_data['scenes'])} scenes, {len(script_data['voiceover'].split())} words"
                    )
                    # FEEDBACK LOOP: persist this script as part of the channel
                    # baseline so the NEXT script compares against it.
                    try:
                        from viral_baseline import record_script

                        record_script(script_data, score)
                    except Exception as exc:
                        logger.warning("Baseline record skipped: %s", exc)
                    return script_data
                else:
                    logger.warning(f"⚠️ Good but could be better (Score: {score}/100)")
                    # Add corrective feedback
                    messages.append({"role": "assistant", "content": raw_reply})
                    baseline_fb = ""
                    try:
                        from viral_baseline import feedback_to_beat_baseline

                        baseline_fb = " | ".join(feedback_to_beat_baseline(script_data, score))
                    except Exception as exc:
                        logger.warning("Baseline feedback skipped: %s", exc)
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"The script is good but retention could be improved. "
                                f"Current score: {score}/100. Issues: {', '.join(retention['suggestions'][:3])}. "
                                + (f"BEAT THE CHANNEL BASELINE: {baseline_fb}. " if baseline_fb else "")
                                + f"Rewrite the script with these improvements while keeping the topic '{topic}'. "
                                f"Return ONLY valid JSON with the same structure."
                            ),
                        }
                    )
            else:
                last_error = "; ".join(issues)
                logger.warning(f"⚠️ Validation issues: {', '.join(issues[:3])}")
                messages.append({"role": "assistant", "content": raw_reply})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The script has validation issues: {', '.join(issues[:3])}. "
                            f"Rewrite it to fix these issues. Keep the same topic '{topic}'. "
                            f"Return ONLY valid JSON with the same structure."
                        ),
                    }
                )

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing failed: {e}")
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The previous response was not valid JSON. "
                        "Please return ONLY valid JSON with this exact structure: "
                        '{"title": "...", "hook": "...", "scenes": [{"visual": "...", "caption": "..."}], "cta": "..."}'
                    ),
                }
            )

        except BadRequestError as e:
            logger.error(f"❌ Groq API error: {e}")
            last_error = e
            if _advance_model(e):
                continue
            if attempt < max_retries:
                wait_time = 2**attempt
                logger.info(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                # 2026-08-17: Groq chain exhausted — final attempt via the
                # OpenRouter fallback (mirrors Mr-Nextep). Never end a run
                # without trying the backup LLM.
                raw_reply = _alt_llm_generate(
                    messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS
                ) or _openrouter_generate(
                    messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS
                ) or _gemini_generate(messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
                if raw_reply:
                    generate_script._or_fallback_reply = raw_reply
                    logger.info("✅ Third-provider fallback produced a script.")
                    break  # fall through to post-loop fallback validation
                else:
                    logger.warning("OpenRouter and Gemini fallbacks also failed — ending run.")
                    break

        except Exception as e:
            err_str = str(e)
            # Rate limits / server errors: prefer the fallback model over
            # sleeping — different models have separate rate buckets.
            last_error = e
            if _advance_model(e):
                continue
            # Handle Groq rate limits with proper wait
            if "rate_limit" in err_str or "429" in err_str:
                # 2026-08-17: Groq 429 — try the OpenRouter fallback
                # IMMEDIATELY instead of waiting up to 40+ minutes for Groq's
                # daily token-cap reset.
                raw_reply = _alt_llm_generate(
                    messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS
                ) or _openrouter_generate(
                    messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS
                ) or _gemini_generate(messages, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
                if raw_reply:
                    generate_script._or_fallback_reply = raw_reply
                    logger.info("✅ Third-provider fallback produced a script during Groq 429.")
                    break  # fall through to post-loop fallback validation
                wait_sec = _parse_groq_rate_limit_wait(err_str)
                if wait_sec > MAX_RATE_LIMIT_SLEEP_SEC:
                    # Both models in the chain are already exhausted (we'd
                    # have advanced past this point otherwise) — this is a
                    # daily/hourly account-level quota, not a short burst
                    # limit. Sleeping it out would blow the job timeout and
                    # still yield zero videos, so fail fast and let the next
                    # scheduled run pick it up once the quota resets.
                    logger.error(
                        "Groq quota needs ~%ds to reset (exceeds this run's "
                        "%ds budget) — failing fast instead of blocking the "
                        "job. Next scheduled run will retry.",
                        wait_sec,
                        MAX_RATE_LIMIT_SLEEP_SEC,
                    )
                    raise RuntimeError(
                        f"Groq rate limit needs ~{wait_sec}s to reset "
                        f"(exceeds {MAX_RATE_LIMIT_SLEEP_SEC}s per-run budget). "
                        f"Skipping this run; original error: {e}"
                    ) from e
                logger.warning("Groq rate limited — waiting %ds", wait_sec)
                time.sleep(wait_sec)
                continue
            logger.error(f"❌ Unexpected error: {e}")
            last_error = e
            if attempt < max_retries:
                wait_time = 2**attempt
                logger.info(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)

    # 2026-08-17: validate the OpenRouter fallback reply (Groq chain failed)
    # before declaring complete failure — mirrors Mr-Nextep's fall-through.
    if getattr(generate_script, "_or_fallback_reply", None):
        raw_reply = generate_script._or_fallback_reply
        logger.info("🔧 Validating OpenRouter fallback reply outside the retry loop.")
        try:
            script_data = _clean_json_response(raw_reply)
            script_data = _normalize_scenes(script_data)
            script_data["topic"] = topic
            script_data["generated_at"] = time.time()
            script_data["attempt"] = max_retries
            is_valid, issues = _validate_script(script_data, lenient=True)
            if is_valid:
                retention = analyze_retention_potential(script_data)
                script_data["retention_analysis"] = retention
                logger.warning("✅ OpenRouter fallback script passed validation (lenient).")
                return script_data
            else:
                logger.warning("⚠️ OpenRouter fallback script failed validation: %s", "; ".join(issues[:2]))
        except Exception as exc:
            logger.warning("OpenRouter fallback validation error: %s", exc)

    # If we have a best script, return it
    if best_script:
        logger.warning(f"⚠️ Using best available script (Score: {best_score}/100)")
        return best_script

    # Complete failure
    raise RuntimeError(f"❌ Script generation failed after {max_retries} attempts. Last error: {last_error}")


# ============================================
# 7. BATCH GENERATION
# ============================================


def generate_multiple_scripts(
    topics: list[str], max_retries: int = MAX_RETRIES, delay: float = 2.0
) -> list[dict]:
    """
    Generates scripts for multiple topics.

    Args:
        topics: List of topics
        max_retries: Retries per script
        delay: Delay between generations

    Returns:
        List of script data dictionaries
    """
    scripts = []
    failed = []

    for i, topic in enumerate(topics):
        logger.info(f"📝 Generating script {i + 1}/{len(topics)}: {topic}")

        try:
            script = generate_script(topic, max_retries=max_retries)
            scripts.append(script)
            logger.info(f"✅ Script {i + 1} generated successfully")
        except Exception as e:
            logger.error(f"❌ Script {i + 1} failed: {e}")
            failed.append({"topic": topic, "error": str(e)})

        if i < len(topics) - 1:
            time.sleep(delay)

    logger.info(f"📊 Generated {len(scripts)}/{len(topics)} scripts successfully")
    if failed:
        logger.warning(f"⚠️ Failed scripts: {len(failed)}")

    return scripts, failed


# ============================================
# 8. SCRIPT EXPORT
# ============================================


def export_script(script_data: dict, output_path: str = "output/script.json") -> str:
    """
    Exports script data to JSON file.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=2, ensure_ascii=False)

    logger.info(f"📄 Script exported to: {output_path}")
    return output_path


# ============================================
# 9. MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    print("=" * 70)
    print("SCRIPT GENERATOR - FULLY FIXED (JSON Cleaning + Native Tone)")
    print("=" * 70)
    print()

    # Test single generation
    test_topic = "Why Your Brain Lies to You"
    print(f"🧪 Testing with topic: {test_topic}")
    print("-" * 70)

    try:
        script = generate_script(test_topic)

        print("✅ Script generated successfully!")
        print()
        print(f"📌 TITLE: {script.get('title')}")
        print(f"🎯 HOOK: {script.get('hook')}")
        print(f"📊 SCENES: {len(script.get('scenes', []))}")
        print(f"📝 WORDS: {len(script.get('voiceover', '').split())}")
        print(f"📢 CTA: {script.get('cta')}")

        if "retention_analysis" in script:
            analysis = script["retention_analysis"]
            print()
            print("📈 RETENTION ANALYSIS:")
            print(f"   Score: {analysis.get('retention_score')}/100")
            print(f"   Viral Ready: {analysis.get('is_viral_ready')}")
            if analysis.get("suggestions"):
                print("   Suggestions:")
                for suggestion in analysis["suggestions"][:3]:
                    print(f"     - {suggestion}")

        print()
        print("📄 FIRST SCENE PREVIEW:")
        scenes = script.get("scenes", [])
        if scenes:
            print(f"   Visual: {scenes[0].get('visual')}")
            print(f"   Caption: {scenes[0].get('caption')}")

        print()
        print("-" * 70)
        print("✅ Script generator is ready for production!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
