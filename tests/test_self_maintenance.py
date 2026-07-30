"""Guard tests for the daily self-healing pass and the publish-slot learner.

These cover the two failure modes that silently cost the channel reach:
a single lucky upload capturing a daily slot, and a broken/collapsed schedule
going unnoticed because nothing checks it.
"""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import self_maintenance  # noqa: E402
from premium_growth_loop import build_upload_slot_intel  # noqa: E402

UTC = timezone.utc


def _video(video_id, published, views, title="Pourquoi le corps réagit"):
    return {
        "youtube_video_id": video_id,
        "title": title,
        "publish_at": published.isoformat(),
        "posted_at": published.isoformat(),
        "views": views,
        "average_view_percentage": 35.0,
    }


class SlotLearningTests(unittest.TestCase):
    """A slot must earn its place with repeated evidence, not one upload."""

    def test_single_video_slot_cannot_outrank_proven_french_peak(self):
        # One video published at 06:00 Paris (a terrible slot for France) that
        # happened to do well. Before the fix its raw score (~3.5) beat every
        # default prior (2.2-2.8), so the channel would move a daily upload to
        # 6am on the strength of a single data point.
        odd_hour = datetime(2026, 7, 20, 4, 0, tzinfo=UTC)  # 06:00 Paris
        history = [_video("lucky1", odd_hour, 1500)]

        intel = build_upload_slot_intel(history)
        slots = [s["slot"] for s in intel["recommended_slots"]]

        self.assertIn("19:30", slots,
                      "the proven French prime slot must survive a one-off outlier")

    def test_repeated_evidence_does_promote_a_slot(self):
        # Learning must still work: five consistent strong videos at 18:00
        # should be trusted, otherwise the system can never improve.
        history = []
        for i in range(5):
            when = datetime(2026, 7, 10 + i, 16, 0, tzinfo=UTC)  # 18:00 Paris
            history.append(_video(f"strong{i}", when, 5000))

        intel = build_upload_slot_intel(history)
        slots = [s["slot"] for s in intel["recommended_slots"]]

        self.assertIn("18:00", slots,
                      "a slot with repeated strong results must be adopted")

    def test_three_distinct_slots_are_always_returned(self):
        intel = build_upload_slot_intel([])
        self.assertEqual(len(intel["recommended_slots"]), 3,
                         "the channel must always have three daily peaks to fill")


class ScheduleHealthTests(unittest.TestCase):

    def test_slots_too_close_together_are_flagged(self):
        original = self_maintenance.SLOT_INTEL_PATH
        temp = ROOT / "data" / "_test_slot_intel.json"
        temp.write_text(json.dumps({"recommended_slots": [
            {"slot": "19:00", "hour": 19, "minute": 0, "samples": 5},
            {"slot": "19:30", "hour": 19, "minute": 30, "samples": 5},
            {"slot": "21:00", "hour": 21, "minute": 0, "samples": 5},
        ]}), encoding="utf-8")
        self_maintenance.SLOT_INTEL_PATH = temp
        try:
            result = self_maintenance.check_schedule_health()
        finally:
            self_maintenance.SLOT_INTEL_PATH = original
            temp.unlink(missing_ok=True)

        self.assertFalse(result["ok"])
        self.assertTrue(any("apart" in problem for problem in result["problems"]))

    def test_missing_intel_file_is_reported_not_crashed(self):
        original = self_maintenance.SLOT_INTEL_PATH
        self_maintenance.SLOT_INTEL_PATH = ROOT / "data" / "_does_not_exist.json"
        try:
            result = self_maintenance.check_schedule_health()
        finally:
            self_maintenance.SLOT_INTEL_PATH = original
        self.assertFalse(result["ok"])
        self.assertTrue(result["problems"])


class CadenceTests(unittest.TestCase):

    def test_incomplete_past_day_is_flagged(self):
        yesterday = datetime.now(UTC) - timedelta(days=1)
        history = [_video("a", yesterday, 100)]  # 1 of 3
        result = self_maintenance.check_publishing_cadence(history)
        self.assertFalse(result["ok"])
        self.assertIn(yesterday.date().isoformat(), result["short_days"])

    def test_today_is_never_flagged_while_still_in_progress(self):
        # Today legitimately has fewer videos until its last slot fires.
        history = [_video("a", datetime.now(UTC), 10)]
        result = self_maintenance.check_publishing_cadence(history)
        self.assertNotIn(datetime.now(UTC).date().isoformat(), result["short_days"])

    def test_full_cadence_passes(self):
        yesterday = datetime.now(UTC) - timedelta(days=1)
        history = [_video(f"v{i}", yesterday, 100, f"Titre unique {i}") for i in range(3)]
        result = self_maintenance.check_publishing_cadence(history, days=2)
        self.assertNotIn(yesterday.date().isoformat(), result["short_days"])


class UploadedVideoRepairTests(unittest.TestCase):

    def test_overlong_title_is_detected(self):
        now = datetime.now(UTC)
        history = [_video("long1", now, 10, "T" * 95)]
        defects = self_maintenance.find_uploaded_video_defects(history)
        self.assertEqual(len(defects), 1)
        self.assertTrue(any("truncated" in issue for issue in defects[0]["issues"]))

    def test_duplicate_titles_are_detected(self):
        now = datetime.now(UTC)
        history = [
            _video("dup1", now, 10, "Pourquoi le ventre se serre"),
            _video("dup2", now, 10, "Pourquoi le ventre se serre"),
        ]
        defects = self_maintenance.find_uploaded_video_defects(history)
        self.assertTrue(any("duplicate" in i for d in defects for i in d["issues"]))

    def test_clean_history_reports_no_defects(self):
        now = datetime.now(UTC)
        history = [_video(f"ok{i}", now, 10, f"Pourquoi le corps réagit {i}") for i in range(3)]
        self.assertEqual(self_maintenance.find_uploaded_video_defects(history), [])

    def test_repair_is_dry_run_unless_explicitly_enabled(self):
        import os
        old = os.environ.pop("SELF_MAINTENANCE_APPLY", None)
        try:
            self.assertFalse(self_maintenance._apply_enabled(),
                             "repair must never write to YouTube by default")
            os.environ["SELF_MAINTENANCE_APPLY"] = "true"
            self.assertTrue(self_maintenance._apply_enabled())
        finally:
            os.environ.pop("SELF_MAINTENANCE_APPLY", None)
            if old is not None:
                os.environ["SELF_MAINTENANCE_APPLY"] = old


class WiringTests(unittest.TestCase):

    def test_maintenance_runs_after_analytics_sync(self):
        source = (ROOT / "src" / "analytics_updater.py").read_text(encoding="utf-8")
        self.assertIn("self_maintenance", source,
                      "the healing pass must be wired into the daily analytics job")

    def test_maintenance_never_fails_the_analytics_job(self):
        source = (ROOT / "src" / "analytics_updater.py").read_text(encoding="utf-8")
        index = source.index("self_maintenance")
        self.assertIn("except Exception", source[index - 400:index + 400],
                      "a monitoring pass must not take down analytics sync")


if __name__ == "__main__":
    unittest.main()
