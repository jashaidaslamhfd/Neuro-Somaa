"""
Neuro-Somaa Autonomous Brain Logic.
Allows the system to make decisions based on French audience performance.
"""

import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
GROWTH_PLAN_PATH = ROOT / "data" / "fr_optimize_plan.json"
HISTORY_PATH = ROOT / "data" / "video_history.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("autonomous_brain")

def get_performance_weights():
    """Extract topic and hook weights from history data."""
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    except:
        return {}

    topic_stats = {}
    for entry in history:
        topic = entry.get("topic", "unknown").lower()
        views = int(entry.get("youtube_shorts", {}).get("views", 0) or 0)
        
        if topic not in topic_stats:
            topic_stats[topic] = []
        topic_stats[topic].append(views)
    
    # Calculate average views per topic
    weights = {t: sum(v)/len(v) for t, v in topic_stats.items() if v}
    return weights

def decide_next_strategy():
    """Autonomous decision making for the next run."""
    weights = get_performance_weights()
    
    # If a topic has > 500 views, it's a winner in France
    winners = [t for t, v in weights.items() if v > 500]
    
    if winners:
        logger.info(f"🧠 Brain Decision: Doubling down on winning French topics: {winners[:3]}")
        return {"mode": "winning_streak", "topics": winners}
    
    logger.info("🧠 Brain Decision: No clear winners yet. Continuing trend discovery.")
    return {"mode": "discovery"}

def apply_learned_weights_to_topics(topics):
    """Sort candidates by learned performance."""
    weights = get_performance_weights()
    
    def score(t):
        t_clean = t.lower().strip()
        # High boost for proven winners
        return weights.get(t_clean, 0)
    
    return sorted(topics, key=score, reverse=True)

