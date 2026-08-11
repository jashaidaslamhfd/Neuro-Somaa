"""Tests for the français-parlé humanizer (2026-08-11 humanization pass)."""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from french_humanizer import humanize_spoken_fr, formality_leftovers  # noqa: E402


class TestRegister(unittest.TestCase):
    def h(self, text):
        return humanize_spoken_fr(text)[0]

    def test_vous_to_tu_full_sentence(self):
        self.assertEqual(
            self.h("Vous avez déjà remarqué que votre cœur s'emballe la nuit ?"),
            "T'as déjà remarqué que ton cœur s'emballe la nuit ?")

    def test_spoken_negations(self):
        self.assertEqual(self.h("Il n'y a pas de danger."), "Y a pas de danger.")
        self.assertEqual(self.h("Ce n'est pas grave."), "C'est pas grave.")
        self.assertEqual(self.h("Il y a une raison simple."), "Y a une raison simple.")

    def test_cela_and_nous(self):
        self.assertEqual(self.h("Cela vous arrive quand vous dormez."),
                         "Ça t'arrive quand tu dors.")
        self.assertEqual(self.h("Nous allons voir pourquoi."), "On va voir pourquoi.")

    def test_gendered_possessives(self):
        self.assertEqual(self.h("Votre peau se fripe, votre corps aussi."),
                         "Ta peau se fripe, ton corps aussi.")
        self.assertEqual(self.h("Vos mains deviennent moites."),
                         "Tes mains deviennent moites.")

    def test_imperatives(self):
        self.assertEqual(self.h("Imaginez votre cerveau la nuit."),
                         "Imagine ton cerveau la nuit.")
        self.assertEqual(self.h("Abonnez-vous pour la suite."),
                         "Abonne-toi pour la suite.")

    def test_nest_ce_pas(self):
        self.assertEqual(self.h("C'est étrange, n'est-ce pas ?"),
                         "C'est étrange non ?")

    def test_cliche_drop(self):
        self.assertEqual(
            self.h("Il est important de noter que le corps se fige."),
            "Le corps se fige.")

    def test_capitalization_after_drop(self):
        self.assertEqual(
            self.h("Le ventre se serre. À noter que le stress joue un rôle."),
            "Le ventre se serre. Le stress joue un rôle.")


class TestBoundaries(unittest.TestCase):
    def h(self, text):
        return humanize_spoken_fr(text)[0]

    def test_glued_sentences_get_period(self):
        out = self.h("C'est dû au fait que le cerveau ralentit Cela reste normal")
        self.assertIn("ralentit. ", out)

    def test_no_split_on_graphic_same_token(self):
        out = self.h("Ton cœur bat fort. C'est normal.")
        self.assertEqual(out, "Ton cœur bat fort. C'est normal.")

    def test_dangling_tail_removed(self):
        out = self.h("Un bon sommeil peut réduire cette sensation de lourdeur Al")
        self.assertTrue(out.endswith("."))
        self.assertNotIn(" Al", out)

    def test_complete_ending_enforced(self):
        out = self.h("Ton corps te protège chaque nuit")
        self.assertEqual(out, "Ton corps te protège chaque nuit.")

    def test_idempotent(self):
        once = self.h("Vous avez déjà vu votre peau se friper ?")
        twice = self.h(once)
        self.assertEqual(once, twice)

    def test_changes_reported(self):
        _, changes = humanize_spoken_fr("Il n'y a pas de souci, n'est-ce pas ?")
        self.assertIn("register:parlé", changes)

    def test_formality_counter(self):
        self.assertGreater(formality_leftovers("Votre corps et vous, la nuit."), 0)
        self.assertEqual(formality_leftovers("Ton corps et toi, la nuit."), 0)


class TestPipelineWiring(unittest.TestCase):
    def test_normalize_scenes_humanizes(self):
        import script_generator
        data = {
            "title": "Pourquoi le cœur bat la nuit ?",
            "hook": "placeholder",
            "description": "Vous allez comprendre votre cœur.",
            "scenes": [
                {"visual": "gros plan poitrine",
                 "caption": "Vous entendez votre cœur la nuit ?"},
                {"visual": "illustration cœur",
                 "caption": "C'est ton corps qui baisse le rythme."},
                {"visual": "horloge", "caption": "Il y a une raison simple."},
            ],
        }
        out = script_generator._normalize_scenes(data)
        self.assertTrue(out["voiceover"].startswith("T'entends ton cœur"))
        self.assertIn("Y a une raison simple.", out["voiceover"])
        self.assertEqual(out["hook"], out["scenes"][0]["caption"])  # resynced


if __name__ == "__main__":
    unittest.main()
