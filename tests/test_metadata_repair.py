"""Guard tests for scripts/metadata_repair.py title detection.

Both cases below are REAL titles that survived a live `apply=true` repair run
on 2026-07-30 because the detector considered them healthy.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from metadata_repair import (
    _carries_description_text,
    _looks_truncated,
    build_new_metadata,
)


def _snippet(title):
    return {"snippet": {"title": title, "tags": [], "description": ""}}


class UnresolvedClauseTests(unittest.TestCase):
    """A title can end on a valid noun and still be cut off."""

    def test_unresolved_quand_clause_is_truncated(self):
        # TaXxSn0YoMc — ends on "silence", a fine noun, but "quand ..." never
        # resolves so the viewer is never told what actually happens.
        self.assertTrue(_looks_truncated("Ce que votre corps vous dit quand le silence"))

    def test_resolved_quand_clause_is_healthy(self):
        # rR7yLwzBakA — the clause completes; must not be rewritten.
        self.assertFalse(_looks_truncated("Pourquoi votre visage rougit quand vous avez honte ?"))

    def test_unresolved_clause_gets_repaired(self):
        changes = build_new_metadata(
            {"topic": "Ce que votre corps vous dit quand le silence devient inconfortable", "voiceover": "x"},
            _snippet("Ce que votre corps vous dit quand le silence"),
        )
        self.assertIsNotNone(changes)
        self.assertTrue(changes.get("title"))
        self.assertFalse(_looks_truncated(changes["title"]))


class DescriptionLeakTests(unittest.TestCase):
    """Description copy must never be accepted as a title."""

    def test_leaked_description_is_detected(self):
        # 1XVYcxQqDqo — description template bled into the title, then got cut
        # mid-word at "on e". channel_seo_audit.py guarded against this;
        # metadata_repair.py did not, so the polluted title stayed live.
        self.assertTrue(
            _carries_description_text("Pourquoi se réveiller avant son réveil Dans ce Short on e ?")
        )

    def test_clean_title_is_not_flagged_as_leaked(self):
        self.assertFalse(_carries_description_text("Pourquoi le hoquet commence brusquement ?"))

    def test_leaked_title_gets_repaired(self):
        changes = build_new_metadata(
            {"topic": "Pourquoi se réveiller avant son réveil peut sembler étrange", "voiceover": "x"},
            _snippet("Pourquoi se réveiller avant son réveil Dans ce Short on e ?"),
        )
        self.assertIsNotNone(changes)
        self.assertTrue(changes.get("title"))
        self.assertFalse(_carries_description_text(changes["title"]))

    def test_replacement_title_is_never_polluted(self):
        # The repair must not be able to WRITE a polluted title either.
        changes = build_new_metadata(
            {"topic": "Dans ce Short on explique pourquoi le corps tremble", "voiceover": "x"},
            _snippet("Corps"),
        )
        if changes and changes.get("title"):
            self.assertFalse(_carries_description_text(changes["title"]))


class HealthyTitlesAreLeftAloneTests(unittest.TestCase):
    """Real, correct titles from the channel must survive untouched."""

    GOOD = (
        "Pourquoi le hoquet commence brusquement ?",
        "Ce qu'il faut comprendre sur les genoux qui craquent",
        "Pourquoi votre visage rougit quand vous avez honte ?",
        "Pourquoi le temps semble passer plus vite en vieillissant ?",
    )

    def test_healthy_titles_are_not_rewritten(self):
        for title in self.GOOD:
            with self.subTest(title=title):
                changes = build_new_metadata({"topic": title, "voiceover": "x"}, _snippet(title))
                self.assertIsNone(
                    (changes or {}).get("title"),
                    f"healthy title must not be rewritten: {title!r}",
                )


if __name__ == "__main__":
    unittest.main()
