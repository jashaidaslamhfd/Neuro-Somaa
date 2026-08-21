"""Tests for the DS/ML/DL intelligence layer (src/intelligence/).

Each module is tested on SYNTHETIC data where ground truth is known, plus
the honesty guards (tiny-n refusal states) that protect a small channel from
its own noise.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _video(
    title: str, views: int, hook: float = 70.0, day: int = 1, hour: int = 19, retention: float = 40.0
) -> dict:
    return {
        "youtube_video_id": f"{title[:6]}{views}",
        "title": title,
        "topic": title.rstrip(" ?"),
        "views": views,
        "hook_score": hook,
        "seo_score": 80.0,
        "predicted_ctr": 4.0,
        "predicted_retention": retention / 100,
        "average_view_percentage": retention,
        "publish_at": f"2026-07-{min(day, 28):02d}T{hour:02d}:30:00+00:00",
    }


class FeatureTests(unittest.TestCase):
    def test_features_extract_question_and_person(self):
        from intelligence import features

        row = features.extract_features(_video("Pourquoi votre cœur bat plus vite ?", 500))
        self.assertEqual(row["is_question"], 1.0)
        self.assertEqual(row["starts_pourquoi"], 1.0)
        self.assertEqual(row["has_second_person"], 1.0)

    def test_dataset_only_uses_real_views(self):
        from intelligence import features

        rows, _y, _ids = features.build_dataset(
            [
                _video("A ok ?", 300),
                {"title": "ghost", "views": None},
            ]
        )
        self.assertEqual(len(rows), 1)

    def test_topic_bucket_stable_across_imports(self):
        from intelligence import features

        a = features.extract_features(_video("X stable ?", 100, retention=40))
        b = features.extract_features(_video("X stable ?", 100, retention=40))
        self.assertEqual(
            [a[k] for k in a if k.startswith("topic_bucket")],
            [b[k] for k in b if k.startswith("topic_bucket")],
        )


class RidgeModelTests(unittest.TestCase):
    def test_ridge_learns_clean_signal(self):
        import random

        from intelligence import models

        rng = random.Random(2)
        rows, y = [], []
        for _ in range(60):
            hook = rng.uniform(0, 1)
            words = rng.uniform(4, 10)
            # views driven mostly by hook_score
            log_views = math.log1p(100 + 900 * hook + 10 * words + rng.gauss(0, 15))
            rows.append({"hook_score": hook, "title_words": words})
            y.append(log_views)
        report = models.kfold_r2(rows, y, ["hook_score", "title_words"])
        self.assertTrue(report["reliable"], report)
        self.assertGreater(report["cv_r2_mean"], 0.5)

    def test_ridge_refuses_tiny_data(self):
        from intelligence import models

        report = models.kfold_r2([{"a": 1.0}] * 5, [1.0] * 5, ["a"])
        self.assertFalse(report["reliable"])

    def test_empty_dataset_does_not_crash(self):
        from intelligence import models

        out = models.compare_models([], [], ["a"])
        self.assertFalse(out["ridge"]["reliable"])


class TinyMLPTests(unittest.TestCase):
    def test_mlp_fits_better_than_constant(self):
        import random

        from intelligence.models import TinyMLP

        rng = random.Random(9)
        rows, y = [], []
        for _ in range(50):
            x1, x2 = rng.uniform(-1, 1), rng.uniform(-1, 1)
            rows.append({"x1": x1, "x2": x2})
            y.append(2 * x1 - x2 + rng.gauss(0, 0.05))
        mlp = TinyMLP(epochs=400).fit(rows, y, ["x1", "x2"])
        preds = [mlp.predict_views_again if False else mlp.predict_views(r) for r in rows]
        avg_pred = sum(preds) / len(preds)
        true = [math.expm1(t) for t in y]
        mae_model = sum(abs(p - t) for p, t in zip(preds, true, strict=False)) / len(true)
        mae_const = sum(abs(avg_pred - t) for t in true) / len(true)
        self.assertLess(mae_model, mae_const * 0.8)


class BanditTests(unittest.TestCase):
    def test_thompson_prefers_better_arm_with_enough_samples(self):
        from intelligence import bandit

        history = [_video(f"Pourquoi sujet {i} ?", 1500) for i in range(8)]
        history += [_video(f"Ce qu'il faut savoir {i}", 80) for i in range(8)]
        report = bandit.bandit_report(history)
        rec = report["recommended_pattern"]
        self.assertIsNotNone(rec)
        self.assertEqual(rec["pattern"], "POURQUOI")

    def test_small_samples_are_never_recommended(self):
        from intelligence import bandit

        # one pattern with 2 great videos — must NOT be recommended
        history = [_video(f"Pourquoi sujet {i} ?", 400) for i in range(8)]
        history += [_video("Comment rare winner ?", 9000), _video("Comment autre ?", 8000)]
        report = bandit.bandit_report(history)
        self.assertEqual(report["recommended_pattern"]["pattern"], "POURQUOI")
        self.assertFalse(report["arms"]["COMMENT"]["confident"])


class AnomalyTests(unittest.TestCase):
    def test_obvious_outlier_flagged(self):
        from intelligence import anomaly

        normal = [_video(f"Pourquoi normal {i} ?", 700 + i * 3) for i in range(20)]
        dead = _video("Pourquoi celle-ci est morte ?", 12)
        out = anomaly.detect_anomalies([*normal, dead])
        self.assertTrue(out["reliable"])
        flagged_ids = [a["video_id"] for a in out["anomalies"]]
        self.assertIn(dead["youtube_video_id"], flagged_ids)

    def test_typical_video_not_flagged(self):
        from intelligence import anomaly

        normal = [_video(f"Pourquoi normal {i} ?", 650 + i * 7) for i in range(21)]
        out = anomaly.detect_anomalies(normal)
        self.assertEqual(out["anomalies"], [])


class ForecastTests(unittest.TestCase):
    def test_holt_follows_linear_trend(self):
        from intelligence import forecast

        series = [100 + 5 * i for i in range(40)]
        out = forecast.holt_forecast(series)
        self.assertTrue(out["reliable"])
        last = out["forecast_daily_views"][-1]
        self.assertGreater(last, series[-1])

    def test_refuses_short_series(self):
        from intelligence import forecast

        out = forecast.holt_forecast([100.0] * 10)
        self.assertFalse(out["reliable"])


class ClusteringTests(unittest.TestCase):
    def test_separable_themes_get_own_clusters(self):
        from intelligence import clustering

        heart = [_video(f"Pourquoi le cœur bat plus fort {i} ?", 900) for i in range(10)]
        sleep = [_video(f"Pourquoi le sommeil profond répare {i} ?", 300) for i in range(10)]
        out = clustering.cluster_topics(heart + sleep, max_k=2)
        self.assertTrue(out["reliable"])
        names = [c["name"] for c in out["clusters"]]
        self.assertTrue(any("cœur" in n for n in names))
        self.assertTrue(any("sommeil" in n for n in names))


class StatsTests(unittest.TestCase):
    def test_permutation_detects_clear_difference(self):
        from intelligence import stats

        out = stats.permutation_test([1500.0] * 8, [80.0] * 8, iters=2000)
        self.assertTrue(out["significant"])
        self.assertLess(out["p_value"], 0.05)

    def test_permutation_honest_about_equal_arms(self):
        from intelligence import stats

        out = stats.permutation_test([700.0, 720, 680, 710] * 2, [705.0, 695, 715, 700] * 2, iters=2000)
        self.assertFalse(out["significant"])

    def test_permutation_refuses_tiny_arms(self):
        from intelligence import stats

        out = stats.permutation_test([100.0, 200.0], [300.0])
        self.assertFalse(out["significant"])
        self.assertIn("reason", out)


class EndToEndReportTests(unittest.TestCase):
    def test_run_all_produces_report_files(self):
        import json
        import tempfile

        from intelligence import run_all

        history = [_video(f"Pourquoi le sujet {i} surprend ?", 500 + i * 40, day=1 + i) for i in range(25)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vh.json"
            path.write_text(json.dumps(history), encoding="utf-8")
            report = run_all(path)
        self.assertEqual(report["n_videos_analyzed"], 25)
        self.assertIn("models", report)
        self.assertIn("bandit", report)
        dash = ROOT / "data" / "intelligence_dashboard_latest.md"
        self.assertTrue(dash.exists())
        self.assertIn("Intelligence Dashboard", dash.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
