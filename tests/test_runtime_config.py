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
    """Valid French 8-scene script: Accroche → Suspense → … → Boucle."""
    return {
        "title": "Sommeil Et Mémoire Cerveau",
        "hook": "Votre cerveau sauvegarde vos souvenirs pendant le sommeil.",
        "cta": "Abonnez-vous pour la science du corps, simplement.",
        "scenes": [
            {"visual": "cerveau lumineux pendant le sommeil", "caption": "Votre cerveau sauvegarde vos souvenirs pendant le sommeil."},
            {"visual": "signaux de mémoire entre neurones", "caption": "Mais comment votre cerveau choisit-il les moments qui restent importants après une longue journée ?"},
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

    def test_scene_two_without_open_question_is_rejected(self):
        data = _arc_fixture()
        data["scenes"][1]["caption"] = "Votre cerveau continue simplement de faire cela chaque jour."
        valid, issues = self._validated(data)
        self.assertFalse(valid)
        self.assertTrue(any("SUSPENSE" in issue for issue in issues), issues)

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
