#!/usr/bin/env python3
"""One-shot metadata REPAIR for the faults found by scripts/video_audit.py
(audit 2026-07-25: 13/26 videos faulty).

Faults and the fix for each:

1. tags_english_only (9 videos)
   The pre-fix engine stamped English-only tag sets on French videos,
   weakening French audience targeting. Replaced with curated French tag
   sets (topic keywords + Shorts base). The untouched winners/legacy
   videos keep their own titles/descriptions — only `tags` change.
   NOTE: YouTube clears omitted snippet fields on update, so the update
   payload resends title/description/categoryId/language unchanged.

2. duplicate_title — junk pair (BOTH named "La Vérité Sur Your Lungs
   Never Fully Empty", bilingual broken-engine titles, 1 view each)
   - DELETE 4Cg6ZMqZuts  (exact duplicate, 1 view — same precedent as the
     earlier c8Rx61Hly_4 cleanup)
   - RETITLE nQI2RkTODb0 -> proper French question title (winner DNA)

3. duplicate_title — healthy pairs (both videos performing 145-1509 views)
   LEFT AS-IS on purpose: both established in the feed; rewriting titles
   now risks their momentum, and the new near-duplicate ban in
   trend_fetcher stops recurrence.

Run DRY by default (prints the plan); pass --apply to write changes.
Needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / REFRESH_TOKEN env.
"""
import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_audit import _classify  # noqa: E402  (same robust FR/EN heuristics)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("video-repair")

DELETE_IDS = {
    "4Cg6ZMqZuts": "exact duplicate of nQI2RkTODb0 (same junk bilingual title, 1 view)",
}

RETITLE = {
    "nQI2RkTODb0": "Pourquoi vos poumons ne se vident jamais complètement ?",
}

BASE_TAGS = ["shorts", "science", "corps humain", "faits étonnants", "curiosité"]

RETAG = {
    "nQI2RkTODb0": ["pourquoi", "poumons", "respiration", "air", "santé",
                    "poumon", "corps", "expliqué simplement"],
    "vAmu8qhid6w": ["pourquoi", "chair de poule", "froid", "réflexe", "peau",
                    "température", "corps", "expliqué simplement"],
    "b3W6KVeZuCo": ["pourquoi", "poumons", "froid", "air froid", "respiration",
                    "poitrine", "hiver", "santé"],
    "6TMN07KA8g4": ["vaisseaux sanguins", "corps humain", "sang", "cœur",
                    "anatomie", "pourquoi", "surprenant", "record"],
    "oYWA48Tbcyc": ["cerveau", "illusions", "perception", "psychologie",
                    "pourquoi", "surprenant", "expliqué simplement", "preuve"],
    "yxoI9-KWXzI": ["stress", "mémoire", "cerveau", "cortisol", "pourquoi",
                    "santé mentale", "oublier", "concentration"],
    "68B-7lTf8nU": ["genoux qui craquent", "articulations", "pourquoi", "corps",
                    "os", "craquement", "santé", "expliqué simplement"],
    "hAb8ztZnG-k": ["oreilles", "grandissent", "vieillir", "corps", "pourquoi",
                    "oreille", "vieillissement", "surprenant"],
}


def _token() -> str:
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["REFRESH_TOKEN"],
        "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(
            urllib.request.Request("https://oauth2.googleapis.com/token", data=data),
            timeout=30) as r:
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


def _update_snippet(token: str, vid: str, sn: dict, *, title=None, tags=None,
                    apply=False) -> None:
    new_title = title if title is not None else sn.get("title", "")
    new_tags = tags if tags is not None else (sn.get("tags") or [])
    if not apply:
        if title is not None:
            log.info("[dry] RETITLE %s\n  old: %r\n  new: %r", vid, sn.get("title"), title)
        if tags is not None:
            log.info("[dry] RETAG %s\n  old: %r\n  new: %r", vid, sn.get("tags"), new_tags)
        return
    payload = {"id": vid, "snippet": {
        "title": new_title,
        "description": sn.get("description", ""),
        "categoryId": sn.get("categoryId", "27"),
        "tags": new_tags,
        **({"defaultLanguage": sn["defaultLanguage"]} if sn.get("defaultLanguage") else {}),
        **({"defaultAudioLanguage": sn["defaultAudioLanguage"]}
           if sn.get("defaultAudioLanguage") else {}),
    }}
    _req("PUT", "https://www.googleapis.com/youtube/v3/videos?part=snippet",
         token, payload)
    log.info("updated %s (title/tags)", vid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    token = _token()

    for vid, why in DELETE_IDS.items():
        if not args.apply:
            log.info("[dry] would DELETE %s (%s)", vid, why)
        else:
            _req("DELETE", f"https://www.googleapis.com/youtube/v3/videos?id={vid}", token)
            log.info("DELETED %s", vid)
        time.sleep(1)

    for vid, new_title in RETITLE.items():
        sn = _get_snippet(token, vid)
        if not sn:
            log.warning("%s not found — skipping retitle", vid)
            continue
        # retitle AND retag in ONE update when both apply (50 units, not 100)
        tags = None
        if vid in RETAG:
            merged = RETAG[vid] + [t for t in BASE_TAGS if t not in RETAG[vid]]
            tags = merged[:14]
        log.info("RETITLE+RETAG %s", vid)
        _update_snippet(token, vid, sn, title=new_title, tags=tags, apply=args.apply)
        RETAG.pop(vid, None)
        time.sleep(1)

    for vid, topic_tags in RETAG.items():
        sn = _get_snippet(token, vid)
        if not sn:
            log.warning("%s not found — skipping retag", vid)
            continue
        merged = topic_tags + [t for t in BASE_TAGS if t not in topic_tags]
        current = sn.get("tags") or []
        en_like = sum(1 for t in current if _classify(t) == "en")
        fr_like = sum(1 for t in current if _classify(t) in ("fr", "mixed"))
        if fr_like > 0 and en_like == 0:
            log.info("%s already has French tags — skipping", vid)
            continue
        _update_snippet(token, vid, sn, tags=merged[:14], apply=args.apply)
        time.sleep(1)

    log.info("done (apply=%s)", args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
