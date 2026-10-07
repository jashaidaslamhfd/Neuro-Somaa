#!/usr/bin/env python3
"""Build a clean France-first demand queue for Neuro-Somaa.

The queue is deliberately narrower than a generic news feed: it keeps
consumer-friendly science, psychology, brain, sleep, behaviour and
human-centred technology topics, while rejecting local events, sports,
politics, crime, medical-news headlines and other items that are poor fits
for an evergreen Shorts channel.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc  # noqa: UP017

USER_AGENT = "Neuro-Somaa-TrendFetcher/2.0 (+https://github.com/jashaidaslamhfd/Neuro-Somaa)"

DEFAULT_SOURCES = {
    "google_trends_fr": "https://trends.google.com/trending/rss?geo=FR",
    "google_news_fr": (
        "https://news.google.com/rss/search?"
        "q=cerveau+OR+sommeil+OR+psychologie+OR+mémoire+OR+stress+OR+émotion+"
        "OR+attention+OR+perception+OR+habitude+OR+intelligence+artificielle&"
        "hl=fr&gl=FR&ceid=FR:fr"
    ),
    "futura_sciences": "https://www.futura-sciences.com/rss/actualites.xml",
    "inserm": "https://www.inserm.fr/feed/",
}

KEYWORDS = {
    "cerveau", "mémoire", "sommeil", "stress", "rêve", "rêves", "émotion",
    "psychologie", "comportement", "science", "neurone", "attention",
    "perception", "dopamine", "habitude", "concentration", "curiosité",
    "peur", "coeur", "cœur", "respiration", "fatigue", "odeur", "odorat",
    "vision", "audition", "réflexe",
    "intelligence artificielle", "ia", "robot", "algorithme", "numérique",
    "téléphone", "écran", "notification", "apprentissage", "créativité",
    "décision", "conscience", "illusion", "sensation",
}

# These are intentionally broad because a single local-news phrase can make
# an otherwise science-looking headline completely unsuitable for the channel.
NOISE = {
    "météo", "résultat", "match", "football", "rugby", "tennis", "basket",
    "cyclisme", "f1", "sport", "horoscope", "loto", "promo", "soldes",
    "élection", "président", "ministre", "politique", "parti", "député",
    "maire", "municipale", "municipales", "gouvernement", "guerre",
    "armée", "obus", "missile", "ukraine", "gaza", "israël",
    "meurtre", "noyade", "accident", "drame", "procès", "justice",
    "police", "tribunal", "victime", "agression", "disparu", "disparue",
    "mort", "décès", "funérailles", "incendie", "inondation", "séisme",
    "festival", "concert", "spectacle", "exposition", "salon", "concours",
    "municipalité", "préfecture", "région", "département", "ville",
    "quimper", "paris", "lyon", "marseille", "bordeaux", "toulouse",
    "lille", "nantes", "nice", "tokyo", "new york",
    "polyarthrite", "cancer", "maladie", "traitement", "médicament",
    "vaccin", "hôpital", "patient", "patients", "clinique", "diagnostic",
    "chirurgie", "thérapie", "symptôme", "symptômes",
    "obésité", "diabète", "addiction", "suicide",
}

EVENT_PATTERNS = (
    r"\b(?:samedi|dimanche|lundi|mardi|mercredi|jeudi|vendredi)\b",
    r"\b(?:octobre|novembre|décembre|janvier|février|mars|avril|mai|juin|juillet|août|septembre)\b",
    r"\b\d{1,2}\s*(?:€|euros|millions?|milliards?)\b",
    r"\b(?:festival|salon|forum|conférence|concours|élection)\b",
)

GENERIC_HEADLINES = {
    "cerveau", "sommeil", "science", "psychologie", "mémoire", "stress",
    "corps", "émotion", "intelligence artificielle", "ia",
}


def fetch(url: str, timeout: int = 20) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def parse_feed(raw: bytes, source: str) -> list[dict[str, str]]:
    root = ET.fromstring(raw)
    rows = []
    for item in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        def value(*names: str, item: ET.Element = item) -> str:
            for name in names:
                node = item.find(name)
                if node is not None and (node.text or "").strip():
                    return clean(node.text or "")
            return ""

        title = value("title", "{http://www.w3.org/2005/Atom}title")
        link = value("link", "{http://www.w3.org/2005/Atom}link")
        if not link:
            node = item.find("{http://www.w3.org/2005/Atom}link")
            link = node.attrib.get("href", "") if node is not None else ""
        date = value(
            "pubDate",
            "published",
            "updated",
            "{http://www.w3.org/2005/Atom}published",
            "{http://www.w3.org/2005/Atom}updated",
        )
        if title:
            rows.append(
                {
                    "title": title,
                    "url": link,
                    "published_at": parse_date(date) or "",
                    "source": source,
                }
            )
    return rows


def normalize_title(title: str) -> str:
    title = re.sub(r"\s*[-|–—:]\s*.*$", "", title)
    title = re.sub(r"\[[^]]+\]|\([^)]*\)", "", title)
    return clean(title).strip(" .?!")


def is_good_topic(title: str) -> bool:
    text = clean(title).lower()
    if len(text) < 18 or len(text) > 150:
        return False
    if text in GENERIC_HEADLINES:
        return False
    if sum(1 for word in NOISE if word in text) > 0:
        return False
    if any(re.search(pattern, text) for pattern in EVENT_PATTERNS):
        return False

    # Reject obvious named-person/news headlines. Proper nouns are useful for
    # verified trends, but most of these are not evergreen Neuro-Somaa topics.
    if re.search(r"\b(?:steve|elon|donald|emmanuel|brigitte|kylian|taylor|jean|marie)\b", text):
        return False
    if text.count(",") >= 2:
        return False

    hits = sum(1 for word in KEYWORDS if word in text)
    return hits >= 1


def score(row: dict[str, str]) -> int:
    text = row["title"].lower()
    hits = sum(1 for word in KEYWORDS if word in text)
    noise = sum(1 for word in NOISE if word in text)
    recency = 2 if row.get("published_at", "").startswith(datetime.now(UTC).date().isoformat()) else 0
    source_bonus = 3 if row["source"] in {"google_trends_fr", "google_news_fr"} else 1
    curiosity_bonus = 2 if "?" in text or any(x in text for x in ("pourquoi", "comment", "étrange", "surprenant")) else 0
    return max(0, hits * 3 + recency + source_bonus + curiosity_bonus - noise * 8)


def make_topic(row: dict[str, str], number: int) -> dict[str, str | int]:
    title = row["title"]
    # Do not blindly prepend "Pourquoi" to a news headline. The LLM receives
    # the clean source title and chooses a natural French curiosity angle.
    question = title
    return {
        "series_number": f"TREND-{number}",
        "series_title": title[:90],
        "topic": title[:180],
        "question_phrase": question[:180],
        "angle": title[:180],
        "thumbnail_text": title[:70],
        "demand_note": f"{row['source']} | {row.get('published_at', '')}",
        "source": row["source"],
        "source_url": row.get("url", ""),
        "trend_score": score(row),
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/search_demand_queue_fr.json")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--min-score", type=int, default=5)
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
        if not row["title"] or key in unique or not is_good_topic(row["title"]):
            continue
        if score(row) >= args.min_score:
            unique[key] = row

    ranked = sorted(unique.values(), key=score, reverse=True)[: max(1, args.limit)]
    payload = {
        "source": "Google Trends France + French science RSS (filtered)",
        "mined_at": datetime.now(UTC).isoformat(),
        "topics": [make_topic(row, i) for i, row in enumerate(ranked, 1)],
        "source_errors": errors,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"output": str(output), "topics": len(ranked), "source_errors": errors},
            ensure_ascii=False,
        )
    )
    return 0 if ranked else 2


if __name__ == "__main__":
    sys.exit(main())
