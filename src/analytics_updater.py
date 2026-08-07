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
    # Step A — build the cross-platform metric store (YouTube + FB + IG). This
    # was previously never called, so data/platform_metrics.json stayed `{}`
    # and the growth engine had nothing to learn from.
    try:
        from platform_metrics import collect as collect_platform_metrics

        result = collect_platform_metrics(min_hours_old=24, refresh_hours=20)
        logger.info("Platform metrics refreshed: %s", result.get("stats"))
    except Exception as exc:
        logger.warning("Platform metrics collection skipped: %s", exc)

    # Step B — learn from that store (slot/topic/hook weights + cadence) and
    # write data/growth_state.json, which the scheduler/trend-fetcher read.
    try:
        from growth_engine import analyse as growth_analyse

        state = growth_analyse()
        logger.info(
            "Growth engine learned: cadence=%s best_slot=%s samples=%s",
            state.get("recommended_cadence"), state.get("best_slot"),
            state.get("sample_size"),
        )
    except Exception as exc:
        logger.warning("Growth engine analysis skipped: %s", exc)

    # Step C — AUTONOMOUS CONTROLS: turn learned signals into enforced
    # decisions (cadence, topic blocklist, throttle, auto-repair list). This
    # is what lets the ML actually MANAGE the system instead of just reporting.
    try:
        from autonomous_controller import analyse as autonomous_analyse

        controls = autonomous_analyse()
        logger.info(
            "Autonomous controls: cadence=%d throttle=%s block=%d repairs=%d",
            controls.get("recommended_cadence"), controls.get("throttle"),
            len(controls.get("topic_blocklist", [])),
            controls.get("auto_repair_count", 0),
        )
    except Exception as exc:
        logger.warning("Autonomous controls skipped: %s", exc)

    try:
        from premium_growth_loop import main as premium_growth_main
        premium_growth_main([])
        logger.info("Premium growth intelligence refreshed after analytics sync")
    except Exception as exc:
        logger.warning("Premium growth intelligence refresh skipped: %s", exc)

    # Self-healing pass. Must run AFTER the growth loop rewrote the publish
    # slots, so it validates the schedule the channel will actually use today.
    # Repairing already-uploaded videos also belongs here rather than in
    # main.py: it needs the real analytics numbers this job just fetched, and
    # it must not add minutes to the time-critical generate-and-upload run.
    try:
        from self_maintenance import main as self_maintenance_main
        self_maintenance_main([])
        logger.info("Self-maintenance pass complete")
    except Exception as exc:
        logger.warning("Self-maintenance pass skipped: %s", exc)
