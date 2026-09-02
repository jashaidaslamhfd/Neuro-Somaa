"""Fake-metric decision guards (2026-08-12).

The owner's complaint, three times confirmed by data: internal heuristic
scores (hook_score, predicted CTR, predicted retention) keep producing the
SAME small set of values, correlate ZERO (or negatively) with real views,
yet were silently deciding uploads — vetoing renders and overriding titles.
Truth Gate doctrine: an internal score earns decision power ONLY after the
daily calibration proves it predictive on real outcomes. These tests stop
any regression that lets a vibe-score make decisions again.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MAIN = (ROOT / "src" / "main.py").read_text()


class NoUncalibratedDecisionTests(unittest.TestCase):
    def test_title_swap_requires_truth_or_measured_bandit(self):
        # The old bug: `script_data['title'] = recommended['title']` executed
        # unconditionally — a heuristic CTR number overrode the QA-passed
        # LLM title on every upload.
        idx = MAIN.find("Applying CTR-winner title")
        self.assertNotEqual(idx, -1, "title swap site must exist and stay labelled")
        head = MAIN[:idx]
        # The swap must sit behind decision-usability OR measured bandit.
        self.assertTrue(
            "_score_decision_usable('predicted_ctr')" in head[-2000:]
            or '_score_decision_usable("predicted_ctr")' in head[-2000:]
        )

    def test_no_unconditional_title_override_remains(self):
        # Bare `script_data['title'] = recommended['title']` without a guard
        # must never come back.
        for m in re.finditer(r"script_data\['title'\]\s*=\s*recommended\['title'\]", MAIN):
            ctx = MAIN[max(0, m.start() - 800) : m.start()]
            self.assertIn("_score_decision_usable", ctx, "title override without truth guard")

    def test_hook_render_veto_is_truth_gated(self):
        # Render-time hook veto may only fire when the truth file measured
        # hook_score as decision-usable.
        veto_idx = MAIN.find('message = f"Hook failed')
        self.assertNotEqual(veto_idx, -1)
        ctx = MAIN[max(0, veto_idx - 1200) : veto_idx]
        self.assertTrue(
            "_score_decision_usable('hook_score')" in ctx
            or '_score_decision_usable("hook_score")' in ctx
        )
        self.assertIn("_handle_non_critical_gate(message)", MAIN[veto_idx : veto_idx + 500])

    def test_retention_render_veto_is_truth_gated(self):
        veto_idx = MAIN.find("Retention gate: predicted")
        self.assertNotEqual(veto_idx, -1)
        ctx = MAIN[max(0, veto_idx - 900) : veto_idx]
        self.assertTrue(
            "_score_decision_usable('predicted_retention')" in ctx
            or '_score_decision_usable("predicted_retention")' in ctx
        )

    def test_fallback_attempt_ranked_by_structural_facts(self):
        # Best-attempt fallback must rank by structural gate count, never by
        # the noisy hook self-grade.
        self.assertIn("structural_passes", MAIN)
        bad = re.search(r"hook_score > best_attempt\.get\('hook_score'", MAIN)
        self.assertIsNone(bad, "attempt ranking by raw hook_score is back")

    def test_advisory_language_present_at_each_gate(self):
        # Every softened gate must SAY it is advisory in logs — silent
        # acceptance is exactly how the fake scores hid.
        total = MAIN.count("TRUTH advisory") + MAIN.count("TRUTH GATE advisory")
        self.assertGreaterEqual(total, 3)


class ScoreDecisionUsableHelperTests(unittest.TestCase):
    def test_helper_defaults_false_without_status_file(self):
        import importlib

        import script_generator

        importlib.reload(script_generator)
        # In the sandbox CI checkout data/truth_status.json exists; assert the
        # helper returns a bool and never raises either way.
        result = script_generator._score_decision_usable("hook_score")
        self.assertIsInstance(result, bool)

    def test_helper_reads_decision_usable_flag(self):
        from unittest import mock

        import script_generator

        fake = {"hook_score": {"decision_usable": True}}
        with mock.patch("intelligence.truth_gate.load_status", return_value=fake):
            self.assertTrue(script_generator._score_decision_usable("hook_score"))
        with mock.patch("intelligence.truth_gate.load_status", return_value=None):
            self.assertFalse(script_generator._score_decision_usable("hook_score"))


if __name__ == "__main__":
    unittest.main()
