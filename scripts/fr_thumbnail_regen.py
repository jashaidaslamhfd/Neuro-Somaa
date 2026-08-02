#!/usr/bin/env python3
"""
SKILLOR FR — Regenerate thumbnails for ALL videos in the house style
(clean blue medical x-ray + big bold hook text, 1080x1920).

Source images: repo assets (assets/thumbnails_fr/<video_id>.jpg if it exists,
else a procedural dark visual). Thumbnails are written to output/thumbs/ and
uploaded via YouTube thumbnails.set (only with --apply).

Usage:
  python scripts/fr_thumbnail_regen.py                # generate only
  python scripts/fr_thumbnail_regen.py --apply        # generate + upload
  python scripts/fr_thumbnail_regen.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("fr_thumbnail_regen")

PLAN_JSON = ROOT / "data" / "fr_optimize_plan.json"
THUMB_DIR = ROOT / "output" / "thumbs"
THUMB_DIR.mkdir(parents=True, exist_ok=True)


def _make_thumbnail(title: str, out_path: str, src_img: str | None = None) -> bool:
    """House-style thumbnail: dark blue gradient + big hook text."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1080, 1920
    if src_img and Path(src_img).exists():
        img = Image.open(src_img).convert("RGB").resize((W, H), Image.LANCZOS)
    else:
        # dark blue medical gradient fallback
        img = Image.new("RGB", (W, H))
        px = img.load()
        for y in range(H):
            f = y / H
            px_set = (int(8 + 8 * f), int(16 + 20 * f), int(40 + 60 * f))
            for x in range(0, W, 8):
                for xx in range(x, min(x + 8, W)):
                    px[xx, y] = px_set

    draw = ImageDraw.Draw(img)
    font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            font = ImageFont.truetype(fp, 76)
            break
    if font is None:
        font = ImageFont.load_default()

    # dark overlay for legibility
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    do = ImageDraw.Draw(ov)
    do.rectangle([0, H - 620, W, H], fill=(0, 0, 0, 190))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(img)

    # wrap text
    import textwrap
    lines = textwrap.wrap(title, width=16)[:4]
    y = H - 560
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((W - w) / 2, y), line, font=font,
                  fill=(255, 255, 255, 255), stroke_width=3,
                  stroke_fill=(10, 30, 60))
        y += 105

    img.save(out_path, quality=90)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    plan = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    videos = plan["videos"]
    if args.limit:
        videos = videos[:args.limit]

    client = None
    if args.apply:
        import google.oauth2.credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        cid = os.environ.get("GOOGLE_CLIENT_ID")
        csec = os.environ.get("GOOGLE_CLIENT_SECRET")
        rtok = os.environ.get("REFRESH_TOKEN")
        if not (cid and csec and rtok):
            log.error("Missing Google creds for --apply")
            return 1
        creds = google.oauth2.credentials.Credentials(
            token=None, refresh_token=rtok,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cid, client_secret=csec)
        client = build("youtube", "v3", credentials=creds)

    ok = 0
    for v in videos:
        vid = v["id"]
        src = ROOT / "assets" / "thumbnails_fr" / f"{vid}.jpg"
        src = src if src.exists() else None
        out = THUMB_DIR / f"{vid}.jpg"
        try:
            _make_thumbnail(v["new_title"], str(out), str(src) if src else None)
            ok += 1
            if args.apply and client:
                client.thumbnails().set(
                    videoId=vid,
                    media_body=MediaFileUpload(str(out), mimetype="image/jpeg"),
                ).execute()
                log.info("✅ thumb %s", vid)
        except Exception as exc:
            log.error("❌ thumb %s: %s", vid, exc)

    log.info("Generated %d thumbnails -> %s%s", ok, THUMB_DIR,
             " (uploaded)" if args.apply else " (dry-run: use --apply to upload)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
