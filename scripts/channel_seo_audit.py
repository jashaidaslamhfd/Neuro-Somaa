#!/usr/bin/env python3
"""Channel SEO audit + repair for SKILLOR (France-first Shorts).

Answers the two questions every channel owner asks:
  1. "Why do some videos get views and others don't?"
  2. "Fix the SEO of the videos I already uploaded."

This tool works in TWO modes:

  * OFFLINE (default, no secrets needed): analyses the channel data already
    committed in data/ (video_history.json + the latest seo_diag_*.json) and
    writes a human-readable markdown report. You get the diagnosis for free.

  * LIVE (needs YouTube OAuth): re-pulls fresh statistics from the YouTube
    Data API, and with --apply rewrites weak/truncated titles, fills tags and
    re-saves the snippet (defaultLanguage=fr) directly on your videos.
    Requires GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / REFRESH_TOKEN env vars.
    Improved titles are generated with the production Groq model when
    GROQ_API_KEY is set (optional — otherwise the topic is cleaned locally).

Run:
    python scripts/channel_seo_audit.py                 # offline report
    python scripts/channel_seo_audit.py --live          # fresh stats, dry-run
    python scripts/channel_seo_audit.py --live --apply  # rewrite SEO on YT

Everything YouTube-mutating is dry by default. Nothing is ever published or
deleted here; only video *metadata* (title/description/tags) is ever changed,
and only with --apply.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, date, datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seo-audit")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "data")
TODAY = datetime.now(UTC).date()

# A video younger than this has not had time to accrue views, so it is excluded
# from the "which pattern performs" correlation (it would just add noise / 0s).
MIN_AGE_DAYS_FOR_STATS = 4

# --------------------------------------------------------------------------- #
# Title-quality heuristics (channel-specific, learned from video_history.json)
# --------------------------------------------------------------------------- #
# Trailing fragments the old broken engine leaked into published titles.
LEAKED_FRAGMENTS = (
    "peut sembler", "semble étrange", "semble etrangement",
    "peut paraître", "peut paraitre", "semble familier",
)
# Trailing connectives / articles that mean a title was cut mid-thought.
TRUNCATION_TAILS = re.compile(
    r"\b(de|du|la|le|les|un|une|des|se|ne|ce|que|qui|pour|sur|dans|avec|son|sa|ses|mon|ma|mes|ton|ta|tes)$",
    re.IGNORECASE,
)

# Opener archetypes seen on this channel. Order matters: first match wins.
OPENER_RULES = [
    ("pourquoi-question",      re.compile(r"^pourquoi\b.+\?\s*$", re.IGNORECASE)),
    ("pourquoi-declarative",   re.compile(r"^pourquoi\b", re.IGNORECASE)),
    ("comprendre-pourquoi",    re.compile(r"^comprendre\b", re.IGNORECASE)),
    ("ce-qu-il-faut",          re.compile(r"^ce qu'?il faut comprendre", re.IGNORECASE)),
    ("ce-que-corps-dit",       re.compile(r"^ce que (votre |ton |le )?corps (vous )?dit", re.IGNORECASE)),
    ("ce-qui-se-passe",        re.compile(r"^ce qui (se passe|change|arrive)", re.IGNORECASE)),
    ("la-science",             re.compile(r"^(la science|ce que la science)", re.IGNORECASE)),
    ("short-fragment",         re.compile(r"^[\wàâäçéèêëîïôöùûüÿœæ]{1,12}$", re.IGNORECASE)),
]


def classify_opener(title: str) -> str:
    t = title.strip()
    for name, rx in OPENER_RULES:
        if rx.search(t):
            return name
    return "other"


def analyze_title(title: str) -> list[str]:
    """Return SEO issues found in a single title (empty list = clean)."""
    issues: list[str] = []
    t = (title or "").strip()
    if not t:
        return ["empty title"]
    low = t.lower()
    # Length: YouTube shows ~50-60 chars before truncating in feed/Shorts shelf.
    if len(t) < 12:
        issues.append(f"very short ({len(t)} chars) — gives viewers no specific hook")
    if len(t) > 70:
        issues.append(f"long ({len(t)} chars) — may truncate in the Shorts shelf")
    # Leaked engine fragments.
    for frag in LEAKED_FRAGMENTS:
        if low.endswith(frag) or f" {frag} " in low:
            issues.append(f"leaked template fragment « {frag} » — looks unfinished")
            break
    # Truncated mid-thought: inspect the last WORD, ignoring trailing punctuation
    # (so "...battre la ?" is still caught — the "?" used to hide the truncation).
    words = t.split()
    last_word = re.sub(r"[?!.\",;:…]+$", "", words[-1]) if words else ""
    if len(words) >= 3 and last_word and TRUNCATION_TAILS.search(last_word):
        issues.append("ends on a connector/article — likely truncated")
    # Question mark is good for curiosity ONLY with "Pourquoi"; otherwise weak.
    if t.endswith("?") and not low.startswith("pourquoi"):
        issues.append("question without 'Pourquoi' — weaker curiosity frame")
    # Weak declarative openers that bury the hook.
    if re.match(r"^(comprendre|voici|voilà|découvrez|sachez)\b", low):
        issues.append("weak declarative opener — 'Pourquoi…?' raises more curiosity")
    return issues


def title_seo_score(title: str) -> int:
    """0-100 proxy: starts at 100, deducted per issue (floor 0)."""
    score = 100
    for _ in analyze_title(title):
        score -= 20
    # reward the channel's proven curiosity openers
    opener = classify_opener(title)
    if opener in {"pourquoi-question", "ce-qu-il-faut", "ce-que-corps-dit"}:
        score = min(100, score + 10)
    if opener == "comprendre-pourquoi":
        score -= 15
    return max(0, score)


# --------------------------------------------------------------------------- #
# Data loading (offline)
# --------------------------------------------------------------------------- #
def _load_history() -> list[dict]:
    path = os.path.join(DATA, "video_history.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else list(data.values())


def _posted_date(v: dict):
    raw = v.get("posted_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)).date()
    except ValueError:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(raw))
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        return None


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def analyze_videos(videos: list[dict]) -> list[dict]:
    out = []
    for v in videos:
        title = v.get("title", "") or ""
        d = _posted_date(v)
        age_days = (TODAY - d).days if d else None
        views = int(v.get("views") or 0)
        retention = v.get("average_view_percentage")
        out.append({
            "id": v.get("youtube_video_id", ""),
            "title": title,
            "topic": v.get("topic", ""),
            "views": views,
            "opener": classify_opener(title),
            "retention_pct": round(retention * 100, 1) if isinstance(retention, (int, float)) else None,
            "avd_sec": v.get("average_view_duration_sec"),
            "hook_score": v.get("hook_score"),
            "posted": d.isoformat() if d else None,
            "age_days": age_days,
            "too_new": (age_days is not None and age_days < MIN_AGE_DAYS_FOR_STATS),
            "title_issues": analyze_title(title),
            "title_seo_score": title_seo_score(title),
        })
    return out


def opener_performance(rows: list[dict]) -> list[tuple[str, float, int]]:
    """Average views per opener archetype, excluding too-new videos."""
    groups: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r["too_new"] or r["age_days"] is None:
            continue
        groups[r["opener"]].append(r["views"])
    ranked = [
        (opener, round(sum(v) / len(v)), len(v))
        for opener, v in groups.items() if v
    ]
    return sorted(ranked, key=lambda x: x[1], reverse=True)


def build_report(rows: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# SKILLOR — Channel SEO Audit\n")
    lines.append(f"_Generated {TODAY.isoformat()} (offline, from `data/`)_\n")

    mature = [r for r in rows if not r["too_new"] and r["age_days"] is not None]
    fresh = [r for r in rows if r["too_new"]]
    total_views = sum(r["views"] for r in mature)

    lines.append("## TL;DR\n")
    lines.append(
        f"- {len(rows)} videos on record. {len(mature)} are ≥{MIN_AGE_DAYS_FOR_STATS}d old "
        f"(used for performance stats), {len(fresh)} are too new to judge.\n"
    )
    if mature:
        avg = round(total_views / len(mature))
        lines.append(f"- Mature-video average: **{avg} views** (total {total_views}).\n")
    retain = [r for r in mature if r["retention_pct"] is not None]
    if retain:
        lines.append(
            f"- Average view 'percentage' (loop factor) is high across the board "
            f"({min(r['retention_pct'] for r in retain):.0f}% to {max(r['retention_pct'] for r in retain):.0f}%) "
            f"— viewers **loop** these Shorts. Content/retention is healthy; the lever is "
            f"**CTR = title + thumbnail**.\n"
        )

    # Which opener pattern performs best
    lines.append("\n## Which title pattern gets views?\n")
    lines.append("(mature videos only — new uploads excluded so 0-view noise doesn't skew it)\n")
    lines.append("| Opener pattern | Avg views | # videos |")
    lines.append("|---|---:|---:|")
    for opener, avg, n in opener_performance(rows):
        lines.append(f"| `{opener}` | {avg} | {n} |")
    lines.append("")

    # Per-video SEO issues, worst first
    lines.append("\n## SEO issues to fix (worst titles first)\n")
    flagged = sorted([r for r in rows if r["title_issues"]], key=lambda r: r["title_seo_score"])
    if not flagged:
        lines.append("_No title issues detected._\n")
    else:
        lines.append("| Video | Views | Title score | Issue(s) |")
        lines.append("|---|---:|---:|---|")
        for r in flagged:
            url = f"https://youtu.be/{r['id']}" if r["id"] else ""
            age = " (new)" if r["too_new"] else ""
            lines.append(
                f"| [{r['title'][:48]}]({url}){age} | {r['views']} | "
                f"{r['title_seo_score']} | {' · '.join(r['title_issues'])} |"
            )
        lines.append("")

    # New videos need attention
    if fresh:
        lines.append("\n## ⚠️ New uploads (0 views, <4 days old)\n")
        lines.append("These are NOT failures yet — Shorts need a few days. But their title/SEO "
                     "matters MOST right now, so review the issues above and fix before the "
                     "algorithm decides their fate.\n")
        for r in fresh:
            lines.append(f"- `{r['title']}` — opener `{r['opener']}`")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# LIVE YouTube mode
# --------------------------------------------------------------------------- #
def _oauth_token() -> str:
    missing = [k for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REFRESH_TOKEN")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"LIVE mode needs env vars: {missing}. Set them in .env or GitHub Secrets.")
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data), timeout=30,
    ) as r:
        return json.load(r)["access_token"]


def _req(token: str, url: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read().decode("utf-8", "replace")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        log.error("YouTube API %s %s: %s", method, url, e.read().decode("utf-8", "replace")[:300])
        raise


def list_my_video_ids(token: str) -> list[str]:
    """All video IDs owned by the channel, via the uploads playlist."""
    ch = _req(token, "https://www.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true")
    items = ch.get("items") or []
    if not items:
        return []
    uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while True:
        url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=contentDetails&maxResults=50&playlistId={uploads_playlist}"
        if page:
            url += f"&pageToken={page}"
        res = _req(token, url)
        for it in res.get("items", []):
            vid = it.get("contentDetails", {}).get("videoId")
            if vid:
                ids.append(vid)
        page = res.get("nextPageToken")
        if not page:
            break
        time.sleep(0.3)
    return ids


def fetch_video_details(token: str, ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 50):
        batch = ",".join(ids[i:i + 50])
        res = _req(token,
                   "https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics,contentDetails&id=" + batch)
        out.extend(res.get("items", []))
        time.sleep(0.3)
    return out


def _groq_client():
    try:
        from groq import Groq  # type: ignore
    except ImportError:
        return None
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    return Groq(api_key=key)


def propose_title(client, topic: str, current: str) -> str | None:
    """Generate one clean French curiosity title. Needs GROQ_API_KEY."""
    if client is None:
        return None
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    prompt = (
        "Tu écris des titres de YouTube Shorts en français de France (science du corps/cerveau). "
        "Un seul titre, 5 à 9 mots, qui ouvre une boucle de curiosité avec « Pourquoi ». "
        "Pas de clickbait, pas de promesse médicale. Réponds uniquement avec le titre, sans guillemets.\n"
        f"Sujet : {topic}\nTitre actuel (souvent cassé/tronqué) : {current}"
    )
    try:
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}],
            temperature=0.7, max_tokens=60,
        )
        title = (resp.choices[0].message.content or "").strip().strip('"').strip("«» ")
        # guardrail: never ship something longer than YT comfortably shows
        return title if title and len(title) <= 90 else None
    except Exception as exc:
        log.warning("title generation failed for %r: %s", topic, exc)
        return None


# --------------------------------------------------------------------------- #
# SEO REPAIR PACKAGE (title + description + tags) + THUMBNAIL regeneration
# --------------------------------------------------------------------------- #
SEO_GEN = None


def _seo_generator():
    """Lazy import of src/seo_generator.py — it only needs stdlib (random, re),
    so importing it does NOT pull torch/moviepy and stays offline-safe."""
    global SEO_GEN
    if SEO_GEN is None:
        sys.path.insert(0, os.path.join(ROOT, "src"))
        import seo_generator as _sg
        SEO_GEN = _sg
    return SEO_GEN


def clean_topic(topic: str) -> str:
    """Strip leaked engine fragments and trailing truncated connectors from a
    topic, so the cleaned topic feeds BOTH the title and the description/tags
    (otherwise 'peut sembler étrange' leaks into the description too)."""
    t = (topic or "").strip()
    for frag in LEAKED_FRAGMENTS:
        t = re.sub(re.escape(frag) + r"[^.?!]*", "", t, flags=re.IGNORECASE)
    t = re.sub(
        r"\s+(de|du|la|le|les|un|une|des|se|ne|ce|que|qui|pour|sur|dans|avec)$",
        "", t, flags=re.IGNORECASE,
    )
    return t.strip(" .,") or (topic or "").strip()


def clean_title_from_topic(topic: str) -> str:
    """Deterministically turn a (often broken) topic into a clean curiosity title.

    Strips weak prefixes ('Comprendre pourquoi', 'Ce qu'il faut comprendre sur',
    ...), removes leaked engine fragments, and ends a 'Pourquoi' title with '?'.
    Used as a no-API fallback when Groq is not configured and seo_generator's
    own output still carries issues.
    """
    t = clean_topic(topic)
    t = re.sub(r"^comprendre\s+pourquoi\s+", "pourquoi ", t, flags=re.IGNORECASE)
    t = re.sub(r"^comprendre\s+", "pourquoi ", t, flags=re.IGNORECASE)
    t = re.sub(r"^ce qu'?il faut comprendre sur\s+", "pourquoi ", t, flags=re.IGNORECASE)
    t = re.sub(r"^ce que (votre |ton |le )?corps (vous )?dit quand\s+", "pourquoi ", t, flags=re.IGNORECASE)
    t = re.sub(r"^ce que la science explique sur\s+", "pourquoi ", t, flags=re.IGNORECASE)
    t = re.sub(r"^ce qui se passe quand\s+", "pourquoi ", t, flags=re.IGNORECASE)
    t = t.strip(" .,")
    if t:
        t = t[0].upper() + t[1:]
    if re.match(r"^pourquoi\b", t, re.IGNORECASE) and not t.endswith("?"):
        t = t.rstrip(" .") + " ?"
    return t


def build_repair_package(row: dict, groq_client) -> dict:
    """Produce improved title + description + tags + thumbnail_text.

    Uses the production deterministic seo_generator; the title is optionally
    refined with Groq when GROQ_API_KEY is set. Never regresses to a title that
    still carries the same issues we are trying to fix.
    """
    sg = _seo_generator()
    # Clean the topic ONCE so leaked fragments / weak prefixes don't reach the
    # title, the description AND the tags through seo_generator.
    topic = clean_topic(row.get("topic") or row.get("title") or "")
    script_data = {
        "title": row.get("title", ""),
        "series_title": row.get("title", ""),
        "hook": topic,
        "description": topic,
        "cta": "Abonne-toi pour plus de science simple.",
    }
    pkg = sg.generate_seo_package(topic, script_data)
    chosen = pkg.get("chosen_title") or pkg.get("title") or row.get("title", "")
    # Groq can make a cleaner curiosity title if a key is configured.
    chosen = propose_title(groq_client, topic, chosen) or chosen
    # Guardrail: never ship a title that STILL has issues. Prefer, in order:
    #   1. the first clean option seo_generator produced,
    #   2. a deterministic cleanup of the topic (no API needed).
    if analyze_title(chosen):
        clean_opt = next((opt for opt in pkg.get("title_options", []) if not analyze_title(opt)), None)
        if clean_opt:
            chosen = clean_opt
        else:
            cleaned = clean_title_from_topic(topic)
            if cleaned:
                chosen = cleaned
    return {
        "title": chosen,
        "description": pkg.get("description", ""),
        "tags": pkg.get("tags", []),
        "thumbnail_text": pkg.get("thumbnail_text") or chosen.upper()[:35],
    }


THUMB_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
THUMBS_DIR = os.path.join(ROOT, "assets", "thumbnails_fr")
OUT_THUMBS = os.path.join(ROOT, "output", "thumbnails_repaired")


def regenerate_thumbnail(video_id: str, thumbnail_text: str) -> str | None:
    """Overlay clean high-contrast text on the EXISTING thumbnail image.

    Reuses the channel's proven look (dark bottom gradient + big bold yellow
    text) but runs on Pillow only — no moviepy — so it works offline. Returns
    the new path, or None if there is no base image to improve.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        log.warning("Pillow not installed — skipping thumbnail regeneration")
        return None
    base = os.path.join(THUMBS_DIR, f"{video_id}.jpg")
    if not os.path.exists(base):
        log.info("no existing thumbnail for %s — skipping (need a base image)", video_id)
        return None
    os.makedirs(OUT_THUMBS, exist_ok=True)
    img = Image.open(base).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    # Bottom gradient strip for legibility.
    strip_h = int(h * 0.42)
    for y in range(h - strip_h, h):
        alpha = int(255 * (y - (h - strip_h)) / strip_h * 0.82)
        draw.rectangle([0, y, w, y + 1], fill=(0, 0, 0, alpha))
    # Word-wrap the thumbnail text into up to 4 centred lines.
    font_size = int(w * 0.11)
    font = ImageFont.truetype(THUMB_FONT, font_size) if os.path.exists(THUMB_FONT) else ImageFont.load_default()
    words = thumbnail_text.upper().strip().split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= w * 0.9:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    lines = lines[:4]
    line_h = font_size + int(font_size * 0.35)
    y = h - line_h * len(lines) - int(h * 0.05)
    for ln in lines:
        x = (w - draw.textlength(ln, font=font)) / 2
        for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            draw.text((x + dx, y + dy), ln, font=font, fill=(0, 0, 0, 230))
        draw.text((x, y), ln, font=font, fill=(255, 235, 80))
        y += line_h
    out = os.path.join(OUT_THUMBS, f"{video_id}.jpg")
    img.save(out, "JPEG", quality=92)
    return out


def build_repair_plan(rows: list[dict], generate_thumbs: bool) -> dict:
    """Generate the full SEO repair package for the given rows (offline-safe)."""
    client = _groq_client()
    plan: dict = {"generated": TODAY.isoformat(), "repairs": []}
    for r in rows:
        if not r["id"]:
            continue
        pkg = build_repair_package(r, client)
        thumb = regenerate_thumbnail(r["id"], pkg["thumbnail_text"]) if generate_thumbs else None
        plan["repairs"].append({
            "id": r["id"],
            "views": r["views"],
            "current_title": r["title"],
            "topic": r["topic"],
            **pkg,
            "issues": r["title_issues"],
            "new_thumbnail": thumb,
            "has_base_thumbnail": os.path.exists(os.path.join(THUMBS_DIR, f"{r['id']}.jpg")),
        })
        log.info("planned repair %s: %r -> %r", r["id"], r["title"], pkg["title"])
    return plan


def build_repair_preview(plan: dict) -> str:
    """Human-readable old -> new preview of the repair plan."""
    lines: list[str] = ["# SKILLOR — SEO Repair Plan\n", f"_Generated {plan.get('generated')}_\n"]
    for it in plan.get("repairs", []):
        lines.append(f"## [{it['current_title'][:50]}](https://youtu.be/{it['id']})  ({it['views']} views)\n")
        if it["issues"]:
            lines.append(f"_{', '.join(it['issues'])}_\n")
        lines.append(f"**New title:** {it['title']}\n")
        lines.append("**Description:**\n```\n" + it["description"][:400] + "\n```\n")
        lines.append(f"**Tags ({len(it['tags'])}):** {', '.join(it['tags'])}\n")
        if it.get("new_thumbnail"):
            lines.append(f"**New thumbnail:** `{it['new_thumbnail']}`\n")
        elif it.get("has_base_thumbnail"):
            lines.append("**Thumbnail:** base found — add `--with-thumbnails` to regenerate\n")
        else:
            lines.append("**Thumbnail:** no base image available — skipped\n")
        lines.append("---\n")
    return "\n".join(lines)


def _set_thumbnail(token: str, vid: str, image_path: str, apply: bool) -> bool:
    """Upload a new custom thumbnail via thumbnails.set. Requires the channel
    to be verified for custom thumbnails; failure is logged, not fatal."""
    if not apply:
        log.info("  [dry] would set new thumbnail for %s", vid)
        return False
    try:
        with open(image_path, "rb") as fh:
            data = fh.read()
        req = urllib.request.Request(
            f"https://www.googleapis.com/youtube/v3/thumbnails/set?videoId={vid}",
            data=data, method="POST",
        )
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "image/jpeg")
        with urllib.request.urlopen(req, timeout=60) as r:
            json.loads(r.read().decode("utf-8", "replace"))
        log.info("  thumbnail updated for %s", vid)
        return True
    except urllib.error.HTTPError as e:
        log.warning(
            "  thumbnail set failed for %s (channel must be verified for custom "
            "thumbnails): %s", vid, e.read().decode("utf-8", "replace")[:200],
        )
        return False
    except Exception as exc:
        log.warning("  thumbnail set failed for %s: %s", vid, exc)
        return False


def apply_repair_plan(token: str, plan: dict, apply: bool, with_thumbnails: bool) -> None:
    """Push title/description/tags (and optionally thumbnail) to YouTube."""
    updated = thumbs = 0
    for item in plan.get("repairs", []):
        vid = item["id"]
        cur = _req(token, f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={vid}")
        items = cur.get("items") or []
        if not items:
            continue
        sn = items[0]["snippet"]
        new_title = item["title"] or sn.get("title", "")
        log.info("UPDATE %s\n  title: %r -> %r", vid, sn.get("title", ""), new_title)
        if not apply:
            continue
        payload = {"id": vid, "snippet": {
            "title": new_title,
            "description": item["description"] or sn.get("description", ""),
            "categoryId": sn.get("categoryId", "27"),
            "tags": item["tags"] or sn.get("tags", []),
            "defaultLanguage": "fr",
            **({"defaultAudioLanguage": sn["defaultAudioLanguage"]}
               if sn.get("defaultAudioLanguage") else {}),
        }}
        _req(token, "https://www.googleapis.com/youtube/v3/videos?part=snippet", "PUT", payload)
        updated += 1
        time.sleep(0.5)
        if with_thumbnails and item.get("new_thumbnail") and os.path.exists(item["new_thumbnail"]):
            if _set_thumbnail(token, vid, item["new_thumbnail"], apply):
                thumbs += 1
            time.sleep(0.5)
    log.info(
        "Applied: %d snippet(s) %s, %d thumbnail(s) %s.",
        updated, "updated" if apply else "planned",
        thumbs, "updated" if apply else "planned",
    )


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="pull fresh stats from YouTube (needs OAuth)")
    ap.add_argument("--apply", action="store_true", help="(with --live) actually rewrite SEO on YouTube")
    ap.add_argument("--plan", action="store_true",
                    help="generate an offline SEO repair plan (title/description/tags/thumbnail) for review")
    ap.add_argument("--with-thumbnails", action="store_true",
                    help="(with --plan or --apply) regenerate and replace thumbnails too")
    ap.add_argument("--all", action="store_true",
                    help="repair ALL videos, not just the ones flagged with title issues")
    ap.add_argument("--out", default=os.path.join(DATA, f"channel_seo_audit_{TODAY.strftime('%Y%m%d')}.md"))
    args = ap.parse_args()

    if args.live:
        log.info("LIVE mode: refreshing channel stats from YouTube…")
        token = _oauth_token()
        ids = list_my_video_ids(token)
        log.info("Found %d videos on the channel.", len(ids))
        details = fetch_video_details(token, ids)
        # merge live snippet/stats into the history-shaped rows the analyser expects
        videos = []
        for it in details:
            sn = it.get("snippet", {})
            st = it.get("statistics", {})
            videos.append({
                "youtube_video_id": it.get("id"),
                "title": sn.get("title", ""),
                "topic": sn.get("description", "").split("\n")[0][:80],
                "views": int(st.get("viewCount", 0)),
                "posted_at": sn.get("publishedAt"),
                "average_view_percentage": None,
                "average_view_duration_sec": None,
                "hook_score": None,
            })
        rows = analyze_videos(videos)
    else:
        log.info("OFFLINE mode: analysing data/video_history.json (no secrets needed).")
        rows = analyze_videos(_load_history())

    report = build_report(rows)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(report)
    log.info("Report written to %s", args.out)

    # ---- SEO repair: build a plan whenever asked, apply only in live+apply ----
    plan: dict | None = None
    if args.plan or args.live:
        repair_rows = rows if args.all else [r for r in rows if r["title_issues"]]
        plan = build_repair_plan(repair_rows, generate_thumbs=bool(args.plan or args.with_thumbnails))
        plan_path = os.path.join(DATA, f"seo_repair_plan_{TODAY.strftime('%Y%m%d')}.json")
        with open(plan_path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, ensure_ascii=False, indent=2)
        md_path = os.path.join(DATA, f"seo_repair_preview_{TODAY.strftime('%Y%m%d')}.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(build_repair_preview(plan))
        log.info("Repair plan: %d video(s) -> %s", len(plan["repairs"]), plan_path)
        log.info("Human-readable preview -> %s", md_path)

    if args.live and args.apply and plan:
        apply_repair_plan(_oauth_token(), plan, apply=True, with_thumbnails=args.with_thumbnails)

    print("\n" + report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
