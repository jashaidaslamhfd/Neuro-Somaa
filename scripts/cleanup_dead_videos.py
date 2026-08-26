#!/usr/bin/env python3
"""cleanup_dead_videos.py — Identify and remove dead videos that drag channel avg down.

Run: python scripts/cleanup_dead_videos.py [--apply]

Without --apply: dry-run showing what would be deleted and why.
With --apply: actually removes from video_history.json.
"""

import json
import os
import sys

HISTORY_PATH = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")

DEAD_VIEW_THRESHOLD = 15
DEAD_RETENTION_THRESHOLD = 20
VOUS_STARTERS = ("Vous avez", "votre corps", "Ce que votre", "Pourquoi votre corps")
GENERIC_STARTERS = ("Voici pourquoi", "Ce qu\u00ebl faut comprendre sur", "Ce que la science explique")


def load_history():
    with open(HISTORY_PATH, encoding="utf-8") as f:
        return json.load(f)

def save_history(data):
    tmp = HISTORY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HISTORY_PATH)

def classify(videos):
    deletes, reedits, keeps = [], [], []
    for v in videos:
        views = v.get("views", 0)
        ret = v.get("average_view_percentage", 0)
        title = v.get("title", "")
        vo = v.get("voiceover", "")
        vid = v.get("video_id", v.get("youtube_video_id", "?"))
        wc = len(vo.split()) if vo else 0

        if views < DEAD_VIEW_THRESHOLD and ret < DEAD_RETENTION_THRESHOLD:
            deletes.append({"id": vid, "title": title, "views": views, "ret": ret,
                "reason": "Vous hook" if vo.startswith(VOUS_STARTERS) else f"{views}v/{ret:.0f}% ret"})
        elif views < 500 and 0 < ret < 35 and (vo.startswith(VOUS_STARTERS) or title.startswith(GENERIC_STARTERS)):
            reedits.append({"id": vid, "title": title, "views": views, "ret": ret})
        elif wc > 60 and ret < 50 and views < 500:
            reedits.append({"id": vid, "title": title, "views": views, "ret": ret,
                "reason": f"oversized: {wc} words"})
        else:
            keeps.append(v)
    return deletes, reedits, keeps

def main():
    apply = "--apply" in sys.argv
    data = load_history()
    print(f"Loaded {len(data)} videos")

    deletes, reedits, keeps = classify(data)

    print(f"\n{'='*60}")
    print(f"DELETE: {len(deletes)} | REEDIT: {len(reedits)} | KEEP: {len(keeps)}")
    print(f"{'='*60}")

    if deletes:
        print(f"\nRED DELETE ({len(deletes)}):")
        for d in deletes:
            print(f"  {d['views']:>3}v | {d['ret']:>5.1f}% | {d['reason']:<30} | {d['title'][:45]}")
            print(f"       youtube.com/watch?v={d['id']}")

    if reedits:
        print(f"\nYELLOW REEDIT ({len(reedits)}):")
        for r in reedits:
            reason = r.get("reason", "weak hook")
            print(f"  {r['views']:>3}v | {r['ret']:>5.1f}% | {reason:<30} | {r['title'][:45]}")

    if deletes:
        dead_rets = [d["ret"] for d in deletes]
        all_rets = [v.get("average_view_percentage", 0) for v in data]
        _alive_rets = [r for r in all_rets if r not in dead_rets[:3]]  # approximate
        print(f"\nIMPACT: avg retention {sum(all_rets)/len(all_rets):.1f}% -> ~{sum(all_rets)/len(all_rets) + len(deletes)*0.5:.1f}%")

    if apply and deletes:
        dead_ids = {d["id"] for d in deletes}
        cleaned = [v for v in data if v.get("video_id", v.get("youtube_video_id")) not in dead_ids]
        save_history(cleaned)
        print(f"\nRemoved {len(data)-len(cleaned)} dead videos. {len(data)} -> {len(cleaned)}")
    elif deletes:
        print(f"\nRun with --apply to remove {len(deletes)} dead videos")

if __name__ == "__main__":
    main()
