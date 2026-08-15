#!/usr/bin/env python3
"""Dump the fresh FR demand queue and simulate the next scheduled topic picks."""
import json
import sys
import random

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

import trend_fetcher  # noqa: E402

Q = "data/search_demand_queue_fr.json"
payload = json.load(open(Q, encoding="utf-8"))
print(f"== FRESH DEMAND QUEUE (mined {payload.get('mined_at', '')[:19]}) ==")
for i, t in enumerate(payload["topics"], 1):
    print(f"{i:>2}. {t['angle']}")
    print(f"     demand : {t.get('demand_note', '')[:110]}")
    print(f"     thumb  : {t.get('thumbnail_text', '')[:60]}")

print("\n== NEXT SCHEDULED TOPIC PICKS (simulated, against last-90 history) ==")
vh = json.load(open("data/video_history.json", encoding="utf-8"))
recent = [v.get("topic") for v in vh[-90:] if v.get("topic")]
for i in range(3):
    rec = trend_fetcher.get_trending_topic(exclude=recent, return_metadata=True)
    recent.append(rec["topic"])
    print(f"{i+1}. [{rec.get('source')}] {rec['topic']}  (series {rec.get('series_number')})")
    print(f"   demand note: {rec.get('demand_note', '')[:100]}")
    print(f"   thumbnail : {rec.get('thumbnail_text', '')[:60]}")
