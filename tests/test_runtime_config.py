"""Regression tests for the runtime-config bugs fixed in the French-channel
reliability pass. Every test maps to a bug that once shipped to production."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


class GitignoreSafetyTests(unittest.TestCase):
    """A `git add .` must never be able to commit credentials or the private
    voice reference."""

    def setUp(self):
        self.gitignore = (ROOT / ".gitignore").read_text()

    def test_token_artifacts_are_ignored(self):
        for pattern in ("oauth_backup.json", "client_secrets*.json", "token*.json"):
            self.assertIn(pattern, self.gitignore, f".gitignore missing {pattern}")

    def test_voice_reference_is_ignored_and_untracked(self):
        self.assertIn("assets/voice_reference.wav", self.gitignore)
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "assets/voice_reference.wav"],
            cwd=ROOT, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0, "voice reference must not be git-tracked")


class RequirementsTests(unittest.TestCase):
    @staticmethod
    def _declared_packages(text: str) -> str:
        lines = [ln.split("#", 1)[0].strip() for ln in text.splitlines()]
        return "\n".join(ln for ln in lines if ln)

    def setUp(self):
        self.core = self._declared_packages((ROOT / "requirements.txt").read_text().lower())
        self.optional = self._declared_packages((ROOT / "requirements-optional.txt").read_text().lower())

    def test_previously_missing_imports_are_declared(self):
        self.assertIn("feedparser", self.core)   # fetch_trending_now.py crashed without it
        self.assertIn("edge-tts", self.core)     # emergency cloud TTS was undeclared

    def test_unused_google_genai_removed_from_core(self):
        self.assertNotIn("google-genai", self.core)

    def test_voice_clone_stack_is_optional_only(self):
        for pkg in ("chatterbox-tts", "torchaudio", "transformers"):
            self.assertNotIn(pkg, self.core)
            self.assertIn(pkg, self.optional)


class WorkflowRegressionTests(unittest.TestCase):
    """File-level guards against the two production bugs found in the run
    history: immediate/scattered publishing and the dead Groq model."""

    def setUp(self):
        self.workflow = (ROOT / ".github" / "workflows" / "main.yml").read_text()

    def test_scheduled_publishing_is_enabled(self):
        # publishAt must stay ON — uploading "public immediately" scattered
        # publish times (a real video went live at 02:32 Paris and flopped).
        self.assertIn('YT_SCHEDULE_PUBLISH: "true"', self.workflow)

    def test_decommissioned_groq_model_is_not_used(self):
        # llama-3.1-70b-versatile was removed by Groq; setting it made every
        # script call return model-not-found (likely cause of failed runs).
        # Check the ASSIGNED value only — the comment explaining the removal
        # legitimately mentions the old name.
        import re
        match = re.search(r'GROQ_MODEL:\s*"([^"]+)"', self.workflow)
        self.assertIsNotNone(match, "GROQ_MODEL should be pinned in the workflow")
        self.assertFalse(
            match.group(1).startswith("llama-3.1-70b"),
            f"GROQ_MODEL points at a decommissioned model: {match.group(1)}",
        )

    def test_posting_gap_is_enforced(self):
        self.assertIn('ENFORCE_POSTING_GAP: "true"', self.workflow)


def _arc_fixture():
    """Valid French 8-scene script, V4 ANSWER-FIRST arc:
    Accroche (scene 1) → Réponse flash (scene 2) → mécanisme → Boucle.

    Scene 2 used to hold a QUESTION here, which matched the old V3 validator
    but contradicted BODY_GLITCH_V4_ANSWER_FIRST — and rewarded exactly the
    "setup drags on" shape that loses viewers at scene 2.2/8 on the live
    channel."""
    return {
        "title": "Sommeil Et Mémoire Cerveau",
        "hook": "Votre cerveau trie vos souvenirs pendant le sommeil.",
        "cta": "Abonnez-vous pour la science du corps, simplement.",
        "scenes": [
            {"visual": "cerveau lumineux pendant le sommeil", "caption": "Votre cerveau trie vos souvenirs pendant le sommeil."},
            {"visual": "signaux de mémoire entre neurones", "caption": "C'est le sommeil profond qui rejoue et fixe chaque souvenir utile."},
            {"visual": "étudiant dans une chambre calme", "caption": "Sans assez de sommeil, une information claire aujourd'hui peut disparaître beaucoup plus vite demain."},
            {"visual": "connexions cérébrales renforcées", "caption": "Pendant le sommeil profond, votre cerveau rejoue les expériences récentes et renforce les connexions utiles."},
            {"visual": "dormeur calme avec cerveau", "caption": "Il relie aussi les idées entre elles, ce qui rend le rappel plus facile au moment où vous en avez besoin."},
            {"visual": "chemin de mémoire lumineux", "caption": "Ce processus explique pourquoi le repos aide l'apprentissage à rester stable après une journée complète."},
            {"visual": "notes organisées près du dormeur", "caption": "La mémoire n'est pas parfaite, mais le sommeil donne au cerveau le temps de tout organiser."},
            {"visual": "lumière du matin, personne concentrée", "caption": "Ainsi le sommeil sauvegarde les souvenirs que votre cerveau éveillé pourrait perdre complètement demain."},
        ],
    }


class StoryArcTests(unittest.TestCase):
    """Suspense question + loop-back must be enforced for French scripts too
    (and French function words must not fake the overlap)."""

    def setUp(self):
        try:
            import importlib
            self.sg = importlib.import_module("script_generator")
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")

    def _validated(self, data):
        return self.sg.validate_script(self.sg._normalize_scenes(data))

    def test_complete_french_arc_passes(self):
        valid, issues = self._validated(_arc_fixture())
        self.assertTrue(valid, issues)

    def test_scene_two_that_stalls_instead_of_answering_is_rejected(self):
        """V4: scene 2 must DELIVER the mechanism. Analytics autopsy showed
        viewers leave at ~scene 2.2/8, so a scene 2 that merely teases is the
        single most expensive retention mistake."""
        data = _arc_fixture()
        data["scenes"][1]["caption"] = "Mais comment votre cerveau choisit-il vraiment les moments importants ?"
        valid, issues = self._validated(data)
        self.assertFalse(valid)
        self.assertTrue(any("RÉPONSE FLASH" in i or "ANSWER" in i for i in issues), issues)

    def test_generic_filler_hook_is_rejected(self):
        """11 of 17 published videos opened with an interchangeable
        "Vous avez déjà…" filler and averaged 11s watched on ~39s Shorts.
        The prompt forbade it; nothing enforced it."""
        for filler in ("Vous avez déjà ressenti cela, n'est-ce pas ?",
                       "Vous vous réveillez avant votre alarme parfois."):
            data = _arc_fixture()
            data["hook"] = filler
            data["scenes"][0]["caption"] = filler
            valid, issues = self._validated(data)
            self.assertFalse(valid, f"should reject: {filler}")
            self.assertTrue(any("ACCROCHE" in i for i in issues), issues)

    def test_final_scene_without_loopback_is_rejected(self):
        data = _arc_fixture()
        data["scenes"][-1]["caption"] = "Les citrouilles décorent les marchés pendant l'automne doré."
        valid, issues = self._validated(data)
        self.assertFalse(valid)
        self.assertTrue(any("LOOP-BACK" in issue for issue in issues), issues)

    def test_french_function_words_do_not_fake_overlap(self):
        # "votre/pour/avec..." appear in almost every French sentence; they
        # must be stopwords, otherwise any two sentences would "overlap".
        hook = self.sg._content_concepts("Votre cerveau sauvegarde vos souvenirs pendant le sommeil.")
        tail = self.sg._content_concepts("Et votre esprit garde aussi vos souvenirs pour demain.")
        self.assertIn("souvenir", hook & tail)
        self.assertNotIn("votre", hook)
        self.assertNotIn("pour", tail)


class FrenchSeoOutputTests(unittest.TestCase):
    """Metadata quality faults measured on the live channel on 2026-07-26:
    107 English tags across 11 videos, 35 template-scaffolding tags, and
    descriptions repeating the same sentence 2-3 times."""

    def setUp(self):
        try:
            from seo_generator import generate_seo_package
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")
        self.package = generate_seo_package(
            "Ce que votre corps vous dit quand la mâchoire craque en mâchant",
            {
                "title": "Pourquoi la mâchoire craque en mâchant ?",
                "description": "Ce que votre corps vous dit quand la mâchoire craque en mâchant.",
                "hook": "Ta mâchoire craque en mâchant",
                "cta": "Abonne-toi pour plus de science simple.",
            },
        )

    def test_no_english_tags_on_a_french_channel(self):
        from seo_generator import ENGLISH_TAG_BLOCKLIST
        for tag in self.package["tags"]:
            self.assertNotIn(
                tag.lower(), ENGLISH_TAG_BLOCKLIST,
                f"English tag '{tag}' splits the French audience signal",
            )

    def test_no_template_scaffolding_tags(self):
        # "faut", "qu'il", "comprendre" are title-template glue, not keywords.
        for junk in ("faut", "qu'il", "quil", "comprendre", "explique", "semble"):
            self.assertNotIn(junk, [t.lower() for t in self.package["tags"]])

    def test_description_does_not_repeat_the_opening_sentence(self):
        import re
        description = self.package["description"]
        sentences = [
            re.sub(r"[^a-zà-ÿœ0-9 ]", "", s.lower()).strip()
            for s in re.split(r"(?<=[.!?])\s+", description) if s.strip()
        ]
        self.assertEqual(
            len(sentences), len(set(sentences)),
            f"duplicate sentence in description:\n{description}",
        )

    def test_hashtags_are_unique(self):
        import re
        tags = [h.lower() for h in re.findall(r"#\w+", self.package["description"])]
        self.assertEqual(len(tags), len(set(tags)), tags)


class MetadataSweepTests(unittest.TestCase):
    """scripts/fr_metadata_sweep.py repairs the ALREADY-PUBLISHED videos."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import fr_metadata_sweep
        self.sweep = fr_metadata_sweep

    def test_strips_english_tags_keeps_french(self):
        tags, report = self.sweep.clean_tags(
            "Pourquoi les genoux qui craquent en bougeant ?",
            ["anatomy", "humanbody", "bodyfacts", "yourbody", "corps", "genoux"],
        )
        self.assertEqual(len(report["removed_english"]), 4)
        self.assertIn("corps", tags)
        self.assertIn("genoux", tags)
        for tag in tags:
            self.assertFalse(self.sweep._is_english_tag(tag), tag)

    def test_accented_french_tag_is_never_treated_as_english(self):
        self.assertFalse(self.sweep._is_english_tag("humidité"))
        self.assertFalse(self.sweep._is_english_tag("santé"))
        self.assertTrue(self.sweep._is_english_tag("humanbody"))

    def test_merges_repeated_hashtag_blocks(self):
        raw = ("Phrase utile.\n\nAutre phrase.\n\n"
               "#shorts #corps #anatomie\n\n#shorts #corps #anatomie\n\n#corps")
        cleaned, report = self.sweep.clean_description(raw)
        self.assertEqual(cleaned.count("#shorts"), 1)
        self.assertEqual(cleaned.count("#corps"), 1)
        self.assertGreaterEqual(report["hashtag_blocks_merged"], 1)

    def test_is_idempotent(self):
        """Re-running must not keep rewriting the same video (quota burn)."""
        title = "Pourquoi le silence devient inconfortable ?"
        first, _ = self.sweep.clean_tags(title, ["anatomy", "bodyfacts", "corps", "silence"])
        second, _ = self.sweep.clean_tags(title, first)
        self.assertEqual({t.lower() for t in first}, {t.lower() for t in second})

        desc = "Une phrase. Une phrase.\n\n#a #b\n\n#a"
        once, _ = self.sweep.clean_description(desc)
        twice, _ = self.sweep.clean_description(once)
        self.assertEqual(once, twice)


class SceneVisualSafetyTests(unittest.TestCase):
    """Live-channel inspection on 2026-07-27 found two published Shorts whose
    opening visual passed every existing check:
      * "Pourquoi un muscle tressaille tout seul ?" — out-of-focus frame
        (edge energy 1.09); stock CLIPS were only size-checked, never viewed.
      * "Pourquoi le sursaut du corps en s'endormant ?" — blood-spattered
        horror face on a calm French science channel.
    """

    def setUp(self):
        try:
            from media_validator import validate_scene_image, MediaValidationError
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")
        self.validate = validate_scene_image
        self.error = MediaValidationError

    def _write(self, array):
        import tempfile
        from PIL import Image
        import numpy as np
        path = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
        Image.fromarray(np.uint8(array)).save(path, quality=95)
        return path

    def test_out_of_focus_image_is_rejected(self):
        import numpy as np
        # Smooth gradient = no edges = the "mush" that shipped.
        blur = np.tile(np.linspace(40, 90, 700, dtype=float), (900, 1)).T
        blurry = np.dstack([blur] * 3)
        with self.assertRaises(self.error) as ctx:
            self.validate(self._write(blurry))
        self.assertIn("focus", str(ctx.exception).lower())

    def test_sharp_image_still_passes(self):
        import numpy as np
        rng = np.random.default_rng(7)
        sharp = rng.integers(0, 255, size=(900, 700, 3))
        result = self.validate(self._write(sharp))
        self.assertGreater(result["sharpness"], 3.0)

    def test_shock_terms_never_reach_a_stock_search(self):
        from image_generator import _safe_query
        for unsafe in ("un cauchemar effrayant avec du sang",
                       "du sang partout", "une scène de zombie horreur"):
            self.assertEqual(_safe_query(unsafe, "human body science"),
                             "human body science", unsafe)
        # A legitimate scene must survive untouched.
        good = "les genoux qui craquent en bougeant"
        self.assertEqual(_safe_query(good, "human body science"), good)

    def test_prompt_carries_anti_gore_constraints(self):
        from image_generator import DARK_STYLE_SUFFIX
        for term in ("no blood", "no gore", "no horror"):
            self.assertIn(term, DARK_STYLE_SUFFIX)


class ThumbnailTextTests(unittest.TestCase):
    """Live thumbnails on 2026-07-27 read "PRNOM OUBLI", "NUD AU VENTRE" and
    "MCHOIRE": the word filter stripped every accented French character
    because its regex was [^A-Z0-9']. On a France-first channel the thumbnail
    text was literally misspelled."""

    def test_accented_french_survives_the_word_filter(self):
        import re
        pattern = r"[^A-ZÀ-ÿŒÆ0-9'’-]"
        cases = {
            "PRÉNOM": "PRÉNOM", "NŒUD": "NŒUD",
            "MÂCHOIRE": "MÂCHOIRE", "REPÈRE": "REPÈRE", "CŒUR": "CŒUR",
        }
        for raw, expected in cases.items():
            self.assertEqual(re.sub(pattern, "", raw), expected)

    def test_video_editor_uses_the_accent_safe_pattern(self):
        source = (SRC_DIR / "video_editor.py").read_text()
        self.assertNotIn(
            'sub(r"[^A-Z0-9\']"', source,
            "the accent-destroying regex must never come back",
        )


class VisualReuseTests(unittest.TestCase):
    """Five live videos shared visuals at 93-95% similarity even though a
    288-entry media ledger existed: it stored SHA-256, so a re-encoded copy
    of the same stock clip hashed differently and passed."""

    def setUp(self):
        try:
            import image_generator
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")
        self.ig = image_generator

    def test_near_identical_hashes_are_blocked(self):
        # 1-bit apart: the exact distance measured between the two live
        # videos that reused one clip.
        base = "phash:383a3abeb8988000"
        near = "phash:383a3abeb8988010"
        self.assertIsNotNone(self.ig._perceptual_clash(near, {base}))

    def test_distinct_visuals_are_allowed(self):
        base = "phash:021a1e3c3c3c3804"      # knee X-ray
        other = "phash:90bc3c7838001800"     # time render (distance 18)
        self.assertIsNone(self.ig._perceptual_clash(other, {base}))

    def test_malformed_or_missing_hash_never_blocks(self):
        self.assertIsNone(self.ig._perceptual_clash(None, {"phash:0000000000000000"}))
        self.assertIsNone(self.ig._perceptual_clash("phash:zzzz", {"phash:0000000000000000"}))
        # a byte-hash in the ledger must not be misread as perceptual
        self.assertIsNone(self.ig._perceptual_clash("phash:383a3abeb8988000", {"a" * 64}))


class PublicApiTests(unittest.TestCase):
    """src/__init__.py once declared __all__ with zero resolvable names."""

    def test_every_advertised_name_is_lazy_mapped(self):
        import src
        self.assertGreater(len(src.__all__), 10)
        for name in src.__all__:
            self.assertIn(name, src._LAZY_EXPORTS, f"{name} in __all__ but has no lazy mapping")

    def test_unknown_attribute_still_raises(self):
        import src
        with self.assertRaises(AttributeError):
            src.DEFINITELY_NOT_A_REAL_EXPORT_123


class SecretHygieneTests(unittest.TestCase):
    """`.env` was NOT ignored while UPDATE_ONLY_MANIFEST.md instructs the
    operator to run `git add .` — one command from leaking GROQ_API_KEY and
    the Google OAuth refresh token to a public repo."""

    def setUp(self):
        self.gitignore = (ROOT / ".gitignore").read_text()

    def test_dotenv_is_ignored_but_template_is_kept(self):
        self.assertIn(".env", self.gitignore)
        self.assertIn("!env.example", self.gitignore)
        self.assertTrue((ROOT / "env.example").exists(), "env.example must stay tracked")

    def test_run_artifacts_are_ignored(self):
        for pattern in ("pipeline.log", "output/*", ".venv/"):
            self.assertIn(pattern, self.gitignore, f".gitignore missing {pattern}")

    def test_no_env_file_is_tracked_by_git(self):
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True
        ).stdout.split()
        leaked = [f for f in tracked if f == ".env" or f.startswith(".env.")]
        self.assertEqual(leaked, [], f"secret files are tracked: {leaked}")


class AnalyticsDependencyTests(unittest.TestCase):
    """analytics.yml installs a light dep set (no numpy/Pillow). A
    module-level `import numpy` in seo_analytics.py made every single
    'YouTube Analytics Sync' run die on import, which is why no video in
    data/video_history.json ever received real view counts."""

    def test_seo_analytics_does_not_import_numpy_or_pillow_at_module_level(self):
        import ast
        tree = ast.parse((SRC_DIR / "seo_analytics.py").read_text())
        top_level = set()
        for node in tree.body:                      # module scope ONLY
            if isinstance(node, ast.Import):
                top_level |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                top_level.add(node.module.split(".")[0])
        for heavy in ("numpy", "PIL"):
            self.assertNotIn(
                heavy, top_level,
                f"{heavy} must stay a lazy import inside score_thumbnail()",
            )

    def test_analytics_entrypoint_imports_without_numpy(self):
        """Simulates the analytics runner, where numpy/Pillow are absent."""
        code = (
            "import sys\n"
            "for m in ('numpy','PIL','PIL.Image'): sys.modules[m]=None\n"
            f"sys.path.insert(0, {str(SRC_DIR)!r})\n"
            "import analytics_updater\n"
        )
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0,
                         f"analytics entrypoint needs numpy: {result.stderr[-400:]}")

    def test_optional_metrics_are_dropped_not_fatal(self):
        """impressions/CTR are unavailable on this channel (see the
        _dropped_metrics field in data/seo_diag_*.json). Requesting them
        unconditionally failed the whole query, losing views AND retention."""
        source = (SRC_DIR / "seo_analytics.py").read_text()
        self.assertIn("Unknown identifier", source,
                      "fetch_actual_performance must retry without unsupported metrics")


class ThresholdParityTests(unittest.TestCase):
    """env.example advertised 70/60 while production ran 85/85, so a local
    run accepted scripts that CI would reject."""

    def setUp(self):
        self.workflow = (ROOT / ".github" / "workflows" / "main.yml").read_text()
        self.env_example = (ROOT / "env.example").read_text()

    def _env_value(self, text, key, sep):
        import re
        match = re.search(rf'^\s*{key}{sep}\s*"?([\d.]+)"?\s*$', text, re.MULTILINE)
        self.assertIsNotNone(match, f"{key} not found")
        return match.group(1)

    def test_quality_gates_match_production(self):
        for key in ("MIN_HOOK_SCORE", "QUALITY_APPROVAL_THRESHOLD"):
            self.assertEqual(
                self._env_value(self.env_example, key, "="),
                self._env_value(self.workflow, key, ":"),
                f"{key} differs between env.example and main.yml",
            )


class DestructiveWorkflowTests(unittest.TestCase):
    """Video deletion is irreversible; the cleanup workflow hardcoded --apply,
    so one click on 'Run workflow' destroyed videos with no confirmation."""

    def test_dead_cleanup_defaults_to_dry_run(self):
        workflow = (ROOT / ".github" / "workflows" / "yt_dead_cleanup_fr.yml").read_text()
        self.assertIn("inputs:", workflow, "cleanup must expose an apply input")
        self.assertIn("default: false", workflow)
        self.assertNotIn(
            "run: python scripts/yt_dead_cleanup_fr.py --apply", workflow,
            "cleanup must not hardcode --apply",
        )


class TitlePatternTests(unittest.TestCase):
    """_title_pattern() only knew English templates, so every French title
    landed in 'OTHER' and the whole A/B comparison collapsed to one bucket."""

    def test_french_titles_bucket_distinctly(self):
        from seo_analytics import _title_pattern
        cases = {
            "Pourquoi le hoquet commence brusquement ?": "POURQUOI",
            "Ce que votre corps vous dit quand le ventre se serre": "CE_QUE_VOTRE_CORPS",
            "La science derrière le temps qui semble accélérer": "LA_SCIENCE",
            "Corps lourd": "SERIE_COURTE",
        }
        for title, expected in cases.items():
            self.assertEqual(_title_pattern(title), expected, title)
        self.assertGreater(len({_title_pattern(t) for t in cases}), 1)


if __name__ == "__main__":
    unittest.main()
