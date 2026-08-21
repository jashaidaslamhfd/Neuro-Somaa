import json
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPETITOR_INTEL_PATH = ROOT / "data" / "competitor_intel_fr.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("competitor_hijacker_fr")

# French niche keywords for relevance checking
BODY_KEYWORDS_FR = {
    "cerveau",
    "corps",
    "sommeil",
    "coeur",
    "cœur",
    "ventre",
    "muscle",
    "nerf",
    "frisson",
    "bâillement",
    "bâille",
    "yeux",
    "oeil",
    "œil",
    "peau",
    "gorge",
    "fatigue",
    "estomac",
    "mémoire",
    "stress",
    "tête",
}


def fetch_youtube_autosuggest_fr(seed: str) -> list[str]:
    """
    Scrapes Google's public YouTube autosuggest endpoint to find real-time
    high-demand keyword variations in French.
    """
    try:
        encoded_seed = urllib.parse.quote(seed)
        url = f"http://suggestqueries.google.com/complete/search?client=youtube&hl=fr&ds=yt&q={encoded_seed}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8", "ignore")
            queries = re.findall(r'"([^"]*)"', content)
            suggestions = [q for q in queries if q.lower() != seed.lower() and len(q) > len(seed)]
            return list(dict.fromkeys(suggestions))
    except Exception as exc:
        logger.warning(f"YouTube FR autosuggest fetch failed for seed '{seed}': {exc}")
        return []


def get_competitor_channels_fr() -> list[dict]:
    """Loads French competitor video profiles from the compiled config."""
    if COMPETITOR_INTEL_PATH.exists():
        try:
            with open(COMPETITOR_INTEL_PATH, encoding="utf-8") as f:
                data = json.load(f)
            # French channel stores reference videos in reference_videos_for_human_review
            return data.get("reference_videos_for_human_review", [])
        except Exception as exc:
            logger.warning(f"Error reading competitor intel: {exc}")
    return []


def score_topic_fr(topic: str, source: str, views: int = 0) -> dict:
    """
    Scores a candidate French topic on relevance, structure, and virality.
    """
    score = 50  # Base score
    lowered = topic.lower()

    # 1. Niche Fit (Body / Brain / Science alignment in French)
    matches = sum(1 for kw in BODY_KEYWORDS_FR if kw in lowered)
    score += min(matches * 15, 30)  # Max 30 points for keyword density

    # 2. Strong Hook Structure Check (French patterns)
    if lowered.startswith(("pourquoi votre", "pourquoi le", "pourquoi on")):
        score += 15
    elif lowered.startswith(("ce qui se passe quand", "ce que votre corps", "la science derrière")):
        score += 10

    # 3. Virality Multiplier
    if views > 1000000:
        score += 10
    elif views > 500000:
        score += 5

    return {"topic": topic, "title": topic, "source": source, "score": min(score, 100), "views": views}


def get_hijacked_viral_topic_fr(exclude_list: list[str] | None = None) -> dict:
    """
    Main orchestrator for the French Viral Hijacker:
    1. Scrapes YouTube autosuggest in French for popular searches.
    2. Analyzes French competitor channel uploads.
    3. Scores all candidates on niche relevance and virality.
    4. Picks the single best-performing topic.
    """
    exclude_list = exclude_list or []
    normalized_excludes = [t.lower().strip() for t in exclude_list]

    candidates = []

    # --- Step 1: Real-time YouTube Autosuggest (French) ---
    logger.info("Step 1/3: Harvesting real-time YouTube France search trends...")
    seeds = ["pourquoi votre corps", "pourquoi le cerveau", "ce qui se passe quand le", "pourquoi on a la"]
    for seed in seeds:
        suggestions = fetch_youtube_autosuggest_fr(seed)
        for sug in suggestions:
            topic_title = sug.capitalize()
            candidates.append(score_topic_fr(topic_title, "youtube_autosuggest_fr"))

    # --- Step 2: Competitor Viral Hijacking ---
    logger.info("Step 2/3: Analyzing French competitor million-view uploads...")
    competitors = get_competitor_channels_fr()
    for vid in competitors:
        title = vid.get("title", "")
        title = re.sub(r"&amp;|&quot;|&#39;|&#x27;", "", title)
        title = re.sub(r"\[.*?\]|\(.*?\)", "", title).strip()
        view_count = vid.get("views", 1000000)
        candidates.append(score_topic_fr(title, "competitor_hijack_fr", view_count))

    # --- Step 3: Filtering, Deduplicating, and Selection ---
    logger.info("Step 3/3: Evaluating, filtering and selecting the ultimate French winner...")

    relevant_candidates = []
    seen = set()
    for cand in candidates:
        topic_normalized = cand["topic"].lower().strip()
        if (
            topic_normalized not in seen
            and topic_normalized not in normalized_excludes
            and any(kw in topic_normalized for kw in BODY_KEYWORDS_FR)
        ):
            seen.add(topic_normalized)
            relevant_candidates.append(cand)

    if not relevant_candidates:
        # Fallback to a proven French evergreen pillar
        fallback_topic = "Pourquoi le bâillement est contagieux"
        logger.warning(f"No suitable French candidates; falling back to: {fallback_topic}")
        return score_topic_fr(fallback_topic, "viral_hijack_fallback_fr", 1200000)

    # Sort by score
    relevant_candidates.sort(key=lambda x: -x["score"])

    # Pick randomly from the top 5 candidates
    top_candidates = relevant_candidates[:5]
    import random

    winner = random.choice(top_candidates)

    logger.info(
        f"🏆 French Winner Chosen: '{winner['topic']}' | Source: {winner['source']} | Score: {winner['score']}/100"
    )

    return winner
