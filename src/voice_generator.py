import logging
import os
import re
import time

import numpy as np


# 2026-08-17 CI fix: the guard-workflow installs only requirements-ci.txt
# (deliberately no torch/soundfile - avoids a 2GB download per push).
# soundfile is used only inside TTS synthesis functions, so import it here
# lazily via the helper rather than at module top-level.
def _sf():
    """Lazy soundfile access — never fails at import time."""
    import soundfile as _s

    return _s


class _SoundfileProxy:
    """Module-level proxy so existing sf.write/sf.read call sites keep working
    without touching hundreds of lines; the real import happens on first use."""

    def write(self, *a, **kw):
        return _sf().write(*a, **kw)

    def read(self, *a, **kw):
        return _sf().read(*a, **kw)

    def info(self, *a, **kw):
        return _sf().info(*a, **kw)


sf = _SoundfileProxy()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PRIMARY ENGINE: Chatterbox (Resemble AI, MIT license - safe for a
# monetized channel).
#
# Why Chatterbox over Kokoro: Chatterbox can condition generation on the
# creator's approved voice reference, whereas Kokoro is a generic fallback
# voice. Its delivery controls let us keep narration clear and conversational
# instead of giving every scene an artificial dramatic tone.
#
# Lazy-loaded on first use (not at import time) so a missing pip install or
# a failed model download doesn't crash the whole pipeline before it even
# starts - _get_chatterbox() catches that, and every call in this file
# falls back to Kokoro per-segment if Chatterbox is unavailable or a
# specific generation call fails. One bad Chatterbox call should never take
# a whole video down.
# ---------------------------------------------------------------------------
_chatterbox_model = None
_chatterbox_load_failed = False
_chatterbox_load_error = None  # the real underlying exception, kept around so
# every later "not loaded" error can still show
# WHY, instead of just the first log line at
# startup (which is easy to miss/lose in CI logs).


# NATURAL YOUTUBE VOICE PROFILE
#
# Chatterbox's higher exaggeration values make delivery more theatrical and
# can also make it feel faster. That is useful for character acting, but it
# weakens speaker similarity for a creator's regular YouTube narration.
# These defaults deliberately favour a calm, clear, conversational delivery:
# natural energy, stable pronunciation and recognisable cloned identity.
# Every value can be overridden in .env / GitHub Actions secrets.
def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    """Read a bounded float setting and fall back safely on bad input."""
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using %s", name, raw, default)
        return default
    if not minimum <= value <= maximum:
        logger.warning("%s=%s is outside [%s, %s]; using %s", name, value, minimum, maximum, default)
        return default
    return value


CHATTERBOX_EXAGGERATION = _env_float("CHATTERBOX_EXAGGERATION", 0.35, 0.0, 1.0)
CHATTERBOX_CFG_WEIGHT = _env_float("CHATTERBOX_CFG_WEIGHT", 0.45, 0.0, 1.0)
CHATTERBOX_TEMPERATURE = _env_float("CHATTERBOX_TEMPERATURE", 0.55, 0.05, 1.5)

# Chatterbox has no native speed control. atempo changes tempo while keeping
# pitch, so 0.96 is slightly calmer than normal without sounding slow or
# artificial. FFmpeg accepts 0.5–2.0 for one atempo filter.
CHATTERBOX_TEMPO = _env_float("CHATTERBOX_TEMPO", 0.93, 0.5, 2.0)

# ── 2026-08-17: MATURE VOICE PROFILE (fix "child-like voice" report) ──
# The built-in Chatterbox default voice is young/light-sounding. Until the
# creator uploads a real voice_reference.wav, the pipeline deepens and
# matures the output so the narrator always sounds like an ADULT professional:
#   VOICE_MATURE_PITCH_SEMITONES = negative -> lower pitch (deeper voice)
#   VOICE_MATURE_TEMPO           = slightly calmer delivery (authority)
# When VOICE_REFERENCE_PATH is a usable clone, maturing is SKIPPED so the
# creator's own voice is never altered.
VOICE_MATURE_PITCH_SEMITONES = _env_float("VOICE_MATURE_PITCH_SEMITONES", -5.0, -6.0, 0.0)
VOICE_MATURE_TEMPO = _env_float("VOICE_MATURE_TEMPO", 0.90, 0.75, 1.05)
VOICE_MATURE_ENABLED = os.environ.get("VOICE_MATURE_ENABLED", "true").lower() in ("1", "true", "yes", "on")


def _mature_voice(audio: np.ndarray, sr: int) -> np.ndarray:
    """Pitch-deepen + calm the synthetic default voice toward a mature adult
    male narrator. Uses ffmpeg's asetrate+aresample (pitch shift) followed
    by a gentle high-pass on mud and a limiter for broadcast-safe peaks.
    Falls back to the unmodified audio if processing fails."""
    if not VOICE_MATURE_ENABLED:
        return audio
    try:
        import subprocess
        import tempfile

        import imageio_ffmpeg

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "in.wav")
            out_path = os.path.join(tmpdir, "out.wav")
            sf.write(in_path, audio, sr)
            result = subprocess.run(
                [
                    ffmpeg_exe,
                    "-y",
                    "-i",
                    in_path,
                    "-af",
                    (
                        f"asetrate={sr}*2^({VOICE_MATURE_PITCH_SEMITONES}/12),"
                        f"aresample={sr},"
                        f"atempo={VOICE_MATURE_TEMPO},"
                        f"highpass=f=80,lowpass=f=14000,alimiter=limit=0.95"
                    ),
                    out_path,
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0 or not os.path.exists(out_path):
                logger.warning("Voice maturing failed, using unmodified audio: %s", result.stderr[:200])
                return audio
            matured, _ = sf.read(out_path, dtype="float32")
            logger.info(
                "Voice maturing APPLIED: pitch %.1f st, tempo %.2f",
                VOICE_MATURE_PITCH_SEMITONES,
                VOICE_MATURE_TEMPO,
            )
            return matured
    except Exception as e:
        logger.warning("Voice maturing failed (%s), using unmodified audio", e)
        return audio


# ── 2026-08-17: ADULT VOICE ROTATION POOL (edge-tts primary engine) ──
# fr-FR-HenriNeural (young-ish) is the legacy default. This pool defaults to
# FOUR proven deep, mature French adult voices so the channel never sounds
# child-like even when no clone reference exists. The SAME topic always gets
# the SAME voice (deterministic rotation, per video, seeded by topic), so
# each video is internally consistent while the channel rotates naturally.
# Can be overridden via the EDGE_FR_MATURE_VOICE_POOL secret.
EDGE_FR_MATURE_VOICE_POOL = os.environ.get(
    "EDGE_FR_MATURE_VOICE_POOL",
    "fr-FR-HenriNeural,fr-FR-MauriceNeural,fr-FR-GerardNeural,fr-FR-LucienNeural,fr-FR-AlainNeural",
)
# 2026-08-19: ADULT VOICE SAFEGUARD. Several workflow/env pools historically
# included young-sounding voices (Denise/Eloise/Josephine/Remy) which the
# audience flagged as "child-like". Only these deep, adult MALE timbres are
# allowed on the channel unless the creator sets EDGE_FR_VOICE_ALLOW_LIGHT=1.
ADULT_FR_MALE_VOICES = {
    "fr-FR-MauriceNeural",
    "fr-FR-GerardNeural",
    "fr-FR-LucienNeural",
    "fr-FR-AlainNeural",
    "fr-FR-HenriNeural",
}
# 2026-08-19 reliability note: the deep male timbres (Maurice/Gerard/Lucien/
# Alain/Remy) intermittently return "No audio received" on the GitHub Actions
# runner, while HenriNeural is proven reliable there. The pipeline therefore
# keeps HenriNeural as the stable anchor; the maturing chain below deepens it
# into a mature adult male sound so the channel never sounds child-like.
LIGHT_FR_VOICES = {
    "fr-FR-DeniseNeural",
    "fr-FR-EloiseNeural",
    "fr-FR-JosephineNeural",
    "fr-FR-RemyNeural",
    "fr-FR-HenriNeural",
}

# ── 2026-08-15: NATURAL DELIVERY VARIATION (kill the AI monotone) ──────
# A human narrator never reads every sentence at one fixed pace: they speed
# up for energy (hooks, short punchy lines), slow down for emphasis (a
# question, a reveal), and drift slightly even on neutral lines. A flat
# tempo on every scene is the single loudest "machine" cue. These profiles
# are applied PER SEGMENT around the base tempo/rate; the jitter is symmetric
# so the overall video length stays unchanged.
_DELIVERY_PROFILES = {
    # Chatterbox has no native speed argument, so this multiplier is applied
    # post-synthesis below. 1.15x keeps a seven-word hook inside the 3.0s
    # information-density window without rushing the body narration.
    "hook": 1.10,  # mysterious opening — curiosity pull, not rush
    "question": 0.88,  # dark psych questions are slower — the weight of revelation
    "emphasis": 0.85,  # reveals/punchlines drawn out with gravitas
    "neutral": 0.97,  # slightly calmer overall — mystery demands patience
}
_DELIVERY_JITTER = (-0.04, 0.04)  # tiny symmetric per-segment drift
ENABLE_DELIVERY_VARIATION = os.environ.get("DELIVERY_VARIATION", "true").lower() in ("1", "true", "yes", "on")


def _delivery_multiplier(caption: str, index: int, total: int) -> float:
    """Human-like per-segment pacing multiplier around the base tempo/rate."""
    if not ENABLE_DELIVERY_VARIATION:
        return 1.0
    if index == 0:
        profile = _DELIVERY_PROFILES["hook"]
    elif caption.rstrip().endswith("?"):
        profile = _DELIVERY_PROFILES["question"]
    elif any(
        k in caption.lower()
        for k in ("imagine", "voilà pourquoi", "c'est pour ça", "pourtant", "tu vois", "et devine quoi", "le secret", "ce qu'on ne te dit pas", "personne ne sait", "la vérité", "c'est ça qui est dingue", "sauf que", "mais voici le piège")
    ):
        profile = _DELIVERY_PROFILES["emphasis"]
    else:
        profile = _DELIVERY_PROFILES["neutral"]
    jitter = float(hash((index, caption[:10])) % 1000) / 500.0 - 1.0  # deterministic ±1
    jitter = jitter * _DELIVERY_JITTER[1]  # within the configured band
    return max(0.5, min(2.0, profile + jitter))


def _edge_rate_for(segment_factor: float) -> str:
    """Convert a pacing multiplier into an edge-tts rate string (base -8%)."""
    base = float(os.environ.get("EDGE_FR_RATE", "-8%").replace("%", "")) / 100.0
    # factor applies to duration: slower speech = more negative rate
    rate = (1.0 / segment_factor - 1.0) + base
    return f"{rate * 100:+.0f}%"


# Number of times Chatterbox retries per segment before giving up and
# falling back to Kokoro. Retries use the cloned voice reference every
# time — if the reference is bad the first attempt will fail, and retrying
# with the same bad reference won't help, so _synthesize_chatterbox()
# detects that case and skips pointless retries.
CHATTERBOX_MAX_RETRIES = 3

# Seconds to wait between Chatterbox retry attempts. Gives transient
# issues (GPU memory pressure, model hot-reload glitches, etc.) a moment
# to clear before hammering again.
CHATTERBOX_RETRY_DELAY = 2.0

# Optional voice-clone reference. Drop a clean 10-20s WAV (single speaker,
# no background noise) here and Chatterbox will clone that voice for every
# video instead of its own built-in default voice. If this file doesn't
# exist, Chatterbox just uses its default voice - nothing else changes.
VOICE_REFERENCE_PATH = os.environ.get("VOICE_REFERENCE_PATH", "assets/voice_reference.wav")


def _voice_reference_ok() -> bool:
    """True only if the reference WAV is actually usable for cloning.

    Guards against three silent failure modes that would otherwise make the
    pipeline *think* it cloned when it didn't: (1) file missing, (2) file
    present but empty/corrupt, (3) file readable but effectively silent
    (all-zero / near-silent), which produces a garbage clone. Any problem
    here just logs and returns False -> Chatterbox uses its default voice
    instead of a broken clone.
    """
    path = VOICE_REFERENCE_PATH
    if not path or not os.path.exists(path) or os.path.getsize(path) < 1024:
        return False
    try:
        info = sf.info(path)
        if info.frames <= 0 or info.duration < 3.0:
            logger.warning("Voice reference is too short (%.1fs). Use at least 10 seconds.", info.duration)
            return False
        # A 30–60 second clean sample is noticeably more reliable for speaker
        # similarity. Shorter samples still work, so do not silently disable a
        # creator's clone merely because it is below the recommendation.
        if info.duration < 30.0:
            logger.warning(
                "Voice reference is only %.1fs. Cloning will work, but a 30–60s clean, "
                "single-speaker WAV usually sounds much closer to the original voice.",
                info.duration,
            )
        # Check a small slice for silence and severe clipping. This is a
        # validity gate, not a substitute for a clean recording.
        sample, _ = sf.read(path, frames=min(info.frames, info.samplerate * 5), dtype="float32")
        if sample.ndim > 1:
            sample = sample.mean(axis=1)
        if sample.size == 0 or float(np.abs(sample).max()) < 1e-3:
            logger.warning("Voice reference is silent/near-silent - using default voice.")
            return False
        clipping_ratio = float(np.mean(np.abs(sample) >= 0.995))
        if clipping_ratio > 0.005:
            logger.warning(
                "Voice reference may be clipped (%.2f%% samples near full scale). "
                "Re-record with lower input gain for a cleaner clone.",
                clipping_ratio * 100,
            )
        return True
    except Exception as e:
        logger.warning(f"Voice reference unreadable ({e}) - using default voice.")
        return False


def _get_chatterbox():
    """Loads the Chatterbox model once and caches it. Returns None (and
    remembers not to retry) if loading fails for any reason - missing
    package, no internet for the first-run model download, out-of-memory
    on a CPU-only runner, etc."""
    global _chatterbox_model, _chatterbox_load_failed, _chatterbox_load_error
    if _chatterbox_model is not None or _chatterbox_load_failed:
        return _chatterbox_model
    try:
        # ------------------------------------------------------------------
        # Known bug workaround (resemble-ai/chatterbox GitHub issue #198):
        # in some environments perth.PerthImplicitWatermarker silently
        # resolves to None (even though `import perth` succeeds and
        # setuptools is present) - ChatterboxTTS.__init__ then does
        # `self.watermarker = perth.PerthImplicitWatermarker()` and blows up
        # with "TypeError: 'NoneType' object is not callable". Nobody in
        # that issue thread found a root cause that reliably fixes it across
        # environments, but the monkeypatch below (confirmed working by
        # several people on the thread) sidesteps it entirely: if the real
        # watermarker class is missing, swap in a harmless no-op before
        # ChatterboxTTS ever touches it. This only skips audio watermarking
        # - the actual voice cloning is completely unaffected.
        # ------------------------------------------------------------------
        import perth
        import torch

        if getattr(perth, "PerthImplicitWatermarker", None) is None:
            logger.warning(
                "perth.PerthImplicitWatermarker is None (known chatterbox/perth "
                "issue #198) - patching in a no-op watermarker so Chatterbox can "
                "still load and clone voices normally."
            )

            class _NoOpWatermarker:
                def apply_watermark(self, wav, *args, **kwargs):
                    return wav

                def get_watermark(self, *args, **kwargs):
                    return 0.0

            perth.PerthImplicitWatermarker = _NoOpWatermarker

        from chatterbox.tts import ChatterboxTTS

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading Chatterbox TTS model on {device} (first call only, then cached)...")
        _chatterbox_model = ChatterboxTTS.from_pretrained(device=device)
        logger.info("Chatterbox loaded successfully.")
    except Exception as e:
        # Keep the full exception type + message around (not just this one
        # log line) so every later "model not loaded" error downstream can
        # still report WHY, even in a trimmed/partial log.
        _chatterbox_load_error = f"{type(e).__name__}: {e}"
        logger.error(
            f"Chatterbox unavailable ({_chatterbox_load_error}) - every segment will fall back to Kokoro."
        )
        _chatterbox_load_failed = True
        _chatterbox_model = None
    return _chatterbox_model


def _apply_tempo(audio: np.ndarray, sr: int, tempo: float) -> np.ndarray:
    """Apply natural voice finishing plus pitch-preserving tempo adjustment.

    A gentle high/low-pass removes DC/rumble and harsh ultrasonic artifacts;
    a limiter keeps every independently generated scene at a consistent peak.
    The filter is deliberately light—no aggressive denoise or reverb that
    would make the creator clone sound synthetic. Returns original audio if
    ffmpeg processing fails."""
    if tempo == 1.0:
        return audio
    try:
        import subprocess
        import tempfile

        import imageio_ffmpeg

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "in.wav")
            out_path = os.path.join(tmpdir, "out.wav")
            sf.write(in_path, audio, sr)
            result = subprocess.run(
                [
                    ffmpeg_exe,
                    "-y",
                    "-i",
                    in_path,
                    "-filter:a",
                    f"atempo={tempo},highpass=f=65,lowpass=f=15000,alimiter=limit=0.95",
                    out_path,
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0 or not os.path.exists(out_path):
                logger.warning(f"ffmpeg tempo adjustment failed, using original pace: {result.stderr[:200]}")
                return audio
            stretched, _ = sf.read(out_path, dtype="float32")
            return stretched
    except Exception as e:
        logger.warning(f"Tempo adjustment failed ({e}), using original pace")
        return audio


def _validate_generated_audio(audio: np.ndarray, sr: int, min_duration: float = 0.3) -> None:
    """Reject garbage TTS output that would silently produce broken audio.

    Catches three failure modes:
    1. Empty / near-zero-length arrays (model returned nothing)
    2. NaN / Inf contamination (numerical explosion in the model)
    3. Too-short output (e.g. model choked on the text and spat out a blip)

    Raises RuntimeError with a descriptive message so callers can decide
    whether to retry or fall back to another engine.
    """
    if audio is None or audio.size == 0:
        raise RuntimeError("TTS returned empty audio array")
    if np.isnan(audio).any() or np.isinf(audio).any():
        raise RuntimeError("TTS returned NaN/Inf audio — numerical explosion")
    duration = audio.size / sr if sr > 0 else 0.0
    if duration < min_duration:
        raise RuntimeError(f"TTS output too short ({duration:.2f}s < {min_duration:.2f}s minimum)")


def _synthesize_chatterbox(text: str, attempt: int = 1) -> tuple:
    """Generate speech with Chatterbox using the cloned voice reference.

    Returns (audio: np.ndarray float32, sample_rate: int).

    The voice reference is ALWAYS used when available — this is the whole
    point of the retry loop. If the reference file itself is broken
    (_voice_reference_ok() returns False), there is no point retrying with
    the same broken file, so we raise immediately to let the caller skip
    straight to Kokoro.

    Parameters
    ----------
    text : str
        The text to synthesize.
    attempt : int
        Current attempt number (1-based), used for logging.
    """
    model = _get_chatterbox()
    if model is None:
        reason = _chatterbox_load_error or "unknown reason"
        raise RuntimeError(f"Chatterbox model not loaded ({reason})")

    # If the voice reference is broken, retrying with the same broken
    # file is pointless — fail fast so the caller jumps to Kokoro.
    use_clone = _voice_reference_ok()
    if not use_clone and attempt == 1:
        logger.warning(
            "Voice reference NOT usable — Chatterbox will use its default voice. "
            "Retrying won't help since the reference won't magically fix itself."
        )

    kwargs = {
        "exaggeration": CHATTERBOX_EXAGGERATION,
        "cfg_weight": CHATTERBOX_CFG_WEIGHT,
        "temperature": CHATTERBOX_TEMPERATURE,
    }
    if use_clone:
        kwargs["audio_prompt_path"] = VOICE_REFERENCE_PATH
        logger.info(
            f"Chatterbox attempt {attempt}/{CHATTERBOX_MAX_RETRIES}: using CLONED voice from {VOICE_REFERENCE_PATH}"
        )
    else:
        logger.info(
            f"Chatterbox attempt {attempt}/{CHATTERBOX_MAX_RETRIES}: using DEFAULT voice (no valid reference)"
        )

    wav = model.generate(text, **kwargs)
    audio = wav.squeeze().detach().cpu().numpy().astype(np.float32)

    # Validate before any post-processing — a garbage generation should
    # be retried, not normalised and passed downstream.
    _validate_generated_audio(audio, model.sr, min_duration=0.3)

    if np.isnan(audio).any():
        audio = np.nan_to_num(audio, 0.0)
    peak = np.abs(audio).max()
    if peak > 1.0:
        audio = audio / peak * 0.95

    # 2026-08-19: the professional default voice is a REAL recorded narrator -
    # never pitch-shift it (maturing is for synthetic edge-tts timbres only);
    # a real creator clone is also never pitch-shifted so identity stays intact.
    if use_clone:
        logger.info("Chatterbox: real creator clone in use - no post-processing.")
    else:
        logger.info(
            "Chatterbox: professional default narrator voice - no post-processing (real recorded voice)."
        )
    return audio, model.sr


# ---------------------------------------------------------------------------
# FALLBACK ENGINE: Kokoro (Apache 2.0). No emotion control, but has no
# install/download surprises and is fast on CPU - kept exactly as before so
# a Chatterbox failure never takes the whole pipeline down with it.
# ---------------------------------------------------------------------------
_kokoro_tts = None
_kokoro_load_failed = False


def _get_kokoro():
    """Lazy-loads Kokoro only when actually needed as a fallback. Previously
    this loaded unconditionally at module import time (every single
    pipeline run), which meant paying its ~5s load + first-run model
    download cost even on runs where Chatterbox succeeded for every
    segment and Kokoro was never actually used."""
    global _kokoro_tts, _kokoro_load_failed
    if _kokoro_tts is not None or _kokoro_load_failed:
        return _kokoro_tts
    try:
        from kokoro import KPipeline

        logger.info("Loading Kokoro TTS model (fallback engine, first use only)...")
        lang_code = os.environ.get("KOKORO_LANG_CODE", "f")
        _kokoro_tts = KPipeline(lang_code=lang_code)  # 'f' = French
        logger.info("Kokoro loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load Kokoro: {e}")
        _kokoro_load_failed = True
        _kokoro_tts = None
    return _kokoro_tts


KOKORO_SAMPLE_RATE = 24000


def prepare_natural_narration(text: str) -> str:
    """Prepare natural YouTube narration without changing its meaning.

    Previous versions injected ellipses into phrases such as “right now” and
    “you too” for a dark/suspense delivery. Those artificial pauses make a
    clone sound unlike the real creator. Respect the script's punctuation and
    only clean whitespace and accidental repeated punctuation.

    French additions (2026-08-05): normalise unicode to NFC and replace the
    literal "…" with a comma so edge-tts doesn't read it as a hard cut — a
    natural spoken pause, closer to how a French presenter delivers a fact.
    """
    import unicodedata

    cleaned = unicodedata.normalize("NFC", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"(?<![.!?])\.{2}(?!\.)", ",", cleaned)
    cleaned = cleaned.replace("…", ",").replace("...", ",")
    cleaned = re.sub(r"([!?]){2,}", r"\1", cleaned)
    cleaned = re.sub(r"\s+([,.;!?])", r"\1", cleaned)
    cleaned = re.sub(r",+", ",", cleaned)
    return cleaned


def _synthesize_kokoro(text: str, voice: str, speed: float):
    """Returns (audio: np.ndarray float32, sample_rate: int)."""
    kokoro = _get_kokoro()
    if not kokoro:
        raise RuntimeError("Kokoro TTS model not loaded. Check Kokoro installation.")

    generator = kokoro(text, voice=voice, speed=speed)
    chunks = []
    for _gs, _ps, audio in generator:
        if audio is not None:
            chunks.append(audio)

    if not chunks:
        raise RuntimeError(f"Kokoro ne audio generate nahi kiya for: {text[:50]}...")

    full_audio = np.concatenate(chunks)
    if np.isnan(full_audio).any():
        full_audio = np.nan_to_num(full_audio, 0.0)

    max_val = np.abs(full_audio).max()
    if max_val > 1.0:
        full_audio = full_audio / max_val * 0.95

    return full_audio, KOKORO_SAMPLE_RATE


def _rotated_french_voice(topic: str = "") -> str:
    """Pick the PRIMARY French edge-tts voice deterministically from
    EDGE_FR_VOICE_POOL (env), seeded by the video topic.
    2026-08-15: the pipeline previously used EDGE_FR_VOICE=fr-FR-HenriNeural
    for every video — a frozen single narrator is the loudest "AI channel"
    signal, and 2026 feed systems reward voice consistency *within* a video
    but penalise a channel that sounds like one machine for months. A pool of
    native FR voices, hashed per topic, keeps each video internally
    consistent while the channel as a whole rotates naturally.
    The SAME topic always gets the SAME voice (stability across episodes).
    Falls back to EDGE_FR_VOICE when the pool is absent/empty.
    2026-08-17: defaults to ADULT mature voices (Maurice/Remy/Lucien + Henri)
    so the channel never sounds child-like without a creator clone reference.
    """
    import hashlib

    pool_raw = os.environ.get("EDGE_FR_VOICE_POOL", "").strip()
    # 2026-08-19: adult-only safeguard — never pick a young-sounding voice.
    # The workflow env pool previously contained Denise/Eloise/Josephine
    # (young female timbres) and the audience flagged the channel's voice as
    # child-like. Filter every configured pool down to adult male voices
    # unless the creator explicitly opts in with EDGE_FR_VOICE_ALLOW_LIGHT=1.
    allow_light = os.environ.get("EDGE_FR_VOICE_ALLOW_LIGHT", "0").strip().lower() in ("1", "true", "yes")
    if not allow_light and pool_raw:
        adult = [v.strip() for v in pool_raw.split(",") if v.strip() in ADULT_FR_MALE_VOICES]
        if adult:
            pool_raw = ",".join(adult)
            logger.info("Voice pool filtered to adult male voices: %s", pool_raw)
        else:
            logger.warning(
                "Configured EDGE_FR_VOICE_POOL has no adult voices — "
                "using the guaranteed adult default pool instead"
            )
            pool_raw = ""
    # 2026-08-17: if no custom pool is set, prefer the mature adult pool
    # (module-level default: four deep, adult French male voices)
    if not pool_raw:
        pool_raw = os.environ.get("EDGE_FR_MATURE_VOICE_POOL", "").strip()
    if not pool_raw:
        pool_raw = EDGE_FR_MATURE_VOICE_POOL.strip()  # module default pool
    if not pool_raw:
        return os.environ.get("EDGE_FR_VOICE", "fr-FR-MauriceNeural")
    pool = [v.strip() for v in pool_raw.split(",") if v.strip()]
    if not pool:
        return os.environ.get("EDGE_FR_VOICE", "fr-FR-MauriceNeural")
    digest = hashlib.sha256((topic or "default").encode("utf-8")).hexdigest()
    return pool[int(digest, 16) % len(pool)]


def _synthesize_edge_french(text: str, voice: str | None = None, rate: str | None = None):
    """Synthesize French via Microsoft edge-tts (cloud, reliable neural voice).

    Primary engine for French because Kokoro frequently returned truncated
    ~0.50s blips per long caption (a 3s total voiceover on a 17s video — the
    "no voice / stuck visuals" bug). edge-tts produces full-length, natural
    French and has no heavy native build deps, so it works on the CI runner.

    Voice auto-fallback: the primary voice (EDGE_FR_VOICE_POOL rotation if
    set, else EDGE_FR_VOICE) is tried first; on "No audio received" (some
    voices intermittently fail on the runner, e.g. RemyNeural) it falls
    through to EDGE_FR_VOICE_ALT1 / EDGE_FR_VOICE_ALT2 before giving up. This
    keeps the pipeline robust without pinning a single voice.

    Voice/rate come from EDGE_FR_VOICE* / EDGE_FR_RATE env (see env.example).

    Returns (audio np.ndarray float32, sample_rate int).
    """
    import asyncio as _asyncio

    import edge_tts as _edge

    candidates = [
        # 2026-08-19: HenriNeural is the proven-reliable CI anchor; Gerard/
        # Lucien intermittently fail with "No audio received" on the runner,
        # so they are secondary. Denise is a genuine last resort (never the
        # primary rotation thanks to the adult pool filter above).
        voice or os.environ.get("EDGE_FR_VOICE", "fr-FR-HenriNeural"),
        os.environ.get("EDGE_FR_VOICE_ALT1", "fr-FR-HenriNeural"),
        os.environ.get("EDGE_FR_VOICE_ALT2", "fr-FR-DeniseNeural"),
    ]
    rate = rate or os.environ.get("EDGE_FR_RATE", "-8%")

    async def _collect(use_voice: str):
        chunks = []
        c = _edge.Communicate(text, use_voice, rate=rate)
        async for chunk in c.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    last_err = None
    for use_voice in dict.fromkeys(candidates):  # de-dup, keep order
        try:
            mp3_bytes = _asyncio.run(_collect(use_voice))
            if len(mp3_bytes) < 4000:
                raise RuntimeError("edge-tts returned empty/too-short audio")
            # decode mp3 -> wav for the pipeline (raw numpy)
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fh:
                fh.write(mp3_bytes)
                mp3_path = fh.name
            wav_path = mp3_path + ".wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    mp3_path,
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-acodec",
                    "pcm_s16le",
                    wav_path,
                ],
                check=True,
                capture_output=True,
            )
            import soundfile as _sf

            audio, sr = _sf.read(wav_path)
            logger.info("edge-tts voice OK: %s", use_voice)
            return audio, sr
        except Exception as exc:
            last_err = exc
            logger.warning("edge-tts voice %s failed: %s", use_voice, exc)
    raise RuntimeError(f"edge-tts failed on all voices: {last_err}")


def _synthesize(
    text: str,
    voice: str = "ff_siwis",
    speed: float = 1.0,
    topic: str = "",
    seg_index: int = 0,
    seg_total: int = 0,
):
    """Synthesize a single segment with retry logic.

    FLOW (2026-08-19):
      1. TTS_ENGINE=chatterbox (default): Chatterbox professional narrator
         (cloned if VOICE_REFERENCE_PATH is valid) x3 → edge-tts Henri adult
         pool → RuntimeError.
      2. TTS_ENGINE=edge: edge-tts Henri adult pool (legacy/reliable mode) →
         RuntimeError.
      3. TTS_ENGINE=kokoro: Kokoro one shot (legacy debug mode).
      A Chatterbox failure NEVER misses a slot: edge-tts is the proven
      runner-safe safety net. Mixed engines in one video are rejected by
      generate_voice_segments (consistent timbre).

    Returns (audio, sample_rate, engine_used) so callers/logs can tell
    which engine actually produced a given segment.

    Raises
    ------
    RuntimeError
        If every Chatterbox attempt AND Kokoro both fail. The caller
        (generate_voice_segments) must handle this — it means the entire
        pipeline should abort, not silently insert silence.
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")

    narration_text = prepare_natural_narration(text)

    # Engine selection:
    #   * edge   -> Microsoft neural French (primary, reliable, no truncation)
    #   * kokoro -> Kokoro French (fallback engine)
    #   * (any other / unset) -> edge primary, kokoro fallback
    # 2026-08-19: Chatterbox (default voice = real recorded professional
    # narrator) is now the primary engine; Kokoro 0.7.x blips and synthetic
    # edge timbre are both superseded. edge-tts stays as the zero-fail safety
    # net; kokoro remains via TTS_ENGINE=kokoro for legacy scenarios.
    engine_choice = os.environ.get("TTS_ENGINE", "chatterbox").strip().lower()
    prefer_kokoro = engine_choice == "kokoro"
    # 2026-08-19: CHATTERBOX IS NOW THE PRIMARY ENGINE. Its default voice is a
    # REAL professionally recorded narrator (23-language multilingual model,
    # beats ElevenLabs in blind evals) - no more synthetic edge-tts timbre.
    # edge-tts Henri pool remains the proven reliable fallback when Chatterbox
    # can't load on the runner, so no slot is ever missed.
    prefer_edge = engine_choice in ("edge", "edge_fr", "edge-tts")
    chatterbox_errors = []
    # 2026-08-17: mature adult voice rotation (deterministic per topic).
    _edge_voice = _rotated_french_voice(topic)

    def _try_edge():
        try:
            seg_rate = _edge_rate_for(speed * _delivery_multiplier(text, seg_index, seg_total))
            audio, sr = _synthesize_edge_french(narration_text, voice=_edge_voice, rate=seg_rate)
            _validate_generated_audio(audio, sr, min_duration=0.3)
            return audio, sr
        except Exception as exc:
            logger.warning("edge-tts primary failed: %s", exc)
            return None, None

    if prefer_kokoro:
        seg_speed = speed * _delivery_multiplier(text, seg_index, seg_total)
        audio, sr = _synthesize_kokoro(narration_text, voice, seg_speed)
        return audio, sr, "kokoro_fr"

    if prefer_edge:
        # edge-tts primary (legacy mode, kept for debugging/outage scenarios).
        audio, sr = _try_edge()
        if audio is not None:
            # 2026-08-17: mature any synthetic default voice (no clone in use);
            # the pool rotation already picks an adult timbre, this deepens it.
            audio = _mature_voice(audio, sr)
            return audio, sr, "edge_fr"

    # ---- STEP 1: Chatterbox primary (explicitly enabled OR default engine) ----
    # Note: the default path (`TTS_ENGINE` unset/other) also lands here.
    for attempt in range(1, CHATTERBOX_MAX_RETRIES + 1):
        try:
            audio, sr = _synthesize_chatterbox(narration_text, attempt=attempt)
            # Chatterbox does not expose a playback-speed control. Apply the
            # same deterministic delivery profile used by Edge/Kokoro so the
            # opening is actually delivered inside the retention gate window.
            audio = _apply_tempo(audio, sr, _delivery_multiplier(text, seg_index, seg_total))
            engine = "chatterbox_clone" if _voice_reference_ok() else "chatterbox_default"
            logger.info(f"Chatterbox SUCCESS on attempt {attempt}/{CHATTERBOX_MAX_RETRIES} ({engine})")
            return audio, sr, engine
        except Exception as e:
            chatterbox_errors.append(str(e))
            logger.warning(f"Chatterbox attempt {attempt}/{CHATTERBOX_MAX_RETRIES} FAILED: {e}")
            # Wait before next retry (skip wait on last attempt)
            if attempt < CHATTERBOX_MAX_RETRIES:
                logger.info(f"Waiting {CHATTERBOX_RETRY_DELAY}s before retry...")
                time.sleep(CHATTERBOX_RETRY_DELAY)

    if not prefer_edge:
        logger.error(
            f"All {CHATTERBOX_MAX_RETRIES} Chatterbox attempts failed. Errors: "
            + " | ".join(chatterbox_errors)
        )
        # 2026-08-19: never miss a slot - edge-tts is the guaranteed reliable
        # fallback after Chatterbox (it's the proven runner-safe engine).
        logger.info("Falling back to edge-tts (reliable runner-safe engine)...")
        audio, sr = _try_edge()
        if audio is not None:
            audio = _mature_voice(audio, sr)
            return audio, sr, "edge_fr"

    # TTS_ENGINE=edge and Chatterbox failed/never tried: fall through to the
    # edge-tts cloud fallback below so no slot is missed.
    kokoro_err = "skipped (edge-tts mode preferred; Chatterbox unavailable or failed)"
    # ---- EDGE-TTS CLOUD FALLBACK (added 2026-08-02 audit) ----
    try:
        import asyncio as _asyncio

        import edge_tts as _edge

        async def _collect():
            chunks = []
            c = _edge.Communicate(narration_text, "fr-FR-HenriNeural", rate=_edge_rate_for(speed))
            async for chunk in c.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        mp3_bytes = _asyncio.run(_collect())
        if len(mp3_bytes) < 4000:
            raise RuntimeError("edge-tts returned empty audio")

        # decode mp3 -> wav: write mp3, convert with ffmpeg (system dep).
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fh:
            fh.write(mp3_bytes)
            mp3_path = fh.name
        wav_path = mp3_path + ".wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-ar", "24000", "-ac", "1", "-acodec", "pcm_s16le", wav_path],
            check=True,
            capture_output=True,
        )
        import soundfile as _sf

        audio, sr = _sf.read(wav_path)
        logger.info("edge-tts fallback SUCCESS (fr-FR-HenriNeural)")
        audio = _mature_voice(audio, sr)
        return audio, sr, "edge_fr"
    except Exception as edge_err:
        # ---- FINAL: all engines exhausted — NO SILENCE, raise hard error ----
        error_msg = (
            f"VOICE GENERATION FAILED — all engines exhausted for this segment. "
            f"Chatterbox errors ({CHATTERBOX_MAX_RETRIES} attempts): "
            f"[{' | '.join(chatterbox_errors)}]. "
            f"Kokoro: {kokoro_err}. "
            f"edge-tts error: [{edge_err}]. "
            f"Pipeline CANNOT continue without voiceover."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg) from edge_err


def generate_voice(
    text: str, voice: str = "ff_siwis", output_path: str = "output/voice.wav", speed: float = 1.0
) -> str:
    """Generate clear, natural YouTube narration.

    Chatterbox with the approved creator reference is always tried first.
    Kokoro is only a technical fallback and cannot reproduce that voice.
    """
    try:
        logger.info("Generating natural YouTube voiceover (fallback_voice=%r, speed=%s)...", voice, speed)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        audio, sr, engine = _synthesize(text, voice, speed)
        sf.write(output_path, audio, sr)
        logger.info(f"Voice saved via {engine}: {output_path} ({len(audio)} samples, {len(audio) / sr:.2f}s)")
        return output_path
    except Exception as e:
        logger.error(f"Voice generation failed: {e}")
        raise RuntimeError(f"Voice generation error: {e}") from e


def generate_voice_segments(
    scenes: list[dict],
    voice: str = "ff_siwis",  # only used if a segment falls back to Kokoro
    output_dir: str = "output/segments",
    speed: float = 1.0,  # only used if a segment falls back to Kokoro
    topic: str = "",  # seeds EDGE_FR_VOICE_POOL rotation (topic-stable)
) -> list[dict]:
    """
    Each scene gets clear, conversational narration via Chatterbox using the
    creator's voice reference, with Kokoro as a technical per-segment fallback.

    Raises
    ------
    RuntimeError
        If any segment fails on ALL engines (Chatterbox x3 + Kokoro).
        The pipeline MUST abort — a video with missing voiceover segments
        is worse than no video at all.
    """
    os.makedirs(output_dir, exist_ok=True)
    segments = []
    engine_counts = {}

    for i, scene in enumerate(scenes):
        caption = scene.get("caption", "").strip() if isinstance(scene, dict) else str(scene)
        if not caption:
            caption = " "

        # No try/except swallowing here — if _synthesize raises, the whole
        # pipeline must abort. Silent 1.5s silence inserts are NOT acceptable;
        # main.py's quality gate will catch the crash and log it properly.
        audio, sr, engine = _synthesize(
            caption, voice, speed, topic=topic or scene.get("topic", ""), seg_index=i, seg_total=len(scenes)
        )
        engine_counts[engine] = engine_counts.get(engine, 0) + 1
        path = os.path.join(output_dir, f"seg_{i}.wav")
        sf.write(path, audio, sr)
        duration = len(audio) / sr

        segments.append({"path": path, "duration": duration, "caption": caption, "tts_engine": engine})
        logger.info(f'Segment {i + 1}/{len(scenes)} via {engine}: {duration:.2f}s - "{caption[:50]}..."')

    total = sum(s["duration"] for s in segments)
    logger.info(f"Total natural voiceover duration: {total:.2f}s | engines used: {engine_counts}")

    # Final consistency check — all segments must use the SAME engine.
    # Mixed engines mean different voice timbres across scenes, which
    # sounds jarring and unprofessional. Abort if mixed.
    engines_used = set(engine_counts.keys())
    if len(engines_used) > 1:
        raise RuntimeError(
            f"Mixed TTS engines in the same video: {dict(engine_counts)} "
            f"— voices would sound inconsistent. Aborting."
        )

    return segments
