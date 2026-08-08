#!/usr/bin/env python3
"""FR Competitor-Driven Repair — re-optimize already-uploaded Shorts.

Ties the whole "scrape top channels -> ML learns -> repair uploads" loop
together:

  1. Reads the uploaded-video ledger (data/video_history.json).
  2. For each video, rebuilds FRENCH title/description/tags through the SAME
     France-first SEO generator the pipeline uses
     (src/seo_generator.generate_seo_package). That generator already consumes
     `data/competitor_intel_fr.json` (scraped top French niche channels) and
     now also `data/ml_brain_state.json` word-impact via
     `_rank_title_options`, so every proposed change is driven by scraped
     competitor + ML-learned patterns — not hardcoded English rules.
  3. Dry-run by default. Pass --apply to write changes to YouTube.

This replaces the old English `repair_all_seo.py` for this French channel:
that tool stamped English titles ("Why Your Body Does This") onto French
videos, which was wrong for a France-first channel.

Run:
    python scripts/fr_competitor_repair.py                # dry-run
    python scripts/fr_competitor_repair.py --apply        # write to YouTube
    python scripts/fr_competitor_repair.py --limit 5      # first 5 only
    python scripts/fr_competitor_repair.py --topic "..."  # one specific topic

Needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / REFRESH_TOKEN when --apply.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

import seo_generator  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fr-competitor-repair")

VIDEO_HISTORY_PATH = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")

BASE_TAGS = ["shorts", "science", "corps humain", "curiosité", "science du quotidien"]


# --------------------------------------------------------------------------- #
# YouTube OAuth (same pattern as scripts/video_repair.py)
# --------------------------------------------------------------------------- #
def _token() -> str:
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data),
        timeout=30,
    ) as r:
        return json.load(r)["access_token"]


def _req(method: str, url: str, token: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=40) as r:
        body = r.read().decode("utf-8", "replace")
        return json.loads(body) if body.strip() else {}


def _get_snippet(token: str, vid: str) -> dict | None:
    cur = _req("GET",
               f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={vid}",
               token)
    items = cur.get("items") or []
    return items[0]["snippet"] if items else None


def _update_snippet(token: str, vid: str, sn: dict, *, title, description, tags, apply: bool):
    if not apply:
        log.info("[dry] RETITLE %s\n   old: %r\n   new: %r", vid, sn.get("title"), title)
        log.info("[dry]   desc %d -> %d chars | %d tags", len(sn.get("description", "")), len(description), len(tags))
        return False
    payload = {"id": vid, "snippet": {
        "title": title,
        "description": description,
        "categoryId": sn.get("categoryId", "27"),
        "tags": tags,
        **( {"defaultLanguage": sn["defaultLanguage"]} if sn.get("defaultLanguage") else {}),
        **( {"defaultAudioLanguage": sn["defaultAudioLanguage"]}
           if sn.get("defaultAudioLanguage") else {}),
    }}
    _req("PUT", "https://www.googleapis.com/youtube/v3/videos?part=snippet", token, payload)
    log.info("updated %s", vid)
    return True


# --------------------------------------------------------------------------- #
# Thumbnails (ML/SEO-aware)
# --------------------------------------------------------------------------- #
def _set_thumbnail(token: str, vid: str, jpeg_path: str) -> None:
    """Upload a rendered thumbnail for a video via thumbnails.set."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2 import credentials as gc
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    csec = os.environ.get("GOOGLE_CLIENT_SECRET")
    rtok = os.environ.get("REFRESH_TOKEN")
    if not (cid and csec and rtok):
        raise RuntimeError("Missing Google creds for thumbnail upload")
    creds = gc.Credentials(token=None, refresh_token=rtok,
                           token_uri="https://oauth2.googleapis.com/token",
                           client_id=cid, client_secret=csec)
    yt = build("youtube", "v3", credentials=creds)
    yt.thumbnails().set(
        videoId=vid,
        media_body=MediaFileUpload(jpeg_path, mimetype="image/jpeg"),
    ).execute()
    log.info("thumbnail set on %s", vid)


def _make_thumbnail(title: str, out_path: str) -> str:
    """Render an ML/SEO-aware thumbnail using the pipeline's generate_thumbnail."""
    from video_editor import generate_thumbnail
    src = os.path.join(ROOT, "assets", "thumbnails_fr", "_base.jpg")
    if not os.path.exists(src):
        from PIL import Image
        os.makedirs(os.path.dirname(src), exist_ok=True)
        Image.new("RGB", (1080, 1920), (12, 14, 34)).save(src)
    return generate_thumbnail(src, title, output_path=out_path, category="Body")


# --------------------------------------------------------------------------- #
# Repair
# --------------------------------------------------------------------------- #
def _video_topic(entry: dict) -> str:
    return (entry.get("topic") or entry.get("base_phenomenon")
            or entry.get("title") or "")


def _needs_repair(sn_title: str, sn_desc: str, new_title: str) -> bool:
    """Decide whether this video should actually be rewritten.

    We avoid churning a healthy winner. A video needs repair if its live title
    is English (the old bug), too short, missing a question/hook, or its
    description is empty/thin.
    """
    t = (sn_title or "").strip()
    if not t:
        return True
    # Old broken-engine English titles
    if t.lower().startswith(("why ", "your body", "what happens", "how your body", "the science")):
        return True
    if "your " in t.lower() and " body " in t.lower():
        return True
    if len(t) < 20:
        return True
    if not sn_desc or len(sn_desc.strip()) < 80:
        return True
    # French, reasonably long, already a question/curiosity -> leave it
    return False


def repair(apply: bool, limit: int = 0, only_topic: str | None = None, with_thumbnails: bool = False):
    if not os.path.exists(VIDEO_HISTORY_PATH):
        log.error("No %s found. Run the pipeline first.", VIDEO_HISTORY_PATH)
        return 1
    with open(VIDEO_HISTORY_PATH, encoding="utf-8") as f:
        history = json.load(f)
    if not isinstance(history, list):
        log.error("video_history.json is not a list")
        return 1

    vids = [v for v in history if v.get("youtube_video_id")]
    log.info("Loaded %d history entries, %d with a YouTube id", len(history), len(vids))

    intel_ok = os.path.exists(os.environ.get("COMPETITOR_INTEL_PATH", "data/competitor_intel_fr.json"))
    ml_ok = os.path.exists(os.environ.get("ML_BRAIN_STATE_PATH", "data/ml_brain_state.json"))
    log.info("Competitor intel present: %s | ML brain present: %s", intel_ok, ml_ok)

    token = _token() if apply else None
    stats = {"scanned": 0, "repair_needed": 0, "applied": 0, "skipped": 0, "errors": 0}

    for i, entry in enumerate(vids):
        if limit and stats["applied"] >= limit:
            break
        vid = entry["youtube_video_id"]
        topic = _video_topic(entry)
        if only_topic and topic.strip().lower() != only_topic.strip().lower():
            continue
        stats["scanned"] += 1

        if apply:
            sn = _get_snippet(token, vid)
            if not sn:
                log.warning("%s not found on YouTube — skipping", vid)
                stats["errors"] += 1
                continue
            live_title, live_desc = sn.get("title", ""), sn.get("description", "")
        else:
            live_title, live_desc = entry.get("title", ""), entry.get("description", "")

        # Rebuild French metadata through the SEO generator (competitor+ML aware)
        pseudo_script = {
            "title": live_title or entry.get("title", topic),
            "series_title": entry.get("series_title") or entry.get("title") or topic,
            "question_phrase": entry.get("question_phrase") or "",
            "base_question": entry.get("base_question") or "",
            "description": live_desc or entry.get("description", ""),
            "hook": entry.get("hook") or entry.get("voiceover", "")[:160],
            "tags": entry.get("tags") or [],
        }
        try:
            pkg = seo_generator.generate_seo_package(topic, pseudo_script)
            new_title = pkg.get("chosen_title") or topic
            new_desc = pkg.get("description") or live_desc
            new_tags = list(dict.fromkeys((pkg.get("tags") or BASE_TAGS) + BASE_TAGS))[:14]
        except Exception as exc:
            log.warning("SEO package failed for %s (%s): %s", vid, topic, exc)
            stats["errors"] += 1
            continue

        # ML/SEO-aware thumbnail for this video: generate + upload regardless
        # of whether the SEO metadata needs changing, so every uploaded video
        # gets an optimized thumbnail.
        if with_thumbnails:
            try:
                os.makedirs(os.path.join(ROOT, "output", "thumbs"), exist_ok=True)
                thumb_path = os.path.join(ROOT, "output", "thumbs", f"{vid}.jpg")
                _make_thumbnail(new_title or live_title or topic, thumb_path)
                if apply and token:
                    _set_thumbnail(token, vid, thumb_path)
                stats["thumbnails"] = stats.get("thumbnails", 0) + 1
            except Exception as exc:
                log.warning("thumbnail failed for %s: %s", vid, exc)
                stats["errors"] += 1

        if not _needs_repair(live_title, live_desc, new_title):
            stats["skipped"] += 1
            continue

        stats["repair_needed"] += 1
        did = _update_snippet(token, vid, {"title": live_title, "description": live_desc, "categoryId": "27"},
                              title=new_title, description=new_desc, tags=new_tags, apply=apply)
        if apply and did:
            stats["applied"] += 1
        elif apply:
            stats["errors"] += 1
        if not apply:
            stats["applied"] += 1  # count as "would apply" in dry-run

        time.sleep(1)

    log.info("=" * 60)
    log.info("Repair done (apply=%s): %s", apply, stats)
    return 0




# --------------------------------------------------------------------------- #
# ML best-slot re-scheduling for scheduled (private) videos
# --------------------------------------------------------------------------- #
def _get_video_status(token: str, vid: str) -> dict | None:
    """Fetch a video's status (privacyStatus + publishAt)."""
    cur = _req("GET", f"https://www.googleapis.com/youtube/v3/videos?part=status&id={vid}", token)
    items = cur.get("items") or []
    return items[0]["status"] if items else None


def _reschedule_video(token: str, vid: str, publish_at_iso: str, dry: bool = True) -> bool:
    """Move a scheduled video to a new publishAt (ML best slot)."""
    if dry:
        log.info("[dry] reschedule %s -> %s", vid, publish_at_iso)
        return True
    payload = {"id": vid, "status": {"privacyStatus": "private", "publishAt": publish_at_iso}}
    _req("PUT", "https://www.googleapis.com/youtube/v3/videos?part=status", token, payload)
    log.info("rescheduled %s -> %s", vid, publish_at_iso)
    return True


def reschedule_ml_slots(apply: bool = False, limit: int = 0) -> dict:
    """Re-align scheduled (private) videos to the ML-learned best publish slots.

    Reads data/upload_slot_intel_fr.json (ML-learned best PKT slots) and
    data/video_history.json (scheduled videos), and assigns each still-private
    video the next best free slot.
    """
    import datetime as _dt
    from zoneinfo import ZoneInfo as _ZoneInfo

    paris = _ZoneInfo("Europe/Paris")
    # ML best slots (PKT) from upload_slot_intel_fr.json
    slots = []
    try:
        with open(os.environ.get("DYNAMIC_SCHEDULE_PATH", "data/upload_slot_intel_fr.json"), encoding="utf-8") as f:
            intel = json.load(f)
        for s in (intel.get("recommended_slots") or [])[:3]:
            slots.append((int(s.get("hour", 0)), int(s.get("minute", 0))))
    except Exception:
        pass
    if not slots:
        slots = [(17, 30), (19, 30), (21, 30)]  # ML default best PKT slots

    # Scheduled videos from video_history
    scheduled = []
    try:
        with open(os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json"), encoding="utf-8") as f:
            history = json.load(f)
        now = _dt.datetime.now(_dt.UTC)
        for v in history:
            pa = v.get("publish_at")
            vid = v.get("youtube_video_id")
            if not pa or not vid:
                continue
            try:
                padt = _dt.datetime.fromisoformat(pa)
                if padt.tzinfo is None:
                    padt = padt.replace(tzinfo=_dt.UTC)
            except Exception:
                continue
            # only future-scheduled (still private/unpublished)
            if padt > now:
                scheduled.append((vid, v.get("title", ""), pa))
    except Exception:
        return {"scheduled": 0}

    if limit:
        scheduled = scheduled[:limit]

    token = _token() if apply else None
    stats = {"found": len(scheduled), "rescheduled": 0, "errors": 0}
    # Assign next best slot per video (distinct, dedup like uploader)
    used = set()
    for vid, title, old_pa in scheduled:
        chosen = None
        for (hh, mm) in slots:
            candidate = f"{hh:02d}:{mm:02d}"
            if candidate in used:
                continue
            used.add(candidate)
            # schedule tomorrow or next at this PKT slot in UTC
            slot_dt = _dt.datetime.now(paris).replace(hour=hh, minute=mm, second=0, microsecond=0)
            if slot_dt < _dt.datetime.now(paris):
                slot_dt += _dt.timedelta(days=1)
            new_iso = slot_dt.astimezone(_dt.UTC).isoformat()
            chosen = new_iso
            break
        if not chosen:
            continue
        try:
            _reschedule_video(token, vid, chosen, dry=not apply)
            stats["rescheduled"] += 1
        except Exception as exc:
            log.warning("reschedule %s failed: %s", vid, exc)
            stats["errors"] += 1
    log.info("ML re-schedule done: %s", stats)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write changes to YouTube (default: dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="max videos to process")
    ap.add_argument("--topic", default=None, help="only repair a specific topic")
    ap.add_argument("--with-thumbnails", action="store_true",
                    help="also render and upload an optimized thumbnail for every video")
    ap.add_argument("--reschedule", action="store_true",
                    help="re-align scheduled (private) videos to ML-learned best slots")
    args = ap.parse_args()
    if args.reschedule:
        return 0 if reschedule_ml_slots(apply=args.apply, limit=args.limit).get("rescheduled", 0) >= 0 else 1
    return repair(apply=args.apply, limit=args.limit, only_topic=args.topic,
                  with_thumbnails=args.with_thumbnails)


if __name__ == "__main__":
    sys.exit(main())
