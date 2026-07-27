#!/usr/bin/env python3
"""
scripts/generate_fallback_images.py
------------------------------------
One-time (or periodic) builder for the local pre-generated image pool at
assets/fallback_images/. This is fallback LAYER 2 in image_generator.py -
it exists so that when every live AI provider (Pollinations/AI-Horde/
HuggingFace/Gemini/DeepAI/...) is rate-limited or down for a given run,
scenes don't have to fall straight through to generic Pexels/Pixabay stock
photos (which trip the pipeline's fallback-ratio quality gate - this is
exactly what happened in the 88.9% fallback-ratio failure).

Run this SEPARATELY from the per-video pipeline - e.g. overnight, or
whenever provider quota/traffic is healthy - NOT as part of every run. It
walks the channel's static DARK_TOPICS pool, builds the same on-brand
dark/moody prompt used for live scenes, and tries every registered
provider (in the same fallback order as image_generator.py) until one
succeeds, saving the result into assets/fallback_images/.

Usage:
    python scripts/generate_fallback_images.py --count 100
    python scripts/generate_fallback_images.py --count 300 --out-dir assets/fallback_images --delay 5
"""

import argparse
import logging
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from image_generator import _build_prompt
from image_providers import RateLimitError, available_providers
from niche_strategy import DARK_TOPICS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _existing_count(out_dir: str) -> int:
    if not os.path.isdir(out_dir):
        return 0
    return len([f for f in os.listdir(out_dir) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))])


def build_pool(count: int, out_dir: str, delay: float = 3.0) -> None:
    os.makedirs(out_dir, exist_ok=True)
    providers = available_providers()
    if not providers:
        logger.error("No AI providers available (check API keys / network) - nothing to generate.")
        return

    start_index = _existing_count(out_dir)
    logger.info(
        f"Building fallback pool: {count} new image(s) -> {out_dir} "
        f"(pool currently has {start_index}, {len(providers)} provider(s) available)"
    )

    made = 0
    attempt = 0
    max_attempts = count * 6  # generous ceiling so a bad streak of failures doesn't loop forever

    while made < count and attempt < max_attempts:
        topic = DARK_TOPICS[attempt % len(DARK_TOPICS)]
        attempt += 1
        prompt_text = _build_prompt(topic)
        prompt = prompt_text.replace(" ", "_").replace(",", "")
        seed = random.randint(1, 999999)

        saved = False
        for provider in providers:
            try:
                image_bytes, ext = provider["generate"](prompt, seed, prompt_text)
                if not image_bytes or len(image_bytes) < 2000:
                    raise RuntimeError(f"{provider['name']}: empty/too-small response")
                path = os.path.join(out_dir, f"pool_{start_index + made:04d}.{ext}")
                with open(path, "wb") as f:
                    f.write(image_bytes)
                logger.info(f"[{made + 1}/{count}] '{topic}' via {provider['name']} -> {path}")
                made += 1
                saved = True
                break
            except RateLimitError as e:
                logger.warning(f"'{topic}' - {provider['name']} rate-limited: {e}")
                continue
            except Exception as e:
                logger.warning(f"'{topic}' - {provider['name']} failed: {e}")
                continue

        if not saved:
            logger.error(f"'{topic}' - all providers failed for this topic, skipping.")

        time.sleep(delay)  # be polite to free/shared APIs

    if attempt >= max_attempts and made < count:
        logger.error(
            f"Stopped after {attempt} attempts with only {made}/{count} generated - "
            f"providers may be out of quota right now. Re-run later to top up the pool."
        )

    logger.info(f"Done. Pool now has {_existing_count(out_dir)} image(s) in {out_dir}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build/top-up the local fallback image pool.")
    parser.add_argument("--count", type=int, default=100, help="How many NEW images to generate this run.")
    parser.add_argument("--out-dir", type=str, default="assets/fallback_images", help="Output directory.")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds to wait between requests (politeness).")
    args = parser.parse_args()

    build_pool(args.count, args.out_dir, args.delay)
