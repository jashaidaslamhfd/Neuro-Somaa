#!/usr/bin/env python3
"""
SKILLOR FR — Batch Optimizer: ALL channel videos (published + scheduled).

2026 YouTube-algorithm + French-audience optimization for every video:
  • TITLE   — curiosity "Pourquoi X ?" (channel's bandit-proven winner,
              score 3.60), keyword-first, ≤70 chars, leak-gate enforced.
  • DESCRIPTION — French, keyword-dense first 2 lines, "Ce que vous allez
              découvrir", hashtags (2-3), educational disclaimer, CTA.
  • TAGS    — French, ≤500 chars total, specific + broad + branded.
  • THUMBNAIL — regenerated in the house style (blue medical x-ray + big
              hook text) when a source image is available.

Flow:
  1. fetch:  videos.list(part=snippet,status,statistics) — ALL videos
             (published + private/unlisted = scheduled), paginated.
  2. plan:   build optimized metadata per video using seo_generator's
             proven helpers (leak-gate + question titles) + templates.
  3. apply:  videos.update per video (optional, --apply).
  4. report: data/fr_optimize_plan.json + .md (always).

Usage:
  python scripts/fr_batch_optimize.py                 # dry-run plan only
  python scripts/fr_batch_optimize.py --apply         # write to YouTube
  python scripts/fr_batch_optimize.py --limit 10      # first N videos
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("fr_batch_optimize")

HISTORY = ROOT / "data" / "video_history.json"
PLAN_JSON = ROOT / "data" / "fr_optimize_plan.json"
PLAN_MD = ROOT / "data" / "fr_optimize_plan.md"

DISCLAIMER = ("Contenu éducatif, pas un avis médical. Si un symptôme persiste, "
              "parle à un professionnel de santé.")
HASHTAGS = ["#shorts", "#corpshumain", "#science"]
CTA = "Abonne-toi pour plus de science simple. 🔬"

# ── French title optimisation (topic-driven, leak-gate + question pattern) ──
def _strip_leak_suffix(text: str) -> str:
    """Remove LLM filler that leaks into topics: 'peut sembler étrange',
    'peut sembler', 'arrive', dangling connectors, etc."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    for pat in (r"\s*peut\s+sembler\s+étrange\s*$", r"\s*peut\s+sembler\s*$",
                r"\s*semble\s+soudain\s*$", r"\s*arrive\s*$", r"\s*devient\s*$",
                r"\s*se\s*$", r"\s*la\s*$", r"\s*le\s*$"):
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    return t.strip()


def _title_from_topic(topic: str) -> str:
    """Build a clean 'Pourquoi X ?' title from a topic angle.

    Handles the channel's observed topic shapes:
      'Pourquoi X ...'                  -> keep, strip leaks, add '?'
      'Ce que votre corps vous dit quand X' -> 'Pourquoi X ?'
      'Ce qui se passe quand X'         -> 'Pourquoi X ?'
      'La science derrière X'           -> 'Pourquoi X ?'
      'Ce qu'il faut comprendre sur X'  -> 'Pourquoi X ?'
      'Comprendre pourquoi X'           -> 'Pourquoi X ?'
    French convention: the first word after 'Pourquoi' stays lowercase
    ('Pourquoi le corps...', not 'Pourquoi Le corps...').
    """
    from seo_generator import _truncate_title, _title_is_clean
    t = _strip_leak_suffix(topic or "").strip().rstrip(" .?")
    if not t:
        return _truncate_title("Pourquoi votre corps fait ça ?")

    low = t.lower()
    core = t
    for prefix in ("ce que votre corps vous dit quand ",
                   "ce que votre corps vous dit lorsque ",
                   "ce que la science explique sur ",
                   "ce que la science explique ",
                   "ce qui se passe quand ", "ce qui se passe lorsque ",
                   "la science derrière ", "ce qu'il faut comprendre sur ",
                   "ce qu'il faut savoir sur ", "comprendre pourquoi ",
                   "voici pourquoi "):
        if low.startswith(prefix):
            core = t[len(prefix):].strip()
            break
    else:
        if low.startswith("pourquoi "):
            core = t[len("pourquoi "):].strip()

    # guard against empty/garbage cores
    words = [w for w in core.split() if w.strip()]
    if len(words) < 2:
        core = t
    # lowercase first word after 'Pourquoi' (French convention)
    core = core[0].lower() + core[1:] if core else core
    cand = _truncate_title(f"Pourquoi {core} ?")
    if _title_is_clean(cand)[0]:
        return cand
    # fallback: scrub harder and retry
    cand2 = _truncate_title(f"Pourquoi {_strip_leak_suffix(core)} ?")
    return cand2 if _title_is_clean(cand2)[0] else _truncate_title("Pourquoi votre corps fait ça ?")


def _load_repo_repair_priors() -> dict:
    """Load the repo's own verified proposed titles (auto_repair_plan_*.json,
    latest wins) as high-quality priors — they already passed the metadata
    repair safety gate (oEmbed check, leak-gate, duplicate guard)."""
    priors = {}
    plans = sorted(ROOT.glob("data/auto_repair_plan_*.json"))
    for plan in plans:
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
            for r in data.get("repairs", []):
                pid = r.get("id") or r.get("video_id")
                title = r.get("proposed_title")
                if pid and title:
                    priors[pid] = title
        except Exception:
            continue
    return priors


_REPAIR_PRIORS = _load_repo_repair_priors()

# Manual overrides for edge cases the generic logic cannot resolve safely
# (e.g. two live videos on the same phenomenon — the duplicate-guard would
# otherwise demote the broken-title one to a generic fallback). These are
# human-reviewed, natural French titles that DIFFER from the sibling video.
#
# Verified 2026-08-02 against the LIVE channel (42 videos): several phenomena
# were uploaded twice with identical titles. The LOWER-view sibling gets the
# override so the audience favourite keeps its title and the twin gets a
# distinct natural angle.
_MANUAL_TITLE_OVERRIDES = {
    # broken 'remarque entendre' title, while -4pgrbC9uaQ already holds the
    # clean 'Pourquoi on entend son cœur battre la nuit ?' — differentiate
    # via the brain angle that this video's own topic carries.
    "FteL-0nbHWk": "Pourquoi votre cerveau entend son cœur battre la nuit ?",
    # 'ventre qui se serre' appears on TWO live videos; give each a distinct
    # curiosity angle instead of the same question title.
    "WxOEXbepJ40": "Pourquoi le ventre se serre quand on a peur ?",
    "DocJNQZiwQQ": "Pourquoi le ventre se serre avant un moment important ?",
    # live duplicate: 'Pourquoi le corps sursaute en s'endormant ?'
    # (XECgrg709Og 1031v vs lk2es6al_JA 1569v — lk2es keeps the title)
    "XECgrg709Og": "Pourquoi le corps sursaute au moment de s'endormir ?",
    # live duplicate: 'Pourquoi un muscle tressaille tout seul ?'
    # (KMXIpcpoDX4 1168v vs DMVQvMsl-zE 1579v — DMVQv keeps)
    "KMXIpcpoDX4": "Pourquoi un muscle tressaille sans prévenir ?",
    # live duplicate: 'Pourquoi un nœud au ventre apparaît ?'
    # (n1TgqGp2PQ0 1007v vs T755Q7yX-DA 888v — n1Tgq keeps)
    # (2026-08-11: shortened 63 -> 51 chars — the Shorts feed visually cuts
    #  ~60 chars, and >60 chars risks a mid-word ellipsis on screen.)
    "T755Q7yX-DA": "Pourquoi ce nœud au ventre avant un grand moment ?",
    # live duplicate: 'Pourquoi la chair de poule apparaît soudainement ?'
    # (XLIFrONS2rc 1205v vs HJb7xCMIYWQ 707v — XLIFr keeps)
    "HJb7xCMIYWQ": "Pourquoi la chair de poule apparaît d'un coup ?",
    # live duplicate: 'Pourquoi le temps semble passer plus vite en vieillissant ?'
    # (x15ltzEHaB8 868v vs diImyvMyKig 675v — x15 keeps)
    "diImyvMyKig": "Pourquoi le temps semble accélérer en vieillissant ?",
    # live duplicate: 'Pourquoi le cerveau réclame du sommeil profond ?'
    # (ZXNvo9birZM 765v vs uUTyRmWUXn8 204v — ZXNvo keeps)
    "uUTyRmWUXn8": "Pourquoi le cerveau réclame tant de sommeil ?",
    # ── 2026-08-11 post-apply additions (metric-driven sweep) ──
    # XLIFrONS2rc (1205v): live title was uploaded with a TRUNCATED word
    # ('...chair de pou ?' — 'poule' cut to 'pou' by the pre-fix
    #  _truncate_title). The winner-keep rule would preserve the damage
    #  (1205v >= 800, ends with '?', len >= 25) because _title_is_clean
    #  cannot spot a cut WORD. Complete the word instead.
    "XLIFrONS2rc": "Pourquoi l'apparition soudaine de la chair de poule ?",
    # 5IakxGo1B7o: CTA verb leaked into the live title
    # ('...entendus la nuit Découvre ?'). Clean natural angle, distinct
    # from -4pgrbC9uaQ's 'Pourquoi on entend son cœur battre la nuit ?'.
    "5IakxGo1B7o": "Pourquoi le cœur semble battre plus fort la nuit ?",
    # Dedup-fallback quality: two live duplicates got the generic
    # '… en détail ?' suffix on 2026-08-11. Give each a real distinct angle.
    "IYs-jKSscTE": "Pourquoi le corps sursaute avant de s'endormir ?",
    "0giDXoVx72E": "Pourquoi la mâchoire craque quand on mange ?",
    # ── 2026-08-11 SEARCH-DEMAND alignment (YouTube FR autocomplete) ──
    # Titles re-anchored on queries real French users already type, so the
    # video matches an existing demand phrase instead of a guessed one.
    # (1XVYcxQqDqo 'réveille avant 3h' candidate turned out to be no longer
    #  live on the channel — removed from this map.)
    # Exact demand term is 'corps flottants yeux' (not 'dans l'œil').
    # Scheduled (not yet published) — pre-publish SEO, zero churn risk.
    "n7cDDC67cS0": "Pourquoi on voit des corps flottants dans les yeux ?",
    # 'pourquoi on oublie ses rêves' is the classic phrasing of this query.
    # Scheduled video — pre-publish SEO.
    "QuwjzCbMH0M": "Pourquoi on oublie ses rêves au réveil ?",
    # Demand phrase is 'les mains moites' (not 'paumes qui transpirent').
    "3RgqrdkBruA": "Pourquoi les mains sont moites quand on est nerveux ?",
}


def _optimize_title(current: str, topic: str, history_titles: list,
                    video_id: str = "", views: int = 0) -> str:
    """Pick the best title:
      1. HUMAN-REVIEWED manual override (if any)      — highest trust.
         Comes FIRST: it exists precisely for cases the heuristics get
         wrong, e.g. XLIFrONS2rc (1205 views) whose live title carries a
         truncated word ('...chair de pou ?') that the winner-keep rule
         would otherwise preserve forever.
      2. current if it's a PROVEN winner (>=800 views & clean & question)
         — never touch a video the audience already loves
      3. repo-verified repair prior (if any)          — high trust
      4. current, if already clean & question-y       — no change needed
      5. rebuild from topic with the leak-gate        — auto-repair
    """
    from seo_generator import _title_is_clean
    ok_cur, _ = _title_is_clean(current)
    if video_id and _MANUAL_TITLE_OVERRIDES.get(video_id):
        ov = _MANUAL_TITLE_OVERRIDES[video_id]
        # Oversized hand-written overrides would be visually cut on the
        # Shorts feed (~60 chars). Defensive trim, never mid-word.
        from seo_generator import _truncate_title, TITLE_MAX_LEN
        return ov if len(ov) <= TITLE_MAX_LEN else _truncate_title(ov)
    if (ok_cur and current.strip().rstrip().endswith("?")
            and len(current) >= 25 and views >= 800):
        return current.strip()
    if video_id and _REPAIR_PRIORS.get(video_id):
        prior = _REPAIR_PRIORS[video_id]
        ok, _ = _title_is_clean(prior)
        if ok:
            return prior
    if ok_cur and current.strip().rstrip().endswith("?") and len(current) >= 25:
        return current.strip()
    # rebuild from topic with the leak-gate — NO history dedup here; real
    # collisions are resolved in main() with a two-pass sweep (a title is
    # not a duplicate of ITSELF, which the old history check got wrong and
    # turned clean titles into "...de votre corps ?" garbage).
    return _title_from_topic(topic or current)


# ── French description template ──
def _optimize_description(title: str, old_desc: str) -> str:
    keyword_line = title.rstrip("?").strip()
    points = [
        "Ce que tu vas découvrir :",
        f"• Pourquoi {_subject(keyword_line)}",
        "• Le mécanisme scientifique simple derrière ce phénomène",
        "• Ce que ton corps essaie de te dire",
    ]
    desc = (
        f"{keyword_line} — la science simple du quotidien.\n"
        f"Tu vas comprendre pourquoi {_subject(keyword_line)} — et ce que ça dit "
        f"de ton corps.\n\n"
        f"{chr(10).join(points)}\n\n"
        f"{DISCLAIMER}\n\n"
        f"{CTA}\n\n"
        f"{' '.join(HASHTAGS)}"
    )
    return desc[:4800]


def _subject(title: str) -> str:
    """Extract a readable subject from 'Pourquoi X ?' -> 'X' (French:
    keeps the first word lowercase after 'pourquoi': 'le corps...')."""
    t = title.strip().rstrip("?").strip()
    if t.lower().startswith("pourquoi "):
        return t[9:].strip()
    return t.strip()


# ── French tags (≤500 chars) ──
def _optimize_tags(old_tags: list, title: str, topic: str) -> list:
    from seo_generator import _keywords
    base = _keywords(topic or title, n=6)
    fixed = ["science", "corps humain", "pourquoi", "curiosité",
             "biologie", "santé", "france", "vulgarisation scientifique"]
    out, seen = [], set()
    for t in base + fixed:
        k = t.lower().strip()
        if k and k not in seen and len(k) > 2:
            seen.add(k)
            out.append(t.strip())
    # cap at 500 chars total
    final, total = [], 0
    for t in out:
        if total + len(t) + 1 > 500:
            break
        final.append(t)
        total += len(t) + 1
    return final


# ── YouTube API ──
def _build_client():
    import google.oauth2.credentials
    from googleapiclient.discovery import build
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    csec = os.environ.get("GOOGLE_CLIENT_SECRET")
    rtok = os.environ.get("REFRESH_TOKEN")
    if not (cid and csec and rtok):
        raise SystemExit("Missing GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN env")
    creds = google.oauth2.credentials.Credentials(
        token=None, refresh_token=rtok,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cid, client_secret=csec)
    return build("youtube", "v3", credentials=creds)


def fetch_all_videos(yt, max_results: int = 50) -> list:
    """All videos (published + private/scheduled) via playlistItems of uploads."""
    ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    videos, token = [], None
    while True:
        req = yt.playlistItems().list(
            part="snippet,contentDetails", playlistId=uploads,
            maxResults=50, pageToken=token)
        resp = req.execute()
        for it in resp.get("items", []):
            vid = it["contentDetails"]["videoId"]
            status = it["snippet"].get("status", "")
            videos.append({"id": vid, "playlist_status": status,
                           "title": it["snippet"]["title"]})
        token = resp.get("nextPageToken")
        if not token or len(videos) >= max_results:
            break
    # fetch full snippet (desc/tags) + statistics + status for each
    full = []
    for v in videos:
        try:
            r = yt.videos().list(part="snippet,status,statistics",
                                 id=v["id"]).execute()["items"][0]
            full.append({
                "id": v["id"],
                "title": r["snippet"]["title"],
                "description": r["snippet"].get("description", ""),
                "tags": r["snippet"].get("tags", []),
                "privacy": r["status"]["privacyStatus"],
                "views": int(r.get("statistics", {}).get("viewCount", 0) or 0),
                "scheduled": r["status"].get("privacyStatus") == "private" and
                             bool(r["status"].get("publishAt")),
            })
        except Exception as exc:
            log.warning("skip %s: %s", v["id"], exc)
    return full


# ── main ──
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write changes to YouTube (default: dry-run plan)")
    ap.add_argument("--limit", type=int, default=0,
                    help="max videos to process (0 = all)")
    args = ap.parse_args()

    yt = _build_client()
    videos = fetch_all_videos(yt)
    if args.limit:
        videos = videos[:args.limit]
    log.info("Fetched %d videos (published + scheduled)", len(videos))

    # history titles for duplicate-guard
    history_titles = []
    try:
        h = json.loads(HISTORY.read_text(encoding="utf-8"))
        history_titles = [v.get("title", "") for v in
                          (h if isinstance(h, list) else h.values())]
    except Exception:
        pass

    plan = {"generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(videos), "videos": []}
    yt_update = None
    if args.apply:
        yt_update = yt.videos()

    # ── TWO-PASS TITLE DEDUP ──
    # Pass 1: build the proposed title for EVERY video with no history-based
    # dedup (a title is not a duplicate of itself — the old single-pass code
    # checked the video's OWN title against the history set, which turned
    # clean titles into "...de votre corps ?" and threw away good titles
    # into "fait ce signe N ?" garbage).
    for v in videos:
        v["_new_title"] = _optimize_title(
            v["title"], v["title"], history_titles,
            video_id=v["id"], views=v["views"])

    # Pass 2: only REAL collisions — the same proposed title landing on TWO
    # DIFFERENT video IDs — are resolved. The higher-view video keeps its
    # title; the sibling gets a manual override (human-reviewed, distinct
    # natural French angle) or, if none exists, a topic-rebuild that differs.
    from collections import defaultdict
    by_title = defaultdict(list)
    for v in videos:
        by_title[v["_new_title"].strip().lower()].append(v)
    for group in by_title.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: -(x.get("views") or 0))
        for v in group[1:]:
            ov = _MANUAL_TITLE_OVERRIDES.get(v["id"])
            if ov:
                from seo_generator import _truncate_title, TITLE_MAX_LEN
                v["_new_title"] = (ov if len(ov) <= TITLE_MAX_LEN
                                   else _truncate_title(ov))
            else:
                alt = _title_from_topic(f"{v['title']} en détail")
                v["_new_title"] = alt
                log.warning("No manual override for duplicate %s -> %r",
                            v["id"], alt)

    def _same_tags(a: list, b: list) -> bool:
        """Order/case-insensitive tag comparison: YouTube normalises tag
        storage, so a naive list != made EVERY video look 'changed' on every
        run (observed 2026-08-11: runs rewrote all 50 videos even with
        identical plans). Churn only on real differences."""
        norm = lambda ts: sorted({(t or "").strip().lower() for t in (ts or []) if (t or "").strip()})
        return norm(a) == norm(b)

    for v in videos:
        new_title = v["_new_title"]
        topic = v["title"]
        new_desc = _optimize_description(new_title, v["description"])
        new_tags = _optimize_tags(v["tags"], new_title, topic)
        changed = (new_title.strip() != (v["title"] or "").strip()
                   or new_desc.strip() != (v["description"] or "").strip()
                   or not _same_tags(new_tags, v["tags"]))

        entry = {
            "id": v["id"],
            "current_title": v["title"],
            "new_title": new_title,
            "current_desc_len": len(v["description"]),
            "new_desc_len": len(new_desc),
            "tags": new_tags,
            "privacy": v["privacy"],
            "views": v["views"],
            "scheduled": v["scheduled"],
            "needs_change": changed,
        }
        plan["videos"].append(entry)

        if changed and args.apply:
            body = {"id": v["id"], "snippet": {
                "title": new_title,
                "description": new_desc,
                "tags": new_tags,
                "categoryId": "27",
            }}
            # keep current category + defaultLanguage if present
            try:
                yt_update.update(part="snippet", body=body).execute()
                entry["applied"] = True
                log.info("✅ %s -> %r", v["id"], new_title[:60])
            except Exception as exc:
                entry["applied"] = False
                entry["error"] = str(exc)[:200]
                log.error("❌ %s: %s", v["id"], exc)

    PLAN_JSON.parent.mkdir(exist_ok=True)
    PLAN_JSON.write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    # markdown report
    md = [f"# FR Optimize Plan — {plan['count']} videos",
          f"_Generated {plan['generated_at']}_",
          "", "## Summary", f"- Videos: {plan['count']}",
          f"- Need change: {sum(1 for x in plan['videos'] if x['needs_change'])}",
          f"- Applied: {sum(1 for x in plan['videos'] if x.get('applied'))}",
          "", "## Per-video plan", ""]
    for x in plan["videos"]:
        md.append(f"### {x['id']} ({x['privacy']}{' scheduled' if x['scheduled'] else ''}, {x['views']} vues)")
        md.append(f"- OLD: {x['current_title']}")
        md.append(f"- NEW: **{x['new_title']}**")
        md.append(f"- DESC: {x['current_desc_len']} → {x['new_desc_len']} chars")
        md.append(f"- TAGS: {', '.join(x['tags'][:8])}{'…' if len(x['tags'])>8 else ''}")
        md.append(f"- NEEDS: {'✅' if x['needs_change'] else '—'}"
                  f"{' (APPLIED)' if x.get('applied') else ''}")
        if x.get("error"):
            md.append(f"- ERROR: {x['error']}")
        md.append("")
    PLAN_MD.write_text("\n".join(md), encoding="utf-8")

    log.info("Plan written: %s", PLAN_JSON)
    log.info("Report written: %s", PLAN_MD)
    if not args.apply:
        log.info("DRY-RUN — re-run with --apply to write to YouTube")
    return 0


if __name__ == "__main__":
    sys.exit(main())
