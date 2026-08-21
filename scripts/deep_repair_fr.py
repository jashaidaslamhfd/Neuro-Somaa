import json
import logging
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("deep_repair_fr")

# Viral French Search Cluster
VIRAL_KEYWORDS = ["corps humain", "cerveau", "mystère", "science", "faits incroyables", "pourquoi"]


def _access_token():
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode(
        {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def _api(path, token, method="GET", body=None):
    import urllib.request

    url = "https://www.googleapis.com/youtube/v3/" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r) if r.status != 204 else None


def repair_video(vid, current_snip, token):
    title = current_snip.get("title", "")
    desc = current_snip.get("description", "")
    # Note: this legacy repair pass only touches title/description/language.
    # Tag repair lives in the newer fr_batch_optimize.py / repair_all_seo.py
    # (measured-demand-backed tags); removed a `tags = ...` read here that
    # was fetched but never actually used (flake8 F841).
    needs_fix = False

    # 1. Title SEO (French Curiosity Pattern)
    if not any(kw in title.lower() for kw in VIRAL_KEYWORDS) or len(title.split()) < 4:
        new_title = f"{title} | Science du Corps Humain"
        if len(new_title) <= 100:
            current_snip["title"] = new_title
            needs_fix = True

    # 2. Description (Hashtag boost)
    if "#Shorts" not in desc or len(re.findall(r"#\w+", desc)) < 3:
        current_snip["description"] = desc + "\n\n#Shorts #science #corpshumain #france #mystere"
        needs_fix = True

    # 3. Language
    if current_snip.get("defaultLanguage") != "fr":
        current_snip["defaultLanguage"] = "fr"
        current_snip["defaultAudioLanguage"] = "fr"
        needs_fix = True

    if needs_fix:
        try:
            _api("videos?part=snippet", token, method="PUT", body={"id": vid, "snippet": current_snip})
            logger.info(f"✅ Repaired: {vid}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed {vid}: {e}")
    return False


def main():
    token = _access_token()
    res = _api("channels?part=contentDetails&mine=true", token)
    playlist_id = res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    vids_res = _api(f"playlistItems?part=contentDetails&playlistId={playlist_id}&maxResults=50", token)
    video_ids = [i["contentDetails"]["videoId"] for i in vids_res.get("items", [])]

    for vid in video_ids:
        video_data = _api(f"videos?part=snippet&id={vid}", token)
        if video_data.get("items"):
            repair_video(vid, video_data["items"][0]["snippet"], token)
            time.sleep(1)


if __name__ == "__main__":
    import sys

    main()
