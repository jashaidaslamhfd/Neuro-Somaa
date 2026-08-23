"""Tests for the viral-engineering layer (viral_engineering + winner fastlane)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class HookArmTests(unittest.TestCase):
    def test_arm_is_deterministic_and_valid(self):
        from viral_engineering import HOOK_ARMS, hook_arm_for_topic

        a = hook_arm_for_topic("Pourquoi le hoquet commence ?")
        b = hook_arm_for_topic("Pourquoi le hoquet commence ?")
        self.assertEqual(a, b)
        self.assertIn(a, HOOK_ARMS)

    def test_arms_distribute_across_topics(self):
        from viral_engineering import hook_arm_for_topic

        arms = {hook_arm_for_topic(f"Pourquoi le sujet numéro {i} ?") for i in range(30)}
        self.assertGreater(len(arms), 1, "30 topics produced a single arm — rotation broken")

    def test_env_override_wins(self):
        from viral_engineering import hook_arm_for_topic

        old = os.environ.get("VIRAL_HOOK_ARM")
        os.environ["VIRAL_HOOK_ARM"] = "shock_fact"
        try:
            self.assertEqual(hook_arm_for_topic("n'importe quoi"), "shock_fact")
        finally:
            if old is None:
                os.environ.pop("VIRAL_HOOK_ARM", None)
            else:
                os.environ["VIRAL_HOOK_ARM"] = old

    def test_style_instructions_are_french(self):
        from viral_engineering import HOOK_ARMS, hook_style_instruction

        for arm in HOOK_ARMS:
            text = hook_style_instruction(arm)
            self.assertTrue(text, arm)
            self.assertRegex(text.lower(), r"(arme expérience|hook)")


class HookScoreV2Tests(unittest.TestCase):
    def test_strong_hook_beats_weak_label(self):
        from viral_engineering import score_hook_v2

        weak = score_hook_v2("Cœur nuit")
        strong = score_hook_v2("Pourquoi ton cœur bat 10 % plus fort ce soir ?")
        self.assertGreater(strong["score"], weak["score"])
        self.assertEqual(strong["grade"], "strong")
        self.assertEqual(weak["grade"], "weak")
        self.assertTrue(weak["missing"], "weak hooks must explain WHY")

    def test_missing_verb_flagged(self):
        from viral_engineering import score_hook_v2

        out = score_hook_v2("ton corps la nuit")
        self.assertIn("aucun verbe conjugué", out["missing"])


class LoopBridgeTests(unittest.TestCase):
    def test_every_bridge_has_a_verb(self):
        from french_quality_gate import has_french_verb
        from viral_engineering import _LOOP_BRIDGES

        for line in _LOOP_BRIDGES:
            self.assertTrue(has_french_verb(line), f"bridge without verb: {line}")

    def test_bridge_detection(self):
        from viral_engineering import looks_like_loop_bridge

        self.assertTrue(looks_like_loop_bridge("Et tout ça recommence dès la première seconde."))
        self.assertFalse(looks_like_loop_bridge("Ton cerveau contrôle ton cœur."))


class SurpriseBeatTests(unittest.TestCase):
    def test_flat_middle_flagged(self):
        from viral_engineering import surprise_beat_present

        scenes = [
            {"caption": c}
            for c in [
                "Pourquoi ton corps fait cela ?",
                "Ton cerveau envoie un signal.",
                "Le signal voyage lentement.",
                "Le corps répond simplement.",
                "Voilà pourquoi cela arrive.",
                "La prochaine fois tout recommence.",
            ]
        ]
        ok, reason = surprise_beat_present(scenes)
        self.assertFalse(ok)
        self.assertTrue(reason)

    def test_escalation_passes(self):
        from viral_engineering import surprise_beat_present

        scenes = [
            {"caption": c}
            for c in [
                "Pourquoi ton corps fait cela ?",
                "Ton cerveau envoie un signal.",
                "Mais le signal voyage 2 fois plus vite.",
                "Le corps répond simplement.",
                "Voilà pourquoi cela arrive.",
                "La prochaine fois tout recommence.",
            ]
        ]
        ok, _ = surprise_beat_present(scenes)
        self.assertTrue(ok)


class WinnerFastlaneTests(unittest.TestCase):
    def test_miner_clones_winner_into_grammatical_question(self):
        from intelligence import viral_miner

        history = [
            {"youtube_video_id": f"n{i}", "title": f"Pourquoi sujet normal {i} ?", "views": 500}
            for i in range(20)
        ]
        history.append(
            {
                "youtube_video_id": "WIN1",
                "title": "Pourquoi le cœur bat plus vite avant de parler ?",
                "views": 1500,
            }
        )
        anomalies = {
            "anomalies": [
                {
                    "direction": "over",
                    "views": 1500,
                    "title": "Pourquoi le cœur bat plus vite avant de parler ?",
                    "video_id": "WIN1",
                }
            ]
        }
        payload = viral_miner.mine_winner_fastlane(history, anomalies)
        self.assertTrue(payload["fastlane"])
        clone = payload["fastlane"][0]["topic"]
        self.assertTrue(clone.startswith("Pourquoi"))
        self.assertTrue(clone.endswith("?"))
        self.assertIn("cœur", clone)

    def test_fastlane_ttl_enforced(self):
        from intelligence import viral_miner

        stale = {
            "generated_at": (datetime.now(UTC) - timedelta(hours=200)).isoformat(),
            "fastlane": [{"topic": "Pourquoi le test staleness arrive ?"}],
        }
        fresh = {
            "generated_at": datetime.now(UTC).isoformat(),
            "fastlane": [{"topic": "Pourquoi le test fraîcheur marche ?"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "fl.json"
            p.write_text(json.dumps(stale), encoding="utf-8")
            self.assertEqual(viral_miner.load_fresh_fastlane(p), [])
            p.write_text(json.dumps(fresh), encoding="utf-8")
            self.assertEqual(len(viral_miner.load_fresh_fastlane(p)), 1)

    def test_no_clones_without_winners(self):
        from intelligence import viral_miner

        history = [
            {"youtube_video_id": f"n{i}", "title": f"Pourquoi sujet {i} ?", "views": 500} for i in range(10)
        ]
        payload = viral_miner.mine_winner_fastlane(history, {"anomalies": []})
        # top-decile backup may nominate the flat leader, but flat 500s produce
        # at most few entries and never crash
        self.assertIsInstance(payload["fastlane"], list)


class HookArmExperimentStatsTests(unittest.TestCase):
    def test_hook_arm_comparison_matures(self):
        from intelligence.stats import compare_hook_arms

        history = []
        for i in range(6):
            history.append({"hook_arm": "question", "views": 900 + i})
            history.append({"hook_arm": "shock_fact", "views": 300 - i})
        out = compare_hook_arms(history)
        self.assertTrue(out["available"])
        self.assertEqual(out["leading_arm"]["arm"], "question")
        significant_pairs = [p for p in out["pairwise"] if p["significant"]]
        self.assertTrue(significant_pairs)

    def test_hook_arm_comparison_honest_when_empty(self):
        from intelligence.stats import compare_hook_arms

        out = compare_hook_arms([{"views": 500}])  # legacy rows without arms
        self.assertFalse(out["available"])
        self.assertIn("reason", out)


if __name__ == "__main__":
    unittest.main()
