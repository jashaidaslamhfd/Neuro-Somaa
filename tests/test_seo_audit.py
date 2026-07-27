"""Offline tests for the channel SEO audit heuristics.

These exercise the pure analysis functions in scripts/channel_seo_audit.py
against the channel's REAL title patterns, so a regression that stops
detecting truncated/leaked titles is caught immediately.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import channel_seo_audit as audit


class TitleClassificationTests(unittest.TestCase):
    def test_pourquoi_question(self):
        self.assertEqual(audit.classify_opener("Pourquoi le hoquet commence ?"), "pourquoi-question")

    def test_pourquoi_declarative(self):
        self.assertEqual(audit.classify_opener("Pourquoi le temps passe vite"), "pourquoi-declarative")

    def test_comprendre_is_weakest(self):
        self.assertEqual(audit.classify_opener("Comprendre pourquoi on dort"), "comprendre-pourquoi")

    def test_ce_quil_faut(self):
        self.assertEqual(audit.classify_opener("Ce qu'il faut comprendre sur le hoquet"), "ce-qu-il-faut")

    def test_short_fragment(self):
        # Single-token titles (<=12 chars) are flagged as fragments.
        self.assertEqual(audit.classify_opener("Sommeil"), "short-fragment")

    def test_two_word_short_title_is_other(self):
        # "Corps lourd" has a space, so it is NOT the single-token fragment
        # pattern; it falls through to "other" (its shortness is caught
        # separately by analyze_title, not by classify_opener).
        self.assertEqual(audit.classify_opener("Corps lourd"), "other")


class TitleIssueDetectionTests(unittest.TestCase):
    def test_leaked_fragment_caught(self):
        # Real broken title from the channel history.
        issues = audit.analyze_title("Pourquoi le ventre se serre lors d'une peur peut sembler")
        self.assertTrue(any("leaked" in i for i in issues), issues)

    def test_truncation_caught(self):
        issues = audit.analyze_title("Pourquoi le cerveau remarque entendre son cœur battre la")
        self.assertTrue(any("truncated" in i for i in issues), issues)

    def test_weak_declarative_caught(self):
        issues = audit.analyze_title("Comprendre pourquoi le cerveau réclame du sommeil profond")
        self.assertTrue(any("declarative" in i for i in issues), issues)

    def test_clean_pourquoi_has_no_issues(self):
        issues = audit.analyze_title("Pourquoi ton cœur bat la nuit")
        self.assertEqual(issues, [], issues)

    def test_question_without_pourquoi_flagged(self):
        issues = audit.analyze_title("Ce qui change quand une lumière fait éternuer ?")
        self.assertTrue(any("question" in i for i in issues), issues)


class SeoScoreTests(unittest.TestCase):
    def test_curiosity_opener_scores_higher_than_comprendre(self):
        good = audit.title_seo_score("Pourquoi ton cœur bat la nuit")
        bad = audit.title_seo_score("Comprendre pourquoi le cerveau réclame du sommeil profond")
        self.assertGreater(good, bad)


class AnalyzeVideosTests(unittest.TestCase):
    def test_too_new_flag(self):
        from datetime import timedelta
        recent = (audit.TODAY - timedelta(days=1)).isoformat()
        rows = audit.analyze_videos([{"youtube_video_id": "x", "title": "Pourquoi x ?", "posted_at": recent}])
        self.assertTrue(rows[0]["too_new"])

    def test_mature_not_flagged(self):
        from datetime import timedelta
        old = (audit.TODAY - timedelta(days=30)).isoformat()
        rows = audit.analyze_videos([{"youtube_video_id": "x", "title": "Pourquoi x ?", "posted_at": old}])
        self.assertFalse(rows[0]["too_new"])


class CleanTitleTests(unittest.TestCase):
    def test_strips_comprendre_prefix(self):
        self.assertEqual(
            audit.clean_title_from_topic("Comprendre pourquoi le cerveau réclame du sommeil profond"),
            "Pourquoi le cerveau réclame du sommeil profond ?",
        )

    def test_removes_leaked_fragment(self):
        self.assertEqual(
            audit.clean_title_from_topic("Pourquoi le ventre se serre lors d'une peur peut sembler"),
            "Pourquoi le ventre se serre lors d'une peur ?",
        )

    def test_keeps_clean_pourquoi(self):
        self.assertEqual(
            audit.clean_title_from_topic("Pourquoi le corps se fige de peur"),
            "Pourquoi le corps se fige de peur ?",
        )


if __name__ == "__main__":
    unittest.main()
