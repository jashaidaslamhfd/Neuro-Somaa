#!/usr/bin/env python3
"""Build a clean France-first demand queue for Neuro-Somaa.

The queue is optimized for a broad curiosity niche:
mysteries of the brain, psychology, human behaviour, perception, illusions,
sleep, dreams, memory, attention and human-centred AI/science. News is only a
supplemental discovery source; the core queue is evergreen and relatable.
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
        "q=cerveau+OR+sommeil+OR+psychologie+OR+m%C3%A9moire+OR+stress+OR+%C3%A9motion+"
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
    "vision", "audition", "réflexe", "illusion", "illusions", "sens",
    "habitude", "récompense", "récompenses", "curiosité", "décision",
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
    "polyarthrite", "alzheimer", "cancer", "maladie", "traitement", "médicament",
    "vaccin", "hôpital", "patient", "patients", "clinique", "diagnostic",
    "chirurgie", "thérapie", "symptôme", "symptômes", "tumeur", "tumeurs",
    "douleur chronique", "maladie rare", "essai clinique",
    "obésité", "diabète", "addiction", "suicide",
    "atelier", "ateliers", "honoraire", "église", "frères", "empire",
    "convalescence", "opération", "astronaute", "prix pour", "mon corps",
    # Personal-case / local-news patterns: poor fit for an evergreen science Short.
    "on lui", "une personne", "un homme", "une femme", "chez lui", "chez elle",
    "après une chute", "après un accident", "témoigne", "témoignage",
    "dans sa ville", "dans le village", "à bannalec", "à concarneau",
    "à belleau", "à quimper", "à paris", "à lyon", "à marseille", "à bordeaux",
}

EVENT_PATTERNS = (
    r"\b(?:samedi|dimanche|lundi|mardi|mercredi|jeudi|vendredi)\b",
    r"\b(?:octobre|novembre|décembre|janvier|février|mars|avril|mai|juin|juillet|août|septembre)\b",
    r"\b\d{1,2}\s*(?:€|euros|millions?|milliards?)\b",
    r"\b(?:festival|salon|forum|conférence|concours|élection)\b",
)


EVERGREEN_SEEDS = [
    "Pourquoi ton cerveau oublie-t-il certains souvenirs ?",
    "Pourquoi oublie-t-on parfois un mot pourtant familier ?",
    "Pourquoi une chanson reste-t-elle dans ta tête ?",
    "Pourquoi le temps semble-t-il accélérer avec l'âge ?",
    "Pourquoi rêves-tu davantage au réveil que la nuit ?",
    "Pourquoi le cerveau invente-t-il de faux souvenirs ?",
    "Pourquoi le stress déforme-t-il parfois ta perception ?",
    "Pourquoi ton téléphone capte-t-il autant ton attention ?",
    "Pourquoi une notification suffit-elle à interrompre ta concentration ?",
    "Pourquoi le cerveau adore-t-il les récompenses imprévisibles ?",
    "Pourquoi bâille-t-on quand quelqu'un d'autre bâille ?",
    "Pourquoi as-tu la chair de poule sans avoir froid ?",
    "Pourquoi une odeur peut-elle réveiller un souvenir ancien ?",
    "Pourquoi tremble-t-on sous l'effet du stress ?",
    "Pourquoi le cerveau cherche-t-il des visages partout ?",
    "Pourquoi ton cerveau te fait-il voir des choses qui n'existent pas ?",
    "Pourquoi ton attention disparaît-elle dès qu'une notification arrive ?",
    "Pourquoi certaines habitudes deviennent-elles presque automatiques ?",
    "Pourquoi ton cerveau préfère-t-il parfois une réponse simple à une réponse vraie ?",
    "Pourquoi un souvenir peut-il changer à chaque fois que tu le racontes ?",
    "Pourquoi ton cerveau déteste-t-il les tâches inachevées ?",
    "Pourquoi as-tu parfois l'impression d'avoir déjà vécu une scène ?",
    "Pourquoi ton cerveau remarque-t-il soudainement un mot que tu vois partout ?",
    "Pourquoi le silence peut-il sembler plus étrange que le bruit ?",
    "Pourquoi ton cerveau imite-t-il parfois les émotions des autres ?",
    "Pourquoi manque-t-on parfois un objet juste devant nos yeux ?",
    "Pourquoi le cerveau aime-t-il autant les histoires incomplètes ?",
    "Pourquoi la musique change-t-elle parfois ton humeur instantanément ?",
    "Pourquoi certaines habitudes deviennent-elles automatiques ?",
    "Pourquoi manque-t-on de concentration après trop d'écrans ?",
    "Pourquoi le cerveau continue-t-il à réfléchir pendant le sommeil ?",
    "Pourquoi une peur peut-elle apparaître avant même de comprendre le danger ?",
]

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

    # Reject article-shaped news headlines. Proper nouns and one-off cases
    # are poor inputs for a reusable evergreen Short.
    if re.search(r"\b(?:steve|elon|donald|emmanuel|brigitte|kylian|taylor|jean|marie)\b", text):
        return False
    if text.count(",") >= 2:
        return False
    if re.search(r"\b(?:on lui|une personne|un homme|une femme|après une|après un|témoigne|témoignage)\b", text):
        return False

    # Reject article-shaped personal/event headlines even when they contain a
    # science keyword. Neuro-Somaa needs a reusable curiosity question, not a
    # one-off local story.
    personal_patterns = (
        r"\bon lui\b", r"\bune personne\b", r"\bun homme\b", r"\bune femme\b",
        r"\baprès (?:une|un)\b", r"\bà [a-zà-ÿ-]+\b.*\b(?:ville|village)\b",
        r"\b(?:témoigne|témoignage)\b",
    )
    if any(re.search(pattern, text) for pattern in personal_patterns):
        return False

    hits = sum(1 for word in KEYWORDS if word in text)
    # The previous check lower-cased the headline and then searched for
    # uppercase proper nouns, so it could never match. Inspect the original
    # title instead.
    if re.search(r"\b(?:à|au|aux|en)\s+[A-ZÀ-Ü][\wÀ-ÿ-]+", title):
        return False
    return hits >= 1


def score(row: dict[str, str]) -> int:
    text = row["title"].lower()
    hits = sum(1 for word in KEYWORDS if word in text)
    noise = sum(1 for word in NOISE if word in text)
    recency = 2 if row.get("published_at", "").startswith(datetime.now(UTC).date().isoformat()) else 0
    source_bonus = 14 if row["source"] == "evergreen_seed" else (4 if row["source"] in {"futura_sciences", "inserm"} else 1)
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

    for seed in EVERGREEN_SEEDS:
        key = re.sub(r"[^a-zà-ÿ0-9]", "", seed.lower())
        unique.setdefault(key, {"title": seed, "url": "", "published_at": "", "source": "evergreen_seed"})

    # Evergreen curiosity topics are the default backbone. News is allowed only
    # as a supplemental discovery source, never as the dominant queue.
    ranked = sorted(
        unique.values(),
        key=lambda row: (row["source"] == "evergreen_seed", score(row)),
        reverse=True,
    )[: max(1, args.limit)]
    payload = {
        "source": "Evergreen science bank + Google Trends France + French science RSS (filtered)",
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
