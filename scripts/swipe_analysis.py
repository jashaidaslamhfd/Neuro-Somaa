#!/usr/bin/env python3
"""Où exactement les spectateurs balaient — courbe de rétention seconde par seconde.

Jusqu'ici la chaîne ne connaissait qu'UN chiffre par vidéo :
« rétention moyenne 33% ». Cela dit combien de gens partent, jamais QUAND.
Toutes les hypothèses testées sur cette moyenne (accroche générique, réponse
tardive, phrase coupée) se sont révélées non concluantes — parce qu'une
moyenne ne peut pas les départager.

Le rapport `audienceRetention` de l'API YouTube Analytics renvoie
`audienceWatchRatio` pour chaque tranche de la vidéo (elapsedVideoTimeRatio
de 0.0 à 1.0). C'est la seule donnée qui montre la SECONDE du balayage.

Ce script :
  1. récupère la courbe de chaque vidéo,
  2. calcule la survie à 1s / 2s / 3s / 5s (la fenêtre de balayage),
  3. repère la plus forte chute et la seconde où elle se produit,
  4. compare les meilleures et les pires vidéos pour en tirer une règle
     applicable aux prochains scripts.

Lecture seule. Aucune modification n'est faite sur la chaîne.
Env requis : GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / REFRESH_TOKEN
"""
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
import itertools

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("swipe")

ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports?"
DATA_API = "https://www.googleapis.com/youtube/v3/"
HISTORY = "data/video_history.json"
OUT = "data/swipe_curves.json"


def access_token() -> str:
    """Bare refresh grant — never send `scope`, Google rejects narrowing it
    with invalid_scope (that bug silently killed the analytics sync)."""
    body = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": os.environ["REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    request = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["access_token"]


def get_json(url: str, token: str) -> dict:
    request = urllib.request.Request(url)
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"error": exc.code,
                "body": exc.read().decode("utf-8", "replace")[:300]}


def retention_curve(token: str, video_id: str, start: str, end: str) -> dict:
    query = urllib.parse.urlencode({
        "ids": "channel==MINE",
        "startDate": start,
        "endDate": end,
        "metrics": "audienceWatchRatio,relativeRetentionPerformance",
        "dimensions": "elapsedVideoTimeRatio",
        "filters": f"video=={video_id};audienceType==ORGANIC",
    })
    result = get_json(ANALYTICS + query, token)
    if "error" in result:
        # relativeRetentionPerformance is not served for every channel.
        query = urllib.parse.urlencode({
            "ids": "channel==MINE", "startDate": start, "endDate": end,
            "metrics": "audienceWatchRatio",
            "dimensions": "elapsedVideoTimeRatio",
            "filters": f"video=={video_id}",
        })
        result = get_json(ANALYTICS + query, token)
    return result


def video_durations(token: str, ids: list) -> dict:
    """Seconds per video, so a ratio can be converted to a real second."""
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ",".join(ids[i:i + 50])
        data = get_json(f"{DATA_API}videos?part=contentDetails&id={chunk}", token)
        for item in data.get("items", []):
            iso = item["contentDetails"]["duration"]
            minutes = seconds = 0
            if "M" in iso:
                minutes = int(iso.split("PT")[1].split("M")[0])
            if "S" in iso:
                seconds = int(iso.split("M")[-1].replace("PT", "").replace("S", "") or 0)
            out[item["id"]] = minutes * 60 + seconds
    return out


def survival_at(curve: list, duration: int, second: float) -> float | None:
    """Share of viewers still watching at `second`."""
    if not duration:
        return None
    target = second / duration
    best = None
    for ratio, watch in curve:
        if ratio <= target:
            best = watch
        else:
            break
    return best


def main() -> int:
    token = access_token()
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=90)

    try:
        with open(HISTORY, encoding="utf-8") as fh:
            history = json.load(fh)
    except OSError:
        history = []
    ids = [v["youtube_video_id"] for v in history if v.get("youtube_video_id")]
    if not ids:
        log.error("No video IDs in %s", HISTORY)
        return 1

    durations = video_durations(token, ids)
    by_id = {v["youtube_video_id"]: v for v in history if v.get("youtube_video_id")}

    results = []
    for video_id in ids:
        report = retention_curve(token, video_id, start.isoformat(), end.isoformat())
        if "error" in report:
            log.warning("%s: %s", video_id, str(report)[:130])
            continue
        rows = report.get("rows") or []
        if not rows:
            log.info("%s: no retention rows yet", video_id)
            continue
        curve = sorted((float(r[0]), float(r[1])) for r in rows)
        duration = durations.get(video_id, 0)

        marks = {f"{s}s": survival_at(curve, duration, s) for s in (1, 2, 3, 5, 10)}

        # steepest drop between consecutive samples
        worst_drop, worst_at = 0.0, None
        for (_r1, w1), (r2, w2) in itertools.pairwise(curve):
            drop = w1 - w2
            if drop > worst_drop:
                worst_drop, worst_at = drop, r2 * duration

        entry = {
            "video_id": video_id,
            "title": by_id[video_id].get("title"),
            "views": by_id[video_id].get("views"),
            "avg_retention": by_id[video_id].get("average_view_percentage"),
            "duration_s": duration,
            "survival": marks,
            "biggest_drop_pct": round(worst_drop * 100, 1),
            "biggest_drop_at_s": round(worst_at, 1) if worst_at else None,
            "curve": [[round(r, 4), round(w, 4)] for r, w in curve],
        }
        results.append(entry)
        log.info("%s  %ss  1s=%s  3s=%s  drop %.1f%% @ %ss",
                 video_id, duration,
                 f"{marks['1s']:.0%}" if marks["1s"] else "?",
                 f"{marks['3s']:.0%}" if marks["3s"] else "?",
                 worst_drop * 100, entry["biggest_drop_at_s"])

    if not results:
        log.error("No retention curves returned. Shorts curves can take a few "
                  "days, and very low-view videos may never get them.")
        return 1

    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({"generated": end.isoformat(), "videos": results},
                  handle, ensure_ascii=False, indent=2)
    log.info("WROTE %s (%d videos)", OUT, len(results))

    # ---- comparison that actually answers "why do they swipe?" ----
    scored = [r for r in results if r["avg_retention"]]
    scored.sort(key=lambda r: -r["avg_retention"])
    top, bottom = scored[:4], scored[-4:]

    def mean(group, key):
        vals = [g["survival"][key] for g in group if g["survival"].get(key)]
        return sum(vals) / len(vals) if vals else None

    print("\n=== SWIPE WINDOW: best vs worst ===")
    print(f"{'':10} {'1s':>7} {'2s':>7} {'3s':>7} {'5s':>7}")
    for label, group in (("BEST 4", top), ("WORST 4", bottom)):
        cells = []
        for mark in ("1s", "2s", "3s", "5s"):
            value = mean(group, mark)
            cells.append(f"{value:6.0%}" if value else "     ?")
        print(f"{label:10} " + " ".join(f"{c:>7}" for c in cells))

    print("\n=== biggest drop per video ===")
    for r in scored:
        print(f"  {r['avg_retention']:5.1f}%  -{r['biggest_drop_pct']:5.1f}% "
              f"@ {r['biggest_drop_at_s']}s   {(r['title'] or '')[:42]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
