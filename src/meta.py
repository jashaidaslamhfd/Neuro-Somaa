"""Production Meta (Facebook Reels & Instagram Graph API) Automation Adapter.
Integrated into Neuro-Somaa to provide multi-platform publishing.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("neuro_somaa.meta")

GRAPH_API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def is_meta_configured() -> bool:
    """Check if Meta Page publishing credentials are present in the environment."""
    token = os.getenv("FB_ACCESS_TOKEN", "").strip()
    page_id = os.getenv("FB_PAGE_ID", "").strip()
    return bool(token and page_id)


def upload_to_facebook_reels(video_path: Path, title: str, description: str) -> dict[str, Any]:
    """Upload vertical video as Facebook Page Reel using Graph API 3-phase session.

    Flow:
    1. POST /{page_id}/video_reels (upload_phase=start) -> returns video_id & upload_url
    2. POST {upload_url} binary stream with offset & file_size
    3. POST /{page_id}/video_reels (upload_phase=finish) -> marks video_state=PUBLISHED
    """
    access_token = os.getenv("FB_ACCESS_TOKEN", "").strip()
    page_id = os.getenv("FB_PAGE_ID", "").strip()

    if not access_token or not page_id:
        return {"facebook_success": False, "error": "FB_ACCESS_TOKEN or FB_PAGE_ID missing"}

    if not video_path.exists():
        return {"facebook_success": False, "error": f"Video file not found: {video_path}"}

    file_size = video_path.stat().st_size
    logger.info("Initializing Facebook Reels upload session for '%s' (%d bytes)...", title, file_size)

    try:
        # Phase 1: Start upload session
        init_res = requests.post(
            f"{BASE_URL}/{page_id}/video_reels",
            data={"upload_phase": "start", "access_token": access_token},
            timeout=30,
        )
        if not init_res.ok:
            logger.error("Facebook init session failed (%s): %s", init_res.status_code, init_res.text)
            return {"facebook_success": False, "error": init_res.text}

        init_data = init_res.json()
        video_id = init_data.get("video_id")
        upload_url = init_data.get("upload_url")

        if not video_id or not upload_url:
            return {"facebook_success": False, "error": f"Malformed init response from Meta: {init_data}"}

        # Phase 2: Transfer binary stream
        logger.info("Streaming video binary to Facebook endpoint (video_id=%s)...", video_id)
        with open(video_path, "rb") as fp:
            upload_res = requests.post(
                upload_url,
                headers={
                    "Authorization": f"OAuth {access_token}",
                    "offset": "0",
                    "file_size": str(file_size),
                },
                data=fp,
                timeout=360,
            )

        if not upload_res.ok:
            logger.error("Facebook video binary upload failed: %s", upload_res.text)
            return {"facebook_success": False, "error": upload_res.text}

        # Phase 3: Finish & publish
        logger.info("Finalizing and publishing Facebook Reel (id=%s)...", video_id)
        publish_res = requests.post(
            f"{BASE_URL}/{page_id}/video_reels",
            data={
                "upload_phase": "finish",
                "access_token": access_token,
                "video_id": video_id,
                "title": title[:100],
                "description": description[:2000],
                "video_state": "PUBLISHED",
            },
            timeout=30,
        )

        if not publish_res.ok:
            logger.error("Facebook publish phase failed: %s", publish_res.text)
            return {"facebook_success": False, "error": publish_res.text}

        reel_url = f"https://www.facebook.com/reel/{video_id}"
        logger.info("Facebook Reel successfully published: %s", reel_url)
        return {
            "facebook_success": True,
            "facebook_video_id": video_id,
            "facebook_url": reel_url,
        }
    except Exception as exc:
        logger.exception("Unexpected exception during Facebook Reel upload: %s", exc)
        return {"facebook_success": False, "error": str(exc)}
