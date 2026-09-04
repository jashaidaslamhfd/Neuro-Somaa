#!/usr/bin/env python3
"""Fetch current France trends and science/psychology RSS items.

Sources are public RSS endpoints; no API key is required. The output is compatible
with Neuro-Somaa's data/search_demand_queue_fr.json topic queue.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

USER_AGENT = "Neuro-Somaa-TrendFetcher/1.0 (+https://github.com/jashaidaslamhfd/Neuro-Somaa)"
DEFAULT_SOURCES = {
    "google_trends_fr": "https://trends.google.com/trending/rss?geo=FR",
    "google_news_fr": "https://news.google.com/rss/search?q=cerveau+OR+sommeil+OR+psychologie+OR+stress+OR+m%C3%A9moire+OR+%C3%A9motion+OR+corps&hl=fr&gl=FR&ceid=FR:fr",
    "futura_sciences": "https://www.futura-sciences.com/rss/actualites.xml",
    "inserm": "https://www.inserm.fr/feed/",
}
KEYWORDS = {
    "cerveau", "mémoire", "sommeil", "stress", "rêve", "rêves", "émotion",
    "psychologie", "corps", "santé", "science", "cerveau", "neurone", "douleur",
    "peur", "coeur", "cœur", "respiration", "fatigue", "odeur", "attention",
    "hormone", "immunité", "immunité", "alimentation", "bien-être", "bizarre",
}
NOISE = {"météo", "résultat", "match", "football", "horoscope", "loto", "promo", "soldes"}


def fetch(url: str, timeout: int = 20) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def parse_feed(raw: bytes, source: str) -> list[dict[str, str]]:
    root = ET.fromstring(raw)
    rows = []
    for item in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        def value(*names: str) -> str:
            for name in names:
                node = item.find(name)
                if node is not None and (node.text or "").strip():
                    return clean(node.text or "")
            return ""
        title = value("title", "{http://www.w3.org/2005/Atom}title")
        link = value("link", "{http://www.w3.org/2005/Atom}link")
        if not link:
            node = item.find("{http://www.w3.org/2005/Atom}link")
            link = (node.attrib.get("href", "") if node is not None else "")
        date = value("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated")
        if title:
            rows.append({"title": title, "url": link, "published_at": parse_date(date) or "", "source": source})
    return rows


def normalize_title(title: str) -> str:
    title = re.sub(r"\s*[-|–—:].*$", "", title)
    title = re.sub(r"\[[^]]+\]|\([^)]*\)", "", title)
    return clean(title).strip(" .?!")


def score(row: dict[str, str]) -> int:
    text = row["title"].lower()
    hits = sum(1 for word in KEYWORDS if word in text)
    noise = sum(1 for word in NOISE if word in text)
    recency = 2 if row.get("published_at", "").startswith(datetime.now(timezone.utc).date().isoformat()) else 0
    source_bonus = 2 if row["source"] in {"google_trends_fr", "google_news_fr"} else 1
    return max(0, hits * 3 + recency + source_bonus - noise * 5)


def make_topic(row: dict[str, str], number: int) -> dict[str, str | int]:
    title = row["title"]
    question = title if title.endswith("?") else f"Pourquoi {title[0].lower() + title[1:]} ?"
    return {
        "series_number": f"TREND-{number}",
        "series_title": title[:90],
        "topic": title[:180],
        "question_phrase": question[:180],
        "angle": question[:180],
        "thumbnail_text": question[:70],
        "demand_note": f"{row['source']} | {row.get('published_at', '')}",
        "source": row["source"],
        "source_url": row.get("url", ""),
        "trend_score": score(row),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/search_demand_queue_fr.json")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--min-score", type=int, default=3)
    parser.add_argument("--source", action="append", metavar="NAME=URL", help="Add/override a source")
    args = parser.parse_args()
    sources = dict(DEFAULT_SOURCES)
    for item in args.source or []:
        if "=" not in item:
            parser.error("--source must be NAME=URL")
        name, url = item.split("=", 1)
        sources[name] = url

    rows: list[dict[str, str]] = []
    errors = []
    for name, url in sources.items():
        try:
            rows.extend(parse_feed(fetch(url), name))
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    unique: dict[str, dict[str, str]] = {}
    for row in rows:
        row["title"] = normalize_title(row["title"])
        key = re.sub(r"[^a-zà-ÿ0-9]", "", row["title"].lower())
        if not row["title"] or key in unique:
            continue
        if score(row) >= args.min_score:
            unique[key] = row
    ranked = sorted(unique.values(), key=score, reverse=True)[: max(1, args.limit)]
    payload = {
        "source": "Google Trends France + French science RSS",
        "mined_at": datetime.now(timezone.utc).isoformat(),
        "topics": [make_topic(row, i) for i, row in enumerate(ranked, 1)],
        "source_errors": errors,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "topics": len(ranked), "source_errors": errors}, ensure_ascii=False))
    return 0 if ranked else 2


if __name__ == "__main__":
    sys.exit(main())
