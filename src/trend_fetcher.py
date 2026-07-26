"""Reliable, best-effort topic research for the SKILLOR Shorts pipeline.

This module deliberately uses documented APIs where credentials are available:
* Google Trends daily RSS feed (public, no key)
* YouTube Data API v3 (optional YOUTUBE_API_KEY)
* Reddit OAuth API (optional REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET)

Every source is optional. A source failure is logged with its HTTP status and
never prevents a video from being made; a curated, non-duplicated topic pool
is the final fallback. Do not treat a trending headline as evidence for a
medical/scientific claim: the script/fact-review layer must still verify it.
"""
from __future__ import annotations

import base64
import logging
import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
MAX_SOURCE_RETRIES = 2
TARGET_REGION = os.environ.get("TREND_REGION", "FR").upper()
YOUTUBE_REGION = os.environ.get("YOUTUBE_REGION_CODE", TARGET_REGION).upper()

# The channel is science/body/brain-oriented. Restricting external headlines
# prevents unrelated politics, celebrity stories and sports results from being
# turned into off-brand Shorts merely because they are trending.
# Deliberately narrow science anchors. Broad words such as "animal", "human",
# "history" and "nature" admitted entertainment headlines like "Why Got Fired
# Matters" that did not give this channel a real explainable science topic.
RELEVANCE_TERMS = (
    "cerveau", "corps", "santé", "médecine", "médecin", "science", "espace", "nasa",
    "technologie", "intelligence artificielle", "robot", "climat", "océan", "planète",
    "physique", "psychologie", "sommeil", "coeur", "cœur", "mémoire", "nerf", "hormone",
    "cellule", "génétique", "recherche", "étude", "virus", "nutrition", "immunité", "anatomie", "biologie",
)
# These are UI/navigation strings sometimes accidentally extracted by fragile
# HTML scrapers. The project no longer scrapes YouTube HTML, but retaining the
# filter protects all sources and future integrations.
INVALID_TOPIC_PATTERNS = (
    r"^try searching to get started$",
    r"^keyboard shortcuts$",
    r"^sign in$",
    r"^home$",
    r"^shorts$",
    r"^subscriptions$",
    r"^youtube$",
    r"^reddit$",
)

# MrNextep's channel data shows the strongest relative performance on familiar,
# low-risk brain/body experiences (yawning, memory, eye twitching, dreams,
# goosebumps)—not broad news headlines or generic "dark" claims. These are
# proven-pillar prompts, never labelled as daily trends.
PROVEN_TOPIC_POOL = [
    "Pourquoi une chanson reste dans la tête", "Pourquoi on oublie un prénom tout de suite",
    "Pourquoi le bâillement est contagieux", "Pourquoi une paupière tressaille",
    "Pourquoi la chair de poule apparaît", "Pourquoi les rêves s'effacent au réveil",
    "Pourquoi le déjà-vu semble familier", "Pourquoi le cœur s'emballe avec le stress",
    "Pourquoi le corps se fige face à la peur", "Pourquoi le ventre gargouille",
    "Pourquoi on se réveille avant le réveil", "Pourquoi les mains se fripent dans l'eau",
    "Pourquoi les souvenirs gênants reviennent le soir", "Pourquoi on oublie une pièce",
    "Pourquoi le silence peut gêner", "Pourquoi le cerveau entend son prénom",
    "Pourquoi le temps semble accélérer", "Pourquoi le stress brouille la mémoire",
    "Pourquoi on a la tête qui tourne en se levant", "Pourquoi le cerveau rejoue les conversations",
    "Pourquoi on entend son coeur la nuit", "Pourquoi la lumière fait éternuer",
    "Pourquoi le cerveau a besoin de sommeil profond", "Pourquoi la musique change l'humeur",
    "Pourquoi on rougit", "Pourquoi on frissonne", "Pourquoi le corps est lourd quand on est fatigué",
]

REDDIT_SUBREDDITS = ("france", "science", "technology", "space")
USER_AGENT = "SKILLOR/1.1 (automated topic research; contact: channel-owner)"
BODY_GLITCH_CATALOGUE_PATH = Path("data/body_glitch_topics.json")


def _normalise_topic(value: str) -> str:
    """Create a comparison key; preserve the original title for display."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.lower())).strip()


# Data-proven flop (Jul 2026): two uploads about "time feels faster with age"
# within 48h — the first earned 800+ views, the second died at 4 views. The
# exact-string dedupe above cannot see this, so topics that merely REWORD a
# recent upload must also be blocked.
_FR_STOPWORDS = {
    "le", "la", "les", "un", "une", "de", "des", "du", "en", "et", "ou",
    "qui", "que", "quand", "avec", "sans", "on", "vous", "tu", "ton", "ta",
    "tes", "votre", "vos", "son", "sa", "ses", "il", "elle", "se", "ce",
    "cette", "pour", "pourquoi", "est", "ne", "pas", "peut", "sembler",
    "dans", "sur", "au", "aux", "a", "d", "l", "j", "qu", "n", "s", "y",
    "comment", "quoi", "vos", "nos", "notre",
}


_WORD_FAMILIES = (
    ("vieill", "age"), ("vieux", "age"),
    ("accel", "vite"), ("rapid", "vite"), ("vitess", "vite"),
    ("pass", "passe"), ("ecoul", "passe"),
    ("dorm", "dort"), ("sommeil", "dort"), ("reveill", "reveil"),
    ("mang", "mange"), ("aliment", "mange"), ("nourrit", "mange"),
    ("peur", "peur"), ("angois", "peur"), ("stress", "peur"), ("anxie", "peur"),
    ("froid", "froid"), ("friss", "froid"),
    ("coeur", "coeur"), ("cardia", "coeur"),
    ("genou", "genou"), ("articul", "genou"),
)


def _strip_accents(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def _topic_words(value: str) -> set:
    norm = _strip_accents(_normalise_topic(value))
    words = set()
    for w in norm.split():
        if len(w) <= 2 or w in _FR_STOPWORDS:
            continue
        stem = w
        for prefix, canon in _WORD_FAMILIES:
            if w.startswith(prefix):
                stem = canon
                break
        words.add(stem)
    return words


def _near_duplicate_of_recent(topic: str, excluded: Iterable[str]) -> bool:
    words = _topic_words(topic)
    if len(words) < 2:
        return False
    for recent in (excluded or []):
        rwords = _topic_words(recent)
        if not rwords:
            continue
        overlap = len(words & rwords)
        score = overlap / min(len(words), len(rwords))
        if score >= 0.6 or (rwords and rwords.issubset(words)) or (words and words.issubset(rwords)):
            return True
    return False


def _clean_topic(value: object) -> str:
    """Return a short, printable title or an empty string."""
    if not isinstance(value, str):
        return ""
    title = re.sub(r"\s+", " ", value).strip().strip("-–—: ")
    if len(title) < 12 or len(title) > 160:
        return ""
    lowered = title.lower()
    if any(re.fullmatch(pattern, lowered) for pattern in INVALID_TOPIC_PATTERNS):
        return ""
    return title


def _is_relevant(title: str) -> bool:
    """Match whole terms so e.g. football club “Hearts” is not body content."""
    lowered = title.lower()
    return any(re.search(r"\b" + re.escape(term) + r"\b", lowered) for term in RELEVANCE_TERMS)


def _request(method: str, url: str, *, source: str, **kwargs) -> Optional[requests.Response]:
    """Perform a bounded request and log useful diagnostics on failure."""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("User-Agent", USER_AGENT)

    for attempt in range(1, MAX_SOURCE_RETRIES + 1):
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            if 200 <= response.status_code < 300:
                return response
            logger.warning(
                "%s unavailable (HTTP %s, attempt %s/%s): %s",
                source, response.status_code, attempt, MAX_SOURCE_RETRIES,
                response.text[:180].replace("\n", " "),
            )
            # Retrying a permanent auth/not-found failure only wastes a run.
            if response.status_code in (400, 401, 403, 404):
                return None
        except requests.RequestException as exc:
            logger.warning("%s request failed (attempt %s/%s): %s", source, attempt, MAX_SOURCE_RETRIES, exc)
        if attempt < MAX_SOURCE_RETRIES:
            time.sleep(1.5 * attempt)
    return None


def _topic_record(topic: str, source: str, **extra: object) -> Dict:
    record: Dict[str, object] = {"topic": topic, "title": topic, "source": source}
    record.update(extra)
    return record


def _deduplicate(records: Iterable[Dict], excluded: Optional[Iterable[str]] = None) -> List[Dict]:
    excluded_keys: Set[str] = {_normalise_topic(x) for x in (excluded or []) if x}
    seen: Set[str] = set()
    result: List[Dict] = []
    for record in records:
        title = _clean_topic(record.get("topic", ""))
        key = _normalise_topic(title)
        if not title or not key or key in seen or key in excluded_keys:
            continue
        seen.add(key)
        clean_record = dict(record)
        clean_record["topic"] = title
        clean_record["title"] = title
        result.append(clean_record)
    return result


def get_google_trends_topics(region: Optional[str] = None) -> List[Dict]:
    """Fetch daily Google trends through its XML RSS feed.

    The former ``/trends/api/dailytrends`` JSON endpoint used by this project
    now returns HTTP 404 in normal requests. RSS is simpler to parse and has a
    stable public response. Google Trends is a discovery signal only.
    """
    region = (region or TARGET_REGION).upper()
    response = _request(
        "GET", "https://trends.google.com/trending/rss", source="Google Trends RSS",
        params={"geo": region}, headers={"Accept": "application/rss+xml, application/xml;q=0.9"},
    )
    if response is None:
        return []
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        logger.warning("Google Trends RSS returned invalid XML: %s", exc)
        return []

    topics: List[Dict] = []
    for item in root.findall("./channel/item"):
        title = _clean_topic(item.findtext("title", default=""))
        if title and _is_relevant(title):
            topics.append(_topic_record(
                title, "google_trends", region=region,
                source_url=item.findtext("link", default=""),
            ))
    logger.info("Google Trends RSS: %s relevant topics for %s.", len(topics), region)
    return _deduplicate(topics)


def get_youtube_trending_topics(region: Optional[str] = None) -> List[Dict]:
    """Use the official YouTube Data API; never scrape the changing HTML UI."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        logger.info("YouTube trends skipped: YOUTUBE_API_KEY is not configured.")
        return []
    region = (region or YOUTUBE_REGION).upper()
    response = _request(
        "GET", "https://www.googleapis.com/youtube/v3/videos", source="YouTube Data API",
        params={
            "part": "snippet,statistics", "chart": "mostPopular", "regionCode": region,
            "maxResults": 25, "key": api_key,
        },
    )
    if response is None:
        return []
    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("YouTube Data API returned non-JSON data: %s", exc)
        return []

    topics: List[Dict] = []
    for item in payload.get("items", []):
        snippet = item.get("snippet", {})
        title = _clean_topic(snippet.get("title", ""))
        if title and _is_relevant(title):
            topics.append(_topic_record(
                title, "youtube_trending", region=region,
                video_id=item.get("id", ""),
                source_url=f"https://www.youtube.com/watch?v={item.get('id', '')}",
                category_id=snippet.get("categoryId", ""),
            ))
    logger.info("YouTube Data API: %s relevant topics for %s.", len(topics), region)
    return _deduplicate(topics)


def _reddit_access_token() -> Optional[str]:
    """Return an app-only Reddit OAuth token, or None when not configured."""
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        logger.info("Reddit trends skipped: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are not configured.")
        return None
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    response = _request(
        "POST", "https://www.reddit.com/api/v1/access_token", source="Reddit OAuth",
        headers={"Authorization": f"Basic {basic}"}, data={"grant_type": "client_credentials"},
    )
    if response is None:
        return None
    try:
        token = response.json().get("access_token")
    except ValueError:
        token = None
    if not token:
        logger.warning("Reddit OAuth returned no access token.")
    return token


def get_reddit_trending_topics() -> List[Dict]:
    """Fetch niche-relevant posts trending today through Reddit OAuth."""
    token = _reddit_access_token()
    if not token:
        return []
    topics: List[Dict] = []
    headers = {"Authorization": f"Bearer {token}"}
    for subreddit in REDDIT_SUBREDDITS:
        response = _request(
            "GET", f"https://oauth.reddit.com/r/{subreddit}/top", source=f"Reddit r/{subreddit}",
            headers=headers, params={"limit": 25, "t": "day", "raw_json": 1},
        )
        if response is None:
            continue
        try:
            children = response.json().get("data", {}).get("children", [])
        except ValueError as exc:
            logger.warning("Reddit r/%s returned non-JSON data: %s", subreddit, exc)
            continue
        for child in children:
            post = child.get("data", {})
            title = _clean_topic(post.get("title", ""))
            if title and _is_relevant(title) and not post.get("over_18", False):
                topics.append(_topic_record(
                    title, f"reddit_r/{subreddit}", subreddit=subreddit,
                    permalink=post.get("permalink", ""),
                    source_url=f"https://www.reddit.com{post.get('permalink', '')}",
                    score=post.get("score", 0),
                ))
    topics = _deduplicate(topics)
    logger.info("Reddit OAuth: %s relevant topics.", len(topics))
    return topics


# ---------------------------------------------------------------------------
# Retention-weighted topic selection
# ---------------------------------------------------------------------------
# Measured on this channel's OWN 14 videos once real YouTube Analytics finally
# landed (2026-07-26). Grouping every published topic by what it asks the
# viewer to feel:
#
#   PHYSICAL  (silence pesant, ventre serré, genoux qui craquent, rougir,
#              se réveiller avant l'alarme)      n=9   avg retention 35.7%
#   ABSTRACT  (le temps qui passe, la mémoire,
#              le déjà-vu, le stress)            n=5   avg retention 28.1%
#
# +7.6 points for the same production effort. The reason is mechanical: a
# Short is watched in silence while scrolling. "Ton ventre se serre" is
# something the viewer can verify in their own body in the first second.
# "Le temps semble accélérer" asks them to reflect — and reflection loses to
# the thumb.
#
# Topic choice was pure random.choice() before this, so half the catalogue's
# retention advantage was being thrown away at the very first step of the
# pipeline. This is a WEIGHTING, not a ban: abstract topics still ship (they
# keep the catalogue varied), just less often.
PHYSICAL_SENSATION_MARKERS = {
    "ventre", "estomac", "gorge", "poitrine", "peau", "chair", "poil",
    "genou", "genoux", "muscle", "jambe", "bras", "main", "doigt", "pied",
    "dos", "nuque", "épaule", "mâchoire", "dent", "langue", "lèvre",
    "oeil", "œil", "yeux", "paupière", "oreille", "nez", "visage", "joue",
    "rougir", "rougit", "frisson", "chair de poule", "tremble", "tressaille",
    "craque", "craquent", "serre", "fige", "sursaut", "hoquet", "bâille",
    "bâillement", "éternue", "démange", "picote", "engourdi", "crampe",
    "transpire", "sueur", "battement", "souffle", "respiration", "ventre",
    "faim", "soif", "fatigue", "lourd", "silence", "réveil", "endormir",
    "sommeil", "dormir", "nuit", "cœur", "coeur", "pouls",
}
ABSTRACT_CONCEPT_MARKERS = {
    "temps", "mémoire", "souvenir", "déjà-vu", "deja-vu", "stress",
    "anxiété", "pensée", "conscience", "perception", "attention",
    "émotion", "humeur", "rêve", "imagination", "vieillissant", "âge",
}
# Odds of picking from the physical pool when both pools are available.
PHYSICAL_TOPIC_BIAS = float(os.environ.get("PHYSICAL_TOPIC_BIAS", "0.75"))


def classify_topic_retention(topic: str) -> str:
    """'physical' | 'abstract' | 'neutral' — see the measurement note above."""
    text = (topic or "").lower()
    physical = sum(1 for marker in PHYSICAL_SENSATION_MARKERS if marker in text)
    abstract = sum(1 for marker in ABSTRACT_CONCEPT_MARKERS if marker in text)
    if physical > abstract:
        return "physical"
    if abstract > physical:
        return "abstract"
    return "neutral"


def _pick_by_retention_class(candidates: List[Dict]) -> Dict:
    """Prefer body-sensation topics, without ever starving the catalogue."""
    physical, other = [], []
    for record in candidates:
        target = physical if classify_topic_retention(
            record.get("topic", "")) == "physical" else other
        target.append(record)

    if physical and other:
        pool = physical if random.random() < PHYSICAL_TOPIC_BIAS else other
    else:
        pool = physical or other

    chosen = random.choice(pool)
    logger.info(
        "Topic class: %s (physical pool=%d, other=%d, bias=%.2f) -> %s",
        classify_topic_retention(chosen.get("topic", "")),
        len(physical), len(other), PHYSICAL_TOPIC_BIAS,
        chosen.get("topic", "")[:60],
    )
    return chosen


def get_body_glitch_topics() -> List[Dict]:
    """Load the fixed 500-topic Body Glitch catalogue with series metadata."""
    try:
        with BODY_GLITCH_CATALOGUE_PATH.open(encoding="utf-8") as file_handle:
            records = json.load(file_handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Body Glitch catalogue unavailable: {exc}") from exc

    result = []
    for item in records:
        topic = _clean_topic(item.get("angle") or item.get("topic", ""))
        if not topic:
            continue
        record = _topic_record(topic, "body_glitch_series_fr", pillar="reflexes_du_corps")
        record.update({
            "series_number": item.get("series_number"),
            "series_title": item.get("series_title"),
            "thumbnail_text": item.get("thumbnail_text"),
            "base_phenomenon": item.get("topic"),
            "angle": item.get("angle"),
        })
        result.append(record)
    if len(result) < 500:
        raise RuntimeError(f"Body Glitch catalogue must contain at least 500 valid topics; found {len(result)}")
    return result


def get_proven_topics() -> List[Dict]:
    """Return channel-fit evergreen topics based on proven content pillars."""
    return [_topic_record(topic, "proven_channel_pillar") for topic in PROVEN_TOPIC_POOL]


def get_trending_topic(
    exclude: Optional[List[str]] = None,
    *,
    return_metadata: bool = False,
) -> str | Dict:
    """Select a fresh topic using channel fit first and trends second.

    ``TOPIC_STRATEGY=proven_evergreen`` is the production default because the
    channel's own performance favors familiar human experiences. Live trends
    are used only as an occasional, niche-filtered inspiration signal; they
    never force unrelated news or workplace drama into a science channel.
    Set ``REQUIRE_DAILY_TREND=true`` only for a deliberate live-trend campaign.
    """
    strategy = os.environ.get("TOPIC_STRATEGY", "body_glitch_series").strip().lower()
    require_daily_trend = os.environ.get("REQUIRE_DAILY_TREND", "false").lower() == "true"

    # The Body Glitch launch is deliberately isolated from noisy general
    # trend feeds. This gives YouTube 500 tightly consistent audience signals.
    if strategy in {"body_glitch_series", "body_glitch_series_fr"}:
        series_topics = _deduplicate(get_body_glitch_topics(), exclude)
        series_topics = [t for t in series_topics
                         if not _near_duplicate_of_recent(t.get("topic", ""), exclude or [])]
        if series_topics:
            chosen = _pick_by_retention_class(series_topics)
        else:
            chosen = random.choice(get_body_glitch_topics())
            logger.warning("All Body Glitch topics were excluded; restarting the 500-topic series.")
        logger.info("Selected Body Glitch #%s: %s", chosen.get("series_number"), chosen["topic"])
        return chosen if return_metadata else str(chosen["topic"])

    records: List[Dict] = []
    records.extend(get_google_trends_topics())
    records.extend(get_youtube_trending_topics())
    records.extend(get_reddit_trending_topics())
    real_topics = _deduplicate(records, exclude)
    proven_topics = _deduplicate(get_proven_topics(), exclude)
    real_topics = [t for t in real_topics
                   if not _near_duplicate_of_recent(t.get("topic", ""), exclude or [])]
    proven_topics = [t for t in proven_topics
                     if not _near_duplicate_of_recent(t.get("topic", ""), exclude or [])]

    if require_daily_trend:
        if not real_topics:
            raise RuntimeError(
                "No relevant daily trend was available. Strict live-trend mode will not publish an off-niche fallback."
            )
        source_weight = {"youtube_trending": 3, "google_trends": 2}
        weights = [source_weight.get(str(item.get("source", "")), 1) for item in real_topics]
        chosen = random.choices(real_topics, weights=weights, k=1)[0]
    elif strategy == "live_trend" and real_topics:
        chosen = random.choice(real_topics)
    elif proven_topics:
        # During the rebuilding period, repeatedly deliver the relatable
        # experiences that already earned this channel's strongest signals.
        chosen = random.choice(proven_topics)
    elif real_topics:
        chosen = random.choice(real_topics)
    else:
        chosen = random.choice(get_proven_topics())
        logger.warning("All fresh topics were excluded; reusing a proven channel pillar.")

    logger.info(
        "Selected topic from %s: %s | source=%s",
        chosen["source"], chosen["topic"], chosen.get("source_url", "n/a"),
    )
    return chosen if return_metadata else str(chosen["topic"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print(get_trending_topic())
