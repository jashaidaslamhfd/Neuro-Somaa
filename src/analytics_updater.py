"""
src/analytics_updater.py

Standalone entrypoint for pulling REAL YouTube Analytics numbers into
output/video_history.json.

IMPORTANT: run this on a SEPARATE cron/GitHub Actions schedule from the
main pipeline (main.py) - e.g. once a day. YouTube Analytics data is not
available immediately after upload (usually needs 24-48h to populate),
so this only touches history entries that are already at least
`min_hours_old` (default 24h).

Requires the SAME OAuth env vars as uploader.py:
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, REFRESH_TOKEN
...and that REFRESH_TOKEN must additionally have been issued with the
`yt-analytics.readonly` scope (uploader.py's upload flow only needs
youtube.upload + youtube.force-ssl, so if your existing token was minted
before this feature, you'll need to re-consent once with the extra scope).

Usage:
    python src/analytics_updater.py

Example GitHub Actions cron (runs daily at 06:00 UTC):
    on:
      schedule:
        - cron: '0 6 * * *'
"""
import logging
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
from seo_analytics import update_history_with_real_metrics

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    result = update_history_with_real_metrics(min_hours_old=24)
    logger.info(f"Analytics update complete: {result}")

    # After real metrics land in video_history.json, refresh every learned
    # growth signal that depends on them — especially dynamic publish slots.
    # Non-fatal: analytics sync must not fail just because a dashboard report
    # could not be generated.
    try:
        from premium_growth_loop import main as premium_growth_main
        premium_growth_main([])
        logger.info("Premium growth intelligence refreshed after analytics sync")
    except Exception as exc:
        logger.warning("Premium growth intelligence refresh skipped: %s", exc)
