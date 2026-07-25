#!/usr/bin/env python3
"""One-shot YouTube admin for SKILLOR FR — legacy junk cleanup.

Diagnosis (28-day analytics, 2026-07-24): every <10-view video carries a
half-French/half-English title from the old broken engine, and two uploads
are the SAME video published twice. These drag the channel's quality signal.

Actions (all idempotent, oldest legacy only):
- DELETE one exact duplicate upload (1 view, twin of the kept 4-view one).
- RETITLE five legacy videos to clean French curiosity titles and set their
  defaultLanguage=fr (snippet is read first and re-saved with every other
  field preserved, per YouTube update semantics).

Run dry by default (prints the plan); pass --apply to write changes.
Needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / REFRESH_TOKEN env.
"""
import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("yt-admin")

DELETE_IDS = {
    "c8Rx61Hly_4": "exact duplicate of oYWA48Tbcyc ('Your Brain Lies to You Every Day')",
}

RETITLE = {
    "6TMN07KA8g4": "Vos vaisseaux sanguins pourraient faire le tour de la Terre ?",
    "hAb8ztZnG-k": "Pourquoi vos oreilles grandissent toute votre vie ?",
    "oYWA48Tbcyc": "Votre cerveau vous ment chaque jour — la preuve",
    "vAmu8qhid6w": "Pourquoi la chair de poule quand vous avez froid ?",
    "b3W6KVeZuCo": "Pourquoi vos poumons piquent quand il fait froid ?",
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


def delete_video(token: str, vid: str, apply: bool) -> None:
    if not apply:
        log.info("[dry] would DELETE %s (%s)", vid, DELETE_IDS[vid])
        return
    _req("DELETE", f"https://www.googleapis.com/youtube/v3/videos?id={vid}", token)
    log.info("DELETED %s", vid)


def retitle_video(token: str, vid: str, new_title: str, apply: bool) -> None:
    cur = _req("GET",
               f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={vid}",
               token)
    items = cur.get("items") or []
    if not items:
        log.warning("video %s not found — skipping", vid)
        return
    sn = items[0]["snippet"]
    have, lang = sn.get("title", ""), sn.get("defaultLanguage")
    if have == new_title and lang == "fr":
        log.info("already clean: %s", vid)
        return
    log.info("RETITLE %s\n  old: %r\n  new: %r (lang %r -> 'fr')", vid, have, new_title, lang)
    if not apply:
        return
    # YouTube clears snippet fields that are omitted from the update payload,
    # so resend every field we want to keep.
    payload = {"id": vid, "snippet": {
        "title": new_title,
        "description": sn.get("description", ""),
        "categoryId": sn.get("categoryId", "27"),
        "tags": sn.get("tags", []),
        "defaultLanguage": "fr",
        **({"defaultAudioLanguage": sn["defaultAudioLanguage"]}
           if sn.get("defaultAudioLanguage") else {}),
    }}
    _req("PUT", "https://www.googleapis.com/youtube/v3/videos?part=snippet",
         token, payload)
    log.info("updated %s", vid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    token = _token()
    for vid in DELETE_IDS:
        delete_video(token, vid, args.apply)
        time.sleep(1)
    for vid, title in RETITLE.items():
        retitle_video(token, vid, title, args.apply)
        time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
