"""
src/seo_analytics.py

Second wave of the PRD "AI SEO Generator" section - the subset that needs
NO external API/keys (no Google Trends, no YouTube Analytics, no
competitor-channel access). Everything here is either a heuristic model
over data SKILLOR already produces, or a PIL/numpy analysis of the actual
thumbnail file already on disk.

Honest scope note up front, since it matters for how much to trust this:
  - predict_ctr() is a HEURISTIC estimate calibrated from the same signals
    quality_checker/seo_generator already score (hook strength, title
    pattern, tag quality). It is NOT trained on real YouTube CTR data,
    because no analytics connection exists yet. Treat the number as "how
    well this follows known CTR-correlated patterns", not a guarantee.
  - score_thumbnail() analyzes contrast/text-length/layout from the actual
    generated image. It does NOT do face/emotion detection - that needs a
    CV model (e.g. opencv + a face/emotion classifier) which isn't in
    requirements.txt. That field is reported as "not_available" rather
    than faked.
  - get_historical_insights() mines output/video_history.json. Today that
    file has no real view/CTR data (nothing pulls YouTube Analytics yet),
    so insights are computed from our own predicted scores and flagged as
    such. The function is written so that the moment real 'actual_ctr' or
    'views' keys start appearing in history entries (once an analytics
    puller is added), it automatically prefers real data over predictions
    without any code changes needed here.
"""

import json
import logging
import os
from collections import defaultdict

# NOTE: numpy / Pillow are imported LAZILY inside score_thumbnail() — they are
# the only consumers, and they are the heaviest deps in this module. Importing
# them at module scope crashed the analytics workflow: analytics.yml installs a
# minimal dependency set (google-api-*, requests, dotenv) and never installs
# numpy/Pillow, so `python src/analytics_updater.py` -> `import seo_analytics`
# died with ModuleNotFoundError before a single metric was fetched. Every
# "YouTube Analytics Sync" run failed this way, which is why no video in
# data/video_history.json ever received real views/CTR.

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HISTORY_FILE = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")


# ---------------------------------------------------------------------------
# 1. CTR Prediction (heuristic, not ML-trained on real data - see module note)
# ---------------------------------------------------------------------------


def predict_ctr(script_data: dict) -> dict:
    """Combines signals already computed elsewhere in the pipeline
    (hook score, SEO score, title pattern) into a single 0-10 CTR estimate
    with a confidence label reflecting how many of those signals were
    actually available. Weights are hand-set from generally-known Shorts
    CTR correlations (strong hook + specific title + tight tags), not
    fitted on this channel's own data."""
    hook_score = None
    if "shorts_report" in script_data:
        hook_score = script_data["shorts_report"].get("hook_detail", {}).get("score")
    seo_score = script_data.get("seo_score", {}).get("scores", {}).get("overall_seo_score")
    title = script_data.get("title", "")

    signals_available = sum(x is not None for x in (hook_score, seo_score, title))

    # Normalize each available signal to 0-10 and weight them.
    parts = []
    if hook_score is not None:
        parts.append((hook_score / 10, 0.45))
    if seo_score is not None:
        parts.append((seo_score / 10, 0.35))
    if title:
        title_len = len(title)
        title_len_score = 10 if 30 <= title_len <= 60 else 6
        parts.append((title_len_score, 0.20))

    if not parts:
        return {
            "ctr_prediction": None,
            "confidence": 0.0,
            "note": "No signals available - run quality/SEO scoring first.",
        }

    weighted_sum = sum(score * weight for score, weight in parts)
    total_weight = sum(weight for _, weight in parts)
    ctr = round(weighted_sum / total_weight, 1)

    confidence = round(0.4 + 0.2 * signals_available, 2)  # 0.6-1.0 range across 1-3 signals
    confidence = min(confidence, 0.85)  # cap - this is a heuristic, never claim near-certainty

    return {
        "ctr_prediction": ctr,
        "confidence": confidence,
        "basis": "heuristic (hook/SEO/title-length signals) - not trained on real channel CTR data yet",
    }


# ---------------------------------------------------------------------------
# 2. Thumbnail SEO scoring (real image analysis via PIL/numpy)
# ---------------------------------------------------------------------------


def score_thumbnail(thumb_path: str, title: str) -> dict:
    """Score the rendered thumbnail using the same geometry as the renderer.

    This remains a deterministic heuristic, not a promise of YouTube CTR. It
    deliberately checks the real headline band, a mobile preview, safe-zone
    compliance, and subject/background separation instead of rewarding pixels
    in an unrelated bottom strip.
    """
    if not thumb_path or not os.path.exists(thumb_path):
        return {"error": f"Thumbnail not found at {thumb_path}"}

    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        return {"error": f"Thumbnail scoring needs numpy+Pillow: {exc}"}

    img = Image.open(thumb_path).convert("RGB")
    arr = np.array(img)
    height, width = arr.shape[:2]

    try:
        from safe_zones import thumbnail_action_safe

        safe_left, band_top, safe_right, band_bottom = thumbnail_action_safe(width, height)
    except Exception:
        safe_left, band_top, safe_right, band_bottom = (
            int(width * 0.05), int(height * 0.53), int(width * 0.86), int(height * 0.76)
        )

    # The renderer places copy in this band. Compare it with the adjacent
    # background bands; global contrast is not a useful proxy for text contrast.
    band = arr[band_top:band_bottom, safe_left:safe_right]
    gray_band = band.mean(axis=2)
    band_contrast = float(gray_band.std())
    contrast_score = min(100, round((band_contrast / 62) * 100))

    # Mobile preview: a Shorts feed makes the artwork tiny. Preserve the
    # original aspect ratio and measure contrast after downsampling.
    preview = img.resize((120, max(1, round(height * 120 / width))))
    preview_arr = np.asarray(preview, dtype=np.float32)
    p_top = round(band_top * preview_arr.shape[0] / height)
    p_bottom = round(band_bottom * preview_arr.shape[0] / height)
    p_left = round(safe_left * preview_arr.shape[1] / width)
    p_right = round(safe_right * preview_arr.shape[1] / width)
    mobile_band = preview_arr[p_top:p_bottom, p_left:p_right]
    mobile_contrast = float(mobile_band.mean(axis=2).std()) if mobile_band.size else 0.0
    mobile_score = min(100, round((mobile_contrast / 48) * 100))

    char_count = len(title)
    word_count = len(title.split())
    if char_count <= 35 and word_count <= 6:
        copy_score = 100
    elif char_count <= 50 and word_count <= 8:
        copy_score = 78
    else:
        copy_score = 52

    # Penalise copy that is likely hidden by the action rail or chrome. The
    # current renderer should always pass this, but the check protects future
    # variants and external thumbnail regeneration scripts.
    safe_zone_score = 100 if safe_right <= int(width * 0.88) and band_bottom <= int(height * 0.80) else 45

    # Colour is a secondary signal only; blue medical visuals must not be
    # penalised merely for lacking warm colours.
    saturation = arr.max(axis=2).astype(np.float32) - arr.min(axis=2).astype(np.float32)
    color_score = max(0, min(100, round(55 + float(saturation.mean()) / 2.5)))

    overall = round(
        (contrast_score * 0.30)
        + (mobile_score * 0.25)
        + (copy_score * 0.20)
        + (safe_zone_score * 0.15)
        + (color_score * 0.10)
    )

    return {
        "contrast_score": contrast_score,
        "mobile_readability_score": mobile_score,
        "readability_score": copy_score,
        "safe_zone_score": safe_zone_score,
        "color_score": color_score,
        "face_emotion_score": "not_available (no face/emotion model configured)",
        "overall_thumbnail_score": overall,
        "title_char_count": char_count,
        "title_word_count": word_count,
        "score_geometry": {
            "text_band": [band_top, band_bottom],
            "safe_box": [safe_left, safe_right],
        },
    }


# ---------------------------------------------------------------------------
# 3. Hashtag ranking (proxy discovery/competition, no real search-volume API)
# ---------------------------------------------------------------------------

# BASE_TAGS in niche_strategy.py are broad/generic -> high volume, high
# competition. CATEGORY_TAGS are mid-specific -> medium/medium. Anything
# else (topic-word tags) is the long-tail -> low volume, low competition,
# highest relevance. This mirrors real tag-volume distributions without
# needing live search-volume data.
_BROAD_TAG_HINTS = {
    "darkfacts",
    "facts",
    "shorts",
    "youtubeshorts",
    "science",
    "didyouknow",
    "mindblowing",
    "funfacts",
    "scaryfacts",
    "viral",
}


def rank_hashtags(tags: list[str]) -> list[dict]:
    """Returns each tag with proxy discovery/competition/trend scores and
    a recommendation, ranked by an overall 'discovery value' that favors a
    realistic broad+niche+long-tail mix over an all-broad or all-long-tail
    list."""
    ranked = []
    for tag in tags:
        clean = tag.lower().lstrip("#")
        if clean in _BROAD_TAG_HINTS:
            volume, competition, tier = 90, 90, "broad"
        elif len(clean) <= 12:
            volume, competition, tier = 55, 50, "niche"
        else:
            volume, competition, tier = 25, 15, "long_tail"

        # Discovery value rewards low competition relative to volume -
        # i.e. the classic "easier to rank, still gets found" sweet spot.
        discovery_score = round((volume * 0.5) + ((100 - competition) * 0.5))

        ranked.append(
            {
                "tag": tag,
                "tier": tier,
                "volume_proxy": volume,
                "competition_proxy": competition,
                "discovery_score": discovery_score,
            }
        )

    ranked.sort(key=lambda x: x["discovery_score"], reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# 4. A/B variant generation + auto-ranking
# ---------------------------------------------------------------------------


def generate_ab_variants(script_data: dict, title_options: list[str]) -> dict:
    """Builds description variants (short-punchy vs longer-context) for
    each of the already-generated title options, scores every
    title+description pairing with predict_ctr(), and returns them ranked
    so the top of the list is the recommended combo - true A/B test PREP,
    not a live split test (that needs real traffic, which happens after
    upload)."""
    hook = script_data.get("hook", "")
    cta = script_data.get("cta", "")
    desc_base = script_data.get("description", "")

    description_variants = {
        "short_punchy": f"{hook}\n\n👇 {cta}",
        "context_first": f"{desc_base}\n\n{hook}\n\n👇 {cta}",
    }

    variants = []
    for title in title_options:
        for desc_label, desc_text in description_variants.items():
            trial_script = dict(script_data)
            trial_script["title"] = title
            trial_script["description"] = desc_text
            ctr = predict_ctr(trial_script)
            variants.append(
                {
                    "title": title,
                    "description_variant": desc_label,
                    "description_preview": desc_text[:120],
                    "predicted_ctr": ctr.get("ctr_prediction"),
                }
            )

    variants.sort(key=lambda v: v["predicted_ctr"] or 0, reverse=True)
    return {
        "variants": variants,
        "recommended": variants[0] if variants else None,
    }


# ---------------------------------------------------------------------------
# 5. Historical learning over output/video_history.json
# ---------------------------------------------------------------------------


def _classify_growth(prev_views, prev_at_iso: str | None, new_views, now) -> dict:
    """Truth-meter for 'views ruk gaye' (2026-08-12).

    Before this, the daily sync overwrote `views` and the old number was
    lost — we could never see WHEN a video stalls (Shorts feed cuts
    distribution after the seed batch flops). Now every fetch records the
    previous reading so growth/stall/flatline is MEASURED, not felt.

    Returns dict with views_prev, velocity/day and a growth_state:
      first_read  — no previous reading exists
      growing     — views increased since last reading
      stalled     — zero growth with >=2 consecutive stalled readings
      flat        — zero growth, first stalled reading
    """
    out = {"views_prev": prev_views, "views_per_day": None, "growth_state": "first_read"}
    if prev_views is None or new_views is None:
        return out
    try:
        hours = 24.0
        if prev_at_iso:
            prev_dt = __import__("datetime").datetime.fromisoformat(prev_at_iso)
            if prev_dt.tzinfo is None:
                prev_dt = prev_dt.replace(tzinfo=__import__("datetime").timezone.utc)
            hours = max((now - prev_dt).total_seconds() / 3600, 1.0)
        out["views_per_day"] = round((new_views - prev_views) * 24.0 / hours, 1)
    except Exception:
        pass
    out["growth_state"] = "growing" if new_views > prev_views else "flat"
    return out


def _load_history() -> list[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _title_pattern(title: str) -> str:
    """Buckets a title by which seo_generator template family produced it,
    so patterns can be compared against each other over time.

    These buckets are FRENCH, matching the templates seo_generator.py actually
    emits. The previous version only recognised English patterns ('truth about',
    "won't tell you", startswith('why')), so on this France-first channel every
    single title fell into 'OTHER' — collapsing all videos into one bucket and
    making the title-pattern comparison completely useless."""
    t = title.lower().strip()

    if t.startswith("pourquoi"):
        return "POURQUOI"  # "Pourquoi le hoquet commence brusquement ?"
    if t.startswith("ce que votre corps"):
        return "CE_QUE_VOTRE_CORPS"  # "Ce que votre corps vous dit quand..."
    if t.startswith(("ce qu'il faut comprendre", "ce qu’il faut comprendre")):
        return "CE_QUIL_FAUT_COMPRENDRE"
    if t.startswith(("ce que la science", "la science derrière", "la science derriere")):
        return "LA_SCIENCE"
    if t.startswith("ce qui se passe"):
        return "CE_QUI_SE_PASSE"
    if t.startswith("comment"):
        return "COMMENT"
    if any(e in title for e in ("🧠", "🫀", "🔬", "⚡")):
        return "EMOJI_ENHANCED"
    # Short branded series labels ("Corps lourd", "Réveil avant l'alarme").
    if len(t.split()) <= 3:
        return "SERIE_COURTE"
    return "OTHER"


def get_historical_insights(min_sample: int = 3) -> dict:
    """Groups past videos by title pattern and compares average performance.
    Uses 'actual_ctr'/'views' from history entries when present (once a
    YouTube Analytics puller is added upstream); otherwise falls back to
    each entry's own predicted_ctr/seo_score recorded at generation time.
    Buckets with fewer than min_sample videos are excluded - not enough
    data to say anything meaningful yet."""
    history = _load_history()
    if not history:
        return {"insights": [], "note": "No video history yet."}

    using_real_data = any("actual_ctr" in v or "views" in v for v in history)

    buckets = defaultdict(list)
    for v in history:
        title = v.get("title", "")
        if not title:
            continue
        pattern = _title_pattern(title)
        if "actual_ctr" in v:
            metric = v["actual_ctr"]
        elif "predicted_ctr" in v:
            metric = v["predicted_ctr"]
        elif "seo_score" in v:
            metric = v["seo_score"]
        else:
            continue
        if metric is not None:
            buckets[pattern].append(metric)

    insights = []
    for pattern, values in buckets.items():
        if len(values) >= min_sample:
            insights.append(
                {
                    "title_pattern": pattern,
                    "sample_size": len(values),
                    "avg_score": round(sum(values) / len(values), 2),
                }
            )
    insights.sort(key=lambda x: x["avg_score"], reverse=True)

    return {
        "insights": insights,
        "data_source": "real_analytics"
        if using_real_data
        else "predicted_scores (no analytics connected yet)",
        "note": None if insights else f"Not enough videos per title-pattern yet (need >= {min_sample} each).",
    }


# ---------------------------------------------------------------------------
# 6. REAL YouTube Analytics fetch (needs OAuth creds - see uploader.py)
#
# Everything above this point is heuristic. This is the actual "system ab
# blind nahi" piece: it calls the real YouTube Analytics API (v2) for one
# video and returns real views / average-view-duration / real CTR.
#
# Reuses the SAME OAuth refresh-token creds uploader.py already uses for
# the Data API upload - it just additionally needs the
# `yt-analytics.readonly` scope to have been granted when that
# REFRESH_TOKEN was issued. If it wasn't, this returns an 'error' instead
# of raising, so a missing scope never crashes the pipeline.
# ---------------------------------------------------------------------------


def _fetch_statistics_fallback(youtube_video_id: str) -> dict:
    """Fetch lifetime views/likes/comments through YouTube Data API v3."""
    try:
        from youtube_oauth import data_video_statistics, refresh_session

        session = refresh_session()
        resp = data_video_statistics(session, youtube_video_id)
        items = resp.get("items") or []
        if not items:
            return {"error": f"video {youtube_video_id} not found via Data API"}
        stats = items[0].get("statistics", {})
        return {
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "via": "statistics",
        }
    except Exception as exc:
        return {"error": f"statistics fallback failed: {str(exc)[:200]}"}


def fetch_actual_performance(youtube_video_id: str, days_back: int = 30) -> dict:
    """Fetch real Shorts performance with OAuth scope validation and retries.

    Analytics uses ``yt-analytics.readonly``. If that scope is missing or the
    channel does not expose an optional metric, the function returns a safe,
    structured result and falls back to Data API lifetime statistics.
    """
    import datetime as _dt
    import re as _re

    from youtube_oauth import YouTubeAPIError, YouTubeOAuthError, analytics_query, refresh_session

    try:
        session = refresh_session()
    except YouTubeOAuthError as exc:
        fallback = _fetch_statistics_fallback(youtube_video_id)
        if "error" not in fallback:
            fallback["analytics_error"] = str(exc)[:300]
            return fallback
        return {"error": str(exc)[:300], "fallback_error": fallback.get("error")}

    end = _dt.datetime.now(_dt.UTC).date()
    start = end - _dt.timedelta(days=max(days_back, 1))
    requested = [
        "views",
        "engagedViews",
        "averageViewDuration",
        "averageViewPercentage",
        # Reach/Shorts-feed identifiers are probed when the API exposes them
        # for this channel/report. Unsupported identifiers are removed one at
        # a time and persisted as unavailable rather than represented as zero.
        "shortsFeedShown",
        "stayedToWatch",
        "viewedVsSwipedAway",
        "impressions",
        "impressionClickThroughRate",
    ]
    requested_initial = tuple(requested)
    dropped = []
    resp = None
    for _ in range(len(requested)):
        try:
            resp = analytics_query(
                session,
                ids="channel==MINE",
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                metrics=",".join(requested),
                dimensions="video",
                filters=f"video=={youtube_video_id}",
            )
            break
        except YouTubeAPIError as exc:
            unknown = _re.search(r"Unknown identifier \(([\w]+)\)", exc.detail)
            if exc.status == 400 and unknown and unknown.group(1) in requested and len(requested) > 1:
                bad = unknown.group(1)
                requested.remove(bad)
                dropped.append(bad)
                logger.info("Metric '%s' unavailable on this channel -> retrying without it.", bad)
                continue
            if exc.status in (401, 403):
                fallback = _fetch_statistics_fallback(youtube_video_id)
                if "error" not in fallback:
                    fallback["analytics_error"] = str(exc)[:300]
                    return fallback
                return {
                    "error": (
                        "YouTube Analytics authorization failed; refresh token needs "
                        "yt-analytics.readonly (fallback also failed: "
                        f"{fallback['error']})"
                    )
                }
            return {"error": str(exc)[:300]}
        except YouTubeOAuthError as exc:
            return {"error": str(exc)[:300]}

    if resp is None:
        return {"error": "No supported metric combination was accepted by the Analytics API."}

    rows = resp.get("rows") or []
    if not rows:
        return {"note": "No analytics rows yet - data can take 24-48h to populate after upload."}

    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    values = dict(zip(headers, rows[0], strict=False))
    unavailable = sorted(set(dropped) | (set(requested_initial) - set(headers)))
    stayed_to_watch = values.get("stayedToWatch")
    viewed_vs_swiped = values.get("viewedVsSwipedAway")
    # YouTube Studio labels this viewer-choice signal "Stayed to watch";
    # expose both normalized names when one supported API field supplies it.
    if stayed_to_watch is None:
        stayed_to_watch = viewed_vs_swiped
    if viewed_vs_swiped is None:
        viewed_vs_swiped = stayed_to_watch
    return {
        "video_id": youtube_video_id,
        "views": values.get("views"),
        "engaged_views": values.get("engagedViews"),
        "average_view_duration_sec": values.get("averageViewDuration"),
        "average_view_percentage": values.get("averageViewPercentage"),
        "shorts_feed_shown": values.get("shortsFeedShown"),
        "stayed_to_watch": stayed_to_watch,
        "viewed_vs_swiped_away": viewed_vs_swiped,
        "impressions": values.get("impressions"),
        "actual_ctr": values.get("impressionClickThroughRate"),
        "available_metrics": headers,
        "unavailable_metrics": unavailable,
        "fetched_at": _dt.datetime.now(_dt.UTC).isoformat(),
    }


def update_history_with_real_metrics(min_hours_old: int = 24, refresh_after_hours: int = 24) -> dict:
    """Meant to run on its OWN schedule (separate cron/GitHub Action),
    NOT inside the main generation pipeline - real analytics data isn't
    available immediately after upload.

    Walks data/video_history.json, finds entries with a youtube_video_id
    that are at least `min_hours_old` hours old, fetches real numbers for
    each via fetch_actual_performance(), and writes them back into that SAME
    history entry. Once this has run for a video,
    get_historical_insights() above automatically prefers
    'real_analytics' over predicted scores - no other code changes
    needed, it already checks for 'actual_ctr'/'views' first.

    Refresh policy: an entry is re-fetched when it has never been fetched, or
    when its last fetch is older than `refresh_after_hours`. The previous
    version skipped any entry that merely CONTAINED an 'actual_ctr' key — on a
    channel where the API does not serve CTR that key gets written as None, so
    the video was permanently frozen at its first (empty) reading and its views
    never grew. Freshness is now tracked by 'analytics_fetched_at' instead."""
    import datetime as _dt

    history = _load_history()
    if not history:
        return {"updated": 0, "note": "No history file yet."}

    now = _dt.datetime.now(_dt.UTC)
    updated, skipped_fresh, failed = 0, 0, 0
    for entry in history:
        vid = entry.get("youtube_video_id")
        posted_at = entry.get("posted_at")
        if not vid or not posted_at:
            continue
        try:
            posted_dt = _dt.datetime.fromisoformat(posted_at)
            if posted_dt.tzinfo is None:  # tolerate legacy naive stamps
                posted_dt = posted_dt.replace(tzinfo=_dt.UTC)
        except Exception:
            continue
        if (now - posted_dt).total_seconds() / 3600 < min_hours_old:
            continue

        last_fetch = entry.get("analytics_fetched_at")
        if last_fetch:
            try:
                last_dt = _dt.datetime.fromisoformat(last_fetch)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=_dt.UTC)
                if (now - last_dt).total_seconds() / 3600 < refresh_after_hours:
                    skipped_fresh += 1
                    continue
            except Exception:
                pass  # unparseable stamp -> just re-fetch

        metrics = fetch_actual_performance(vid)
        if "error" in metrics or "note" in metrics:
            failed += 1
            logger.info(f"{vid}: {metrics.get('error') or metrics.get('note')}")
            continue

        # 2026-08-12: keep the PREVIOUS reading before overwriting so the
        # truth report can see growth vs stall per video (was invisible).
        growth = _classify_growth(
            entry.get("views"), entry.get("analytics_fetched_at"), metrics.get("views"), now
        )
        if growth["growth_state"] == "flat":
            entry["stall_streak"] = int(entry.get("stall_streak") or 0) + 1
            if entry["stall_streak"] >= 2:
                growth["growth_state"] = "stalled"
        elif growth["growth_state"] == "growing":
            entry["stall_streak"] = 0
        entry["views_prev"] = growth["views_prev"]
        entry["views_per_day"] = growth["views_per_day"]
        entry["growth_state"] = growth["growth_state"]

        entry["views"] = metrics.get("views")
        entry["engaged_views"] = metrics.get("engaged_views")
        entry["actual_ctr"] = metrics.get("actual_ctr")
        entry["average_view_duration_sec"] = metrics.get("average_view_duration_sec")
        entry["average_view_percentage"] = metrics.get("average_view_percentage")
        entry["shorts_feed_shown"] = metrics.get("shorts_feed_shown")
        entry["stayed_to_watch"] = metrics.get("stayed_to_watch")
        entry["viewed_vs_swiped_away"] = metrics.get("viewed_vs_swiped_away")
        entry["analytics_available_metrics"] = metrics.get("available_metrics", [])
        entry["analytics_unavailable_metrics"] = metrics.get("unavailable_metrics", [])
        if metrics.get("likes") is not None:
            entry["likes"] = metrics["likes"]
        if metrics.get("comments") is not None:
            entry["comments"] = metrics["comments"]
        entry["analytics_fetched_at"] = metrics.get("fetched_at") or (_dt.datetime.now(_dt.UTC).isoformat())
        entry["analytics_via"] = metrics.get("via", "analytics")
        updated += 1
        logger.info(
            f"Updated real metrics for {vid} (via {metrics.get('via', 'analytics')}): "
            f"views={metrics.get('views')}, engaged_views={metrics.get('engaged_views')}, "
            f"stayed_to_watch={metrics.get('stayed_to_watch')}, "
            f"feed_shown={metrics.get('shorts_feed_shown')}, "
            f"CTR={metrics.get('actual_ctr')}, avg_view_pct={metrics.get('average_view_percentage')}, "
            f"unavailable={metrics.get('unavailable_metrics', [])}"
        )

    if updated:
        # Atomic write (tmp + replace), matching the rest of the pipeline. A
        # crash mid-write previously truncated the whole channel history.
        os.makedirs(os.path.dirname(HISTORY_FILE) or ".", exist_ok=True)
        tmp_path = HISTORY_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, HISTORY_FILE)

    return {
        "updated": updated,
        "skipped_fresh": skipped_fresh,
        "failed": failed,
        "total_entries": len(history),
    }


if __name__ == "__main__":
    test_script = {
        "title": "🫀 Your Heart Has Its Own Brain",
        "hook": "Doctors don't want you to know this about your heart...",
        "cta": "Follow for more dark body secrets",
        "description": "Your heart contains its own independent nervous system.",
        "seo_score": {"scores": {"overall_seo_score": 85}},
        "shorts_report": {"hook_detail": {"score": 60}},
    }
    print(json.dumps(predict_ctr(test_script), indent=2))
    print(json.dumps(rank_hashtags(["darkfacts", "heartfacts", "neuroscience"]), indent=2))
    print(json.dumps(generate_ab_variants(test_script, ["Title A", "Title B"]), indent=2))
