#!/usr/bin/env python3
"""Inspect the structure of the NS analytics data files to find retention fields."""
import json
import os
import glob

ROOT = "/home/ubuntu/Neuro-Somaa"

def dump(name, path, n=3):
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[{name}] read error: {e}")
        return
    if isinstance(data, dict):
        keys = list(data.keys())
        print(f"\n=== {name}: dict with keys {keys[:20]} (size {os.path.getsize(path)} bytes) ===")
        # find the first list field
        for k in keys:
            v = data[k]
            if isinstance(v, list) and v:
                print(f"  list field '{k}': {len(v)} items")
                first = v[0]
                if isinstance(first, dict):
                    print(f"    item keys: {list(first.keys())}")
                    for i, it in enumerate(v[:n]):
                        print(f"    [{i}] {json.dumps({kk: it[kk] for kk in list(it.keys())[:12]}, ensure_ascii=False)[:300]}")
                else:
                    print(f"    sample: {json.dumps(first, ensure_ascii=False)[:200]}")
                break
        # show scalar metadata
        for k in keys:
            v = data[k]
            if not isinstance(v, (list, dict)):
                print(f"  scalar '{k}': {str(v)[:120]}")
    elif isinstance(data, list):
        print(f"\n=== {name}: list of {len(data)} items (size {os.path.getsize(path)} bytes) ===")
        if data and isinstance(data[0], dict):
            print(f"  item keys: {list(data[0].keys())}")
            for i, it in enumerate(data[:n]):
                print(f"  [{i}] {json.dumps({k: it.get(k) for k in list(it.keys())[:14]}, ensure_ascii=False)[:320]}")

for p in sorted(glob.glob(f"{ROOT}/data/*metric*")) + sorted(glob.glob(f"{ROOT}/data/*analytic*")) + sorted(glob.glob(f"{ROOT}/data/*growth*")) + [f"{ROOT}/data/video_history.json"]:
    dump(os.path.basename(p), p)
