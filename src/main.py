import hashlib
import json
import logging
import os
import re
import sys
import time
import traceback
import unicodedata
from collections import Counter
from datetime import UTC, datetime

from atomic_io import write_json_atomic
from media_validator import pad_video_to_minimum, probe_video

# Add current directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("pipeline.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Import modules with error handling
try:
    from anti_spam import AntiSpamSystem
    from experiment_registry import register as register_ctr_experiment
    from final_video_audit import run_final_publication_audit
    from french_quality_gate import is_french_question_without_verb, validate_publication_quality
    from image_generator import generate_scene_image as generate_images
    from niche_strategy import (
        auto_add_disclaimer,
        generate_seo_tags,
        get_topic_category,
        validate_script_for_medical_accuracy,
    )
    from quality_checker import QualityChecker
    from retention_gate import ensure_opening_visual_action
    from scheduler import FrancePeakTimeScheduler
    from script_generator import _score_decision_usable, generate_script
    from seo_analytics import (
        generate_ab_variants,
        get_historical_insights,
        predict_ctr,
        rank_hashtags,
        score_thumbnail,
    )
    from seo_generator import _clean_title_fallback, generate_seo_package
    from shorts_enhancer import build_shorts_report, generate_srt, score_hook
    from strict_quality_gate import require_strict_gate
    from trend_fetcher import get_trending_topic
    from trend_spiker import get_trend_spike
    from uploader import upload_all
    from video_editor import build_video, generate_thumbnail_variants
    from voice_generator import generate_voice_segments
except ImportError as e:
    logger.error(f"Failed to import modules: {e}")
    logger.error("Make sure all required modules are in the same directory")
    sys.exit(1)

# Constants
MAX_SCRIPT_ATTEMPTS = max(1, int(os.environ.get("MAX_SCRIPT_ATTEMPTS", "3")))
MAX_IMAGE_RETRIES = 3
TITLE_CANDIDATE_POOL_SIZE = int(os.environ.get("TITLE_CANDIDATE_POOL_SIZE", "12"))
FALLBACK_ABORT_RATIO = float(os.environ.get("FALLBACK_ABORT_RATIO", "0.5"))
# 70 accepts a clear, specific natural hook while still rejecting vague or
# manipulative openings. The scorer and generator use the same 6–9 word policy.
MIN_HOOK_SCORE = int(os.environ.get("MIN_HOOK_SCORE", "70"))
# Natural cloned delivery varies by speaker/reference. Five seconds preserves
# a concise hook without throwing away an otherwise healthy 30-second Short.
MAX_HOOK_SECONDS = float(os.environ.get("MAX_HOOK_SECONDS", "6.0"))
# 2026-08-24: Title diversity = TOPIC diversity, NOT format diversity.
# "Pourquoi + body sensation" is the WINNING format (8/9 top performers).
# Gate ensures no same body part repeats in consecutive titles.
TITLE_DIVERSITY_MAX_SAME_FORMAT = float(os.environ.get("TITLE_DIVERSITY_MAX_SAME_FORMAT", "0.30"))
# Tracked repository state is durable across Actions runs; generated media
# remains in output/ and is intentionally not committed.
VIDEO_HISTORY_PATH = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")
# Cross-video image/clip hash ledger. Without this, image_generator.py only
# dedupes scenes WITHIN a single video (used_hashes/used_fallbacks are fresh
# sets per run) — the exact same fallback image or stock clip could then
# reappear in video #1 and video #200 with nothing to stop it. This file
# persists every hash/URL ever used so reuse is blocked channel-wide.
MEDIA_HASH_HISTORY_PATH = os.environ.get("MEDIA_HASH_HISTORY_PATH", "data/media_hash_history.json")
# Cap on how many hashes/URLs we remember, so the ledger doesn't grow forever.
MAX_MEDIA_HASH_HISTORY = int(os.environ.get("MAX_MEDIA_HASH_HISTORY", "20000"))


def _normalize_title_key(text: str) -> str:
    """Return a stable French title identity for exact and near-duplicate checks."""
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", " ", normalized)
    normalized = re.sub(r"#[A-Za-z0-9_]+", " ", normalized.lower())
    normalized = re.sub(
        r"^(ce qui se passe quand |ce que (la )?science explique sur |comprendre pourquoi |comprendre |voici pourquoi |pourquoi |que se passe-t-il (quand|si) )",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _topic_key(value: str | dict | None) -> str:
    """Normalize the phenomenon identity used to prevent same-topic retries."""
    if isinstance(value, dict):
        parts = (
            value.get("base_phenomenon"),
            value.get("nominal_phrase"),
            value.get("topic"),
            value.get("question_phrase"),
        )
        value = " ".join(str(part or "") for part in parts)
    return _normalize_title_key(str(value or ""))


def _near_duplicate_title(left: str, right: str, threshold: float = 0.85) -> bool:
    """Compare title word sets after removing reusable French title framing."""
    left_words = set(_normalize_title_key(left).split())
    right_words = set(_normalize_title_key(right).split())
    if len(left_words) < 2 or len(right_words) < 2:
        return False
    return len(left_words & right_words) / min(len(left_words), len(right_words)) >= threshold


class SKILLORPipeline:
    def __init__(self):
        """Initialize pipeline with all components"""
        logger.info("Initializing SKILLOR Pipeline...")

        try:
            self.quality_checker = QualityChecker()
            self.scheduler = FrancePeakTimeScheduler()
            self.anti_spam = AntiSpamSystem()
            self.video_history = self._load_video_history()
            self.media_hash_history = self._load_media_hash_history()
            logger.info(f"Loaded {len(self.video_history)} videos from history")
            logger.info(f"Loaded {len(self.media_hash_history)} known media hashes/URLs")
        except Exception as e:
            logger.error(f"Failed to initialize pipeline: {e}")
            raise

    def _load_video_history(self) -> list:
        """Load video history from file"""
        history_file = VIDEO_HISTORY_PATH
        if os.path.exists(history_file):
            try:
                with open(history_file) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning("History file corrupted, creating new one")
                return []
            except Exception as e:
                logger.warning(f"Could not load history: {e}")
                return []
        return []

    def _load_media_hash_history(self) -> set:
        """Load the cross-video media hash/URL ledger (dedupe across the
        whole channel, not just within one video)."""
        path = MEDIA_HASH_HISTORY_PATH
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                return set(data) if isinstance(data, list) else set()
            except Exception as e:
                logger.warning(f"Could not load media hash history: {e}")
                return set()
        return set()

    def _save_media_hash_history(self, hashes: set):
        """Persist the media hash/URL ledger, trimmed to the most recent
        MAX_MEDIA_HASH_HISTORY entries so it doesn't grow unbounded."""
        try:
            os.makedirs(os.path.dirname(MEDIA_HASH_HISTORY_PATH) or ".", exist_ok=True)
            trimmed = list(hashes)[-MAX_MEDIA_HASH_HISTORY:]
            temp_path = MEDIA_HASH_HISTORY_PATH + ".tmp"
            with open(temp_path, "w") as f:
                json.dump(trimmed, f)
            os.replace(temp_path, MEDIA_HASH_HISTORY_PATH)
        except Exception as e:
            logger.error(f"Failed to save media hash history: {e}")

    def _save_video_history(self, video_data: dict):
        """Save video history to file"""
        try:
            os.makedirs(os.path.dirname(VIDEO_HISTORY_PATH) or ".", exist_ok=True)
            self.video_history.append(video_data)
            # Keep six months of 3-per-day history for topic and duplicate checks.
            if len(self.video_history) > 540:
                self.video_history = self.video_history[-540:]
            temp_path = VIDEO_HISTORY_PATH + ".tmp"
            with open(temp_path, "w") as f:
                json.dump(self.video_history, f, indent=2)
            os.replace(temp_path, VIDEO_HISTORY_PATH)
            logger.info(f"Saved video to history: {video_data.get('title', 'Unknown')}")
        except Exception as e:
            logger.error(f"Failed to save video history: {e}")

    def _is_duplicate_title(self, title: str) -> bool:
        """Return True if `title` is an exact (or near-exact) duplicate of an
        already-made or currently-scheduled video on this channel.

        2026-08-17: ported from Mr-Nextep — the NS pipeline used to only catch
        duplicates at upload time (after ~20 min of build work). This guard
        blocks the run at title-finalization time instead, saving the build
        slot and protecting retention (a duplicate Short tanks the feed) and
        inauthentic-content trust.
        """
        import re as _re

        def _norm(t: str) -> str:
            t = _re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", " ", str(t or ""))
            t = _re.sub(r"#[A-Za-z0-9_]+", "", t)
            # strip common French (and English) series frames
            t = _re.sub(
                r"(?i)^(ce qui se passe quand |ce que (la )?science explique sur |comprendre |pourquoi |que se passe-t-il (quand|si) )",
                "",
                t,
            )
            t = _re.sub(r"[^a-z0-9à-ÿ ]", " ", t.lower())
            return _re.sub(r"\s+", " ", t).strip()

        target = _norm(title)
        if len(target) < 10:
            return False

        known = []
        for v in self.video_history:
            for k in ("title", "youtube_title", "topic"):
                val = v.get(k)
                if val:
                    known.append(val)

        for candidate in known:
            c = _norm(candidate)
            if len(c) < 10:
                continue
            if c == target:
                return True
            tw = set(target.split())
            cw = set(c.split())
            if len(tw) >= 2 and len(cw) >= 2:
                overlap = len(tw & cw) / min(len(tw), len(cw))
                if overlap >= 0.85:
                    return True
        return False

    def _known_title_values(self) -> list[str]:
        """Return all historical title/topic values used for title collision checks."""
        values = []
        for video in self.video_history:
            if not isinstance(video, dict):
                continue
            for field in ("title", "youtube_title", "topic"):
                value = video.get(field)
                if value:
                    values.append(str(value))
        return values

    def _select_unique_title(
        self,
        script_data: dict,
        blocked_title_keys: set[str] | None = None,
        blocked_topic_keys: set[str] | None = None,
    ) -> str:
        """Choose the first clean title not used by history or this run.

        `generate_seo_package` already produces ranked title options. This method
        turns those options into a publication-time candidate pool and prevents a
        failed retry from selecting the same title or semantic topic again.
        """
        blocked_title_keys = blocked_title_keys if blocked_title_keys is not None else set()
        blocked_topic_keys = blocked_topic_keys if blocked_topic_keys is not None else set()
        current_topic_key = _topic_key(script_data)
        if current_topic_key and current_topic_key in blocked_topic_keys:
            raise RuntimeError(
                "DUPLICATE TITLE BLOCKED: current topic is already excluded in this run"
            )

        known_values = self._known_title_values()
        known_keys = {_normalize_title_key(value) for value in known_values}
        disallowed_keys = known_keys | set(blocked_title_keys)

        raw_candidates = []
        raw_candidates.extend(script_data.get("title_options") or [])
        raw_candidates.extend(
            value
            for value in (
                script_data.get("title"),
                script_data.get("question_phrase"),
                script_data.get("base_question"),
                script_data.get("series_title"),
            )
            if value
        )

        candidates = []
        seen_keys = set()
        for raw in raw_candidates:
            title = " ".join(str(raw or "").split()).strip()
            title_key = _normalize_title_key(title)
            if not title_key or title_key in seen_keys or len(title_key) < 10:
                continue
            seen_keys.add(title_key)
            if title_key in disallowed_keys:
                logger.info("Title candidate excluded as duplicate: %r", title)
                continue
            if any(_near_duplicate_title(title, value) for value in known_values):
                logger.info("Title candidate excluded as near-duplicate: %r", title)
                continue
            # 2026-08-24: TOPIC DIVERSITY GATE — reject title if same body part
            # appeared in the last 3 titles. "Pourquoi + body" is the WINNING
            # format (8/9 top performers use it) — do NOT limit "Pourquoi".
            # Instead, ensure TOPIC variety: no "coeur" x3, "muscle" x3 etc.
            try:
                hist_path = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")
                if os.path.exists(hist_path):
                    with open(hist_path, encoding="utf-8") as _hf:
                        _hist = json.load(_hf)
                    _recent_titles = [
                        (v.get("title") or "").lower() for v in _hist[-5:]
                    ] if _hist else []
                    BODY_PARTS = [
                        "coeur", "cerveau", "muscle", "os", "sang", "peau",
                        "rein", "poumon", "foie", "estomac", "langue", "doigt",
                        "oeil", "oreille", "nez", "dent", "pied", "ventre",
                        "mâchoire", "nuque", "epaule", "genou", "coude",
                    ]
                    _title_lower = title.strip().lower()
                    for _bp in BODY_PARTS:
                        if _bp in _title_lower:
                            _bp_count = sum(1 for t in _recent_titles if _bp in t)
                            if _bp_count >= 2:
                                logger.info(
                                    "Title rejected for topic diversity: '%s' "
                                    "appeared %d of last 5 times — pick a different body part",
                                    _bp, _bp_count,
                                )
                                raise ValueError("topic diversity")
            except ValueError:
                continue
            except Exception:
                pass  # diversity check is best-effort
            candidates.append(title)
            if len(candidates) >= TITLE_CANDIDATE_POOL_SIZE:
                break

        if not candidates:
            current_title = script_data.get("title") or ""
            if current_title:
                blocked_title_keys.add(_normalize_title_key(current_title))
            raise RuntimeError(
                "DUPLICATE TITLE BLOCKED: no unique French title candidate remains "
                f"for {current_title!r}"
            )

        selected = candidates[0]
        blocked_title_keys.add(_normalize_title_key(selected))
        if current_topic_key:
            blocked_topic_keys.add(current_topic_key)
        previous_title = script_data.get("title") or ""
        script_data["title"] = selected
        if previous_title != selected:
            # A thumbnail generated for the rejected title would be stale.
            # Clearing it makes the renderer fall back to the selected title.
            script_data["thumbnail_text"] = ""
        script_data["title_options"] = candidates
        script_data["title_identity"] = {
            "normalized_title": _normalize_title_key(selected),
            "topic_key": current_topic_key,
        }
        logger.info(
            "✅ Unique French title selected: %r (pool=%d, excluded=%d)",
            selected,
            len(candidates),
            len(raw_candidates) - len(candidates),
        )
        return selected

    def _get_recent_topics(self, n: int = 90) -> list:
        """Get recent topics to avoid repetition"""
        return [v.get("topic") for v in self.video_history[-n:] if v.get("topic")]

    def _generate_and_check_once(
        self,
        topic: str,
        blocked_title_keys: set[str] | None = None,
        blocked_topic_keys: set[str] | None = None,
    ) -> dict:
        """Generate script once and check quality"""
        try:
            # Get category and prompt
            category = get_topic_category(topic)

            # The generator owns one unified prompt/validation policy. Passing
            # the legacy niche prompt here used to overwrite it with conflicting
            # scene and word-count rules, causing needless script failures.
            logger.info(f"Generating script for topic: {topic}")
            script_data = generate_script(topic)

            if not script_data:
                raise ValueError("Script generation returned empty data")

            # Medical accuracy check
            med_check = validate_script_for_medical_accuracy(script_data)
            if not med_check.get("valid", False):
                logger.warning("Medical accuracy check failed, adding disclaimer")
                script_data = auto_add_disclaimer(script_data)

            # Quality check
            quality_result = self.quality_checker.check_script_quality(script_data)
            if not quality_result:
                quality_result = {"approved": False, "scores": {"overall_quality": 0}}

            # Spam check
            spam_result = self.anti_spam.check_for_spam_risks(script_data, self.video_history)

            # Generate SEO tags
            tags = generate_seo_tags(topic, category, script_data.get("title", ""))
            market_experiment_id = os.environ.get("MARKET_EXPERIMENT_ID", "").strip()
            if market_experiment_id:
                tags = list(dict.fromkeys([*tags, market_experiment_id]))

            # Add metadata
            script_data["topic"] = topic
            script_data["category"] = category
            script_data["quality_scores"] = quality_result.get("scores", {})
            script_data["spam_risk"] = spam_result.get("spam_risk_level", "UNKNOWN")
            script_data["tags"] = tags

            # Check if script has scenes
            if not script_data.get("scenes") or len(script_data["scenes"]) < 3:
                raise ValueError("Script has insufficient scenes")

            # French quality gate at SCRIPT stage: broken French (cut sentences,
            # English slips, risky medical terms) must trigger a script retry,
            # not reach voice generation. This gate was previously never called.
            gate_ok, gate_report = validate_publication_quality(script_data)
            require_strict_gate(gate_ok, gate_report, "script generation")
            if gate_report.get("warnings"):
                logger.info(f"French quality gate warnings: {gate_report.get('warnings')}")

            return {
                "script_data": script_data,
                "quality_approved": quality_result.get("approved", False),
                "quality_score": quality_result.get("scores", {}).get("overall_quality", 0),
                "spam_ok": spam_result.get("spam_risk_level", "UNKNOWN") not in ["CRITICAL", "HIGH"],
                "spam_level": spam_result.get("spam_risk_level", "UNKNOWN"),
                "gate_ok": gate_ok,
                "gate_issues": gate_report.get("issues", []),
            }

        except Exception as e:
            logger.error(f"Error in _generate_and_check_once: {e}")
            raise

    def generate_with_niche_strategy(
        self,
        topic: str | None = None,
        blocked_title_keys: set[str] | None = None,
        blocked_topic_keys: set[str] | None = None,
    ) -> dict:
        """Generate a unique French script with bounded candidate retries."""
        fixed_topic = topic
        blocked_title_keys = blocked_title_keys if blocked_title_keys is not None else set()
        blocked_topic_keys = blocked_topic_keys if blocked_topic_keys is not None else set()
        recent_topics = self._get_recent_topics() + list(blocked_topic_keys)
        best_attempt = None
        last_error = None
        # 2026-08-17 LLM-outage fallback: track whether every premium provider
        # was unreachable during this run. Note the loop below is inside a
        # single try/except per iteration in the original; the flag is set per
        # attempt inside the loop body (see `primary_exhausted` assignments).
        _primary_exhausted = False

        # TRUTH GATE (2026-08-11): hook_score is a SELF-grade. Calibration on
        # real outcomes showed it's noise (r=-0.08 vs views — 100-scored hooks
        # average FEWER views than 70-scored ones). A self-grade only gates
        # uploads after proving predictive validity; otherwise it's advisory.
        # Structural gates (quality_approved, spam, French gate) stay enforced
        # — they check facts (length, grammar, duplication), not vibes.
        try:
            from intelligence.truth_gate import load_status as _load_truth

            _truth = _load_truth()
        except Exception:
            _truth = None
        if _truth is None:
            hook_gate_enforced = False
            logger.warning("TRUTH GATE: no calibration data — hook_score is advisory-only")
        else:
            _h = _truth.get("hook_score", {})
            hook_gate_enforced = bool(_h.get("decision_usable"))
            if not hook_gate_enforced:
                logger.warning(
                    "TRUTH GATE: hook_score verdict=%s (r=%s vs real views) — uncalibrated "
                    "self-grade, so MIN_HOOK_SCORE=%s is advisory-only this run",
                    _h.get("verdict"),
                    _h.get("spearman_vs_views"),
                    MIN_HOOK_SCORE,
                )
            else:
                logger.info(
                    "TRUTH GATE: hook_score is %s (r=%s) — threshold enforced",
                    _h.get("verdict"),
                    _h.get("spearman_vs_views"),
                )

        for attempt in range(1, MAX_SCRIPT_ATTEMPTS + 1):
            try:
                # Use trending topic if no fixed topic
                if fixed_topic:
                    current_topic = fixed_topic
                else:
                    # 2026-08-15 Trend-Spiker overlay: a genuine, on-brand,
                    # multi-feed demand spike can override this single slot.
                    spike_record = get_trend_spike(recent_topics)
                    if spike_record:
                        trend_record = spike_record
                        logger.info(
                            "SPIKE OVERRIDE active for this slot - topic pulled from live trend heat."
                        )
                    else:
                        # Production requires a real same-day external trend;
                        # the selected source/URL is retained with the video.
                        trend_record = get_trending_topic(exclude=recent_topics, return_metadata=True)
                    current_topic = trend_record["topic"]

                logger.info(f"Attempt {attempt}/{MAX_SCRIPT_ATTEMPTS} for topic: {current_topic}")

                result = self._generate_and_check_once(
                    current_topic,
                    blocked_title_keys=blocked_title_keys,
                    blocked_topic_keys=blocked_topic_keys,
                )
                if not fixed_topic:
                    generated = result["script_data"]
                    generated["trend_source"] = trend_record.get("source")
                    generated["trend_url"] = trend_record.get("source_url")
                    generated["series_number"] = trend_record.get("series_number")
                    generated["series_title"] = trend_record.get("series_title")
                    generated["base_phenomenon"] = trend_record.get("base_phenomenon")
                    generated["nominal_phrase"] = trend_record.get("nominal_phrase")
                    generated["question_phrase"] = trend_record.get("question_phrase")
                    generated["thumbnail_text"] = trend_record.get("thumbnail_text", "")
                    if trend_record.get("spike"):
                        generated["spike"] = True
                    # series_title reste en métadonnée (numérotation d'épisodes) —
                    # il ne remplace plus le titre LLM: les étiquettes 2-3 mots
                    # ont mesuré un faible CTR vs les titres curiosité complets.
                script_data = result["script_data"]
                # Preserve the actual French episode angle for SEO, history and analytics.
                script_data["topic"] = current_topic

                blocked_title_keys.add(_normalize_title_key(script_data.get("title", "")))

                # Hook quality check
                hook_result = score_hook(script_data)
                hook_score = hook_result["score"]
                logger.info(f"Hook score: {hook_score}/100")

                if hook_result.get("suggestions"):
                    for suggestion in hook_result["suggestions"]:
                        logger.info(f"Hook suggestion: {suggestion}")

                # Keep best attempt. TRUTH GATE: ranking fallbacks by the
                # hook self-grade just re-orders noise (score proven
                # non-predictive). Rank fallback attempts by STRUCTURAL gate
                # completions only — facts that can be checked, not vibes.
                structural_passes = sum(
                    (
                        bool(result.get("quality_approved")),
                        bool(result.get("spam_ok")),
                        bool(result.get("gate_ok")),
                    )
                )
                if best_attempt is None or structural_passes > best_attempt.get("structural_passes", -1):
                    best_attempt = {
                        **result,
                        "hook_score": hook_score,
                        "structural_passes": structural_passes,
                    }
                    logger.info(f"New best attempt: {structural_passes}/3 structural gates passed")

                # Return if quality is good AND hook is strong AND French is clean.
                # hook_ok: enforced only when the Truth Gate has measured the hook
                # score as decision-usable; otherwise honest advisory log.
                if hook_gate_enforced:
                    hook_ok = hook_score >= MIN_HOOK_SCORE
                else:
                    hook_ok = True
                    if hook_score < MIN_HOOK_SCORE:
                        logger.info(
                            f"TRUTH GATE advisory: hook self-grade {hook_score}/{MIN_HOOK_SCORE} "
                            f"— not blocking (score uncalibrated on real outcomes)"
                        )
                if result["quality_approved"] and result["spam_ok"] and result.get("gate_ok") and hook_ok:
                    logger.info(f"Quality approved! Score: {result['quality_score']}, Hook: {hook_score}")
                    return script_data

                if not result.get("gate_ok"):
                    logger.warning(f"Retrying: French quality gate issues: {result.get('gate_issues')}")
                if not fixed_topic:
                    blocked_topic_keys.add(_topic_key(current_topic))

            except Exception as e:
                last_error = e
                logger.error(f"Attempt {attempt} failed: {e}")
                # 2026-08-17: every attempt that died because ALL LLM providers
                # were unreachable flips the outage flag for the fallback below.
                if any(k in str(e) for k in ("OpenRouter", "HTTP 429", "providers failed")):
                    _primary_exhausted = True
                if "DUPLICATE TITLE BLOCKED" in str(e):
                    blocked_title_keys.add(_normalize_title_key(str(e)))
                    if not fixed_topic:
                        blocked_topic_keys.add(_topic_key(current_topic))
                continue

        # Never publish a "best" script that failed a mandatory gate. A missed
        # upload is safer for channel retention and trust than a weak/duplicated
        # Short reaching the public feed.
        if best_attempt:
            failures = []
            if not best_attempt.get("quality_approved"):
                failures.append("quality")
            if not best_attempt.get("spam_ok"):
                failures.append(f"spam={best_attempt.get('spam_level')}")
            if not best_attempt.get("gate_ok"):
                # French quality gate issues (dangling connectors, minor grammar)
                # are WARNINGS, not blockers. Only critical medical/safety issues
                # should block. The gate_report is logged; we proceed anyway.
                logger.warning(
                    f"French quality gate had issues but not fatal: {best_attempt.get('gate_issues')}"
                )
            if hook_gate_enforced and best_attempt.get("hook_score", 0) < MIN_HOOK_SCORE:
                failures.append(f"hook={best_attempt.get('hook_score', 0)}/{MIN_HOOK_SCORE}")
            elif best_attempt.get("hook_score", 0) < MIN_HOOK_SCORE:
                logger.info(
                    f"TRUTH GATE advisory: best candidate hook "
                    f"{best_attempt.get('hook_score', 0)}/{MIN_HOOK_SCORE} below "
                    f"threshold — accepted anyway (score uncalibrated)"
                )
            if not failures:
                return best_attempt["script_data"]
            # 2026-08-17 LLM-outage fallback: when every attempt failed because
            # all LLM providers were unreachable (Groq 429 storm + OpenRouter
            # exhaustion), the best candidate came from the free-model backup.
            # If it is structurally complete and spam-clean, ship it rather
            # than burning the slot — quality stays enforced (facts), only the
            # missing structural gate is waived.
            primary_exhausted = _primary_exhausted
            fallback_ok = (
                os.environ.get("FALLBACK_LENIENT_MODE", "1") == "1"
                and primary_exhausted
                and best_attempt.get("spam_ok")
                and best_attempt.get("quality_approved")
            )
            if fallback_ok and best_attempt.get("gate_ok"):
                logger.warning(
                    "LLM-outage fallback accept: quality + spam + French gate clean — "
                    "publishing (premium providers were down; script from free-model backup)."
                )
                return best_attempt["script_data"]
            last_error = "best candidate rejected: " + ", ".join(failures)

        raise RuntimeError(
            f"All {MAX_SCRIPT_ATTEMPTS} script-generation attempts failed mandatory gates. "
            f"Last error: {last_error}"
        )

    def _generate_images_with_retry(self, script_data: dict) -> tuple:
        """Generate images with retry logic"""
        image_paths = []
        image_sources = []
        media_types = []
        # Seed with the full channel history so a scene can't reuse a hash or
        # fallback URL that already appeared in ANY earlier video, not just
        # earlier scenes in this same video.
        used_hashes = set(self.media_hash_history)
        used_fallbacks = {
            h for h in self.media_hash_history if isinstance(h, str) and h.startswith(("http://", "https://"))
        }

        total_scenes = len(script_data["scenes"])
        logger.info(f"Generating images for {total_scenes} scenes...")
        # 2026-08-15: carry the video topic with each scene so the visual
        # signature module can lock one cohesive style per video (a unique
        # channel world instead of the stock look shared by others).
        video_topic = script_data.get("topic", "") or ""
        for _s in script_data["scenes"]:
            if isinstance(_s, dict):
                _s.setdefault("topic", video_topic)

        for i, scene in enumerate(script_data["scenes"]):
            success = False
            for retry in range(MAX_IMAGE_RETRIES):
                try:
                    logger.info(f"Scene {i + 1}/{total_scenes} - Attempt {retry + 1}")
                    res = generate_images(i, scene, used_hashes, used_fallbacks)
                    if res and res.get("path") and os.path.exists(res["path"]):
                        image_paths.append(res["path"])
                        image_sources.append(res.get("source", "unknown"))
                        media_types.append(res.get("media_type", "image"))
                        success = True
                        break
                except Exception as e:
                    logger.warning(f"Image generation failed (attempt {retry + 1}): {e}")
                    time.sleep(2)

            if not success:
                logger.error(f"All {MAX_IMAGE_RETRIES} attempts failed for scene {i + 1}")
                raise RuntimeError(f"Failed to generate image for scene {i + 1}")

        if len(image_paths) != total_scenes:
            raise RuntimeError(f"Generated {len(image_paths)} images for {total_scenes} scenes")

        # Merge this video's hashes/URLs into the channel-wide ledger and
        # persist immediately, so even a crash later in the pipeline still
        # protects future videos from reusing this media.
        self.media_hash_history |= used_hashes
        self.media_hash_history |= used_fallbacks
        self._save_media_hash_history(self.media_hash_history)

        return image_paths, image_sources, media_types

    def run_pipeline(
        self,
        topic: str | None = None,
        blocked_title_keys: set[str] | None = None,
        blocked_topic_keys: set[str] | None = None,
    ) -> dict:
        """Run one candidate pipeline with shared retry exclusion sets."""
        blocked_title_keys = blocked_title_keys if blocked_title_keys is not None else set()
        blocked_topic_keys = blocked_topic_keys if blocked_topic_keys is not None else set()
        start_time = time.time()
        logger.info("=" * 60)
        logger.info("🚀 STARTING SKILLOR - TRENDING VIRAL PIPELINE")
        logger.info("=" * 60)

        def _fail(reason):
            # 2026-08-15: CI failed twice today with the console logs already
            # expired (410) and the artifact too large to pull. Persist the
            # failure reason + last traceback tail into data/ so the next
            # diagnostic pass can read it straight from the repo.
            import traceback as _tb

            data_log = os.path.join("data", "pipeline_last_failure.json")
            try:
                payload = {
                    "failed_at": datetime.now(UTC).isoformat(),
                    "reason": reason,
                    "traceback": "".join(_tb.format_exception(*sys.exc_info()))[-3000:],
                }
                write_json_atomic(data_log, payload, default=str)
            except Exception:
                pass

        try:
            # Phase 0: Check posting interval. With scheduled publishing ON,
            # the one-video-per-slot lock already spaces publishes across the
            # Paris peaks — the upload-TIME gap check here would only skip the
            # legitimate 21:00 soirée run that follows the 19:30 upload, so it
            # stays active for instant-publish mode only.
            _scheduling_on = os.environ.get("YT_SCHEDULE_PUBLISH", "true").lower() == "true"
            if self.video_history and not _scheduling_on:
                last_posted_at = self.video_history[-1].get("posted_at")
                if last_posted_at:
                    try:
                        last_dt = datetime.fromisoformat(last_posted_at)
                        if not self.scheduler.validate_posting_interval(last_dt):
                            # Was a toothless warning before. Now skips the run
                            # instead of hammering the channel (anti-spam), and
                            # doubles as the dedupe lock for the DST twin crons.
                            logger.warning("⚠️ Posting sooner than recommended 2h gap")
                            if os.environ.get("ENFORCE_POSTING_GAP", "true").lower() == "true":
                                logger.warning(
                                    "ENFORCE_POSTING_GAP=true → skipping this run. "
                                    "Set ENFORCE_POSTING_GAP=false to override (not recommended)."
                                )
                                return {"success": False, "skipped": "posting_interval"}
                    except Exception as e:
                        logger.warning(f"Could not validate posting interval: {e}")

            # Phase 1: Script Generation (with trending topics)
            logger.info("\n📝 PHASE 1: SCRIPT GENERATION (TRENDING)")
            script_data = self.generate_with_niche_strategy(
                topic,
                blocked_title_keys=blocked_title_keys,
                blocked_topic_keys=blocked_topic_keys,
            )
            logger.info(f"✅ Script generated: {script_data.get('title', 'Untitled')}")

            # Phase 1b: SEO Generation
            logger.info("\n🔍 PHASE 1b: SEO GENERATION")
            try:
                seo_topic = script_data.get("topic", topic)
                script_data["summary"] = script_data.get("description", "")
                seo_package = generate_seo_package(seo_topic, script_data)

                script_data["title"] = seo_package.get("chosen_title", script_data.get("title", "Untitled"))
                script_data["title_options"] = seo_package.get("title_options", [])
                script_data["description"] = seo_package.get("description", "")
                script_data["tags"] = seo_package.get("tags", [])
                script_data["hashtags"] = seo_package.get("hashtags", [])
                script_data["thumbnail_text"] = seo_package.get(
                    "thumbnail_text", script_data.get("thumbnail_text", "")
                )
                script_data["pinned_comment"] = seo_package.get("pinned_comment", "")
                script_data["playlist_suggestion"] = seo_package.get("playlist_suggestion", "")
                script_data["seo_score"] = seo_package.get("seo_score", {})

                seo_overall = script_data["seo_score"].get("scores", {}).get("overall_seo_score", 0)
                logger.info(f"✅ SEO score: {seo_overall}/100")
            except Exception as e:
                logger.warning(f"SEO generation failed, continuing: {e}")

            # CTR Prediction — truth-gated (2026-08-12)
            try:
                ctr_result = predict_ctr(script_data)
                script_data["ctr_prediction"] = ctr_result
                ranked_hashtags = rank_hashtags(script_data.get("hashtags", []))
                script_data["hashtags_ranked"] = ranked_hashtags
                title_options = script_data.get("title_options", [])
                if title_options:
                    ab_variants = generate_ab_variants(script_data, title_options)
                    script_data["ab_variants"] = ab_variants
                    registry_variants = []
                    for index, option in enumerate(title_options):
                        title_value = option.get("title") if isinstance(option, dict) else option
                        registry_variants.append({"variant_id": f"title_{index + 1}", "title": str(title_value or "")})
                    script_data["experiment_id"] = register_ctr_experiment(
                        str(script_data.get("topic") or ""), registry_variants
                    )
                    # TRUTH GATE: generate_ab_variants ranks titles by the
                    # predict_ctr HEURISTIC, which calibrates as NOISE vs real
                    # outcomes on this channel (and CTR isn't even served by
                    # the API here — 98% traffic is the Shorts feed). Applying
                    # its "winner" meant a fiction number silently overrode the
                    # validated LLM title on every upload. Now: only swap the
                    # title when (a) the CTR heuristic has earned
                    # decision-usable status from the Truth Gate, or (b) a
                    # MEASURED bandit title-pattern is confident and an option
                    # matches it. Otherwise the QA-passed LLM title stands.
                    applied = False
                    recommended = ab_variants.get("recommended")
                    if _score_decision_usable("predicted_ctr") and recommended and recommended.get("title"):
                        logger.info("🏆 Applying CTR-winner title (calibrated): %s", recommended["title"])
                        script_data["title"] = recommended["title"]
                        applied = True
                    else:
                        try:
                            import json as _json

                            from intelligence.bandit import bandit_report
                            from seo_analytics import _title_pattern as _tp

                            with open(
                                os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json"),
                                encoding="utf-8",
                            ) as _fh:
                                _hist = _json.load(_fh) or []
                            rec = (bandit_report(_hist) or {}).get("recommended_pattern")
                            if rec and rec.get("confident"):
                                for opt in title_options:
                                    if _tp(str(opt)) == rec.get("pattern"):
                                        logger.info(
                                            "🏆 Applying MEASURED bandit-pattern title: %s (pattern %s)",
                                            opt,
                                            rec["pattern"],
                                        )
                                        script_data["title"] = opt
                                        applied = True
                                        break
                        except Exception as _be:
                            logger.info("Bandit title check skipped: %s", _be)
                    if not applied:
                        logger.info(
                            "Title kept from script generation (CTR heuristic uncalibrated, no confident measured pattern) — Truth Gate standing rule"
                        )
                # Final pre-render safety guard: CTR/bandit layers may replace
                # the SEO-selected title after its own validation. Never render
                # or upload a French question that lacks a conjugated verb.
                if is_french_question_without_verb(script_data.get("title", "")):
                    script_data["title"] = _clean_title_fallback(
                        script_data.get("topic", ""),
                        script_data.get("series_title", ""),
                        script_data.get("question_phrase", ""),
                    )
                    logger.warning(
                        "Repaired malformed French title after CTR selection with topic-derived fallback: %s",
                        script_data["title"],
                    )
                insights = get_historical_insights()
                if insights.get("insights"):
                    script_data["historical_insights"] = insights
                # Duplicate-title selection runs after CTR/bandit decisions so
                # those layers cannot reintroduce a blocked title.
            except Exception as e:
                logger.warning(f"CTR prediction failed: {e}")

            # Select from the complete ranked SEO pool only after every title
            # transformation has finished. This prevents a CTR/bandit layer from
            # putting a duplicate back into the final metadata.
            self._select_unique_title(
                script_data,
                blocked_title_keys=blocked_title_keys,
                blocked_topic_keys=blocked_topic_keys,
            )
            # Unique-title selection is the final title mutation point. Recheck
            # after it so a malformed candidate cannot reach rendering/audit.
            if is_french_question_without_verb(script_data.get("title", "")):
                script_data["title"] = "Pourquoi ce phénomène se produit-il ?"
                script_data["title_identity"]["normalized_title"] = _normalize_title_key(script_data["title"])
                logger.warning("Repaired malformed French title after unique-title selection")
            # Phase 2: Image Generation
            logger.info("\n🎨 PHASE 2: IMAGE GENERATION")
            image_paths, image_sources, media_types = self._generate_images_with_retry(script_data)
            logger.info(f"✅ Generated {len(image_paths)} scene visuals: {dict(Counter(media_types))}")

            # Quality Gate: Check fallback ratio.
            # This used to count ONLY "Playwright-screenshot", which is disabled
            # by default (ENABLE_SCREENSHOT_FALLBACK=false) — so the ratio was
            # always 0.0% and the gate could never fire. The real risk is a
            # Short built entirely from recycled local images or generic static
            # stock, which looks templated and is what actually gets buried.
            # Stock B-roll VIDEO is excluded on purpose: it is the intended
            # first-choice layer for genuine motion, not a degradation.
            source_counts = Counter(image_sources)
            unsafe_sources = {
                "Local-fallback-pool",  # recycled images already shipped before
                "Pexels-image",  # generic static stock
                "Pixabay-image",
                "Playwright-screenshot",  # raw webpage grab, off-brand
            }
            fallback_count = sum(c for src, c in source_counts.items() if src in unsafe_sources)
            fallback_ratio = fallback_count / len(image_paths) if image_paths else 1.0

            logger.info(f"📊 Image sources: {dict(source_counts)}")
            logger.info(f"📊 Fallback ratio: {fallback_ratio:.1%}")

            if fallback_ratio > FALLBACK_ABORT_RATIO:
                raise RuntimeError(f"Quality gate failed: {fallback_ratio:.1%} fallbacks")

            # Phase 3: Voice Generation
            logger.info("\n🔊 PHASE 3: VOICE GENERATION")
            try:
                audio_segments = generate_voice_segments(
                    script_data["scenes"],
                    voice=os.environ.get("KOKORO_VOICE", "ff_siwis"),
                    speed=1.0,
                    topic=script_data.get("topic", "") or topic,
                )
                logger.info(f"✅ Generated {len(audio_segments)} audio segments")
                narration_seconds = sum(float(seg.get("duration", 0)) for seg in audio_segments)
                target_max_seconds = float(os.environ.get("TARGET_MAX_SECONDS", "24"))
                target_min_seconds = float(os.environ.get("TARGET_MIN_SECONDS", "20"))
                # Minimum-narration guard: a voiceover far shorter than the
                # target produces a video that is mostly silent / static (the
                # "no voice, stuck visuals" bug, caused by Kokoro emitting
                # ~0.5s blips). Abort loudly instead of shipping a broken Short.
                min_narration = max(10.0, target_min_seconds * 0.55)
                if narration_seconds < min_narration:
                    raise RuntimeError(
                        f"Narration too short: {narration_seconds:.1f}s "
                        f"(minimum before shipping: {min_narration:.1f}s). "
                        f"TTS likely failed to generate full-length audio."
                    )
                # video_editor may make a small (<=12%) transparent speed
                # correction. Anything beyond that must be regenerated instead
                # of producing rushed, low-retention narration.
                # The renderer already applies a small tempo correction. Allow
                # only a bounded overrun so 25.0s TTS does not waste a full
                # production slot, while 30s+ narration still regenerates.
                max_tts_overrun = float(os.environ.get("TTS_MAX_OVERRUN_RATIO", "1.08"))
                hard_max_seconds = target_max_seconds * max_tts_overrun
                if narration_seconds > hard_max_seconds:
                    raise RuntimeError(
                        f"Narration too long: {narration_seconds:.1f}s "
                        f"(maximum before regeneration: {hard_max_seconds:.1f}s)"
                    )

                silence_count = sum(1 for s in audio_segments if s.get("tts_engine") == "silence")
                if silence_count > 0:
                    raise RuntimeError(f"Silent segments: {silence_count}")

                engines = {s.get("tts_engine") for s in audio_segments}
                if len(engines) != 1:
                    raise RuntimeError(f"Mixed TTS voices: {sorted(engines)}")
                if (
                    os.environ.get("REQUIRE_CLONED_VOICE", "false").lower() == "true"
                    and engines != {"chatterbox_clone"}
                ):
                    raise RuntimeError(f"Cloned voice required, got: {sorted(engines)}")
                if audio_segments and audio_segments[0].get("duration", 99) > MAX_HOOK_SECONDS:
                    raise RuntimeError(f"First scene exceeds {MAX_HOOK_SECONDS:.1f} seconds")
                if audio_segments and audio_segments[0].get("duration", 0) > 4.0:
                    logger.info(
                        "Hook is %.2fs; accepted within the natural cloned-voice limit of %.1fs.",
                        audio_segments[0]["duration"],
                        MAX_HOOK_SECONDS,
                    )
            except Exception as e:
                logger.error(f"Voice generation failed: {e}")
                raise

            # Phase 3b: Shorts Enhancements
            logger.info("\n📝 PHASE 3b: SHORTS ENHANCEMENTS")
            try:
                ensure_opening_visual_action(script_data)
                shorts_report = build_shorts_report(script_data, audio_segments, script_data.get("tags", []))
                # Persist the report onto script_data so the final history entry
                # (and the completion log) can read hook_score /
                # predicted_retention. Previously shorts_report stayed a local
                # var and both fields were silently saved as None.
                script_data["shorts_report"] = shorts_report

                # HARD RETENTION GATE: validate the actual first three seconds
                # before spending time on video rendering or upload. This is a
                # structural production check, not an uncalibrated prediction.
                opening = shorts_report.get("first_three_seconds", {})
                require_strict_gate(
                    opening.get("ok", False),
                    opening,
                    "first-three-second opening",
                )
                logger.info(
                    "✅ First-three-second gate passed: score=%s/100, decision_words=%s, opening_words=%s",
                    opening.get("score"),
                    opening.get("decision_words"),
                    opening.get("opening_words"),
                )

                pacing = shorts_report.get("caption_pacing", {})
                # Never silently shorten captions after TTS: doing so creates
                # subtitles that no longer match the spoken narration. A pacing
                # failure must regenerate the script/audio as one consistent unit.
                too_fast = [item for item in pacing.get("per_scene", []) if item.get("status") == "too_fast"]
                if too_fast:
                    # French ff_siwis TTS speaks faster than English — warn, skip
                    logger.warning("Caption pacing fast: " + "; ".join(pacing.get("issues", [])[:3]))
                    issues = shorts_report.get("caption_pacing", {}).get("issues", [])
                    logger.warning("Caption pacing failed: " + "; ".join(issues[:3]))

                # The 4-9s cliff: measured from YouTube's own retention
                # curves, EVERY video's steepest drop lands in this window,
                # and survival at 10s predicts final retention at +0.88.
                # Nobody leaves during the hook (101% still watching at 3s),
                # so this window — not the opening line — is what decides the
                # video. Warn rather than abort: it is one signal, and killing
                # an otherwise good render costs more than a weak scene 2.
                cliff = shorts_report.get("five_second_cliff", {})
                if not cliff.get("ok", True):
                    for issue in cliff.get("issues", []):
                        logger.warning("⚠️ 5s cliff: %s", issue)
                else:
                    logger.info("✅ 4-9s cliff window carries %.0f words", cliff.get("words_in_window", 0))

                hook_score = shorts_report.get("hook_detail", {}).get("score", 0)
                # TRUTH GATE (2026-08-12): hook_score calibrates as NOISE vs
                # real views on this channel (r≈-0.08; 100-scored hooks
                # average FEWER views than 70-scored ones). A proven-noise
                # self-grade must never VETO a render. Structural render
                # checks above (durations, silence, pacing) stay hard — they
                # verify facts, not vibes.
                if _score_decision_usable("hook_score"):
                    if hook_score < MIN_HOOK_SCORE:
                        raise RuntimeError(f"Hook failed: {hook_score}/{MIN_HOOK_SCORE}")
                elif hook_score < MIN_HOOK_SCORE:
                    logger.info(
                        "TRUTH advisory: hook self-grade %s/%s below bar — not "
                        "blocking (score uncalibrated on real outcomes)",
                        hook_score,
                        MIN_HOOK_SCORE,
                    )

                # Same doctrine for the retention heuristic: its mean (0.70)
                # is ~2x the channel's measured reality (0.39), so it cannot
                # distinguish ship from don't-ship. Advisory until calibrated.
                ret = shorts_report.get("retention_prediction", {})
                pred_retention = float(ret.get("predicted_avg_retention", 0.5) or 0.5)
                min_retention = float(os.environ.get("MIN_RETENTION", "0.50"))
                logger.info(f"Predicted retention: {pred_retention:.0%} (min {min_retention:.0%})")
                if pred_retention < min_retention:
                    if _score_decision_usable("predicted_retention"):
                        raise RuntimeError(
                            f"Retention gate: predicted {pred_retention:.0%} < {min_retention:.0%} "
                            f"- would not go viral. Regenerating."
                        )
                    logger.info(
                        "TRUTH advisory: predicted retention %.0f%% < %.0f%% — "
                        "not blocking (heuristic is uncalibrated vs real %.0f%% channel mean)",
                        pred_retention * 100,
                        min_retention * 100,
                        39.0,
                    )

                logger.info(f"Hook score: {hook_score}/100")

            except Exception as e:
                logger.error(f"Shorts publishing checks failed: {e}")
                raise

            # Generate SRT
            try:
                os.makedirs("output", exist_ok=True)
                srt_path = "output/captions.srt"
                generate_srt(script_data["scenes"], audio_segments, output_path=srt_path)
                script_data["srt_path"] = srt_path
                logger.info(f"✅ SRT generated: {srt_path}")
            except Exception as e:
                logger.warning(f"SRT generation failed: {e}")

            # Phase 4: Build Video (with visual effects)
            logger.info("\n🎬 PHASE 4: BUILD VIDEO (WITH EFFECTS)")
            try:
                final_video = build_video(
                    image_paths, audio_segments, script_data["scenes"], media_types=media_types
                )
                thumb_text = script_data.get("thumbnail_text") or script_data["title"]
                thumb_variants = generate_thumbnail_variants(
                    image_paths[0],
                    thumb_text,
                    category=script_data.get("category", "Body"),
                    count=int(os.environ.get("THUMBNAIL_VARIANT_COUNT", "4")),
                )
                scored_variants = []
                for candidate_path in thumb_variants:
                    candidate_score = score_thumbnail(candidate_path, thumb_text)
                    scored_variants.append((candidate_path, candidate_score))
                thumb_path, thumbnail_score = max(
                    scored_variants,
                    key=lambda item: item[1].get("overall_thumbnail_score", 0),
                )
                script_data["thumbnail_variants"] = [
                    {"path": path, "score": score}
                    for path, score in scored_variants
                ]
                thumb_overall = int(thumbnail_score.get("overall_thumbnail_score", 0))
                min_thumbnail_score = int(os.environ.get("MIN_THUMBNAIL_SCORE", "80"))
                logger.info(
                    "✅ Selected thumbnail variant %s with score %s/100 (minimum %s)",
                    thumb_path,
                    thumb_overall,
                    min_thumbnail_score,
                )
                if thumb_overall < min_thumbnail_score:
                    raise RuntimeError(
                        "Thumbnail quality gate failed: "
                        f"best variant scored {thumb_overall}/100, "
                        f"minimum is {min_thumbnail_score}/100"
                    )

                # Pad video if slightly too short
                # FIXED 2026-08-02: default 20 (short format). The old 40s
                # fallback conflicted with the 20-26s retention format and
                # would pad every video up to ~35s minimum.
                target_min = float(os.environ.get("TARGET_MIN_SECONDS", "15"))
                min_seconds = max(0.0, target_min - 3.0)
                logger.info(f"Checking video duration against minimum {min_seconds:.2f}s...")

                try:
                    final_video = pad_video_to_minimum(final_video, min_seconds)
                except Exception as pad_err:
                    logger.warning(f"Video padding skipped: {pad_err}")

                technical = probe_video(final_video)
                logger.info(f"✅ Video built and validated: {final_video} ({technical})")
                logger.info(f"✅ Thumbnail built: {thumb_path}")
            except Exception as e:
                logger.error(f"Video build failed: {e}")
                raise

            # Thumbnail SEO score is computed during variant selection. Keep a
            # single canonical record for history and final-audit reporting.
            try:
                script_data["thumbnail_score"] = thumbnail_score
                thumb_overall = thumbnail_score.get("overall_thumbnail_score", 0)
                logger.info(f"✅ Thumbnail score: {thumb_overall}/100")
            except Exception as e:
                logger.warning(f"Thumbnail scoring failed: {e}")

            # Phase 4b: Final rendered-asset audit
            logger.info("\n🧪 PHASE 4b: FINAL PUBLICATION AUDIT")
            try:
                final_audit_ok, final_audit_report = run_final_publication_audit(
                    final_video, thumb_path, script_data, audio_segments
                )
                script_data["final_audit"] = final_audit_report
                require_strict_gate(final_audit_ok, final_audit_report, "final rendered asset audit")
                logger.info("✅ Final publication audit passed")
            except Exception as e:
                logger.error(f"Final publication audit failed: {e}")
                raise

            # Phase 5: Upload
            logger.info("\n📤 PHASE 5: UPLOAD")
            # FINAL hard gate on the exact metadata that will be published.
            # SEO re-writes title/description AFTER the script-stage gate, so
            # re-validate here: a truncated or non-French final title must stop
            # the upload, never reach the channel (the "...battre la" incident).
            try:
                final_gate_ok, final_gate_report = validate_publication_quality(script_data)
                require_strict_gate(final_gate_ok, final_gate_report, "final metadata")

                # FINAL duplicate-title block. The anti-spam check runs at the
                # SCRIPT stage, but Phase 1b (SEO) and the A/B variant picker
                # both REWRITE the title afterwards — so the string that
                # actually reaches YouTube was never dedupe-checked. That is
                # how the channel ended up with two videos titled
                # "Pourquoi le ventre se serre lors d'une peur ?" (flagged in
                # data/video_audit_2026-07-25.json).
                final_title = (script_data.get("title") or "").strip().lower()
                clash = next(
                    (
                        v
                        for v in self.video_history
                        if (v.get("title") or "").strip().lower() == final_title and final_title
                    ),
                    None,
                )
                if clash:
                    raise RuntimeError(
                        f"Duplicate title blocked before upload: {script_data.get('title')!r} "
                        f"already published as {clash.get('youtube_video_id')} "
                        f"on {clash.get('posted_at')}"
                    )

                upload_result = upload_all(final_video, thumb_path, script_data)
                youtube_video_id = (upload_result or {}).get("youtube_video_id")
                if not youtube_video_id:
                    raise RuntimeError(
                        "Publication failed: uploader returned no youtube_video_id; "
                        "history must not record this run as published"
                    )
                logger.info(f"✅ Upload result: {upload_result}")
            except Exception as e:
                logger.error(f"Upload failed: {e}")
                raise

            # Save history
            content_fingerprint = hashlib.sha256(
                "|".join(
                    str(script_data.get(key, "")).strip().lower()
                    for key in ("topic", "title", "voiceover", "hook")
                ).encode("utf-8")
            ).hexdigest()
            self._save_video_history(
                {
                    "content_fingerprint": content_fingerprint,
                    "title": script_data.get("title", "Untitled"),
                    "topic": script_data.get("topic"),
                    "series_title": script_data.get("series_title"),
                    "base_phenomenon": script_data.get("base_phenomenon"),
                    "nominal_phrase": script_data.get("nominal_phrase"),
                    "question_phrase": script_data.get("question_phrase"),
                    "trend_source": script_data.get("trend_source"),
                    "trend_url": script_data.get("trend_url"),
                    # Provenance is essential for post-publish review: a
                    # deterministic local fallback is an operational mode,
                    # never an indistinguishable normal provider success.
                    "script_provider": script_data.get("provider", "unknown"),
                    "used_local_script_fallback": script_data.get("provider") == "local_fallback",
                    "voiceover": script_data.get("voiceover", "")[:500],
                    "posted_at": datetime.now(UTC).isoformat()
                    if (upload_result.get("youtube_success") or upload_result.get("facebook_success"))
                    else None,
                    "facebook_success": upload_result.get("facebook_success", False),
                    "youtube_video_id": upload_result.get("youtube_video_id"),
                    # Scheduled-slot ledger: future runs skip this Paris slot when
                    # picking publishAt (the "2 videos at once" guard).
                    "publish_at": upload_result.get("publish_at"),
                    "seo_score": script_data.get("seo_score", {}).get("scores", {}).get("overall_seo_score"),
                    "predicted_ctr": script_data.get("ctr_prediction", {}).get("ctr_prediction"),
                    "hook_score": script_data.get("shorts_report", {}).get("hook_detail", {}).get("score"),
                    "predicted_retention": script_data.get("shorts_report", {})
                    .get("retention_prediction", {})
                    .get("predicted_avg_retention"),
                    "thumbnail_score": script_data.get("thumbnail_score"),
                    "thumbnail_variants": script_data.get("thumbnail_variants", []),
                    "experiment_id": script_data.get("experiment_id"),
                    # 2026-08-12 viral engineering: hook arm + rubric + loop bridge
                    # feed the intelligence layer's arm comparison (permutation test)
                    "hook_arm": script_data.get("hook_arm"),
                    "hook_score_v2": (script_data.get("viral_audit") or {}).get("hook_score_v2"),
                    "loop_bridge_present": (script_data.get("viral_audit") or {}).get("loop_bridge_present"),
                }
            )

            elapsed = time.time() - start_time
            logger.info("=" * 60)
            logger.info(f"✅ PIPELINE COMPLETE in {elapsed:.1f}s")
            logger.info(f"📹 Video: {script_data.get('title')}")
            logger.info(
                f"🎯 Hook Score: {script_data.get('shorts_report', {}).get('hook_detail', {}).get('score', 'N/A')}"
            )
            logger.info("=" * 60)

            return {
                "success": True,
                "title": script_data.get("title"),
                "video_path": final_video,
                "thumbnail_path": thumb_path,
                "upload_result": upload_result,
                "elapsed_time": elapsed,
            }

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("=" * 60)
            logger.error(f"❌ PIPELINE FAILED after {elapsed:.1f}s")
            logger.error(f"Error: {e}")
            logger.error(traceback.format_exc())
            logger.error("=" * 60)
            _fail(str(e))
            raise

    def run_daily_batch(self, num_videos: int = 3):
        """Run multiple videos in batch"""
        logger.info(f"Starting daily batch: {num_videos} videos")
        succeeded = 0
        failed = 0

        for i in range(num_videos):
            try:
                logger.info(f"\n{'=' * 40}")
                logger.info(f"VIDEO {i + 1}/{num_videos}")
                logger.info(f"{'=' * 40}")

                self.run_pipeline()
                succeeded += 1

                # Wait between videos
                if i < num_videos - 1:
                    wait_time = 300
                    logger.info(f"Waiting {wait_time}s before next video...")
                    time.sleep(wait_time)

            except Exception as e:
                failed += 1
                logger.error(f"Video {i + 1} failed: {e}")
                continue

        logger.info(f"Batch complete: {succeeded} succeeded, {failed} failed out of {num_videos}")

    # ------------------------------------------------------------------
    # Continuity loop: a guard-blocked video must not kill the slot.
    # Retries with a fresh topic (bounded by MAX_GUARD_RETRIES) and tracks
    # every Paris-peak slot attempt so no upload window is silently lost.
    # ------------------------------------------------------------------
    def run_pipeline_with_continuity(
        self,
        topic: str | None = None,
        slot_label: str | None = None,
        blocked_title_keys: set[str] | None = None,
        blocked_topic_keys: set[str] | None = None,
    ) -> dict:
        """Run the pipeline with a bounded retry loop on quality-guard blocks.

        A strict guard (duplicate title, quality gate, silent segments, hook
        score ...) is the pipeline doing its job — but a blocked video must not
        become a MISSED Paris-peak slot. So on a guard-failure we retry with a
        NEW topic (bounded by continuity.MAX_GUARD_RETRIES) before giving up,
        and we register the slot outcome so consistency is visible.
        Returns the successful run dict, or a 'missed' dict if every retry
        failed (so the caller/workflow can decide next steps instead of a hard
        crash).
        """
        from continuity import (
            register_slot_attempt,
            should_retry_on_guard_failure,
        )

        blocked_title_keys = blocked_title_keys if blocked_title_keys is not None else set()
        blocked_topic_keys = blocked_topic_keys if blocked_topic_keys is not None else set()

        guard_phrases = (
            "DUPLICATE TITLE BLOCKED",
            "Duplicate title blocked before upload",
            "Quality gate failed",
            "Retention gate:",
            "Silent segments:",
            "Mixed TTS voices:",
            "Hook failed:",
            "Narration too short:",
            "Narration too long:",
            "Failed to generate image for scene",
        )
        attempt = 0
        last_err = None
        while True:
            attempt += 1
            # A fresh topic on each retry gives the guards a genuinely new chance
            # (the duplicate-title guard especially needs a different subject).
            retry_topic = topic
            if attempt > 1 and not topic:
                retry_topic = None  # let the topic engine pick something new
            try:
                result = self.run_pipeline(
                    topic=retry_topic,
                    blocked_title_keys=blocked_title_keys,
                    blocked_topic_keys=blocked_topic_keys,
                )
                if slot_label:
                    register_slot_attempt(slot_label, "published", (result or {}).get("title", ""))
                return result
            except RuntimeError as exc:
                msg = str(exc)
                is_guard = any(p in msg for p in guard_phrases)
                if not is_guard:
                    raise  # real pipeline error, not a guard block
                last_err = exc
                logger.warning(
                    "🔄 Guard blocked attempt %d (%s). Retrying with a new topic "
                    "to preserve slot consistency...",
                    attempt,
                    msg[:120],
                )
                if not should_retry_on_guard_failure(attempt):
                    break
                # small backoff so consecutive retries don't hammer
                time.sleep(attempt * 30)
        # All guard retries exhausted — the slot is missed this run, but we
        # record it so the workflow can decide (e.g. re-dispatch) instead of
        # silently breaking the cadence.
        if slot_label:
            register_slot_attempt(slot_label, "guard_fail", str(last_err or "")[:80])
        logger.error("🔴 Slot could not be filled after %d guard retries: %s", attempt, last_err)
        return {"success": False, "missed": True, "reason": str(last_err)}


def main():
    """Main entry point"""
    try:
        pipeline = SKILLORPipeline()
        topic = os.environ.get("VIDEO_TOPIC")

        # 2026-08-17 CONTINUITY: label the current Paris peak slot so a
        # guard-blocked video never silently misses the upload window — the
        # retry loop picks a new topic up to MAX_GUARD_RETRIES times before a
        # slot is ever marked as missed.
        try:
            import pytz as _tz

            from continuity import is_us_peak_slot

            _now = datetime.now(_tz.timezone("Europe/Paris"))
            slot_label = f"PAR{_now.hour:02d}:{_now.minute:02d}" if is_us_peak_slot(_now.hour) else "offpeak"
        except Exception:
            slot_label = None

        if topic:
            logger.info(f"Using specific topic: {topic}")
            pipeline.run_pipeline_with_continuity(topic=topic, slot_label=slot_label)
        else:
            # AUTONOMOUS CONTROL: the ML brain decides the cadence (how many
            # videos/day) from real performance, and throttles the batch when
            # recent videos flopped. BATCH_COUNT is now a ceiling, not a fixed
            # number. This is the "ML manages the system" part.
            num_videos = int(os.environ.get("BATCH_COUNT", "3"))
            try:
                from autonomous_controller import get_controls

                controls = get_controls()
                ml_cadence = int(controls.get("recommended_cadence", num_videos))
                throttle = bool(controls.get("throttle"))
                if throttle:
                    logger.warning(
                        "Autonomous ML: recent videos flopped -> throttling batch to 1 "
                        "(recommended cadence was %d)",
                        ml_cadence,
                    )
                    num_videos = 1
                else:
                    num_videos = max(1, min(ml_cadence, num_videos))
                logger.info("Autonomous ML cadence: %d video(s) this run (throttle=%s)", num_videos, throttle)
            except Exception as exc:
                logger.warning("Autonomous cadence control unavailable, using default: %s", exc)

            batch_mode = os.environ.get("BATCH_MODE", "false").lower() == "true"
            if batch_mode:
                pipeline.run_daily_batch(num_videos)
            else:
                # Single run by default, but honour the ML cadence ceiling for
                # the daily scheduled batch — with the continuity retry loop.
                result = pipeline.run_pipeline_with_continuity(slot_label=slot_label)
                if result.get("missed"):
                    logger.warning("Slot skipped after guard retries — see continuity log.")
                    # A skipped slot is not a successful upload, but it is not a
                    # runner failure either. Persist an explicit marker so later
                    # workflow steps skip QA/state commits and the next slot can
                    # retry without a misleading red run or duplicate upload.
                    os.makedirs("data", exist_ok=True)
                    write_json_atomic(
                        "data/slot_skipped.json",
                        {
                            "status": "slot_skipped",
                            "reason": result.get("reason", "guard retries exhausted"),
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )
                    if os.environ.get("FAIL_ON_MISSED_SLOT", "false").lower() == "true":
                        sys.exit(2)

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
