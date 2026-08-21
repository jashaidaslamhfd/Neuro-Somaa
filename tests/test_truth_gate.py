"""Truth Gate tests — the pipeline must never trust a score it can't prove.

Includes the LIVE-data regression: on the channel's real 47-video history,
hook_score is noise (r≈-0.08) and seo_score is inverted (r≈-0.16). If a
future, genuinely better rubric makes them predictive (n>=12, r>0.35), these
tests flip red on purpose — that flip would be real news, not a bug.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from intelligence import truth_gate as tg

ROOT = Path(__file__).resolve().parents[1]


class TestSpearman(unittest.TestCase):
    def test_perfect_monotone(self):
        xs = list(range(1, 15))
        self.assertAlmostEqual(tg.spearman(xs, xs), 1.0, places=6)

    def test_perfect_inverse(self):
        xs = list(range(1, 15))
        self.assertAlmostEqual(tg.spearman(xs, list(reversed(xs))), -1.0, places=6)

    def test_too_small_is_none(self):
        self.assertIsNone(tg.spearman([1, 2], [1, 2]))

    def test_constant_series_is_none(self):
        self.assertIsNone(tg.spearman([5] * 10, list(range(10))))

    def test_pure_noise_is_tiny(self):
        import random

        xs = list(range(1, 17))
        ys = xs[:]
        random.Random(13).shuffle(ys)  # verified r = +0.009
        r = tg.spearman(xs, ys)
        self.assertIsNotNone(r)
        self.assertLess(abs(r), 0.15)

    def test_adversarial_is_inverted(self):
        # high self-grades paired with LOW real views: the fake-score pattern
        xs = [70 + (i % 5) * 10 for i in range(14)]
        ys = [1400 - i * 100 for i in range(14)]
        r = tg.spearman(xs, ys)
        self.assertIsNotNone(r)
        self.assertLessEqual(r, -0.15)


class TestVerdicts(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(tg._verdict(None, 5), "INSUFFICIENT_DATA")
        self.assertEqual(tg._verdict(0.9, 5), "INSUFFICIENT_DATA")  # n wins over r
        self.assertEqual(tg._verdict(-0.4, 30), "INVERTED")
        self.assertEqual(tg._verdict(0.08, 30), "NOISE")
        self.assertEqual(tg._verdict(0.22, 30), "WEAK")
        self.assertEqual(tg._verdict(0.6, 30), "CALIBRATED")


class TestCalibration(unittest.TestCase):
    def _hist(self, pairs):
        return [{"hook_score": p, "views": v, "average_view_percentage": r} for p, v, r in pairs]

    def test_uncalibrated_metric_is_locked_out(self):
        # high self-grades on LOW-view videos, low grades on winners: the
        # live channel's actual signature — must be locked out of decisions.
        pairs = [(70 + (i % 5) * 10, max(3, 1400 - i * 100), 35.0) for i in range(14)]
        cal = tg.calibrate_scores(self._hist(pairs))
        self.assertIn(cal["hook_score"]["verdict"], ("NOISE", "INVERTED"))
        self.assertFalse(cal["hook_score"]["decision_usable"])

    def test_constant_metric_cannot_be_judged(self):
        # zero variance → no correlation computable → honest INSUFFICIENT_DATA
        pairs = [(85, v, 35.0) for v in range(20)]
        cal = tg.calibrate_scores(self._hist(pairs))
        self.assertEqual(cal["hook_score"]["verdict"], "INSUFFICIENT_DATA")
        self.assertFalse(cal["hook_score"]["decision_usable"])

    def test_predictive_metric_unlocks(self):
        pairs = [(40 + i * 4, 100 + i * 100, 30.0) for i in range(15)]
        cal = tg.calibrate_scores(self._hist(pairs))
        self.assertEqual(cal["hook_score"]["verdict"], "CALIBRATED")
        self.assertTrue(cal["hook_score"]["decision_usable"])

    def test_bias_measured(self):
        hist = [
            {"hook_score": 80, "views": 500, "average_view_percentage": 38.0, "predicted_retention": 0.70}
            for _ in range(15)
        ]
        cal = tg.calibrate_scores(hist)
        self.assertAlmostEqual(cal["predicted_retention"]["bias"], 0.32, places=2)


class TestEmpiricalPrediction(unittest.TestCase):
    def test_similar_videos_drive_the_prior(self):
        hist = [
            {
                "topic": "le ventre qui gargouille sans faim",
                "title": "Pourquoi le ventre gargouille sans faim ?",
                "views": 731,
                "average_view_percentage": 47.0,
            },
            {
                "topic": "le ventre qui se serre quand on a peur",
                "title": "Pourquoi le ventre se serre quand on a peur ?",
                "views": 1456,
                "average_view_percentage": 27.0,
            },
            {
                "topic": "le ventre qui gargouille le matin",
                "title": "Pourquoi le ventre gargouille le matin ?",
                "views": 900,
                "average_view_percentage": 40.0,
            },
            {
                "topic": "le cœur qui bat la nuit",
                "title": "Pourquoi on entend son cœur battre la nuit ?",
                "views": 637,
                "average_view_percentage": 48.0,
            },
        ] * 4  # n=16 so mins are met
        pred = tg.empirical_prediction("Pourquoi le ventre se serre au réveil ?", hist)
        self.assertEqual(pred["confidence"], "SIMILAR_VIDEOS")
        # pool = 8 strongest of the 12 ventre matches — the cœur video
        # must NOT leak into a ventre prediction
        self.assertTrue(731 <= pred["views_median"] <= 1456)
        self.assertEqual(pred["n"], 8)  # pool capped at 8 strongest similars
        self.assertTrue(all("ventre" in t.lower() or "peur" in t.lower() for t in pred["similar"]))

    def test_unknown_topic_falls_back_honestly(self):
        hist = [
            {"topic": "xyz", "title": "Pourquoi xyz arrive ?", "views": 500, "average_view_percentage": 40.0}
            for _ in range(20)
        ]
        pred = tg.empirical_prediction("phalène nocturne quantique", hist)
        self.assertEqual(pred["confidence"], "GLOBAL_FALLBACK")
        self.assertEqual(pred["views_median"], 500)

    def test_empty_history_is_unknown_not_fake_precision(self):
        pred = tg.empirical_prediction("anything", [])
        self.assertEqual(pred["confidence"], "UNKNOWN")
        self.assertIsNone(pred["views_median"])


class TestStatusFile(unittest.TestCase):
    def test_missing_status_means_advisory_only(self):
        self.assertIsNone(tg.load_status(Path("/tmp/__no_such_truth__.json")))

    def test_status_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "truth_status.json"
            hist = [
                {"hook_score": 80, "views": 100 * i, "average_view_percentage": 40.0} for i in range(1, 16)
            ]
            out = tg.run(hist, p)
            self.assertTrue(p.exists())
            loaded = tg.load_status(p)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["hook_score"]["verdict"], out["status"]["hook_score"]["verdict"])


class TestLiveDataTruth(unittest.TestCase):
    """The killer test: on the channel's REAL history, the self-graded hook
    and SEO scores must be exposed as non-predictive. If this ever goes green
    (CALIBRATED) — celebrate and update the test, it means the rubric learned
    to predict reality."""

    def test_real_scores_are_exposed(self):
        hist_path = ROOT / "data" / "video_history.json"
        history = json.loads(hist_path.read_text(encoding="utf-8"))
        cal = tg.calibrate_scores(history)
        self.assertGreaterEqual(cal["hook_score"]["n"], 40)
        self.assertIn(
            cal["hook_score"]["verdict"],
            ("NOISE", "INVERTED"),
            f"hook_score claims predictive power: {cal['hook_score']}",
        )
        self.assertFalse(cal["hook_score"]["decision_usable"])
        self.assertIn(cal["seo_score"]["verdict"], ("NOISE", "INVERTED"))
        self.assertIsNotNone(cal["predicted_retention"].get("bias"))
        self.assertGreater(
            cal["predicted_retention"]["bias"],
            0.15,
            "predicted_retention bias shrank — re-audit before trusting",
        )


if __name__ == "__main__":
    unittest.main()
