import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from main import SKILLORPipeline, _near_duplicate_title, _normalize_title_key, _topic_key


class TitleCandidatePoolTests(unittest.TestCase):
    def make_pipeline(self, history=None):
        pipeline = object.__new__(SKILLORPipeline)
        pipeline.video_history = history or []
        return pipeline

    def test_normalized_french_title_identity_removes_accents_and_frame(self):
        self.assertEqual(
            _normalize_title_key("Pourquoi le cerveau ralentit le temps ?"),
            "le cerveau ralentit le temps",
        )

    def test_near_duplicate_titles_ignore_reusable_question_frame(self):
        self.assertTrue(
            _near_duplicate_title(
                "Pourquoi le cerveau semble ralentir le temps en danger ?",
                "Ce qui se passe quand le cerveau semble ralentir le temps en danger",
            )
        )

    def test_pool_skips_history_and_selects_next_candidate(self):
        pipeline = self.make_pipeline(
            [{"title": "Pourquoi le cerveau ralentit le temps en danger ?"}]
        )
        script = {
            "topic": "la perception du temps en situation de danger",
            "title": "Pourquoi le cerveau ralentit le temps en danger ?",
            "title_options": [
                "Pourquoi le cerveau ralentit le temps en danger ?",
                "Comment ton cerveau estime les secondes sous stress ?",
            ],
        }

        selected = pipeline._select_unique_title(script)

        self.assertEqual(selected, "Comment ton cerveau estime les secondes sous stress ?")
        self.assertEqual(script["title_identity"]["normalized_title"], _normalize_title_key(selected))

    def test_selected_candidate_is_added_to_current_run_exclusions(self):
        pipeline = self.make_pipeline()
        blocked_titles = set()
        blocked_topics = set()
        script = {
            "topic": "la voix tremble sous stress",
            "title": "Pourquoi ta voix tremble sous stress ?",
            "title_options": ["Pourquoi ta voix tremble sous stress ?"],
        }

        selected = pipeline._select_unique_title(script, blocked_titles, blocked_topics)

        self.assertIn(_normalize_title_key(selected), blocked_titles)
        self.assertIn(_topic_key(script), blocked_topics)

    def test_pool_respects_current_run_title_and_topic_exclusions(self):
        pipeline = self.make_pipeline()
        blocked_titles = {_normalize_title_key("Pourquoi tes yeux tremblent-ils ?")}
        blocked_topics = {_topic_key("tes yeux tremblent")}
        script = {
            "topic": "la mémoire invente des détails",
            "title": "Pourquoi tes yeux tremblent-ils ?",
            "title_options": [
                "Pourquoi tes yeux tremblent-ils ?",
                "Pourquoi la mémoire invente des détails ?",
            ],
        }

        selected = pipeline._select_unique_title(script, blocked_titles, blocked_topics)

        self.assertEqual(selected, "Pourquoi la mémoire invente des détails ?")
        self.assertIn(selected, script["title_options"])

    def test_pool_raises_when_every_candidate_is_blocked(self):
        pipeline = self.make_pipeline([{"title": "Pourquoi le cerveau ralentit le temps ?"}])
        script = {
            "topic": "la perception du temps",
            "title": "Pourquoi le cerveau ralentit le temps ?",
            "title_options": ["Pourquoi le cerveau ralentit le temps ?"],
        }

        with self.assertRaisesRegex(RuntimeError, "no unique French title candidate"):
            pipeline._select_unique_title(script)


if __name__ == "__main__":
    unittest.main()
