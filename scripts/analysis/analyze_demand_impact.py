#!/usr/bin/env python3
"""Compare demand-backed vs catalogue-backed video performance (Neuro-Somaa).

Classifies every video in video_history.json:
  - DEMAND      : topic overlaps with a demand-queue entry (any mined queue snapshot)
  - CATALOGUE   : everything else
Then compares views, completion %, and recency-controlled averages.
"""
import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from trend_fetcher import _topic_words  # noqa: E402

STOP = {"le", "la", "les", "un", "une", "du", "des", "de", "et", "ou", "que",
        "qui", "quoi", "quand", "sans", "pour", "sur", "dans", "par", "est",
        "sont", "se", "ce", "cette", "on", "pas", "ne", "plus", "très"}



def topic_words(text: str) -> set:
    toks = [w for w in re.split(r"\s+", (text or "").lower())
            if w and len(w) >= 3]
    return {w.strip("'\".,;:!?-") for w in toks} - STOP

# 1. Build the demand vocabulary from ALL demand queue snapshots
demand_words = set()
demand_entries = []
try:
    payload = json.load(open(ROOT / "data" / "search_demand_queue_fr.json", encoding="utf-8"))
    for item in payload.get("topics", []):
        t = item.get("topic") or item.get("angle") or ""
        demand_entries.append(t)
        demand_words.update(topic_words(t))
except OSError:
    pass

# 2. Load history with real views
vh = json.load(open(ROOT / "data" / "video_history.json", encoding="utf-8"))
rows = []
for e in vh:
    views = e.get("views")
    if not isinstance(views, (int, float)):
        continue
    rows.append({
        "views": int(views),
        "topic": e.get("topic", ""),
        "completion": e.get("avg_view_duration_percentage") or e.get("completion") or None,
        "posted": e.get("posted_at") or e.get("upload_date") or e.get("published_at") or None,
    })

def classify(topic: str) -> str:
    tw = topic_words(topic)
    # demand match = 2+ content words shared with any demand-queue topic
    if len(tw & demand_words) >= 2:
        return "DEMAND"
    return "CATALOGUE"

groups = defaultdict(list)
for r in rows:
    groups[classify(r["topic"])].append(r)

def stats(g: list) -> dict:
    if not g:
        return {}
    views = sorted(x["views"] for x in g)
    comps = [x["completion"] for x in g if x["completion"]]
    n1k = sum(1 for v in views if v >= 1000)
    return {
        "n": len(g),
        "mean_views": sum(views) / len(views),
        "median_views": views[len(views) // 2],
        "videos_1k_plus": n1k,
        "win_rate_1k": n1k / len(views),
        "mean_completion": (sum(comps) / len(comps)) if comps else None,
        "max_views": max(views),
        "min_views": min(views),
    }

print("=== PERFORMANCE: DEMAND-BACKED vs CATALOGUE (all videos with views) ===")
for name, g in groups.items():
    s = stats(g)
    comp = f"{s['mean_completion']:.1f}%" if s["mean_completion"] else "n/a"
    print(f"{name:>12}: n={s['n']:>3} | mean={s['mean_views']:>7.0f} | median={s['median_views']:>6.0f} "
          f"| 1k+ wins={s['win_rate_1k']:.0%} | avg completion={comp}")

d = stats(groups["DEMAND"]); c = stats(groups["CATALOGUE"])
if d and c:
    print(f"\nDemand advantage: mean +{d['mean_views']/c['mean_views']*100-100:+.0f}%, "
          f"median +{d['median_views']/c['median_views']*100-100:+.0f}%, "
          f"1k-win rate x{d['win_rate_1k']/c['win_rate_1k']:.1f}")

# 3. Recency control: only videos posted in last 7 days
print("\n=== LAST-7-DAYS CONTROL (removes channel-age drift) ===")
now = datetime.now(timezone.utc)
for name in groups:
    fresh = []
    for r in groups[name]:
        try:
            dt = datetime.fromisoformat(str(r["posted"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).days <= 7:
                fresh.append(r)
        except (ValueError, TypeError):
            pass
    if fresh:
        s = stats(fresh)
        print(f"{name:>12}: n={s['n']} recent videos | mean={s['mean_views']:.0f} | median={s['median_views']:.0f}")

# 4. Show actual demand-matched videos (top & bottom) for transparency
print("\n=== DEMAND-MATCHED VIDEOS (examples) ===")
for r in sorted(groups["DEMAND"], key=lambda x: -x["views"])[:12]:
    print(f"  {r['views']:>5}v | {r['topic'][:75]}")
print("=== CATALOGUE-ONLY VIDEOS (examples) ===")
for r in sorted(groups["CATALOGUE"], key=lambda x: -x["views"])[:12]:
    print(f"  {r['views']:>5}v | {r['topic'][:75]}")
