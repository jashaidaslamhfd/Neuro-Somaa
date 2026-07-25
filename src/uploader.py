import os
import json
import logging
import time
import hashlib
import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import requests
from seo_generator import generate_description

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5

# ---------------------------------------------------------------------------
# FRENCH-AUDIENCE TARGETING & PUBLISH CONTROLS
# defaultLanguage/defaultAudioLanguage are set to 'fr' on every upload so
# YouTube's recommendation system targets the French audience correctly.
#
# YT_SCHEDULE_PUBLISH=true (default): when YT_PRIVACY_STATUS=public, the video
# uploads as PRIVATE with status.publishAt = the next Paris peak time
# (08:00/13:00/19:00 Europe/Paris). YouTube then publishes it automatically at
# that exact moment - generation takes a variable 2-3h, so uploading "public"
# immediately used to scatter publish times (a real video once went live at
# 02:32 Paris time and flopped). With publishAt, the publish time is exact no
# matter how long generation took.
#
# YT_DECLARE_SYNTHETIC_MEDIA=true (default): accepts YouTube's altered /
# synthetic content disclosure (AI voice + AI visuals) via the official
# status.containsSyntheticMedia field (Data API v3, supported since Oct 2024).
#
# YT_PLAYLIST_ENABLED=true: adds the video to the playlist suggested by the
# SEO package (created if missing, newest first) - helps binge/session watch.
# Needs the youtube.force-ssl scope on REFRESH_TOKEN; failure is not fatal.
# ---------------------------------------------------------------------------
SCHEDULE_PUBLISH = os.environ.get("YT_SCHEDULE_PUBLISH", "true").strip().lower() == "true"
DECLARE_SYNTHETIC_MEDIA = os.environ.get("YT_DECLARE_SYNTHETIC_MEDIA", "true").strip().lower() == "true"
PLAYLIST_ENABLED = os.environ.get("YT_PLAYLIST_ENABLED", "true").strip().lower() == "true"
MIN_SCHEDULE_LEAD_SECONDS = 15 * 60  # publishAt must sit safely in the future

# ---------------------------------------------------------------------------
# ONE VIDEO PER SLOT LOCK
# _next_publish_at used to pick the next Paris slot from the CLOCK ONLY. Two
# runs (or two videos in a batch) could then both grab e.g. 18:30 and publish
# at the exact same minute (the "2 videos at once" bug). Now every slot claim
# is recorded and re-checked from THREE sources before a slot is chosen:
#   1. _CLAIMED_PUBLISH_ATS - claims made inside this same process (batch mode)
#   2. data/video_history.json - publish_at ledger persisted across runs by git
#   3. the YouTube channel itself - videos already uploaded private+publishAt
#      (best-effort: needs youtube.force-ssl; failure falls back to 1+2)
# ---------------------------------------------------------------------------
_CLAIMED_PUBLISH_ATS = []  # list of timezone-aware datetimes, this process only
SLOT_CLAIM_TOLERANCE_SECONDS = 30 * 60  # slots are 2.5h apart; 30min is safe
SCHEDULE_LOOKAHEAD_SLOTS = 12  # must exceed 6: claims may push us to tomorrow

# ---------------------------------------------------------------------------
# IMPORTANT: YouTube video uploads require OAuth 2.0 USER credentials, not a
# service-account key. Credentials are read from THREE separate secrets/env
# vars: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, REFRESH_TOKEN.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# YOUTUBE "MADE FOR KIDS" (COPPA)
# This channel's content is dark/mystery body-science facts aimed at adults
# (18+), so MADE_FOR_KIDS defaults to False. If your niche or audience
# changes again, re-verify this setting - COPPA fines are no joke.
# ---------------------------------------------------------------------------
MADE_FOR_KIDS = os.environ.get("YT_MADE_FOR_KIDS", "false").lower() == "true"
YT_PRIVACY_STATUS = os.environ.get("YT_PRIVACY_STATUS", "private").strip().lower()
if YT_PRIVACY_STATUS not in {"private", "unlisted", "public"}:
    raise ValueError("YT_PRIVACY_STATUS must be private, unlisted, or public")


def _build_youtube_description(script_data: dict, tags: list) -> str:
    """CTR-optimized YouTube description. Delegates to
    seo_generator.generate_description() so upload and the SEO-package
    preview (script_data['description'] set in main.py) can never drift
    out of sync - this used to be a separate copy of the same logic."""
    return generate_description(script_data, tags)


def _build_facebook_description(script_data: dict, tags: list) -> str:
    """Facebook Reels description:
    - Facebook's own guidelines warn that MORE THAN 5 hashtags can
      suppress reach — so we use MAX 3 (sweet spot for Reels).
    - Hook in first line (shows before 'See more' truncation).
    - Clean CTA drives the follow/share action."""
    hook = script_data.get('hook', '')
    cta = script_data.get('cta', 'Abonnez-vous pour plus de science expliquée simplement.')
    description = script_data.get('description', '')

    # Facebook 2026: the algorithm categorises Reels mainly via NLP on the
    # caption text (hook + description above), with hashtags as a secondary
    # signal. So we (a) keep the strict 3-hashtag limit (>5 suppresses reach)
    # and (b) pick the most topic-SPECIFIC tags first, dropping generic
    # filler like "facts"/"science"/"shorts" that add no categorisation value
    # on Facebook. Falls back to the first tags only if nothing specific is
    # left, so a Reel is never posted with zero hashtags.
    _generic = {"facts", "science", "shorts", "viral", "fyp", "reels",
                "education", "trending", "video", "youtube"}
    specific = [t for t in tags if str(t).lstrip("#").lower() not in _generic]
    chosen = (specific or tags)[:3]
    fb_hashtags = ' '.join(f"#{str(t).lstrip('#')}" for t in chosen)

    return (
        f"{hook}\n\n"
        f"{description}\n\n"
        f"{cta}\n\n"
        f"{fb_hashtags}"
    )[:2200]


VIDEO_HISTORY_PATH = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")
UPLOAD_STATE_PATH = os.environ.get("UPLOAD_STATE_PATH", "data/upload_state.json")


def _load_upload_state() -> dict:
    if not os.path.exists(UPLOAD_STATE_PATH):
        return {}
    try:
        with open(UPLOAD_STATE_PATH, encoding="utf-8") as file_handle:
            data = json.load(file_handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load upload state: %s", exc)
        return {}


def _save_upload_state(state: dict) -> None:
    os.makedirs(os.path.dirname(UPLOAD_STATE_PATH) or ".", exist_ok=True)
    temp_path = UPLOAD_STATE_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file_handle:
        json.dump(state, file_handle, indent=2)
    os.replace(temp_path, UPLOAD_STATE_PATH)


def _content_fingerprint(script_data: dict) -> str:
    """Stable identity for a script, independent of temporary media paths."""
    material = "|".join(
        str(script_data.get(key, "")).strip().lower()
        for key in ("topic", "title", "voiceover", "hook")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _load_upload_history() -> list:
    if not os.path.exists(VIDEO_HISTORY_PATH):
        return []
    try:
        with open(VIDEO_HISTORY_PATH, encoding="utf-8") as file_handle:
            data = json.load(file_handle)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load upload history: %s", exc)
        return []


def _existing_youtube_upload(script_data: dict) -> str | None:
    """Return a prior upload ID for the exact script, preventing retry duplicates."""
    fingerprint = _content_fingerprint(script_data)
    state = _load_upload_state().get(fingerprint, {})
    if state.get("status") == "completed" and state.get("youtube_video_id"):
        return str(state["youtube_video_id"])
    if state.get("status") == "started":
        # We cannot safely know whether a timeout happened before or after
        # YouTube accepted the binary. Block rather than risk a duplicate.
        raise RuntimeError(
            "An earlier YouTube upload has unknown completion state for this script. "
            "Review YouTube Studio, then clear or resolve its data/upload_state.json record."
        )
    for item in reversed(_load_upload_history()):
        if item.get("content_fingerprint") == fingerprint and item.get("youtube_video_id"):
            return str(item["youtube_video_id"])
    return None


def _already_uploaded_to_facebook(script_data: dict) -> bool:
    """Prevent a duplicate Facebook Reel for an already recorded script."""
    fingerprint = _content_fingerprint(script_data)
    return any(
        item.get("content_fingerprint") == fingerprint and item.get("facebook_success")
        for item in _load_upload_history()
    )


def _parse_iso_quiet(value):
    """Parse an ISO-8601 timestamp to an aware datetime, or None."""
    if not value:
        return None
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=__import__("datetime").timezone.utc)
    except Exception:
        return None


def _channel_scheduled_publish_ats(yt) -> list:
    """publishAt times of videos ALREADY scheduled on the channel (private +
    publishAt). This is the cross-run source of truth: a queued cron run sees
    the slot the previous run just claimed and moves to the next one.
    Best-effort only: any scope/quota failure returns []."""
    claimed = []
    try:
        from datetime import datetime, timezone, timedelta
        channels = yt.channels().list(part="contentDetails", mine=True).execute()
        items = channels.get("items") or []
        if not items:
            return claimed
        uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        video_ids = []
        request = yt.playlistItems().list(
            part="contentDetails", playlistId=uploads_playlist, maxResults=25)
        response = request.execute()
        for item in response.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                video_ids.append(vid)
        if not video_ids:
            return claimed
        videos = yt.videos().list(part="status", id=",".join(video_ids)).execute()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=3)
        for video in videos.get("items", []):
            publish_at = _parse_iso_quiet(video.get("status", {}).get("publishAt"))
            if publish_at and publish_at > cutoff:
                claimed.append(publish_at)
        if claimed:
            logger.info("Channel already has %d scheduled slot(s): %s",
                        len(claimed), [c.isoformat() for c in claimed])
    except Exception as exc:
        logger.warning("Scheduled-slot check via YouTube API skipped (%s); "
                       "falling back to local ledger only.", exc)
    return claimed


def _claimed_publish_times(yt=None) -> list:
    """Every publish time already taken, from all three sources."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    claimed = [dt for dt in _CLAIMED_PUBLISH_ATS if dt and dt > now - timedelta(hours=3)]
    try:
        history_path = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")
        if os.path.exists(history_path):
            with open(history_path, "r") as handle:
                for entry in json.load(handle):
                    publish_at = _parse_iso_quiet(entry.get("publish_at"))
                    if publish_at and publish_at > now - timedelta(hours=3):
                        claimed.append(publish_at)
    except Exception as exc:
        logger.warning("Local publish_at ledger unreadable (%s).", exc)
    if yt is not None:
        claimed.extend(_channel_scheduled_publish_ats(yt))
    return claimed


def _slot_is_taken(when, claimed) -> bool:
    return any(abs((when - taken).total_seconds()) < SLOT_CLAIM_TOLERANCE_SECONDS
               for taken in claimed)


def _next_publish_at(yt=None) -> tuple:
    """Return (publish_at_rfc3339_utc | None, slot_info | None).

    Picks the next Paris peak window that is at least MIN_SCHEDULE_LEAD_SECONDS
    in the future AND not already claimed by another video - so YouTube always
    publishes inside a French peak slot, and never two videos at the same
    minute (regression guard for the "2 videos at once" bug).
    """
    try:
        from datetime import datetime, timezone
        from scheduler import FrancePeakTimeScheduler
        scheduler = FrancePeakTimeScheduler()
        now_utc = datetime.now(timezone.utc)
        claimed = _claimed_publish_times(yt)
        for slot in scheduler.get_next_posting_times(SCHEDULE_LOOKAHEAD_SLOTS):
            when = datetime.fromisoformat(slot["time_utc"])
            if (when - now_utc).total_seconds() < MIN_SCHEDULE_LEAD_SECONDS:
                continue
            if _slot_is_taken(when, claimed):
                logger.info("Slot %s already taken by another upload - skipping it.",
                            slot.get("time_paris", when.isoformat()))
                continue
            return when.isoformat(), slot
        logger.warning("No free upcoming Paris peak slot found far enough in the future.")
    except Exception as exc:
        logger.warning("Could not compute publishAt (%s); uploading immediately instead.", exc)
    return None, None


def _add_video_to_playlist(yt, yt_video_id: str, playlist_title: str) -> None:
    """Add the video to the SEO-suggested playlist (created if missing,
    newest first). Best-effort only: a scope/quota failure must never fail
    an otherwise successful upload."""
    if not playlist_title:
        return
    try:
        playlist_id = None
        request = yt.playlists().list(part="snippet", mine=True, maxResults=50)
        while request is not None:
            response = request.execute()
            for playlist in response.get("items", []):
                if playlist.get("snippet", {}).get("title") == playlist_title:
                    playlist_id = playlist["id"]
                    break
            if playlist_id:
                break
            request = yt.playlists().list_next(request, response)
        if playlist_id is None:
            created = yt.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": playlist_title,
                        "description": "Les Shorts de la série, regroupés automatiquement.",
                    },
                    "status": {"privacyStatus": "public"},
                },
            ).execute()
            playlist_id = created["id"]
            logger.info("Playlist created: %s (%s)", playlist_title, playlist_id)
        yt.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "position": 0,
                    "resourceId": {"kind": "youtube#video", "videoId": yt_video_id},
                }
            },
        ).execute()
        logger.info("Video added to playlist '%s' (%s)", playlist_title, playlist_id)
    except Exception as playlist_error:
        logger.warning("Playlist add skipped (needs youtube.force-ssl scope): %s", playlist_error)


def _upload_youtube(video_path, thumb_path, script_data, tags):
    """Returns (success: bool, video_id: str|None)."""
    existing_video_id = _existing_youtube_upload(script_data)
    if existing_video_id:
        logger.warning("Duplicate script blocked; existing YouTube upload: %s", existing_video_id)
        return True, existing_video_id

    google_client_id = os.environ.get("GOOGLE_CLIENT_ID")
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

    missing = [
        name for name, val in {
            "GOOGLE_CLIENT_ID": google_client_id,
            "GOOGLE_CLIENT_SECRET": google_client_secret,
            "REFRESH_TOKEN": refresh_token,
        }.items() if not val
    ]
    if missing:
        logger.error(f"YouTube upload skipped - missing secrets: {missing}")
        return False, None

    title = script_data.get('title', 'Untitled')
    enhanced_title = title  # already selected/scored by generate_seo_package
    desc = _build_youtube_description(script_data, tags)

    # NOTE: captions.insert (SRT upload) and commentThreads.insert (posting
    # the pinned_comment from seo_generator) both need the broader
    # youtube.force-ssl scope, not just youtube.upload. Listing it here
    # doesn't grant it by itself - your REFRESH_TOKEN has to have actually
    # been issued with consent for this scope, or those two calls below
    # will fail with a 403 and get skipped (logged as a warning, not fatal -
    # the video upload itself only needs youtube.upload and is unaffected).
    creds = google.oauth2.credentials.Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=google_client_id,
        client_secret=google_client_secret,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
    )
    yt = build('youtube', 'v3', credentials=creds)

    # Scheduled publishing: only meaningful when the video would otherwise go
    # live immediately (public). A manual-review run (private) stays untouched.
    publish_at_iso, slot_info = (None, None)
    if SCHEDULE_PUBLISH and YT_PRIVACY_STATUS == "public":
        publish_at_iso, slot_info = _next_publish_at(yt)

    body = {
        'snippet': {
            'title': enhanced_title[:100],
            'description': desc[:5000],
            'categoryId': '28',
            # FIX: was a fixed hardcoded list on every single video - now
            # topic/category-aware tags from niche_strategy.generate_seo_tags,
            # which also helps SEO reach and avoids duplicate-metadata spam risk.
            'tags': tags,
            # French audience targeting: YouTube's recommendation system uses
            # these two fields to decide which audience to push the Short to.
            'defaultLanguage': 'fr',
            'defaultAudioLanguage': 'fr',
        },
        'status': {
            'privacyStatus': YT_PRIVACY_STATUS,
            'selfDeclaredMadeForKids': MADE_FOR_KIDS,
        }
    }

    if DECLARE_SYNTHETIC_MEDIA:
        # Honest disclosure for AI voice + AI visuals (YouTube A/S content policy).
        body['status']['containsSyntheticMedia'] = True

    if publish_at_iso:
        # publishAt REQUIRES privacyStatus=private; YouTube flips it to public
        # automatically at the scheduled Paris peak time.
        body['status']['privacyStatus'] = 'private'
        body['status']['publishAt'] = publish_at_iso
        logger.info(
            "📅 Scheduled publish: %s (%s, %s Europe/Paris)",
            publish_at_iso, slot_info.get("peak_name"), slot_info.get("time_paris"),
        )
    else:
        logger.info("Upload privacy status will be: %s (no schedule applied)", YT_PRIVACY_STATUS)

    fingerprint = _content_fingerprint(script_data)
    upload_state = _load_upload_state()
    upload_state[fingerprint] = {
        "status": "started",
        "title": enhanced_title,
        "started_at": time.time(),
    }
    _save_upload_state(upload_state)

    logger.info("Uploading to YouTube...")
    yt_video_id = None
    youtube_success = False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = yt.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(video_path, chunksize=1024 * 1024, resumable=True)
            )
            res = req.execute()
            yt_video_id = res.get('id')
            if not yt_video_id:
                raise RuntimeError(f"YouTube upload returned no video ID: {res}")
            upload_state[fingerprint] = {
                "status": "completed",
                "title": enhanced_title,
                "youtube_video_id": yt_video_id,
                "completed_at": time.time(),
            }
            _save_upload_state(upload_state)
            logger.info(f"YouTube upload successful: https://youtu.be/{yt_video_id}")
            youtube_success = True

            # Lock this slot for the rest of THIS process run (batch mode):
            # the next video in the batch must not publish at the same minute.
            claimed_at = _parse_iso_quiet(publish_at_iso)
            if claimed_at:
                _CLAIMED_PUBLISH_ATS.append(claimed_at)

            if thumb_path and os.path.exists(thumb_path):
                try:
                    yt.thumbnails().set(
                        videoId=yt_video_id,
                        media_body=MediaFileUpload(thumb_path)
                    ).execute()
                    logger.info("Thumbnail uploaded successfully")
                except Exception as thumb_error:
                    logger.warning(f"Thumbnail upload failed: {thumb_error}")

            # Optional: real closed-caption track from seo/shorts modules'
            # SRT export (main.py sets script_data['srt_path']). Best-effort
            # only - see scope note above.
            srt_path = script_data.get('srt_path')
            if srt_path and os.path.exists(srt_path):
                try:
                    yt.captions().insert(
                        part="snippet",
                        body={
                            "snippet": {
                                "videoId": yt_video_id,
                                "language": "fr",
                                "name": "French",
                                "isDraft": False,
                            }
                        },
                        media_body=MediaFileUpload(srt_path, mimetype="application/octet-stream"),
                    ).execute()
                    logger.info("Captions uploaded successfully")
                except Exception as captions_error:
                    logger.warning(
                        f"Captions upload failed (needs youtube.force-ssl scope on REFRESH_TOKEN): {captions_error}"
                    )

            # Optional: post the pinned_comment from seo_generator as the
            # first top-level comment. NOTE: this only posts the comment -
            # the YouTube Data API has no public endpoint to actually pin a
            # comment, so pinning it still needs one manual click in Studio.
            pinned_comment = script_data.get('pinned_comment')
            if pinned_comment:
                try:
                    yt.commentThreads().insert(
                        part="snippet",
                        body={
                            "snippet": {
                                "videoId": yt_video_id,
                                "topLevelComment": {
                                    "snippet": {"textOriginal": pinned_comment}
                                },
                            }
                        },
                    ).execute()
                    logger.info("Seed comment posted (pin it manually in YouTube Studio for best effect)")
                except Exception as comment_error:
                    logger.warning(
                        f"Seed comment post failed (needs youtube.force-ssl scope on REFRESH_TOKEN): {comment_error}"
                    )

            # Group the Short into its series playlist (binge/session watch).
            if PLAYLIST_ENABLED:
                _add_video_to_playlist(yt, yt_video_id, script_data.get('playlist_suggestion', ''))
            break

        except HttpError as e:
            if e.resp.status in [429, 500, 502, 503]:
                logger.warning(f"YouTube API error {e.resp.status} (attempt {attempt}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * (2 ** (attempt - 1)))
                continue
            else:
                logger.error(f"YouTube upload failed: {e}")
                break
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            break

    return youtube_success, yt_video_id, (publish_at_iso if youtube_success else None)
    """
    FIX: previously this posted to /{page-id}/videos as a plain video post.
    Facebook's 2026 recommendation algorithm gives materially better organic
    reach to content published through the actual Reels pipeline. This now
    uses the correct 3-phase Reels publishing flow:
      1. upload_phase=start   -> get video_id + upload_url
      2. POST binary to upload_url (rupload host)
      3. upload_phase=finish  -> attach description/hashtags and publish
    Returns success: bool.
    """
    # Facebook Reels has no equivalent private-review workflow in this code.
    # Keep it opt-in so a private YouTube review run never publishes a public
    # Reel by surprise.
    if os.environ.get("FB_UPLOAD_ENABLED", "false").lower() != "true":
        logger.info("Facebook upload disabled (set FB_UPLOAD_ENABLED=true to publish a Reel).")
        return False

    fb_token = os.environ.get("FB_ACCESS_TOKEN")
    fb_page = os.environ.get("FB_PAGE_ID")

    if not fb_token or not fb_page:
        logger.warning("FB_ACCESS_TOKEN or FB_PAGE_ID missing - Facebook upload skipped")
        return False

    # Duplicate prevention: if this exact video title was already successfully
    # posted to Facebook in a previous run, skip it rather than uploading again.
    if _already_uploaded_to_facebook(script_data):
        logger.info(f"Facebook: '{script_data.get('title')}' already uploaded — skipping duplicate.")
        return True  # treat as success so pipeline doesn't retry/fail

    # Max 3 hashtags — Facebook's own algorithm penalises Reels with >5 hashtags
    description = _build_facebook_description(script_data, tags)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # ---- Phase 1: start ----
            start_resp = requests.post(
                f"https://graph.facebook.com/v19.0/{fb_page}/video_reels",
                data={"upload_phase": "start", "access_token": fb_token},
                timeout=30,
            )
            start_data = start_resp.json()
            if "error" in start_data or "video_id" not in start_data:
                raise RuntimeError(f"Reels start phase failed: {start_data}")

            video_id = start_data["video_id"]
            upload_url = start_data["upload_url"]

            # ---- Phase 2: upload binary ----
            file_size = os.path.getsize(video_path)
            with open(video_path, "rb") as f:
                upload_resp = requests.post(
                    upload_url,
                    headers={
                        "Authorization": f"OAuth {fb_token}",
                        "offset": "0",
                        "file_size": str(file_size),
                    },
                    data=f,
                    timeout=300,
                )
            upload_data = upload_resp.json() if upload_resp.content else {}
            if upload_resp.status_code != 200 or upload_data.get("success") is False:
                raise RuntimeError(f"Reels upload phase failed: {upload_resp.status_code} {upload_data}")

            # ---- Phase 3: finish/publish ----
            finish_resp = requests.post(
                f"https://graph.facebook.com/v19.0/{fb_page}/video_reels",
                data={
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "description": description,
                    "video_state": "PUBLISHED",
                    "access_token": fb_token,
                },
                timeout=60,
            )
            finish_data = finish_resp.json()
            if finish_resp.status_code == 200 and finish_data.get("success", True) and "error" not in finish_data:
                logger.info(f"Facebook Reels published successfully: video_id={video_id}")
                return True
            else:
                raise RuntimeError(f"Reels finish phase failed: {finish_data}")

        except Exception as e:
            logger.warning(f"Facebook Reels upload attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (2 ** (attempt - 1)))
            continue

    logger.error("Facebook Reels upload failed after all retries")
    return False


def upload_all(video_path, thumb_path, script_data):
    """Upload video to YouTube and Facebook Reels with comprehensive error handling."""

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if not script_data or 'title' not in script_data:
        raise ValueError("Invalid script data - missing title")

    title = script_data.get('title', 'Untitled')
    # Tags come from script_data (set by main.py via niche_strategy.generate_seo_tags).
    # Fallback below only fires if that ever comes back empty - matches the
    # current dark-facts niche, not the old parenting-channel tags.
    # French fallback (was leftover English 'darkfacts'/'bodyfacts' tags).
    tags = script_data.get('tags') or ['science', 'shorts', 'corps humain', 'cerveau']

    logger.info(f"Starting upload process for: {title}")
    logger.info(f"selfDeclaredMadeForKids = {MADE_FOR_KIDS} (verify this is correct for your content!)")
    logger.info("YouTube language metadata = fr (defaultLanguage + defaultAudioLanguage)")
    logger.info(f"Privacy status = {YT_PRIVACY_STATUS} | scheduled publish = {SCHEDULE_PUBLISH} | synthetic disclosure = {DECLARE_SYNTHETIC_MEDIA}")
    logger.info(f"SEO tags for this video: {tags}")

    youtube_success, yt_video_id, publish_at = _upload_youtube(video_path, thumb_path, script_data, tags)
    facebook_success = _upload_facebook_reels(video_path, script_data, tags)

    logger.info(f"YouTube Upload: {'SUCCESS' if youtube_success else 'FAILED/SKIPPED'}")
    if yt_video_id:
        logger.info(f"  URL: https://youtu.be/{yt_video_id}")
    logger.info(f"Facebook Upload: {'SUCCESS' if facebook_success else 'FAILED/SKIPPED'}")

    if not (youtube_success or facebook_success):
        raise RuntimeError("Both YouTube and Facebook uploads failed")

    return {
        "youtube_success": youtube_success,
        "youtube_video_id": yt_video_id,
        "facebook_success": facebook_success,
        "publish_at": publish_at,
    }
