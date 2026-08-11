"""Regression tests for the 2026-08-11 deep audit fixes.

Covers:
  1. CTR metric identifier must be the real YouTube Analytics name
     (`impressionClickThroughRate`), never the silently-dropped misspelling.
  2. Learned publish slots: a 1-4 sample slot must NEVER capture a daily
     publish slot while prior-backed defaults are available.
  3. French quality gate: a verb-less French question title is hard-blocked.
  4. Thumbnail hooks: bare labels are downgraded to a verb-ful question hook.
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


class CtrMetricNameTests(unittest.TestCase):
    """The CTR metric's real identifier is `impressionClickThroughRate`."""

    def test_sync_requests_correct_ctr_metric(self):
        src = (ROOT / "src" / "seo_analytics.py").read_text(encoding="utf-8")
        self.assertIn('"impressionClickThroughRate"', src)
        # the misspelled request form must not survive outside explanatory comments
        code_lines = [
            line for line in src.splitlines()
            if not line.lstrip().startswith("#")
        ]
        self.assertNotIn('"impressionsClickThroughRate"', "\n".join(code_lines))

    def test_seo_diag_uses_correct_ctr_metric(self):
        src = (ROOT / "scripts" / "seo_diag.py").read_text(encoding="utf-8")
        self.assertIn("impressionClickThroughRate", src)
        self.assertNotIn("impressionsClickThroughRate", src)


class SlotConfidenceTests(unittest.TestCase):
    """Tiny-sample slots inform the table but never the daily schedule."""

    def _video(self, vid: str, when: datetime, views: int):
        return {
            "youtube_video_id": vid,
            "publish_at": when.isoformat(),
            "views": views,
            "average_view_percentage": 45.0,
        }

    def test_low_sample_slot_never_displaces_default(self):
        from premium_growth_loop import build_upload_slot_intel

        # 4 strong videos at 06:00 Paris — below the 5-sample confidence bar.
        history = [
            self._video(f"low{i}", datetime(2026, 7, 10 + i, 4, 0, tzinfo=timezone.utc), 20000)
            for i in range(4)
        ]
        intel = build_upload_slot_intel(history)
        chosen = [s["slot"] for s in intel["recommended_slots"]]
        self.assertNotIn("06:00", chosen,
                         "a sub-5-sample slot must not capture a daily publish slot")
        self.assertEqual(len(chosen), 3)

    def test_confident_slot_is_adopted(self):
        from premium_growth_loop import build_upload_slot_intel

        history = [
            self._video(f"hi{i}", datetime(2026, 7, 10 + i, 16, 0, tzinfo=timezone.utc), 20000)
            for i in range(5)  # exactly the confidence minimum
        ]
        intel = build_upload_slot_intel(history)
        chosen = [s["slot"] for s in intel["recommended_slots"]]
        self.assertIn("18:00", chosen, "5 consistent samples must promote the slot")

    def test_recommended_slots_carry_score_rank_and_confidence(self):
        from premium_growth_loop import build_upload_slot_intel

        intel = build_upload_slot_intel([])
        for slot in intel["recommended_slots"]:
            self.assertIn("score_rank", slot)
            self.assertIn("confident", slot)
        # file order stays chronological (scheduler + existing tests rely on it)
        hours = [s["hour"] for s in intel["recommended_slots"]]
        self.assertEqual(hours, sorted(hours))


class FrenchVerbGateTests(unittest.TestCase):

    def test_verbless_question_title_is_blocked(self):
        from french_quality_gate import is_french_question_without_verb

        self.assertTrue(is_french_question_without_verb(
            "Pourquoi des corps flottants visibles dans l'œil ?"))
        self.assertFalse(is_french_question_without_verb(
            "Pourquoi le corps sursaute en s'endormant ?"))
        self.assertFalse(is_french_question_without_verb(
            "Le cœur bat plus vite la nuit"))  # not a question

    def test_verb_detector_handles_accents_and_apostrophes(self):
        from french_quality_gate import has_french_verb

        self.assertTrue(has_french_verb("ton cœur s'accélère"))
        self.assertTrue(has_french_verb("les paumes transpirent"))
        self.assertFalse(has_french_verb("cœur nuit"))
        self.assertFalse(has_french_verb(""))


class ThumbnailHookTests(unittest.TestCase):

    def test_bare_label_is_downgraded_to_question_hook(self):
        from seo_generator import _fr_thumbnail_hook

        script = {
            "thumbnail_text": "CŒUR NUIT",
            "title": "Pourquoi le cœur bat plus vite avant de parler en public ?",
        }
        hook = _fr_thumbnail_hook(script, "Faits surprenants", script["title"])
        self.assertTrue(hook.endswith("?"), hook)
        self.assertNotEqual(hook, "CŒUR NUIT")
        self.assertLessEqual(len(hook), 35)

    def test_verbless_free_thumbnail_falls_back_to_series(self):
        from seo_generator import _question_hook_from_title

        # A title too long and verb-poor produces no hook (caller then falls back)
        self.assertEqual(_question_hook_from_title("Nuances vert rétine science quotidien matin"), "")

    def test_good_llm_hook_is_kept(self):
        from seo_generator import _fr_thumbnail_hook

        script = {
            "thumbnail_text": "ton cœur s'accélère",
            "title": "Pourquoi le cœur bat plus vite avant de parler en public ?",
        }
        hook = _fr_thumbnail_hook(script, "Faits surprenants", script["title"])
        self.assertEqual(hook, "TON CŒUR S'ACCÉLÈRE")


if __name__ == "__main__":
    unittest.main()
