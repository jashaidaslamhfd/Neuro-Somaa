"""uploader.py — publish to YouTube, Facebook (Reels) and Instagram (Reels).

2026-grade cross-platform publishing:

* YouTube: honours YT_PRIVACY_STATUS and YT_SCHEDULE_PUBLISH. When scheduling is
  on it computes the next free Paris peak (via FrancePeakTimeScheduler) and sends
  the video as `private` with a `publishAt` so YouTube flips it public at that
  exact minute. Uploads the generated thumbnail with thumbnails.set.
* Facebook Reels: real Graph API multipart upload to ``/{page_id}/video_reels``.
* Instagram Reels: two-step Graph API flow (``/media`` then ``/media_publish``)
  against the connected Business/Creator account.

Everything supports a safe DRY_RUN, fails loudly with a clear cause, and
returns structured results that main.py persists into video_history.json.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime

import pytz
import requests
from google.oauth2 import credentials as google_credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

MAX_RETRIES = 3
RETRY_DELAY = 5
FB_API_VERSION = os.environ.get("FB_API_VERSION", "v23.0").strip()
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

_PUBLISH_TZ = pytz.timezone("Europe/Paris")
UPLOAD_STATE_PATH = os.environ.get("UPLOAD_STATE_PATH", "data/upload_state.json")

DEFAULT_TAGS = ["science", "shorts", "corps humain", "curiosités", "santé"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _content_fingerprint(script_data: dict) -> str:
    material = "|".join(
        str(script_data.get(k, "")).strip().lower() for k in ("topic", "title", "voiceover", "hook")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _load_upload_state() -> dict:
    if not os.path.exists(UPLOAD_STATE_PATH):
        return {}
    try:
        with open(UPLOAD_STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Could not load upload state: %s", exc)
        return {}


def _save_upload_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(UPLOAD_STATE_PATH) or ".", exist_ok=True)
        tmp = UPLOAD_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, UPLOAD_STATE_PATH)
    except Exception as exc:
        logger.warning("Could not save upload state: %s", exc)


def _next_publish_time() -> dict | None:
    """Choose the next Paris peak for a scheduled publish.

    Returns a dict with the ISO `publishAt` (UTC) plus human-friendly context,
    or None when the operator disabled scheduling or no slot can be found.

    IMPORTANT (2026-08-07): previously every run picked the FIRST available
    future slot, so if 3 runs happened in quick succession they all claimed
    the SAME 15:30 slot -> 3+ videos published at once. Now we read the set of
    already-scheduled publishAt times from upload_state + video_history and
    skip any slot that is already taken, so each run gets a distinct slot.
    """
    if os.environ.get("YT_SCHEDULE_PUBLISH", "true").lower() != "true":
        return None
    try:
        from scheduler import FrancePeakTimeScheduler

        # Collect already-taken publish timestamps (UTC ISO).
        taken = set()
        for record in list(_load_upload_state().values()):
            if not isinstance(record, dict):
                continue
            pa = record.get("publish_at") or ""
            has_platform_id = bool(
                record.get("youtube_video_id")
                or (record.get("facebook") or {}).get("video_id")
                or (record.get("instagram") or {}).get("media_id")
            )
            # Failed/placeholder records may retain a publish_at but have no
            # platform ID; they must not reserve a slot forever.
            if pa and has_platform_id:
                taken.add(pa)
        # Also honor video_history published entries.
        try:
            import json as _json

            history_path = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")
            with open(history_path, encoding="utf-8") as history_file:
                vh = _json.load(history_file)
            for rec in vh if isinstance(vh, list) else []:
                if not isinstance(rec, dict):
                    continue
                pa = rec.get("publish_at")
                has_platform_id = bool(
                    rec.get("youtube_video_id")
                    or (rec.get("facebook") or {}).get("video_id")
                    or (rec.get("instagram") or {}).get("media_id")
                )
                if pa and has_platform_id:
                    taken.add(pa)
        except Exception:
            pass

        sched = FrancePeakTimeScheduler()
        # Ask for many future slots so we can skip the ones already taken.
        slots = sched.get_next_posting_times(count=24)
        for slot in slots:
            if slot["time_utc"] in taken:
                logger.info("Skipping already-taken publish slot %s", slot["time_utc"])
                continue
            return {
                "publishAt": slot["time_utc"],
                "peak_name": slot["peak_name"],
                "time_paris": slot["time_paris"],
                "reason": slot["reason"],
            }
        logger.warning("No free publish slot found in the next 7 days")
        return None
    except Exception as exc:
        logger.warning("Scheduled publish slot lookup failed: %s", exc)
        return None


def _retry(fn, *args, retries=MAX_RETRIES, **kwargs):
    """Run fn, retrying transient failures with a short backoff."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except requests.exceptions.RequestException as exc:
            last_err = exc
            if attempt < retries:
                logger.warning(
                    "Attempt %d/%d failed (%s); retrying in %ss", attempt, retries, exc, RETRY_DELAY
                )
                time.sleep(RETRY_DELAY)
    raise last_err


# --------------------------------------------------------------------------- #
# YouTube
# --------------------------------------------------------------------------- #
def _yt_client():
    creds = google_credentials.Credentials(
        token=None,
        refresh_token=os.environ.get("REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        scopes=[
            # Only the two scopes a normal channel needs to upload Shorts +
            # set metadata. youtubepartner was previously included but it is
            # only grantable to MCN/Content-ID partners — a normal OAuth token
            # lacks it, so every upload died with 'invalid_scope: Bad Request'.
            # Analytics uses a separate token/scope (yt-analytics.readonly)
            # via analytics_updater.py.
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
    )
    return build("youtube", "v3", credentials=creds)



_YT_SHORTS_HASHTAGS = "#Shorts #YouTubeShorts #FaitsCorps #ScienceCorps #TonCorps"


def _append_hashtags(script_data: dict) -> str:
    """Append ranked hashtags + mandatory Shorts hashtags to YouTube description."""
    base_desc = (script_data.get("description") or "")[:4500]
    ranked = script_data.get("hashtags_ranked") or script_data.get("hashtags") or []
    hashtag_strs = [f"#{t}" if not t.startswith("#") else t for t in ranked[:5]]
    all_hashtags = hashtag_strs + _YT_SHORTS_HASHTAGS.split()
    unique_hashtags = list(dict.fromkeys(all_hashtags))
    return f"{base_desc}\n\n" + " ".join(unique_hashtags)

def _upload_youtube(video_path, thumb_path, script_data, tags) -> dict:
    """Upload a Short to YouTube with optional scheduled publishing."""
    scheduled = _next_publish_time()
    privacy = os.environ.get("YT_PRIVACY_STATUS", "private").strip().lower()

    status = {
        "selfDeclaredMadeForKids": os.environ.get("YT_MADE_FOR_KIDS", "false").lower() == "true",
        "privacyStatus": privacy,
    }
    if scheduled is not None:
        # YouTube requires private + publishAt for scheduled publish; it then
        # flips the video public automatically at the chosen minute.
        status["privacyStatus"] = "private"
        status["publishAt"] = scheduled["publishAt"]
        logger.info("📅 Scheduled publish at %s (%s)", scheduled["publishAt"], scheduled.get("peak_name"))

    # Honest AI-content disclosure (altered/synthetic content policy).
    if os.environ.get("YT_DECLARE_SYNTHETIC_MEDIA", "true").lower() == "true":
        status["madeForKids"] = os.environ.get("YT_MADE_FOR_KIDS", "false").lower() == "true"

    body = {
        "snippet": {
            "title": (script_data.get("title") or "")[:100],
            "description": _append_hashtags(script_data)[:5000],
            "tags": (tags or DEFAULT_TAGS)[:500],
            "defaultLanguage": script_data.get("channel_language", "fr"),
            "defaultAudioLanguage": "fr",
            "categoryId": "27",  # Education
        },
        "status": status,
    }

    if DRY_RUN:
        logger.info("[DRY_RUN] Would upload YouTube: %r", body["snippet"]["title"])
        return {
            "ok": True,
            "video_id": None,
            "dry_run": True,
            "publish_at": scheduled and scheduled["publishAt"],
        }

    # Do not even construct an authenticated client until all local safeguards
    # have passed and this is a real upload.
    yt = _yt_client()
    media = MediaFileUpload(video_path, chunksize=1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"YouTube upload returned no video id: {response}")

    # Confirm the resource exists before reporting upload success. This avoids
    # treating a partial/ambiguous API response as a publish receipt.
    verified = yt.videos().list(part="id,status,snippet", id=video_id).execute()
    verified_items = verified.get("items", [])
    if not verified_items or verified_items[0].get("id") != video_id:
        raise RuntimeError(f"YouTube upload receipt verification failed for video id {video_id}")
    logger.info("✅ YouTube upload receipt verified: %s", video_id)

    # Attach the generated thumbnail after the video exists.
    if video_id and thumb_path and os.path.exists(thumb_path):
        try:
            yt.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumb_path),
            ).execute()
            logger.info("🖼️ Thumbnail attached to %s", video_id)
        except Exception as exc:
            logger.warning("Thumbnail upload failed for %s: %s", video_id, exc)

    return {
        "ok": bool(video_id),
        "video_id": video_id,
        "dry_run": False,
        "publish_at": scheduled and scheduled["publishAt"],
        "privacyStatus": status["privacyStatus"],
    }


# --------------------------------------------------------------------------- #
# Facebook Reels (Graph API)
# --------------------------------------------------------------------------- #
def _facebook_upload_reel(video_path, script_data, tags) -> dict:
    """Upload a Reel to a Facebook Page via Graph API ``/v23.0/{page}/video_reels``."""
    fb_token = os.environ.get("FB_ACCESS_TOKEN")
    fb_page = os.environ.get("FB_PAGE_ID")
    if not fb_token or not fb_page:
        logger.info("Facebook skipped: FB_ACCESS_TOKEN/FB_PAGE_ID not configured")
        return {"ok": False, "reason": "not_configured"}

    description = (script_data.get("description") or "")[:2200]
    endpoint = f"https://graph.facebook.com/{FB_API_VERSION}/{fb_page}/video_reels"

    def _do():
        with open(video_path, "rb") as fh:
            data = {"description": description, "access_token": fb_token}
            files = {"source": (os.path.basename(video_path), fh, "video/mp4")}
            resp = requests.post(endpoint, data=data, files=files, timeout=600)
        payload = resp.json()
        if resp.status_code >= 300:
            raise RuntimeError(f"Facebook error {resp.status_code}: {payload}")
        return payload

    if DRY_RUN:
        logger.info("[DRY_RUN] Would upload Facebook Reel to page %s", fb_page)
        return {"ok": True, "video_id": None, "dry_run": True}
    payload = _retry(_do)
    logger.info("📘 Facebook Reel published to page %s", fb_page)
    return {"ok": bool(payload.get("id")), "video_id": payload.get("id"), "dry_run": False}


# --------------------------------------------------------------------------- #
# Instagram Reels (Graph API)
# --------------------------------------------------------------------------- #
def _instagram_upload_reel(video_path, script_data, tags) -> dict:
    """Publish a Reel to Instagram via the two-step Graph API media flow."""
    ig_token = os.environ.get("FB_ACCESS_TOKEN")
    ig_user = os.environ.get("INSTAGRAM_USER_ID")
    if not ig_token or not ig_user:
        logger.info("Instagram skipped: FB_ACCESS_TOKEN/INSTAGRAM_USER_ID not configured")
        return {"ok": False, "reason": "not_configured"}

    base = f"https://graph.facebook.com/{FB_API_VERSION}/{ig_user}"
    caption = (script_data.get("title") or "")[:2200]

    def _do():
        # Step 1: create a REELS media container (direct file upload).
        with open(video_path, "rb") as fh:
            data = {
                "media_type": "REELS",
                "caption": caption,
                "share_to_feed": "true",
                "access_token": ig_token,
            }
            files = {"source": (os.path.basename(video_path), fh, "video/mp4")}
            resp = requests.post(f"{base}/media", data=data, files=files, timeout=600)
        payload = resp.json()
        if resp.status_code >= 300:
            raise RuntimeError(f"Instagram create error {resp.status_code}: {payload}")
        creation_id = payload.get("id")
        if not creation_id:
            raise RuntimeError(f"Instagram did not return a creation id: {payload}")

        # Step 2: publish the staged container.
        pub = requests.post(
            f"{base}/media_publish",
            data={"creation_id": creation_id, "access_token": ig_token},
            timeout=600,
        )
        pub_payload = pub.json()
        if pub.status_code >= 300:
            raise RuntimeError(f"Instagram publish error {pub.status_code}: {pub_payload}")
        return pub_payload

    if DRY_RUN:
        logger.info("[DRY_RUN] Would upload Instagram Reel for user %s", ig_user)
        return {"ok": True, "video_id": None, "dry_run": True}
    payload = _retry(_do)
    logger.info("📸 Instagram Reel published for user %s", ig_user)
    return {"ok": bool(payload.get("id")), "video_id": payload.get("id"), "dry_run": False}


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def upload_all(video_path, thumb_path, script_data, meta_video_path=None) -> dict:
    """Publish a Short to every configured platform. Never crashes silently.

    Returns a flat dict main.py can persist directly into video_history.json:
    youtube_success, youtube_video_id, facebook_success, instagram_success,
    publish_at and per-platform payloads.
    """
    logger.info("Publishing French Short: %s", script_data.get("title"))
    tags = script_data.get("tags") or DEFAULT_TAGS
    state = _load_upload_state()
    fp = _content_fingerprint(script_data)

    # Crash-safe idempotency: check the durable fingerprint before touching any
    # external API. A runner retry must not create a second YouTube/Reel upload.
    existing = state.get(fp)
    if existing and existing.get("status") == "completed" and not DRY_RUN:
        logger.warning(
            "Duplicate content fingerprint blocked before upload: %s (title=%r)",
            fp[:12],
            script_data.get("title"),
        )
        return {
            "youtube_success": bool(existing.get("youtube_video_id")),
            "youtube_video_id": existing.get("youtube_video_id"),
            "facebook_success": bool((existing.get("facebook") or {}).get("video_id")),
            "instagram_success": bool((existing.get("instagram") or {}).get("media_id")),
            "publish_at": existing.get("publish_at"),
            "dry_run": False,
            "idempotent_replay": True,
            "content_fingerprint": fp,
        }

    yt = _upload_youtube(video_path, thumb_path, script_data, tags)
    if not yt.get("ok") or not yt.get("video_id"):
        raise RuntimeError("YouTube upload did not return a verified video id; refusing to persist completed state")

    # Facebook/Instagram publishing is opt-in (FB_UPLOAD_ENABLED=true) and only
    # runs when the matching credentials are present. This mirrors the privacy
    # stance: Reels publish instantly, so don't send them out until the operator
    # has switched them on.
    socials_on = os.environ.get("FB_UPLOAD_ENABLED", "false").lower() == "true"
    fb = (
        _facebook_upload_reel(video_path, script_data, tags)
        if socials_on
        else {"ok": False, "reason": "disabled"}
    )
    ig = (
        _instagram_upload_reel(video_path, script_data, tags)
        if socials_on
        else {"ok": False, "reason": "disabled"}
    )

    # Dry-runs are intentionally side-effect free: they must not mark content
    # as completed and block a later real upload of the same candidate.
    if DRY_RUN:
        return {
            "youtube_success": bool(yt.get("ok")),
            "youtube_video_id": yt.get("video_id"),
            "facebook_success": bool(fb.get("ok")),
            "instagram_success": bool(ig.get("ok")),
            "publish_at": yt.get("publish_at"),
            "dry_run": True,
            "youtube": yt,
            "facebook": fb,
            "instagram": ig,
            "content_fingerprint": fp,
        }

    # Nested facebook/instagram objects match what platform_metrics.collect()
    # reads to pull per-platform analytics (fb.video_id / ig.media_id).
    state[fp] = {
        "status": "completed",
        "title": script_data.get("title"),
        "youtube_video_id": yt.get("video_id"),
        "facebook": {"video_id": fb.get("video_id")},
        "instagram": {"media_id": ig.get("video_id")},
        "publish_at": yt.get("publish_at"),
        "completed_at": datetime.now(pytz.UTC).timestamp(),
    }
    _save_upload_state(state)

    return {
        "youtube_success": bool(yt.get("ok")),
        "youtube_video_id": yt.get("video_id"),
        "facebook_success": bool(fb.get("ok")),
        "instagram_success": bool(ig.get("ok")),
        "publish_at": yt.get("publish_at"),
        "dry_run": DRY_RUN,
        "youtube": yt,
        "facebook": fb,
        "instagram": ig,
    }
