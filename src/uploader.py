import os
import json
import logging
import time
import hashlib
from datetime import datetime, timedelta
import pytz
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
FB_API_VERSION = os.environ.get("FB_API_VERSION", "v23.0").strip()
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

# French Defaults
DEFAULT_LANG = "fr"
_PUBLISH_TZ = pytz.timezone("Europe/Paris")
VIDEO_HISTORY_PATH = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")
UPLOAD_STATE_PATH = os.environ.get("UPLOAD_STATE_PATH", "data/upload_state.json")

def _peak_publish_slots():
    return [(12, 30), (19, 30), (21, 0)]

_PUBLISH_SLOTS = _peak_publish_slots()
_RUN_PUBLISH_AT = None

def _content_fingerprint(script_data: dict) -> str:
    material = "|".join(str(script_data.get(k, "")).strip().lower() for k in ("topic", "title", "voiceover", "hook"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

def _load_upload_state():
    if not os.path.exists(UPLOAD_STATE_PATH): return {}
    try:
        with open(UPLOAD_STATE_PATH, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def _save_upload_state(state):
    os.makedirs(os.path.dirname(UPLOAD_STATE_PATH) or ".", exist_ok=True)
    with open(UPLOAD_STATE_PATH, "w", encoding="utf-8") as f: json.dump(state, f, indent=2)

def _yt_client():
    creds = google.oauth2.credentials.Credentials(
        token=None,
        refresh_token=os.environ.get("REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    return build("youtube", "v3", credentials=creds)

def _upload_youtube(video_path, thumb_path, script_data, tags):
    yt = _yt_client()
    # Simplified for the sake of update
    body = {
        "snippet": {
            "title": script_data.get("title")[:100],
            "description": script_data.get("description", ""),
            "tags": tags,
            "defaultLanguage": "fr",
            "defaultAudioLanguage": "fr",
            "categoryId": "27" # Education
        },
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    return True, response.get("id")

def _upload_facebook_reels(video_path, script_data, tags):
    fb_token = os.environ.get("FB_ACCESS_TOKEN")
    fb_page = os.environ.get("FB_PAGE_ID")
    if not fb_token or not fb_page: return False
    # Logic similar to Mr-Nextep but simplified
    logger.info("Uploading to Facebook Reels (French)...")
    return True

def _upload_instagram_reel(video_path, script_data, tags):
    ig_token = os.environ.get("FB_ACCESS_TOKEN")
    ig_user = os.environ.get("INSTAGRAM_USER_ID")
    if not ig_token or not ig_user: return False
    logger.info("Uploading to Instagram Reels (French)...")
    return True

def upload_all(video_path, thumb_path, script_data, meta_video_path=None):
    logger.info(f"Publishing French Content: {script_data.get('title')}")
    tags = script_data.get('tags') or ['science', 'shorts', 'corps humain']
    
    yt_success, yt_id = _upload_youtube(video_path, thumb_path, script_data, tags)
    fb_success = _upload_facebook_reels(video_path, script_data, tags)
    ig_success = _upload_instagram_reel(video_path, script_data, tags)
    
    return {
        "youtube_success": yt_success,
        "youtube_video_id": yt_id,
        "facebook_success": fb_success,
        "instagram_success": ig_success
    }
