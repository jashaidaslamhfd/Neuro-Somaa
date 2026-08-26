#!/usr/bin/env python3
"""reedit_old_videos.py — Regenerate scripts for old videos that underperformed.

Identifies videos with <500 views and <50% retention, then creates a batch
regeneration queue with optimized hooks (Ton/Tu format, 15-22s duration).

Run: python scripts/reedit_old_videos.py [--apply]
"""

import json
import os
import sys

HISTORY_PATH = os.environ.get("VIDEO_HISTORY_PATH", "data/video_history.json")

# Videos eligible for re-edit: decent content but killed by hook/length
REEDIT_VIEW_CEILING = 500
REEDIT_RETENTION_CEILING = 50

# Hook templates — proven to work (from 1000+ view videos)
HOOK_TEMPLATES = [
    "Ton {body_part} {verb} sans que tu le {verb2}",
    "Ton {body_part} fait un truc que tu {verb}",
    "Tu sens ton {body_part} {verb} pour aucune raison",
    "Ton {body_part} te cache quelque chose",
    "Ce que ton {body_part} fait sans que tu le {verb}",
]

BODY_PARTS = [
    "cerveau", "cœur", "corps", "ventre", "estomac",
    "muscle", "rein", "foie", "sang", "peau",
]


def load_history():
    with open(HISTORY_PATH, encoding="utf-8") as f:
        return json.load(f)


def find_reedit_candidates(videos):
    """Find videos worth re-editing."""
    candidates = []
    seen_topics = set()

    for v in videos:
        views = v.get("views", 0)
        ret = v.get("average_view_percentage", 0)
        title = v.get("title", "")
        vo = v.get("voiceover", "")
        vid = v.get("video_id", v.get("youtube_video_id", "?"))
        wc = len(vo.split()) if vo else 0
        posted = v.get("posted_at") or v.get("publish_at", "")

        # Must have analytics but underperforming
        if ret <= 0:
            continue
        if views >= REEDIT_VIEW_CEILING and ret >= REEDIT_RETENTION_CEILING:
            continue

        # Identify the TOPIC from voiceover
        topic = "unknown"
        for part in ["cerveau", "cœur", "coeur", "ventre", "muscle", "peau", "sang", "rein"]:
            if part in vo.lower():
                topic = part
                break

        # Skip if we already have a re-edit for this topic (avoid duplicates)
        if topic in seen_topics and views > 50:
            continue

        # Determine why it failed
        issues = []
        if vo.startswith(("Vous", "votre", "Ce que votre")):
            issues.append("vouvoiement hook")
        if title.startswith("Pourquoi"):
            issues.append("pourquoi pattern")
        if wc > 60:
            issues.append(f"too long ({wc} words)")
        if ret < 25:
            issues.append(f"terrible retention ({ret:.0f}%)")

        # Build a new hook suggestion
        suggested_hook = None
        if "ventre" in vo.lower() or "estomac" in vo.lower():
            suggested_hook = "Ton ventre fait un truc étrange sans raison"
        elif "cœur" in vo.lower() or "coeur" in vo.lower():
            suggested_hook = "Ton cœur bat plus vite que la normale"
        elif "muscle" in vo.lower():
            suggested_hook = "Ton muscle tressaille tout seul"
        elif "cerveau" in vo.lower():
            suggested_hook = "Ton cerveau te trompe sans que tu le saches"
        elif "yeux" in vo.lower() or "œil" in vo.lower() or "oeil" in vo.lower():
            suggested_hook = "Ton œil bouge sans que tu le contrôles"
        else:
            suggested_hook = "Ton corps fait quelque chose d'inexplicable"

        candidates.append({
            "video_id": vid,
            "title": title,
            "views": views,
            "retention": ret,
            "words": wc,
            "topic": topic,
            "issues": issues,
            "suggested_hook": suggested_hook,
            "published": posted,
            "voiceover": vo[:100] + "..." if len(vo) > 100 else vo,
        })
        seen_topics.add(topic)

    return candidates


def main():
    apply = "--apply" in sys.argv
    data = load_history()

    candidates = find_reedit_candidates(data)

    print(f"{'='*70}")
    print(f"📝 RE-EDIT CANDIDATES: {len(candidates)} videos")
    print(f"{'='*70}")

    for i, c in enumerate(candidates, 1):
        print(f"\n{i}. {c['title'][:55]}")
        print(f"   Video ID: {c['video_id']}")
        print(f"   Views: {c['views']} | Retention: {c['retention']:.1f}% | Words: {c['words']}")
        print(f"   Issues: {', '.join(c['issues']) if c['issues'] else 'oversized'}")
        print("   Suggested new hook:", c["suggested_hook"])
        print("   Original snippet:", c["voiceover"])

    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Total candidates: {len(candidates)}")
    print(f"  Average views: {sum(c['views'] for c in candidates)/max(1,len(candidates)):.0f}")
    print(f"  Average retention: {sum(c['retention'] for c in candidates)/max(1,len(candidates)):.1f}%")
    print("\n  To re-edit manually:")
    print("  1. Go to YouTube Studio → Delete old video")
    print("  2. Create new Short with the suggested hook above")
    print("  3. Duration: 15-20 seconds (45-55 words)")
    print("  4. Upload at 19:30 or 21:30 Paris time")

    if apply:
        # Write re-edit queue to file
        queue_path = "data/reedit_queue.json"
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2)
        print(f"\n  ✅ Re-edit queue saved to {queue_path}")


if __name__ == "__main__":
    main()
