#!/usr/bin/env python3
"""One-shot YouTube metadata repair for SKILLOR FR.

Fixes the vintage of videos published BEFORE the 2026-07-23 content fixes:
- Titles truncated mid-sentence ("...peut sembler" cut off) → clean dangling-
  safe curiosity titles rebuilt from the catalogue angle stored in history.
- Short 2-3 word label titles → full curiosity-loop French titles.
- Missing/thin tags → topic-specific SEO tags.
- Descriptions → rebuilt with the current generator (hook + CTA + hashtags,
  max 3 hashtags).

SAFETY:
- Default is DRY RUN: prints the full before/after plan, changes nothing.
- Pass --apply to write changes to YouTube (videos.update).
- --limit N to process at most N videos (oldest-first).
- Anything the script cannot confidently improve is SKIPPED, never guessed.
- Uses ONLY data in data/video_history.json (the pipeline's own record of
  title/topic per upload), so every new title stays on-topic by construction.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("metadata_repair")

from niche_strategy import generate_seo_tags  # noqa: E402
from seo_generator import _truncate_title  # noqa: E402 — clean dangling-safe truncation


# --------------------------------------------------------------------------- #
# YouTube helpers (std-lib only — workflow installs google libs, but we don't
# need them for a couple of REST calls)
# --------------------------------------------------------------------------- #
def _access_token() -> str:
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def _api(path: str, token: str, *, method: str = "GET", body: dict = None):
    import urllib.error
    import urllib.request

    url = "https://www.googleapis.com/youtube/v3/" + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if r.status == 204:
                return None
            return json.load(r)
    except urllib.error.HTTPError as e:
        payload = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"YouTube API {method} {path} -> {e.code}: {payload}") from e


def _get_video(token: str, video_id: str) -> dict:
    res = _api(f"videos?part=snippet&id={video_id}", token)
    items = res.get("items") or []
    return items[0]


# --------------------------------------------------------------------------- #
# Repair logic
# --------------------------------------------------------------------------- #
def _looks_truncated(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    last = t.split()[-1].lower().rstrip("?!.")
    from seo_generator import _DANGLING_ENDINGS
    if last in _DANGLING_ENDINGS:
        return True
    # A dangling ARTICLE is not the only way a title gets cut. "Ce que votre
    # corps vous dit quand le silence" ends on a perfectly good noun, yet the
    # subordinate clause opened by "quand/lorsque/si" never resolves — the
    # viewer is never told what happens. Live example: TaXxSn0YoMc, which the
    # first repair pass left untouched because the last word looked fine.
    lowered = t.lower().rstrip("?!. ")
    for opener in (" quand ", " lorsque ", " lorsqu'", " si "):
        if opener in f" {lowered} ":
            tail = f" {lowered} ".rsplit(opener, 1)[1].strip()
            # "quand le silence" = article + noun and nothing else: unresolved.
            if len(tail.split()) <= 2:
                return True
    return False


def _carries_description_text(title: str) -> bool:
    """True when body/description copy leaked into the title.

    A previous repair run published
    "Pourquoi se réveiller avant son réveil Dans ce Short on e ?" (1XVYcxQqDqo)
    — the description template bled into the title and was then truncated
    mid-word. scripts/channel_seo_audit.py already guards against this via
    _repair_title_is_safe(), but metadata_repair.py had no equivalent check,
    so it treated the polluted title as healthy and left it live.
    """
    low = (title or "").lower()
    leaked = (
        "dans ce short", "ce short", "abonne", "abonnez", "hashtags",
        "description", "voici", "```", "#", "http", "www.", " on e",
    )
    return any(token in low for token in leaked)


def _is_label_title(title: str) -> bool:
    words = [w for w in (title or "").split() if w.strip()]
    # "Throat Lump 🫀" style = 2-3 tokens, no curiosity starter
    if len(words) <= 3:
        starters = ("pourquoi", "ce qu", "ce que", "ce qui", "comment", "la science", "comprendre")
        return not (title or "").lower().startswith(starters)
    return False


def build_new_metadata(entry: dict, current: dict) -> dict | None:
    """Return dict of changed fields, or None if nothing worth changing."""
    snip = current["snippet"]
    topic_full = (entry.get("topic") or "").strip()  # full angle from catalogue
    old_title = (snip.get("title") or "").strip()

    changes: dict = {}

    # --- TITLE ---
    # Only touch a BROKEN title (clips mid-sentence, dangling verb, or a bare
    # 2-3 word label). A full grammatical question/sentence title is left
    # alone even if it differs from the catalogue angle — question titles in
    # second person ("Pourquoi ton corps... ?") are the winning style.
    title_broken = (
        _looks_truncated(old_title)
        or _is_label_title(old_title)
        or _carries_description_text(old_title)
    )
    if topic_full and title_broken:
        cap = topic_full[0].upper() + topic_full[1:]
        new_title = _truncate_title(cap)
        if new_title and new_title != old_title and len(new_title.split()) >= 3 \
                and not _looks_truncated(new_title) \
                and not _carries_description_text(new_title):
            # Never write a replacement that is itself polluted or unresolved —
            # that is how "…Dans ce Short on e ?" reached the channel.
            changes["title"] = new_title

    # --- TAGS ---
    category = "Body"
    title_for_tags = changes.get("title", old_title)
    raw_tags = generate_seo_tags(changes.get("title", old_title) or topic_full, category, title_for_tags)
    # strip connector/short junk ("d'une", "lors") — tags must be searchable words/phrases
    junk = {"d'une", "d'un", "lors", "dans", "avec", "sans", "pour", "quand", "que", "qui", "des", "les",
            "sur", "sous", "une", "par", "aux", "est", "sont", "pas", "plus", "tout"}
    new_tags = []
    for t in raw_tags:
        t = (t or "").strip()
        tl = t.lower()
        if not t or tl in junk or len(t) < 4:
            continue
        new_tags.append(t)
    if "science" not in {x.lower() for x in new_tags}:
        new_tags.append("science")
    if "corps humain" not in {x.lower() for x in new_tags}:
        new_tags.append("corps humain")
    seen_t, dedup_t = set(), []
    for t in new_tags:
        if t.lower() not in seen_t:
            seen_t.add(t.lower())
            dedup_t.append(t)
    new_tags = dedup_t[:14]
    old_tags = snip.get("tags") or []
    if new_tags and {t.lower() for t in new_tags} != {t.lower() for t in old_tags}:
        changes["tags"] = new_tags

    # --- DESCRIPTION ---
    voiceover = (entry.get("voiceover") or "").strip().replace("\n", " ")
    desc_topic = topic_full or old_title
    script_like = {
        "title": changes.get("title", old_title),
        "description": (
            f"Dans ce Short, on explique clairement : {desc_topic}. "
            f"{voiceover[:240].rstrip()}".strip()
        ),
        "cta": "Abonnez-vous pour plus de science expliquée simplement.",
    }
    from seo_generator import generate_description
    new_desc = generate_description(script_like, changes.get("tags", old_tags) or new_tags)
    # tidy the hashtag block: dedupe, drop junk fragments, cap at 10 (YouTube
    # only surfaces the first 3 above the title; the rest are search signals)
    junk_h = {"#d'une", "#d'un", "#lors", "#dans", "#avec", "#sans", "#pour", "#que", "#qui"}
    lines = new_desc.strip().split("\n")
    body_lines, tags_seen, tag_lines = [], set(), []
    for ln in lines:
        words = ln.split()
        if words and all(w.startswith("#") for w in words):
            for w in words:
                wl = w.lower()
                if wl not in tags_seen and wl not in junk_h and len(w) >= 4:
                    tags_seen.add(wl)
                    tag_lines.append(w)
        else:
            body_lines.append(ln)
    rebuilt = "\n".join(body_lines).rstrip()
    if tag_lines:
        rebuilt += "\n\n" + " ".join(tag_lines[:10])
    new_desc = rebuilt
    old_desc = (snip.get("description") or "").strip()
    if new_desc and new_desc.strip() != old_desc:
        changes["description"] = new_desc.strip()

    return changes or None


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default = dry run)")
    ap.add_argument("--limit", type=int, default=0, help="max videos to process (oldest first)")
    ap.add_argument("--history", default="data/video_history.json")
    args = ap.parse_args()

    history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    entries = history if isinstance(history, list) else history.get("videos", [])
    entries = [e for e in entries if e.get("youtube_video_id")]
    entries.sort(key=lambda e: e.get("posted_at", ""))  # oldest first
    if args.limit:
        entries = entries[: args.limit]

    logger.info("Repair candidates: %d (mode=%s)", len(entries), "APPLY" if args.apply else "DRY RUN")
    if not entries:
        return 0

    token = _access_token()
    plan_rows = []
    updated = skipped = failed = 0

    for e in entries:
        vid = e["youtube_video_id"]
        old_hist_title = (e.get("title") or "")[:70]
        try:
            current = _get_video(token, vid)
            live_title = current["snippet"].get("title", "")
            changes = build_new_metadata(e, current)
            if not changes:
                skipped += 1
                plan_rows.append(f"SKIP  {vid} | already good | {live_title[:60]}")
                continue
            plan_rows.append(f"FIX   {vid}\n"
                             f"  old: {live_title[:90]}\n"
                             f"  new: {changes.get('title', live_title)[:90]}")
            if args.apply:
                snip = dict(current["snippet"])
                snip.update(changes)
                # 'position' is not writable on update; keep known fields only
                allowed = {"title", "description", "tags", "categoryId",
                           "defaultLanguage", "defaultAudioLanguage"}
                body = {"id": vid, "snippet": {k: v for k, v in snip.items() if k in allowed and v is not None}}
                _api("videos?part=snippet", token, method="PUT", body=body)
                updated += 1
                time.sleep(1.5)  # gentle on quota — 10k/day, each update ~50
            else:
                updated += 1  # counted in plan
        except Exception as exc:
            failed += 1
            plan_rows.append(f"FAIL  {vid} | {old_hist_title} | {exc}")
            logger.warning("Failed %s: %s", vid, exc)

    report = "\n".join(plan_rows)
    print(report)
    Path("output").mkdir(exist_ok=True)
    Path("output/metadata_repair_report.txt").write_text(report, encoding="utf-8")
    logger.info("DONE — fixed: %d, skipped: %d, failed: %d (mode=%s)",
                updated, skipped, failed, "APPLY" if args.apply else "DRY RUN")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
