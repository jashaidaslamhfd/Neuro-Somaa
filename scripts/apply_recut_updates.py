"""Apply approved re-cut metadata and create safe YouTube uploads.

The script is intentionally opt-in: it requires --execute, updates only the
source IDs present in the manifest, and uploads re-cuts as private by default.
Set RECUT_UPLOAD_MODE=scheduled only when the operator wants YouTube to publish
at a future timestamp supplied in the manifest.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

LOG = logging.getLogger("apply_recut_updates")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def _yt():
    required = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REFRESH_TOKEN"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing OAuth variables: " + ", ".join(missing))
    creds = Credentials(
        token=None,
        refresh_token=os.environ["REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds)


def _description(item: dict) -> str:
    script = item["script"]
    topic = script.get("topic") or item.get("topic", "")
    hook = script.get("hook", "").strip()
    cta = script.get("cta", "").strip()
    tags = script.get("tags", [])
    hashtags = " ".join("#" + str(tag).replace(" ", "") for tag in tags[:5])
    return (
        f"{hook}\n\nDans ce Short, on explore {topic.lower()}. "
        "Une explication courte, claire et fondée sur les mécanismes du corps et du cerveau.\n\n"
        f"{cta}\n\n{hashtags}\n\n"
        "Contenu éducatif : il ne remplace pas un avis médical professionnel."
    )[:5000]


def _tags(item: dict) -> list[str]:
    base = [str(x).strip() for x in item["script"].get("tags", []) if str(x).strip()]
    fixed = ["shorts", "santé", "cerveau", "corps humain", "neurosciences", "français"]
    return list(dict.fromkeys(base + fixed))[:500]


def update_existing(yt, item: dict, thumb: Path) -> dict:
    video_id = item["source_video_id"]
    current = yt.videos().list(part="snippet,status", id=video_id).execute().get("items", [])
    if not current:
        raise RuntimeError(f"Source video not found: {video_id}")
    old = current[0]
    old_snippet = old.get("snippet", {})
    snippet = dict(old_snippet)
    snippet.update({
        "title": item["script"]["title"][:100],
        "description": _description(item),
        "tags": _tags(item),
        "defaultLanguage": "fr",
        "defaultAudioLanguage": "fr",
    })
    yt.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    if not thumb.is_file():
        raise RuntimeError(f"Rendered thumbnail missing: {thumb}")
    thumb_response = yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumb))).execute()
    return {
        "video_id": video_id,
        "old_title": old_snippet.get("title"),
        "new_title": snippet["title"],
        "thumbnail_id": thumb_response.get("items", [{}])[0].get("id"),
        "metadata_updated": True,
        "thumbnail_updated": True,
    }


def upload_recut(yt, item: dict, video: Path, thumb: Path, mode: str) -> dict:
    if mode not in {"private", "scheduled"}:
        raise ValueError("RECUT_UPLOAD_MODE must be private or scheduled")
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    publish_at = item.get("publish_at")
    if mode == "scheduled":
        if not publish_at:
            raise RuntimeError(f"Scheduled mode requires publish_at for {item['id']}")
        status["publishAt"] = publish_at
    body = {
        "snippet": {
            "title": item["script"]["title"][:100] + " | Recut",
            "description": _description(item),
            "tags": _tags(item) + [item["experiment_id"]],
            "categoryId": "27",
            "defaultLanguage": "fr",
            "defaultAudioLanguage": "fr",
        },
        "status": status,
    }
    response = yt.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(video), chunksize=1024 * 1024, resumable=True),
    ).execute()
    new_id = response["id"]
    thumb_ok = False
    if thumb.is_file():
        yt.thumbnails().set(videoId=new_id, media_body=MediaFileUpload(str(thumb))).execute()
        thumb_ok = True
    return {"video_id": new_id, "privacy_status": "private", "publish_at": publish_at, "thumbnail_uploaded": thumb_ok}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--output-dir", type=Path, default=Path("output/recut_batch"))
    ap.add_argument("--execute", action="store_true", help="Perform YouTube writes; otherwise only validate artifacts")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--skip-uploads", action="store_true")
    args = ap.parse_args()
    items = json.loads(args.manifest.read_text(encoding="utf-8"))["items"]
    mode = os.environ.get("RECUT_UPLOAD_MODE", "private").strip().lower()
    if mode not in {"private", "scheduled"}:
        raise SystemExit("RECUT_UPLOAD_MODE must be private or scheduled")
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "mode": mode, "executed": args.execute, "items": []}
    yt = _yt() if args.execute else None
    for item in items:
        item_dir = args.output_dir / item["id"]
        evidence_path = item_dir / "evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not evidence.get("final_audit", {}).get("approved", True) and args.execute:
            raise RuntimeError(f"Audit not approved for {item['id']}")
        video = Path(evidence["outputs"]["video"])
        thumb = Path(evidence["outputs"]["thumbnail"])
        if not video.is_file() or not thumb.is_file():
            raise RuntimeError(f"Missing approved render for {item['id']}")
        result = {"id": item["id"], "source_video_id": item["source_video_id"], "artifacts_valid": True}
        if args.execute and not args.skip_existing:
            result["existing_update"] = update_existing(yt, item, thumb)
        if args.execute and not args.skip_uploads:
            result["recut_upload"] = upload_recut(yt, item, video, thumb, mode)
        report["items"].append(result)
        LOG.info("%s ready%s", item["id"], " and applied" if args.execute else "")
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report_path = args.output_dir / "apply_recut_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("Report written to %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

