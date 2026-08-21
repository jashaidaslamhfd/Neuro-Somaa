"""Measured-truth picker tests (2026-08-12): topic choice must be grounded in
REAL measured outcomes, and every analytics sync must record whether a video
is still growing or has stalled ('views ruk gaye' must be a measured fact)."""

import datetime as dt
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import seo_analytics
import trend_fetcher


def _history(rows):
    out = []
    for i, (topic, views, ret) in enumerate(rows):
        out.append(
            {
                "topic": topic,
                "title": topic,
                "views": views,
                "average_view_percentage": ret,
                "youtube_video_id": f"v{i}",
                "posted_at": "2026-07-01T00:00:00+00:00",
            }
        )
    return out


class MeasuredTopicBoostTests(unittest.TestCase):
    def setUp(self):
        # corpus family retains great, flop family retains terribly
        rows = [(f"Pourquoi votre corps devient lourd numero {i}", 600, 45.0) for i in range(6)]
        rows += [(f"Pourquoi le temps semble accelerer version {i}", 600, 25.0) for i in range(6)]
        self.h = _history(rows)

    def test_good_family_is_boosted(self):
        cands = [
            {"topic": "Pourquoi votre corps devient lourd apres le sport"},
            {"topic": "Pourquoi le temps semble accelerer en vieillissant"},
        ]
        boosted, rest = trend_fetcher._measured_topic_boost(cands, self.h)
        self.assertEqual([c["topic"] for c in boosted], ["Pourquoi votre corps devient lourd apres le sport"])
        self.assertEqual(len(rest), 1)

    def test_bad_family_is_not_boosted(self):
        cands = [{"topic": "Pourquoi le temps semble accelerer en vieillissant"}]
        boosted, _ = trend_fetcher._measured_topic_boost(cands, self.h)
        self.assertEqual(boosted, [])

    def test_picker_prefers_boosted_pool(self):
        cands = [
            {"topic": "Pourquoi votre corps devient lourd apres le sport"},
            {"topic": "Pourquoi le temps semble accelerer en vieillissant"},
        ]
        picks = {trend_fetcher._pick_by_retention_class(cands, history=self.h)["topic"] for _ in range(10)}
        self.assertEqual(picks, {"Pourquoi votre corps devient lourd apres le sport"})

    def test_empty_history_falls_back_to_class_bias(self):
        cands = [{"topic": "Pourquoi la peau fait la chair de poule"}]
        chosen = trend_fetcher._pick_by_retention_class(cands, history=[])
        self.assertEqual(chosen["topic"], cands[0]["topic"])


class GrowthClassificationTests(unittest.TestCase):
    def test_first_read(self):
        g = seo_analytics._classify_growth(None, None, 100, dt.datetime.now(dt.UTC))
        self.assertEqual(g["growth_state"], "first_read")

    def test_growing(self):
        prev_at = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=24)).isoformat()
        g = seo_analytics._classify_growth(100, prev_at, 160, dt.datetime.now(dt.UTC))
        self.assertEqual(g["growth_state"], "growing")
        self.assertAlmostEqual(g["views_per_day"], 60.0, places=0)

    def test_flat_zero_growth_is_detected(self):
        prev_at = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=24)).isoformat()
        g = seo_analytics._classify_growth(500, prev_at, 500, dt.datetime.now(dt.UTC))
        self.assertEqual(g["growth_state"], "flat")
        self.assertEqual(g["views_per_day"], 0.0)

    def test_velocity_scales_with_gap(self):
        prev_at = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=48)).isoformat()
        g = seo_analytics._classify_growth(100, prev_at, 200, dt.datetime.now(dt.UTC))
        self.assertAlmostEqual(g["views_per_day"], 50.0, delta=2.0)


if __name__ == "__main__":
    unittest.main()
