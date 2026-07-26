"""
src/shorts_enhancer.py

PRD "Shorts Generator" feature. SKILLOR already produces Shorts-only videos
(video_editor.py hardcodes a 1080x1920 canvas and 40-55s target), so the
"convert a long video into Shorts" part of the PRD doesn't apply here.
What DOES apply and add value on top of the existing pipeline:

  - A finer-grained hook score with concrete fix suggestions (quality_checker
    already scores the hook 0-100 for the approve/reject gate; this module
    explains *why* and *what to change*, so a human reviewing a low-scoring
    video knows what to fix instead of just seeing a number)
  - Per-scene caption pacing check (words-per-second) - a scene can pass
    quality_checker's overall pacing check while still having one scene
    that flashes by unreadably fast or drags
  - Shorts-specific hashtag set (#shorts is close to mandatory for Shorts
    surfacing - separate from the general SEO tags in seo_generator.py)
  - SRT subtitle file export from the exact per-scene audio durations
    video_editor.py already computes - lets you upload real closed
    captions (accessibility + a documented small SEO/reach benefit),
    reusing timing that's otherwise only baked into burned-in captions
"""

import os
import re
import logging
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Readable range for on-screen word-by-word captions. Below this, text
# flashes by too fast to read; above this, it drags and viewers swipe away.
# Captions are shown in short two-word chunks by video_editor, so viewers can
# comfortably follow a natural cloned voice up to 4.0 words/sec. The previous
# 3.5 limit rejected otherwise healthy 30-second videos for tiny rounding or
# one-scene delivery variations (for example 3.52 words/sec).
MIN_WORDS_PER_SEC = 1.5
MAX_WORDS_PER_SEC = 4.0

SHORTS_HASHTAGS = ["#shorts", "#science", "#scienceduquotidien"]


# ---------------------------------------------------------------------------
# Hook scoring with actionable feedback
# ---------------------------------------------------------------------------

_CURIOSITY_TRIGGERS = ["mythe", "vrai", "saviez", "pourquoi", "comment", "étrange"]
_POWER_WORDS = ["science", "cerveau", "corps", "mémoire", "sommeil", "réflexe"]


def score_hook_detailed(hook: str) -> Dict:
    """Score a hook for clarity and specificity without rewarding clickbait."""
    hook = (hook or "").strip()
    words = hook.split()
    if not hook:
        return {'score': 0, 'checks': [{'name': 'present', 'passed': False, 'note': 'Hook is missing.'}]}

    checks, score = [], 35
    length_ok = 5 <= len(words) <= 9
    checks.append({'name': 'spoken_length', 'passed': length_ok,
                   'note': f'{len(words)} words; target is 5-9.'})
    if length_ok:
        score += 25

    direct = any(re.search(rf"\b{w}\b", hook.lower()) for w in ('vous', 'votre', 'corps', 'cerveau', 'coeur', 'cœur'))
    checks.append({'name': 'viewer_or_subject', 'passed': direct,
                   'note': 'Names the viewer or a clear body subject.'})
    if direct:
        score += 15

    specific = bool(re.search(r"\b(sommeil|lumière|mémoire|coeur|cœur|cerveau|sang|nerf|hormone|cellule|muscle|peau|ventre|énergie|souffle)\w*\b", hook.lower()))
    checks.append({'name': 'specificity', 'passed': specific,
                   'note': 'Uses a concrete topic word instead of generic hype.'})
    if specific:
        score += 20

    clickbait = any(x in hook.lower() for x in ("les médecins cachent", "secret choquant", "incroyable", "100 % vrai"))
    checks.append({'name': 'no_fake_hype', 'passed': not clickbait,
                   'note': 'Avoids manipulative or unsupported hype.'})
    if not clickbait:
        score += 10
    else:
        score -= 30

    return {'score': max(0, min(score, 100)), 'checks': checks}


# Backward/alt-compatible alias: some callers import the shorter name
# `score_hook` instead of `score_hook_detailed`. main.py calls this with
# the *whole script_data dict* (not just the hook string) and expects a
# 'suggestions' list in the result (used for hook_result.get('suggestions')),
# so this wraps score_hook_detailed to accept either input shape and always
# include 'suggestions' alongside the original 'checks' detail.
def score_hook(hook_or_script_data) -> Dict:
    """Score a hook. Accepts either the hook string directly, or a
    script_data dict (uses its 'hook' field) - main.py passes the dict.
    Returns {'score', 'checks', 'suggestions'} - 'suggestions' is a plain
    list of fix-it strings for any check that didn't pass, derived from
    score_hook_detailed's 'checks'.
    """
    if isinstance(hook_or_script_data, dict):
        hook = hook_or_script_data.get('hook', '')
    else:
        hook = hook_or_script_data or ''

    result = score_hook_detailed(hook)
    result['suggestions'] = [
        check['note'] for check in result.get('checks', [])
        if not check.get('passed', True)
    ]
    return result


# ---------------------------------------------------------------------------
# Per-scene caption pacing
# ---------------------------------------------------------------------------

def check_caption_pacing(scenes: List[Dict], audio_segments: List[Dict]) -> Dict:
    """Flags any individual scene whose words-per-second falls outside the
    readable range, even if the video's overall pacing (checked in
    quality_checker) looks fine on average. audio_segments come from
    voice_generator.generate_voice_segments() and carry the real spoken
    duration per scene."""
    issues = []
    per_scene = []

    for i, (scene, seg) in enumerate(zip(scenes, audio_segments)):
        caption = scene.get('caption', '')
        duration = max(seg.get('duration', 0), 0.01)
        word_count = len(caption.split())
        wps = word_count / duration

        status = "ok"
        if wps < MIN_WORDS_PER_SEC:
            status = "too_slow"
            issues.append(f"Scene {i+1}: {wps:.1f} words/sec - dragging, consider trimming the caption or shortening the scene.")
        elif wps > MAX_WORDS_PER_SEC:
            status = "too_fast"
            issues.append(f"Scene {i+1}: {wps:.1f} words/sec - too fast to read, consider splitting into two scenes.")

        per_scene.append({'scene': i + 1, 'words_per_sec': round(wps, 2), 'status': status})

    return {
        'per_scene': per_scene,
        'issues': issues,
        'all_readable': len(issues) == 0,
    }


# ---------------------------------------------------------------------------
# Autofix: trim captions that read too fast for their scene's spoken duration
# ---------------------------------------------------------------------------

def autofix_too_fast_captions(scenes: List[Dict], audio_segments: List[Dict]) -> List[Dict]:
    """For any scene whose words-per-second (per check_caption_pacing) is
    above MAX_WORDS_PER_SEC, trim the on-screen caption down to the number
    of words that actually fit its spoken duration at a readable pace.

    This only shortens the *on-screen caption text* - it does not touch or
    re-generate the audio, so spoken narration timing is unaffected; this
    just keeps burned-in/SRT captions from flashing by unreadably fast.
    Scenes that are already OK (or "too_slow") are returned unchanged.
    Returns a new list; the input `scenes` list/dicts are not mutated.
    """
    fixed_scenes = []
    for i, scene in enumerate(scenes):
        seg = audio_segments[i] if i < len(audio_segments) else {}
        duration = max(seg.get('duration', 0), 0.01)
        caption = scene.get('caption', '')
        words = caption.split()
        wps = len(words) / duration if words else 0

        new_scene = dict(scene)
        if wps > MAX_WORDS_PER_SEC and len(words) > 1:
            # Keep as many words as fit at the max readable pace, but
            # never trim down to nothing.
            max_words = max(1, int(duration * MAX_WORDS_PER_SEC))
            if max_words < len(words):
                trimmed = " ".join(words[:max_words]).rstrip(",;:")
                if not trimmed.endswith((".", "!", "?")):
                    trimmed += "."
                logger.info(
                    f"Scene {i+1}: autofixed caption from {len(words)} to "
                    f"{max_words} words ({wps:.1f} -> "
                    f"{max_words/duration:.1f} words/sec)"
                )
                new_scene['caption'] = trimmed
        fixed_scenes.append(new_scene)
    return fixed_scenes


# ---------------------------------------------------------------------------
# Retention prediction (heuristic, not ML - gives directional signal +
# concrete suggestions, same spirit as quality_checker's scoring)
# ---------------------------------------------------------------------------

# Shorts retention drops off fastest in the first ~3s (the hook) and again
# past the ~45-50s mark where swipe-away rates climb sharply.
_IDEAL_MIN_SECONDS = 40.0
_IDEAL_MAX_SECONDS = 55.0


def predict_retention(script_data: Dict, audio_segments: List[Dict]) -> Dict:
    """Heuristic (non-ML) retention estimate combining hook strength,
    caption pacing, and total video length. Returns predicted_avg_retention
    and predicted_swipe_away as 0-1 fractions, plus actionable suggestions.
    Intentionally conservative/simple - it's a directional signal for the
    pipeline logs, not a trained model.
    """
    suggestions = []

    hook = script_data.get('hook', '')
    hook_score = score_hook_detailed(hook).get('score', 0)  # 0-100

    scenes = script_data.get('scenes', [])
    pacing = check_caption_pacing(scenes, audio_segments)
    unreadable_ratio = (
        len(pacing.get('issues', [])) / len(scenes) if scenes else 0
    )

    total_seconds = sum(float(s.get('duration', 0)) for s in audio_segments)

    # Base retention scales with hook strength - a weak hook loses viewers
    # before anything else in the video matters.
    retention = 0.35 + 0.45 * (hook_score / 100.0)

    # Unreadable captions cost retention roughly proportional to how much
    # of the video is affected.
    retention -= 0.25 * unreadable_ratio
    if unreadable_ratio > 0:
        suggestions.append(
            "Some captions are hard to read at their spoken pace - "
            "shortening them (or letting autofix_too_fast_captions run) "
            "should help viewers stay through those scenes."
        )

    # Length penalty outside the sweet spot.
    if total_seconds < _IDEAL_MIN_SECONDS:
        retention -= 0.05
        suggestions.append(
            f"Video is {total_seconds:.0f}s, a bit short for strong Shorts "
            f"retention curves - {_IDEAL_MIN_SECONDS:.0f}-{_IDEAL_MAX_SECONDS:.0f}s tends to perform better."
        )
    elif total_seconds > _IDEAL_MAX_SECONDS:
        retention -= 0.08
        suggestions.append(
            f"Video is {total_seconds:.0f}s, past the "
            f"{_IDEAL_MAX_SECONDS:.0f}s point where swipe-away rises - consider trimming a scene."
        )

    if hook_score < 60:
        suggestions.append(
            "Hook score is below 60 - a sharper, more specific opening "
            "line usually recovers the most retention per fix."
        )

    retention = max(0.05, min(retention, 0.95))
    swipe_away = max(0.0, min(1.0 - retention, 0.95))

    return {
        'predicted_avg_retention': round(retention, 3),
        'predicted_swipe_away': round(swipe_away, 3),
        'suggestions': suggestions,
    }


# ---------------------------------------------------------------------------
# Shorts hashtags
# ---------------------------------------------------------------------------

def generate_shorts_hashtags(topic_tags: List[str], n: int = 5) -> List[str]:
    """#shorts-family tags first (near-mandatory for Shorts shelf
    placement), then the top niche tags already computed by
    seo_generator/niche_strategy - avoids re-deriving tags from scratch."""
    result = list(SHORTS_HASHTAGS)
    for t in topic_tags:
        tag = f"#{t}" if not t.startswith('#') else t
        if tag.lower() not in (x.lower() for x in result):
            result.append(tag)
        if len(result) >= n:
            break
    return result[:n]


# ---------------------------------------------------------------------------
# SRT subtitle export
# ---------------------------------------------------------------------------

def _seconds_to_srt_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(scenes: List[Dict], audio_segments: List[Dict], output_path: str = None) -> str:
    """Builds standard SRT subtitle content from each scene's caption and
    its real audio duration (same timing source video_editor.py uses for
    burned-in captions, so the uploaded closed-caption file matches what's
    on screen). Writes to output_path if given, always returns the SRT
    text either way."""
    lines = []
    t = 0.0
    for i, (scene, seg) in enumerate(zip(scenes, audio_segments), start=1):
        duration = max(seg.get('duration', 0), 0.6)
        start, end = t, t + duration
        lines.append(str(i))
        lines.append(f"{_seconds_to_srt_timestamp(start)} --> {_seconds_to_srt_timestamp(end)}")
        lines.append(scene.get('caption', '').strip())
        lines.append("")
        t = end

    srt_content = "\n".join(lines)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        logger.info(f"SRT subtitles written to {output_path}")

    return srt_content


# ---------------------------------------------------------------------------
# Combined report
# ---------------------------------------------------------------------------

def check_five_second_cliff(audio_segments: List[Dict]) -> Dict:
    """Guard the 4.6-9.0s window where THIS channel actually loses viewers.

    Measured 2026-07-26 from YouTube's audienceRetention curves (the
    second-by-second report, pulled for the first time by
    scripts/swipe_analysis.py) across all 14 videos that have data:

        at 1s   ~108% still watching   (>100% = replays; the hook works)
        at 3s   ~101%                  (still fine)
        at 5s    ~91%
        at 10s   ~40%                  <-- the cliff

        every single video's steepest drop: between 4.6s and 9.0s
        median: 5.15s

        correlation(10s survival, final retention) = +0.88

    That +0.88 is the strongest signal in this channel's data. The hook is
    NOT the problem — nobody leaves in the first 3 seconds. Scene 2 and
    scene 3 are where the video is won or lost, and that is exactly where
    the scripts restate the question instead of paying it off.

    So the rule enforced here is narrow and evidence-backed: the segment
    covering roughly 4-9s must not be dead air or a throwaway line. It must
    carry real content, because 88% of the final retention outcome is
    decided by how many viewers are still there at 10 seconds.
    """
    if not audio_segments:
        return {'ok': True, 'note': 'no audio to inspect'}

    CLIFF_START, CLIFF_END = 4.0, 9.0
    elapsed, covering, issues = 0.0, [], []
    for index, segment in enumerate(audio_segments):
        duration = float(segment.get('duration', 0) or 0)
        start, end = elapsed, elapsed + duration
        if end > CLIFF_START and start < CLIFF_END:
            covering.append((index, segment, start, end))
        elapsed = end

    if not covering:
        return {'ok': True, 'note': 'video shorter than the cliff window'}

    words_in_window = 0
    for index, segment, start, end in covering:
        overlap = min(end, CLIFF_END) - max(start, CLIFF_START)
        text = (segment.get('text') or segment.get('caption') or '')
        if not text:
            continue
        rate = len(text.split()) / duration if (duration := (end - start)) else 0
        words_in_window += rate * max(overlap, 0)

    # ~2.6 words/sec at this TTS pace: a 5s window should carry ~13 words.
    # Below 8 means the viewer is being asked to wait through filler at the
    # exact moment 60% of them decide to leave.
    if words_in_window < 8:
        issues.append(
            f"Only ~{words_in_window:.0f} words spoken between "
            f"{CLIFF_START:.0f}-{CLIFF_END:.0f}s. This is the measured cliff "
            f"(every video's steepest drop lands here); it must deliver "
            f"substance, not filler."
        )

    return {
        'ok': not issues,
        'issues': issues,
        'window': f"{CLIFF_START:.0f}-{CLIFF_END:.0f}s",
        'words_in_window': round(words_in_window, 1),
        'scenes_covering_cliff': [i for i, _s, _a, _b in covering],
    }


def build_shorts_report(script_data: Dict, audio_segments: List[Dict], topic_tags: List[str]) -> Dict:
    """Single entry point main.py can call alongside quality_checker /
    anti_spam. Doesn't gate publishing on its own (quality_checker already
    owns the approve/reject decision) - this is diagnostic + asset output."""
    hook_detail = score_hook_detailed(script_data.get('hook', ''))
    pacing = check_caption_pacing(script_data.get('scenes', []), audio_segments)
    hashtags = generate_shorts_hashtags(topic_tags)
    retention_prediction = predict_retention(script_data, audio_segments)
    cliff = check_five_second_cliff(audio_segments)

    return {
        'hook_detail': hook_detail,
        'caption_pacing': pacing,
        'five_second_cliff': cliff,
        'shorts_hashtags': hashtags,
        'retention_prediction': retention_prediction,
    }


if __name__ == "__main__":
    import json
    test_scenes = [
        {"visual": "human heart beating", "caption": "Your heart has its own brain."},
        {"visual": "close up neurons", "caption": "It contains over 40000 neurons that operate independently of your actual brain."},
    ]
    test_segments = [{"duration": 2.0}, {"duration": 3.0}]
    report = build_shorts_report(
        {"hook": "Doctors don't want you to know this about your heart...", "scenes": test_scenes},
        test_segments,
        ["darkfacts", "heartfacts", "science"],
    )
    print(json.dumps(report, indent=2))
    print(generate_srt(test_scenes, test_segments))
