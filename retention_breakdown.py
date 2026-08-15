#!/usr/bin/env python3
"""Deep retention breakdown for the top-5 demand-backed Neuro-Somaa videos.

Reads video_history.json (analytics synced by the pipeline). Correct field names:
average_view_percentage, average_view_duration_sec, views, predicted_retention.
"""
import json
import sys

sys.path.insert(0, "src")

ROOT = "/home/ubuntu/Neuro-Somaa"

TOP5_KEYS = [
    ("genoux qui craquent", "1. Pourquoi les genoux qui craquent en bougeant"),
    ("ventre se serre", "2. Pourquoi le ventre se serre lors d'une peur"),
    ("mal de tete froid", "3. Pourquoi un aliment froid provoque un mal de tete"),
    ("chair de poule", "4. Pourquoi la chair de poule"),
    ("muscle tressaille", "5. Pourquoi le muscle qui tressaille"),
]

vh = json.load(open(f"{ROOT}/data/video_history.json", encoding="utf-8"))
print(f"Loaded {len(vh)} history entries\n")

def classify(item):
    topic = (item.get("topic") or item.get("title") or "").lower()
    for key, _ in TOP5_KEYS:
        if key in topic:
            return key
    return None

# group all demand-matched videos for baseline
from collections import defaultdict
demand = defaultdict(list)
others = []
for it in vh:
    k = classify(it)
    if k:
        demand[k].append(it)
    elif it.get("views"):
        others.append(it)

# channel baseline
all_with_ret = [x for x in vh if isinstance(x.get("average_view_percentage"), (int, float))]
baseline = sum(x["average_view_percentage"] for x in all_with_ret) / len(all_with_ret) if all_with_ret else None
all_view_pct = [x["average_view_percentage"] for x in all_with_ret]
print(f"CHANNEL BASELINE: n={len(all_with_ret)} videos | avg completion {baseline:.1f}% | "
      f"range {min(all_view_pct):.0f}%-{max(all_view_pct):.0f}% | 2026 gate = 50%\n")

print("=== TOP-5 DEMAND-BACKED VIDEOS ===\n")
rows = []
for key, label in TOP5_KEYS:
    items = demand.get(key, [])
    if not items:
        print(f"{label}: NO analytics row\n")
        continue
    v = max(items, key=lambda x: int(x.get("views") or 0))
    comp = v.get("average_view_percentage")
    dur = v.get("average_view_duration_sec")
    pred = v.get("predicted_retention")
    views = v.get("views")
    rows.append((label, views, comp, dur, pred))
    print(f"{label}")
    print(f"  views            : {views}")
    if isinstance(comp, (int, float)):
        print(f"  completion       : {comp:.1f}%  (gate: 50% | vs baseline {baseline:+.1f} pts)"
              if baseline else f"  completion       : {comp:.1f}%")
        print(f"  gate verdict     : {'ABOVE GATE — algorithm amplifies' if comp >= 50 else 'below gate — needs shorter cut / stronger hook'}")
    else:
        print(f"  completion       : n/a (retention not yet fetched)")
    print(f"  avg view dur     : {dur}s" if isinstance(dur, (int, float)) else "  avg view dur     : n/a")
    print(f"  predicted ret.   : {pred}" if pred is not None else "  predicted ret.   : n/a")
    print()

print("=== COMPARISON TABLE ===")
print(f"{'video':<62} {'views':>6} {'comp%':>6} {'dur s':>6} {'vs base':>7}")
for label, views, comp, dur, pred in rows:
    comp_s = f"{comp:.1f}" if isinstance(comp, (int, float)) else "n/a"
    dur_s = f"{dur:.0f}" if isinstance(dur, (int, float)) else "n/a"
    delta = f"{comp-baseline:+.1f}" if isinstance(comp, (int, float)) and baseline else "n/a"
    print(f"{label[:62]:<62} {str(views):>6} {comp_s:>6} {dur_s:>6} {delta:>7}")

print()
print("=== RETENTION DISTRIBUTION (all videos with data) ===")
import statistics
comps = sorted(x["average_view_percentage"] for x in all_with_ret)
print(f"median {statistics.median(comps):.1f}% | p25 {comps[len(comps)//4]:.1f}% | "
      f"p75 {comps[3*len(comps)//4]:.1f}%")
above_gate = sum(1 for c in comps if c >= 50)
print(f"videos at/above 50% gate: {above_gate}/{len(comps)} ({above_gate/len(comps):.0%})")
