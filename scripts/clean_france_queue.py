#!/usr/bin/env python3
"""Clean an existing France demand queue without waiting for a fresh RSS fetch."""
from __future__ import annotations

import json
from pathlib import Path

from fetch_france_trends import is_good_topic, normalize_title, score


def main() -> int:
    path = Path("data/search_demand_queue_fr.json")
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    topics = payload.get("topics", []) if isinstance(payload, dict) else payload
    clean = []
    seen = set()
    for item in topics:
        if not isinstance(item, dict):
            continue
        raw = item.get("topic") or item.get("question_phrase") or item.get("series_title") or ""
        title = normalize_title(str(raw))
        key = "".join(ch for ch in title.lower() if ch.isalnum())
        if not title or key in seen or not is_good_topic(title):
            continue
        if score({"title": title, "source": str(item.get("source", "")), "published_at": str(item.get("published_at", ""))}) < 5:
            continue
        seen.add(key)
        item["topic"] = title
        item["question_phrase"] = title
        item["angle"] = title
        item["series_title"] = title[:90]
        item["thumbnail_text"] = title[:70]
        clean.append(item)
    if isinstance(payload, dict):
        payload["topics"] = clean
        payload["filtered_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    else:
        payload = {"topics": clean}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"France queue cleaned: {len(clean)} usable topics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
