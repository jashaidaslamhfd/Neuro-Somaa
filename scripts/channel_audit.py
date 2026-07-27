#!/usr/bin/env python3
"""One-shot CHANNEL-level audit + branding repair for SKILLOR FR.

Checks the things the YouTube algorithm looks at ABOVE single videos:
- channel description (niche clarity + keywords)
- channel keywords field
- defaultLanguage (fr for a French channel)
- avatar / banner / video-watermark presence (read-only — API can't set images)

Mode A (default) = READ audit only.
Mode B (--apply) = writes optimized branding via channels.update.
"""
import argparse
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger("channel_audit")

NEW_DESCRIPTION = (
    "SKILLOR — la science de votre corps expliquée simplement.\n\n"
    "Chaque jour, 3 nouveaux Shorts sur les phénomènes étranges du corps humain :\n"
    "pourquoi vos genoux craquent, pourquoi le temps semble accélérer en vieillissant, "
    "ce que le stress fait à votre cerveau, pourquoi vous entendez votre cœur battre la nuit.\n\n"
    "Science amusante, réponses claires, zéro jargon médical — tout vérifié.\n"
    "Abonnez-vous pour ne jamais rater un fait étonnant. 🧠⚡"
)

NEW_KEYWORDS = (
    'science shorts "corps humain" pourquoi cerveau '
    '"expliqué simplement" "faits étonnants" phénomènes curiosité '
    '"science amusante" santé "culture générale" français'
)


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


def _api(path, token, *, method="GET", body=None):
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
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')[:300]}") from e


def audit(item):
    ch = item["snippet"]
    bs = item.get("brandingSettings", {})
    chs = bs.get("channel", {})
    img = bs.get("image", {})
    stats = item.get("statistics", {})
    print("================ CHANNEL AUDIT ================")
    print(f"Title:           {ch.get('title')}")
    print(f"Handle:          {ch.get('customUrl')}")
    print(f"Subscribers:     {stats.get('subscriberCount')} | Views: {stats.get('viewCount')} | Videos: {stats.get('videoCount')}")
    print(f"defaultLanguage: {chs.get('defaultLanguage')!r}")
    print(f"country:         {chs.get('country')!r}")
    print(f"keywords:        {chs.get('keywords')!r}")
    print(f"description len: {len(chs.get('description') or '')}")
    print(f"--- description ---\n{chs.get('description') or '(EMPTY)'}")
    print(f"avatar set:      {'YES' if (ch.get('thumbnails') or {}).get('medium') else 'NO'}")
    print(f"banner set:      {'YES' if img.get('bannerExternalUrl') else 'NO'}  ({(img.get('bannerExternalUrl') or '')[:60]})")
    print(f"watermark set:   {'YES' if img.get('watchIconImageUrl') else 'NO'}")
    print("===============================================")
    issues = []
    if not (chs.get("defaultLanguage") or "").lower().startswith("fr"):
        issues.append("defaultLanguage is not French")
    desc = chs.get("description") or ""
    if len(desc) < 200 or "corps" not in desc.lower():
        issues.append("channel description thin / missing niche keywords")
    if len(chs.get("keywords") or "") < 40:
        issues.append("channel keywords field empty/thin")
    if not img.get("bannerExternalUrl"):
        issues.append("NO channel banner (art) — must be set in YouTube Studio app")
    return issues


def geo_report(token, days=90):
    """Audience geography from YouTube Analytics API (needs yt-analytics.readonly)."""
    import datetime
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    path = ("https://youtubeanalytics.googleapis.com/v2/reports"
            f"?ids=channel==MINE&startDate={start}&endDate={end}"
            "&metrics=views,estimatedMinutesWatched,subscribersGained"
            "&dimensions=country&sort=-views&maxResults=10")
    import urllib.error
    import urllib.request
    req = urllib.request.Request(path)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"GEO: analytics query blocked ({e.code}) — {e.read().decode(errors='replace')[:200]}")
        return
    rows = res.get("rows") or []
    total = sum(r[1] for r in rows) or 1
    print(f"================ AUDIENCE GEOGRAPHY (last {days}d) ================")
    for r in rows:
        print(f"  {r[0]:4} | {r[1]:>7} views ({100*r[1]/total:4.1f}%) | {r[2]:>7} min | +{r[3]} subs")
    print("=================================================================")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    token = _access_token()
    res = _api("channels?part=snippet,brandingSettings,statistics&mine=true", token)
    item = res["items"][0]
    issues = audit(item)
    print("ISSUES FOUND:", len(issues))
    for i in issues:
        print(" -", i)
    geo_report(token)

    if args.apply:
        cid = item["id"]
        body = {"id": cid, "brandingSettings": {"channel": {
            "description": NEW_DESCRIPTION,
            "keywords": NEW_KEYWORDS,
            "defaultLanguage": "fr",
            "country": "FR",
        }}}
        try:
            _api("channels?part=brandingSettings", token, method="PUT", body=body)
            print("APPLY: branding updated (description + keywords + defaultLanguage=fr + country=FR)")
        except Exception as exc:
            print("APPLY FAILED:", exc)
            return 1
        # Read-back verification
        ver = _api("channels?part=brandingSettings&mine=true", token)
        vch = ver["items"][0].get("brandingSettings", {}).get("channel", {})
        print("VERIFY branding:", json.dumps({
            "defaultLanguage": vch.get("defaultLanguage"),
            "country": vch.get("country"),
            "keywords_head": (vch.get("keywords") or "")[:80],
        }, ensure_ascii=False))
        repair_video_languages(token)
        repair_broken_titles(token)
    return 0


def repair_broken_titles(token) -> None:
    """Re-derive titles for uploads whose live title is a clipped fragment of
    the original catalogue topic (e.g. "Ce que votre corps vous dit quand le
    silence" — a real shipped title cut mid-sentence).  The new seo_generator
    title engine rebuilds a complete question/clause from the SAME topic, so
    re-running is idempotent: once live == engine(topic) the video is skipped."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    try:
        from seo_generator import _truncate_title
    except Exception as exc:
        print("TITLE REPAIR: seo_generator import failed:", exc)
        return
    hist_path = os.path.join(os.path.dirname(__file__), "..", "data", "video_history.json")
    try:
        with open(hist_path, encoding="utf-8") as fh:
            hist = json.load(fh)
    except Exception as exc:
        print("TITLE REPAIR: history unreadable:", exc)
        return
    topics = {v["youtube_video_id"]: (v.get("topic") or "")
              for v in hist if v.get("youtube_video_id") and v.get("topic")}

    ch = _api("channels?part=contentDetails&mine=true", token)
    upl = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while len(ids) < 30:
        url = (f"playlistItems?part=contentDetails&maxResults=30&playlistId={upl}"
               + (f"&pageToken={page}" if page else ""))
        res = _api(url, token)
        ids += [it["contentDetails"]["videoId"] for it in res.get("items", [])]
        page = res.get("nextPageToken")
        if not page:
            break
    def _norm(s: str) -> str:
        import re as _re
        return " ".join(_re.findall(r"[\wÀ-ÿŒœ'’-]+", (s or "").lower(), flags=_re.UNICODE))

    vids = _api("videos?part=snippet&id=" + ",".join(ids), token).get("items", [])
    fixed = skipped = failed = 0
    for v in vids:
        topic = topics.get(v["id"])
        if not topic:
            continue
        sn = v["snippet"]
        # SAFETY GUARD: only videos whose live title is a *strict prefix* of
        # the original topic were visibly clipped mid-sentence at upload time.
        # Anything else is a complete (possibly already repaired) title —
        # leave it untouched so this repair can never churn or downgrade one.
        live_n, topic_n = _norm(sn["title"]), _norm(topic)
        if not (len(live_n) >= 15 and topic_n.startswith(live_n) and live_n != topic_n):
            skipped += 1
            continue
        new_title = _truncate_title(topic)
        if not new_title or new_title == sn["title"]:
            skipped += 1
            continue
        body = {"id": v["id"], "snippet": {
            "title": new_title,
            "description": sn.get("description", ""),
            "tags": sn.get("tags", []),
            "categoryId": sn.get("categoryId", "28"),
            "defaultLanguage": (sn.get("defaultLanguage") or "fr"),
            "defaultAudioLanguage": (sn.get("defaultAudioLanguage") or "fr"),
        }}
        try:
            _api("videos?part=snippet", token, method="PUT", body=body)
            fixed += 1
            print(f"TITLE FIX {v['id']}\n   old: {sn['title'][:90]}\n   new: {new_title[:90]}")
        except Exception as exc:
            failed += 1
            print(f"TITLE FAIL {v['id']} | {exc}")
    print(f"BROKEN TITLE REPAIR: fixed={fixed} already_ok={skipped} failed={failed}")


def repair_video_languages(token) -> None:
    """Set defaultLanguage/defaultAudioLanguage to 'fr' on every upload whose
    language metadata is missing or wrong.  A video tagged 'en' gets tested
    against English-speaking viewers first; French audio then earns instant
    swipe-aways and the algorithm buries it.  videos.update replaces the whole
    snippet part, so title/description/tags/categoryId are re-sent verbatim."""
    ch = _api("channels?part=contentDetails&mine=true", token)
    upl = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while len(ids) < 30:
        url = (f"playlistItems?part=contentDetails&maxResults=30&playlistId={upl}"
               + (f"&pageToken={page}" if page else ""))
        res = _api(url, token)
        ids += [it["contentDetails"]["videoId"] for it in res.get("items", [])]
        page = res.get("nextPageToken")
        if not page:
            break
    vids = _api("videos?part=snippet&id=" + ",".join(ids), token).get("items", [])
    fixed = skipped = failed = 0
    for v in vids:
        sn = v["snippet"]
        lang = (sn.get("defaultLanguage") or "").lower()
        if lang == "fr":
            skipped += 1
            continue
        body = {"id": v["id"], "snippet": {
            "title": sn["title"],
            "description": sn.get("description", ""),
            "tags": sn.get("tags", []),
            "categoryId": sn.get("categoryId", "28"),
            "defaultLanguage": "fr",
            "defaultAudioLanguage": "fr",
        }}
        try:
            resp = _api("videos?part=snippet", token, method="PUT", body=body)
            got = (resp or {}).get("snippet", {}).get("defaultLanguage")
            fixed += 1
            print(f"LANG FIX  {v['id']} | {lang or 'None'} -> {got or 'fr?'} | {sn['title'][:60]}")
        except Exception as exc:
            failed += 1
            print(f"LANG FAIL {v['id']} | {exc}")
    print(f"VIDEO LANG REPAIR: fixed={fixed} already_ok={skipped} failed={failed}")


if __name__ == "__main__":
    sys.exit(main())
