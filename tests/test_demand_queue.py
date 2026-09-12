"""Tests for the real French search-demand topic queue (2026-08-11)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import trend_fetcher


class TestSearchDemandQueue(unittest.TestCase):
    def test_short_primary_queue_uses_only_provenance_backfill(self):
        primary = {
            "topics": [
                {
                    "topic": "un sujet mesuré",
                    "angle": "Pourquoi un sujet mesuré ?",
                    "question_phrase": "un sujet mesuré",
                    "thumbnail_text": "UN SUJET MESURÉ ?",
                    "demand_note": "autocomplete: 'un sujet mesuré'",
                }
            ]
        }
        backfill = {
            "topics": [
                {
                    "topic": f"sujet de secours {index}",
                    "angle": f"Pourquoi le sujet de secours {index} ?",
                    "question_phrase": f"le sujet de secours {index}",
                    "thumbnail_text": f"SUJET DE SECOURS {index} ?",
                    "demand_note": f"Google autocomplete FR exact suggestion: sujet de secours {index}",
                }
                for index in range(1, 6)
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            primary_path = temp / "primary.json"
            backfill_path = temp / "backfill.json"
            primary_path.write_text(json.dumps(primary), encoding="utf-8")
            backfill_path.write_text(json.dumps(backfill), encoding="utf-8")
            with (
                mock.patch.object(trend_fetcher, "SEARCH_DEMAND_QUEUE_PATH", primary_path),
                mock.patch.object(trend_fetcher, "SEARCH_DEMAND_BACKFILL_PATH", backfill_path),
            ):
                queue = trend_fetcher.load_search_demand_queue()
        self.assertEqual(len(queue), trend_fetcher.MIN_SEARCH_DEMAND_ENTRIES)
        self.assertNotIn("demand_provenance", queue[0])
        self.assertEqual(
            sum(item.get("demand_provenance") == "autocomplete_backfill" for item in queue),
            trend_fetcher.MIN_SEARCH_DEMAND_ENTRIES - 1,
        )
        self.assertTrue(all(item["source"] == "fr_search_demand" for item in queue))

    def test_real_queue_loads_with_catalogue_shape(self):
        queue = trend_fetcher.load_search_demand_queue()
        self.assertGreaterEqual(len(queue), 5)
        for rec in queue:
            with self.subTest(topic=rec.get("topic")):
                self.assertEqual(rec["source"], "fr_search_demand")
                self.assertTrue(rec["topic"])
                self.assertTrue(rec["question_phrase"])
                self.assertTrue(rec["thumbnail_text"].endswith("?"))
                self.assertTrue(rec["demand_note"])

    def test_malformed_truncated_record_is_never_selected(self):
        malformed = {
            "topics": [
                {
                    "topic": "l'illusion d'objectivité qui te contrô",
                    "angle": "Pourquoi l'illusion d'objectivité qui te contrô ?",
                    "question_phrase": "pourquoi l'illusion d'objectivité qui te contrô",
                    "thumbnail_text": "Pourquoi l'illusion d'objectivité qui te contrô ?",
                    "demand_note": "autocomplete: 'illusion d’optique'",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "malformed.json"
            path.write_text(json.dumps(malformed), encoding="utf-8")
            with mock.patch.object(trend_fetcher, "SEARCH_DEMAND_QUEUE_PATH", path):
                queue = trend_fetcher.load_search_demand_queue()
        # The malformed primary record is rejected; valid provenanced backfill
        # may still be supplied to preserve the queue's five-topic contract.
        self.assertTrue(all(item["topic"] != "Pourquoi l'illusion d'objectivité qui te contrô ?" for item in queue))
        self.assertTrue(all(item.get("demand_provenance") == "autocomplete_backfill" for item in queue))

    def test_missing_file_yields_empty_queue_not_crash(self):
        with mock.patch.object(
            trend_fetcher, "SEARCH_DEMAND_QUEUE_PATH", Path("data/__definitely_missing__.json")
        ):
            self.assertEqual(trend_fetcher.load_search_demand_queue(), [])

    def test_queue_is_consulted_before_catalogue_pick(self):
        fake = [
            {
                "topic": "Pourquoi on teste la demande réelle",
                "angle": "Pourquoi on teste la demande réelle",
                "nominal_phrase": "la demande réelle",
                "question_phrase": "on teste la demande réelle",
                "thumbnail_text": "ON TESTE LA DEMANDE ?",
                "demand_note": "test",
            }
        ]
        with (
            mock.patch.object(
                trend_fetcher,
                "load_search_demand_queue",
                return_value=[
                    trend_fetcher._topic_record(
                        fake[0]["angle"], "fr_search_demand", pillar="dark_psychology"
                    )
                    | {"demand_note": "test", "question_phrase": fake[0]["question_phrase"]}
                ],
            ),
            mock.patch("intelligence.viral_miner.load_fresh_fastlane", return_value=[]),
            mock.patch.dict("os.environ", {"TOPIC_STRATEGY": "dark_psychology_series"}),
        ):
            chosen = trend_fetcher.get_trending_topic(exclude=[], return_metadata=True)
        self.assertEqual(chosen["source"], "fr_search_demand")

    def test_queue_respects_exclude_history(self):
        rec = trend_fetcher._topic_record(
            "Pourquoi le ventre gargouille sans faim", "fr_search_demand", pillar="dark_psychology"
        ) | {"question_phrase": "le ventre gargouille sans faim"}
        with (
            mock.patch.object(trend_fetcher, "load_search_demand_queue", return_value=[rec]),
            mock.patch("intelligence.viral_miner.load_fresh_fastlane", return_value=[]),
            mock.patch("demand_refresh.refresh_demand_queue", return_value=False),
            mock.patch.dict("os.environ", {"TOPIC_STRATEGY": "dark_psychology_series"}),
        ):
            # The only queue entry is excluded. A failed live refresh must
            # safely fall back to the catalogue without touching network/state.
            chosen = trend_fetcher.get_trending_topic(
                exclude=["Pourquoi le ventre gargouille sans faim"], return_metadata=True
            )
        self.assertNotEqual(chosen.get("source"), "fr_search_demand")


if __name__ == "__main__":
    unittest.main()


class DemandBackedSeoTests(unittest.TestCase):
    """2026-08-12 truth-SEO: tags must come from REAL autocomplete demand
    phrases, not keyword guesses — same doctrine as the truth gate."""

    def test_optimizer_uses_measured_demand_first(self):
        import fr_batch_optimize as fbo

        # 2026-08-17: this test used to rely on the LIVE queue file still
        # containing the "3h du matin" entry, falling back to an UNMOCKED
        # network call (_mine_live_demand) when the queue rotated it out.
        # That's exactly the non-determinism truth-SEO doctrine forbids
        # elsewhere in this file (see LiveDemandMiningTests, which mocks
        # requests.get for the same function) — a passing/failing result
        # here depended on queue rotation state and live network
        # availability, not on the code under test. Mock the same way the
        # rest of this file already does.
        with mock.patch.object(
            fbo,
            "_mine_live_demand",
            return_value=["pourquoi on se réveille à 3h du matin", "réveil nocturne 3h du matin sans raison"],
        ):
            ph = fbo._demand_phrases_for(
                "Pourquoi on se réveille à 3h du matin", "Pourquoi on se réveille à 3h du matin ?"
            )
        self.assertTrue(any("réveille" in p and "3h du matin" in p for p in ph))
        tags = fbo._optimize_tags(
            [],
            "Pourquoi on se réveille à 3h du matin ?",
            "le réveil à 3h du matin sans raison",
            demand_phrases=ph,
        )
        self.assertIn("3h", tags[0].lower())

    def test_tags_never_exceed_youtube_limit(self):
        import fr_batch_optimize as fbo

        tags = fbo._optimize_tags(
            [],
            "Pourquoi le ventre bouge tout seul ?",
            "le ventre qui bouge tout seul",
            demand_phrases=["pourquoi mon ventre bouge tout seul"],
        )
        self.assertLessEqual(sum(len(t) + 1 for t in tags), 500)


class LiveDemandMiningTests(unittest.TestCase):
    """2026-08-12 repair sweep: per-video LIVE autocomplete mining must be
    relevance-guarded, offline-safe, and never raise."""

    def test_relevance_guard_drops_unrelated_suggestions(self):
        import unittest.mock as mock

        import fr_batch_optimize as fbo

        fake_resp = mock.Mock(ok=True)
        fake_resp.json = lambda: [
            "q",
            [
                "la chair de poule quand il fait froid",  # relevant
                "recette poulet basquaise facile",  # off-topic — must be dropped
                "x",  # too short — dropped
            ],
        ]
        with mock.patch("requests.get", return_value=fake_resp):
            out = fbo._mine_live_demand(
                "Pourquoi la chair de poule apparait soudainement",
                "Pourquoi la chair de poule apparaît soudainement ?",
            )
        self.assertIn("la chair de poule quand il fait froid", out)
        self.assertNotIn("recette poulet basquaise facile", out)

    def test_network_failure_returns_empty_silently(self):
        import unittest.mock as mock

        import fr_batch_optimize as fbo

        with mock.patch("requests.get", side_effect=TimeoutError()):
            out = fbo._mine_live_demand("sujet quelconque assez long", "Pourquoi le corps se fige ?")
        self.assertEqual(out, [])

    def test_env_kill_switch(self):
        import os

        import fr_batch_optimize as fbo

        os.environ["REPAIR_LIVE_DEMAND"] = "false"
        try:
            out = fbo._mine_live_demand("sujet de test assez long ici", "Pourquoi le hoquet commence ?")
        finally:
            os.environ.pop("REPAIR_LIVE_DEMAND")
        self.assertEqual(out, [])

    def test_garbage_suggestions_filtered(self):
        import unittest.mock as mock

        import fr_batch_optimize as fbo

        fake_resp = mock.Mock(ok=True)
        fake_resp.json = lambda: [
            "q",
            [
                "la peau la peau",  # degenerate repeat
                "pourquoi je ne prend pas de muscle",  # only weak 'muscle' shared
                "pourquoi la peau gratte apres la douche",  # 2+ strong shared words — keep
                "la chair de poule quand il fait froid",  # strong shared words — keep
            ],
        ]
        with mock.patch("requests.get", return_value=fake_resp):
            out = fbo._mine_live_demand(
                "Pourquoi la chair de poule apparait quand la peau a froid",
                "Pourquoi la chair de poule apparaît quand la peau a froid ?",
            )
        self.assertNotIn("la peau la peau", out)
        self.assertNotIn("pourquoi je ne prend pas de muscle", out)
