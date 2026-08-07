#!/usr/bin/env python3
"""French competitor-intelligence builder for SKILLOR.

This is deliberately *analysis*, not cloning. It fetches public YouTube metadata
from high-performing French/French-language Shorts, learns which title patterns
and topic tags correlate with high views, and writes a compact signal file used
by `src/seo_generator.py`.

Copy policy:
- exact competitor titles are stored only as human audit references;
- the generator uses derived templates such as "Pourquoi {question_phrase} ?";
- exact title matches are blocked before a competitor-inspired option is used.

Configuration (env or CLI):
- YOUTUBE_API_KEY                  required for live fetches
- COMPETITOR_CHANNEL_IDS           comma-separated channel IDs (UC...)
- COMPETITOR_QUERIES_FR            fallback discovery queries, pipe/comma-separated
- COMPETITOR_MIN_VIEWS             default: 1000000
- COMPETITOR_MAX_DURATION_SECONDS  default: 90
- COMPETITOR_INTEL_PATH            default: data/competitor_intel_fr.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

LOG = logging.getLogger("competitor-intel")
API = "https://www.googleapis.com/youtube/v3"
# Auto competitor discovery. The owner does NOT need to hand-pick channels:
# these French queries discover high-view Shorts across the niche, then the
# script learns from whichever channels/videos actually crossed the view filter.
DEFAULT_QUERIES = (
    "shorts science corps humain français",
    "shorts cerveau sommeil français",
    "shorts santé corps humain français",
    "shorts psychologie cerveau français",
    "shorts curiosités scientifiques français",
    "pourquoi le corps humain shorts",
    "pourquoi le cerveau shorts français",
    "vulgarisation scientifique shorts français",
    "science du quotidien shorts français",
    "faits scientifiques shorts français",
)

FRENCH_MARKERS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "ce", "cette", "ces",
    "ton", "ta", "tes", "votre", "vos", "tu", "vous", "pourquoi", "comment",
    "quand", "corps", "cerveau", "sommeil", "cœur", "coeur", "science", "santé",
    "mémoire", "stress", "ventre", "peau", "français", "france",
}
ENGLISH_TAG_BLOCKLIST = {
    "facts", "bodyfacts", "body facts", "humanbody", "human body", "brainfacts",
    "brain facts", "sciencefacts", "science facts", "didyouknow", "mindblown",
    "amazingfacts", "health", "body", "brain",
}
STOP = {
    "le", "la", "les", "un", "une", "des", "du", "de", "ce", "cette", "ces",
    "et", "ou", "pour", "dans", "sur", "avec", "sans", "que", "qui", "quand",
    "quoi", "dont", "plus", "très", "tres", "votre", "vous", "ton", "tes",
    "pourquoi", "comment", "short", "shorts", "video", "vidéo", "français",
    "francaise", "française", "science", "savoir", "faut", "comprendre",
}

SAFE_TEMPLATE_BY_PATTERN = {
    "pourquoi-question": {
        "id": "pourquoi-question",
        "template": "Pourquoi {question_phrase} ?",
        "needs": "question_phrase",
    },
    "ce-qui-se-passe": {
        "id": "ce-qui-se-passe",
        "template": "Ce qui se passe quand {question_phrase}",
        "needs": "question_phrase",
    },
    "ce-que-corps-revele": {
        "id": "ce-que-corps-revele",
        "template": "Ce que ton corps révèle quand {question_phrase}",
        "needs": "question_phrase",
    },
    "la-science": {
        "id": "la-science",
        "template": "La science derrière {nominal_phrase}",
        "needs": "nominal_phrase",
    },
    "ce-quil-faut": {
        "id": "ce-quil-faut",
        "template": "Ce qu'il faut savoir sur {nominal_phrase}",
        "needs": "nominal_phrase",
    },
}


def _split_env(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,|\n]", value) if item.strip()]


def _resolve_channel_handle(handle: str, api_key: str) -> str | None:
    """Resolve a '@handle' (or bare handle) to a channel UC... id via the
    channels.list forHandle endpoint. If the input already looks like a UC...
    id, return it unchanged. Returns None if resolution fails."""
    h = handle.strip().lstrip("@").strip()
    if h.startswith("UC") and len(h) == 24:
        return handle.strip()
    try:
        payload = _request(
            "channels",
            {"part": "id", "forHandle": h},
            api_key,
        )
        items = payload.get("items") or []
        return items[0]["id"] if items else None
    except Exception as exc:
        LOG.warning("Could not resolve handle %r to channel id: %s", handle, exc)
        return None


def _request(path: str, params: dict, api_key: str, *, retries: int = 2) -> dict:
    query = dict(params)
    query["key"] = api_key
    url = f"{API}/{path}?{urllib.parse.urlencode(query)}"
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            last_error = RuntimeError(f"HTTP {exc.code}: {body}")
            if exc.code in {400, 401, 403, 404}:
                break
        except Exception as exc:  # network timeout/transient
            last_error = exc
        if attempt < retries:
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"YouTube API {path} failed: {last_error}")


def _duration_seconds(iso_duration: str) -> int:
    """Parse the PT#H#M#S subset YouTube returns in contentDetails.duration."""
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not match:
        return 0
    hours, minutes, seconds = (int(x or 0) for x in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _normalise_title(title: str) -> str:
    return re.sub(r"[^a-z0-9à-ÿœæ ]", "", (title or "").lower()).strip()


def _title_hash(title: str) -> str:
    return hashlib.sha256(_normalise_title(title).encode("utf-8")).hexdigest()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-ZÀ-ÿŒœÆæ']+", (text or "").lower())


def _looks_french(title: str, description: str = "", tags: Iterable[str] = ()) -> bool:
    text = " ".join([title or "", description or "", " ".join(tags or [])])
    toks = _tokens(text)
    if not toks:
        return False
    hits = sum(1 for token in toks if token in FRENCH_MARKERS)
    accented = bool(re.search(r"[àâäéèêëîïôöùûüÿçœæ]", text.lower()))
    return hits >= 3 or accented


def _safe_tag(tag: str) -> str:
    tag = re.sub(r"\s+", " ", (tag or "").strip().lower().lstrip("#"))
    if not tag or len(tag) < 3 or len(tag) > 38:
        return ""
    if tag in STOP or tag in ENGLISH_TAG_BLOCKLIST:
        return ""
    if re.fullmatch(r"\d+", tag):
        return ""
    return tag


def classify_title_pattern(title: str) -> str:
    t = (title or "").strip().lower()
    if re.match(r"^pourquoi\b.+\?\s*$", t):
        return "pourquoi-question"
    if t.startswith("pourquoi"):
        return "pourquoi-declarative"
    if t.startswith("ce qui se passe") or t.startswith("ce qui arrive") or t.startswith("ce qui change"):
        return "ce-qui-se-passe"
    if t.startswith("ce que ton corps") or t.startswith("ce que votre corps") or t.startswith("ce que le corps"):
        return "ce-que-corps-revele"
    if t.startswith("ce qu'il faut") or t.startswith("ce qu’il faut"):
        return "ce-quil-faut"
    if t.startswith("la science") or t.startswith("ce que la science"):
        return "la-science"
    if t.startswith("comment"):
        return "comment"
    if re.search(r"\b\d+\b", t) or re.match(r"^(\d+|trois|cinq|sept)\b", t):
        return "numbered-list"
    return "other"


def _title_keywords(title: str) -> list[str]:
    out: list[str] = []
    for token in _tokens(title):
        token = token.strip("'").lower()
        if len(token) > 3 and token not in STOP and token not in ENGLISH_TAG_BLOCKLIST and token not in out:
            out.append(token)
    return out[:8]


def fetch_channel_video_ids(channel_id: str, api_key: str, max_results: int) -> list[str]:
    ids: list[str] = []
    page_token = ""
    while len(ids) < max_results:
        payload = _request(
            "search",
            {
                "part": "snippet",
                "channelId": channel_id,
                "type": "video",
                "order": "viewCount",
                "maxResults": min(50, max_results - len(ids)),
                **({"pageToken": page_token} if page_token else {}),
            },
            api_key,
        )
        for item in payload.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                ids.append(vid)
        page_token = payload.get("nextPageToken") or ""
        if not page_token:
            break
    return ids


def fetch_query_video_ids(query: str, api_key: str, max_results: int) -> list[str]:
    ids: list[str] = []
    page_token = ""
    while len(ids) < max_results:
        payload = _request(
            "search",
            {
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "viewCount",
                "regionCode": "FR",
                "relevanceLanguage": "fr",
                "videoDuration": "short",
                "maxResults": min(50, max_results - len(ids)),
                **({"pageToken": page_token} if page_token else {}),
            },
            api_key,
        )
        for item in payload.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                ids.append(vid)
        page_token = payload.get("nextPageToken") or ""
        if not page_token:
            break
    return ids


def fetch_video_details(video_ids: list[str], api_key: str) -> list[dict]:
    details: list[dict] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        payload = _request(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk), "maxResults": 50},
            api_key,
        )
        details.extend(payload.get("items", []))
    return details


def _thumbnail_profile(thumbnails: dict) -> dict:
    """Best-effort visual profile of a competitor thumbnail.

    No OCR is attempted; this measures the style signals we can compute cheaply:
    contrast, brightness and warm/red-yellow bias. Missing Pillow/network simply
    returns {} so API collection remains reliable.
    """
    try:
        from io import BytesIO

        import numpy as np
        from PIL import Image
    except ImportError:
        return {}
    candidates = [thumbnails.get(key, {}) for key in ("maxres", "standard", "high", "medium", "default")]
    url = next((item.get("url") for item in candidates if item.get("url")), "")
    if not url:
        return {}
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            raw = response.read(2_000_000)
        image = Image.open(BytesIO(raw)).convert("RGB").resize((160, 90))
        arr = np.asarray(image, dtype=np.float32)
        brightness = float(arr.mean())
        contrast = float(arr.mean(axis=2).std())
        r_mean, g_mean, b_mean = arr[:, :, 0].mean(), arr[:, :, 1].mean(), arr[:, :, 2].mean()
        warm_bias = float((r_mean + 0.7 * g_mean) - 1.3 * b_mean)
        red_yellow_ratio = float(((arr[:, :, 0] > 150) & (arr[:, :, 1] > 80) & (arr[:, :, 2] < 120)).mean())
        return {
            "brightness": round(brightness, 2),
            "contrast": round(contrast, 2),
            "warm_bias": round(warm_bias, 2),
            "red_yellow_ratio": round(red_yellow_ratio, 4),
        }
    except Exception:
        return {}


def _record_from_video(item: dict, source: str, min_views: int, max_duration: int) -> dict | None:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    duration = _duration_seconds(item.get("contentDetails", {}).get("duration", ""))
    views = int(stats.get("viewCount") or 0)
    title = snippet.get("title") or ""
    tags = snippet.get("tags") or []
    description = snippet.get("description") or ""
    if views < min_views or not title:
        return None
    if duration and duration > max_duration:
        return None
    if not _looks_french(title, description, tags):
        return None
    safe_tags = [tag for tag in (_safe_tag(t) for t in tags) if tag]
    return {
        "video_id": item.get("id"),
        "url": f"https://youtu.be/{item.get('id')}",
        "title": title.strip(),
        "title_hash": _title_hash(title),
        "channel_id": snippet.get("channelId"),
        "channel_title": snippet.get("channelTitle"),
        "views": views,
        "duration_seconds": duration,
        "published_at": snippet.get("publishedAt"),
        "source": source,
        "pattern": classify_title_pattern(title),
        "tags": safe_tags,
        "title_keywords": _title_keywords(title),
        "thumbnail_profile": _thumbnail_profile(snippet.get("thumbnails") or {}),
    }


def build_intel(records: list[dict], *, min_views: int, sources: dict) -> dict:
    pattern_scores: dict[str, float] = defaultdict(float)
    pattern_views: dict[str, list[int]] = defaultdict(list)
    tag_scores: dict[str, float] = defaultdict(float)
    keyword_scores: dict[str, float] = defaultdict(float)

    for record in records:
        weight = max(1.0, math.log10(max(record.get("views") or 1, 10)))
        pattern = record.get("pattern") or "other"
        pattern_scores[pattern] += weight
        pattern_views[pattern].append(int(record.get("views") or 0))
        for tag in record.get("tags", []):
            tag_scores[tag] += weight
        for word in record.get("title_keywords", []):
            keyword_scores[word] += weight

    patterns = []
    for pattern, score in sorted(pattern_scores.items(), key=lambda kv: kv[1], reverse=True):
        views = pattern_views[pattern]
        patterns.append({
            "pattern": pattern,
            "score": round(score, 3),
            "count": len(views),
            "avg_views": round(sum(views) / len(views)) if views else 0,
        })

    safe_templates = []
    for row in patterns:
        template = SAFE_TEMPLATE_BY_PATTERN.get(row["pattern"])
        if template:
            safe_templates.append({**template, "score": row["score"], "count": row["count"]})
    if not safe_templates:
        safe_templates.append({**SAFE_TEMPLATE_BY_PATTERN["pourquoi-question"], "score": 0, "count": 0})

    thumbnail_rows = [r.get("thumbnail_profile", {}) for r in records if r.get("thumbnail_profile")]
    thumbnail_intel = {}
    if thumbnail_rows:
        def avg(key: str) -> float:
            vals = [float(row.get(key, 0)) for row in thumbnail_rows if row.get(key) is not None]
            return round(sum(vals) / len(vals), 3) if vals else 0.0
        thumbnail_intel = {
            "sample_size": len(thumbnail_rows),
            "avg_brightness": avg("brightness"),
            "avg_contrast": avg("contrast"),
            "avg_warm_bias": avg("warm_bias"),
            "avg_red_yellow_ratio": avg("red_yellow_ratio"),
            "recommendation": "high-contrast warm text band" if avg("warm_bias") >= 0 else "high-contrast cool/neutral text band",
        }

    top_refs = sorted(records, key=lambda r: int(r.get("views") or 0), reverse=True)[:25]
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "copy_policy": (
            "Use competitor data as pattern inspiration only. Do not copy exact titles, "
            "descriptions, thumbnails or tag dumps. seo_generator blocks exact-title reuse."
        ),
        "filters": {"min_views": min_views, "max_duration_seconds": sources.get("max_duration_seconds")},
        "sources": sources,
        "video_count": len(records),
        "patterns": patterns,
        "safe_title_templates": safe_templates[:5],
        "thumbnail_intel": thumbnail_intel,
        "high_value_tags": [
            {"tag": tag, "score": round(score, 3)}
            for tag, score in sorted(tag_scores.items(), key=lambda kv: kv[1], reverse=True)[:40]
        ],
        "title_keywords": [
            {"keyword": word, "score": round(score, 3)}
            for word, score in sorted(keyword_scores.items(), key=lambda kv: kv[1], reverse=True)[:40]
        ],
        "exact_title_hashes": sorted({record["title_hash"] for record in records if record.get("title_hash")}),
        "reference_videos_for_human_review": [
            {
                "video_id": r["video_id"],
                "url": r["url"],
                "title": r["title"],
                "channel_title": r.get("channel_title"),
                "views": r.get("views"),
                "pattern": r.get("pattern"),
                "tags_sample": r.get("tags", [])[:8],
            }
            for r in top_refs
        ],
    }


def collect_competitor_records(
    *,
    api_key: str,
    channel_ids: list[str],
    queries: list[str],
    min_views: int,
    max_duration: int,
    max_per_channel: int,
    max_per_query: int,
) -> list[dict]:
    seen_ids: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for channel_id in channel_ids:
        try:
            ids = fetch_channel_video_ids(channel_id, api_key, max_per_channel)
            LOG.info("%s: %d candidate video id(s)", channel_id, len(ids))
            candidates.extend((vid, f"channel:{channel_id}") for vid in ids)
        except Exception as exc:
            LOG.warning("channel %s skipped: %s", channel_id, exc)
    for query in queries:
        try:
            ids = fetch_query_video_ids(query, api_key, max_per_query)
            LOG.info("query %r: %d candidate video id(s)", query, len(ids))
            candidates.extend((vid, f"query:{query}") for vid in ids)
        except Exception as exc:
            LOG.warning("query %r skipped: %s", query, exc)

    records: list[dict] = []
    batch_ids: list[str] = []
    source_by_id: dict[str, str] = {}
    for vid, source in candidates:
        if vid in seen_ids:
            continue
        seen_ids.add(vid)
        batch_ids.append(vid)
        source_by_id[vid] = source

    for item in fetch_video_details(batch_ids, api_key) if batch_ids else []:
        record = _record_from_video(item, source_by_id.get(item.get("id"), "unknown"), min_views, max_duration)
        if record:
            records.append(record)
    return records


def _write_json(path: str, data: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--channels", default=os.environ.get("COMPETITOR_CHANNEL_IDS", ""))
    parser.add_argument("--queries", default=os.environ.get("COMPETITOR_QUERIES_FR", "|".join(DEFAULT_QUERIES)))
    parser.add_argument("--min-views", type=int, default=int(os.environ.get("COMPETITOR_MIN_VIEWS", "1000000")))
    parser.add_argument("--max-duration", type=int, default=int(os.environ.get("COMPETITOR_MAX_DURATION_SECONDS", "90")))
    parser.add_argument("--max-per-channel", type=int, default=int(os.environ.get("COMPETITOR_MAX_VIDEOS_PER_CHANNEL", "30")))
    parser.add_argument("--max-per-query", type=int, default=int(os.environ.get("COMPETITOR_MAX_RESULTS_PER_QUERY", "25")))
    parser.add_argument("--out", default=os.environ.get("COMPETITOR_INTEL_PATH", "data/competitor_intel_fr.json"))
    args = parser.parse_args(argv)

    api_key = os.environ.get("YOUTUBE_API_KEY")
    channels = _split_env(args.channels)
    queries = _split_env(args.queries) or list(DEFAULT_QUERIES)
    sources = {
        "channels": channels,
        "queries": queries,
        "selection_mode": "auto-discover from French high-view query winners" if not channels else "channels + auto-discovery queries",
        "max_duration_seconds": args.max_duration,
    }

    if not api_key:
        LOG.warning("YOUTUBE_API_KEY missing; writing empty competitor-intel file.")
        _write_json(args.out, {
            "schema_version": 1,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "configured": False,
            "reason": "YOUTUBE_API_KEY missing",
            "sources": sources,
            "safe_title_templates": [{**SAFE_TEMPLATE_BY_PATTERN["pourquoi-question"], "score": 0, "count": 0}],
            "high_value_tags": [],
            "exact_title_hashes": [],
            "reference_videos_for_human_review": [],
        })
        return 0

    # Resolve any @handle entries to UC... channel ids so COMPETITOR_CHANNEL_IDS
    # accepts both handles and ids. Keep the original for the sources report.
    resolved_channels = []
    for ch in channels:
        resolved = _resolve_channel_handle(ch, api_key) or ch
        resolved_channels.append(resolved)
    sources["channels"] = channels
    sources["resolved_channel_ids"] = resolved_channels

    records = collect_competitor_records(
        api_key=api_key,
        channel_ids=resolved_channels,
        queries=queries,
        min_views=args.min_views,
        max_duration=args.max_duration,
        max_per_channel=args.max_per_channel,
        max_per_query=args.max_per_query,
    )
    intel = build_intel(records, min_views=args.min_views, sources=sources)
    intel["configured"] = True
    _write_json(args.out, intel)
    LOG.info("Wrote %d competitor winner(s) to %s", len(records), args.out)
    if not records:
        LOG.warning("No videos passed filters. Lower COMPETITOR_MIN_VIEWS or add competitor channel IDs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
