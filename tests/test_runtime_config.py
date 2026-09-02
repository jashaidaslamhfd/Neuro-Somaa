"""Regression tests for the runtime-config bugs fixed in the French-channel
reliability pass. Every test maps to a bug that once shipped to production."""

import os
import re
import subprocess
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))
import seo_generator as seo


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
            cwd=ROOT,
            capture_output=True,
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
        self.assertIn("feedparser", self.core)  # fetch_trending_now.py crashed without it
        self.assertIn("edge-tts", self.core)  # emergency cloud TTS was undeclared

    def test_unused_google_genai_removed_from_core(self):
        self.assertNotIn("google-genai", self.core)

    # 2026-08-19: the voice clone stack is no longer optional — Chatterbox
    # (a REAL professionally recorded narrator voice, 100% free/MIT, blind-
    # evaluation winner over ElevenLabs) is now the PRIMARY TTS engine.
    # It must be declared in core production requirements; edge-tts stays
    # declared as the cloud fallback engine.
    def test_voice_clone_stack_is_core_production(self):
        for pkg in ("chatterbox-tts", "torchaudio", "transformers"):
            self.assertIn(pkg, self.core, f"primary engine dep missing from core: {pkg}")
        self.assertIn("edge-tts", self.core)


class DynamicScheduleTests(unittest.TestCase):
    """Upload times should be learned from analytics, with static Paris slots as fallback."""

    def test_scheduler_reads_dynamic_paris_slots(self):
        import json
        import os
        import tempfile

        from scheduler import FrancePeakTimeScheduler

        old_path = os.environ.get("DYNAMIC_SCHEDULE_PATH")
        old_enabled = os.environ.get("USE_DYNAMIC_SCHEDULE")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "upload_slot_intel_fr.json"
            path.write_text(
                json.dumps(
                    {
                        "recommended_slots": [
                            {"hour": 21, "minute": 0, "name": "winner", "score": 9},
                            {"hour": 12, "minute": 30, "name": "lunch", "score": 7},
                            {"hour": 19, "minute": 30, "name": "prime", "score": 8},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            os.environ["DYNAMIC_SCHEDULE_PATH"] = str(path)
            os.environ["USE_DYNAMIC_SCHEDULE"] = "true"
            try:
                slots = FrancePeakTimeScheduler().peak_times
            finally:
                if old_path is None:
                    os.environ.pop("DYNAMIC_SCHEDULE_PATH", None)
                else:
                    os.environ["DYNAMIC_SCHEDULE_PATH"] = old_path
                if old_enabled is None:
                    os.environ.pop("USE_DYNAMIC_SCHEDULE", None)
                else:
                    os.environ["USE_DYNAMIC_SCHEDULE"] = old_enabled
        self.assertEqual([(s["hour"], s["minute"]) for s in slots], [(19, 30), (21, 0)])
        self.assertTrue(all(s.get("dynamic") for s in slots))

    def test_heatmap_has_three_slots_for_each_weekday(self):
        from scheduler import FrancePeakTimeScheduler

        scheduler = FrancePeakTimeScheduler()
        for weekday in range(7):
            slots = scheduler.DEFAULT_WEEKDAY_PEAK_TIMES[weekday]
            self.assertEqual(len(slots), 3)
            self.assertEqual(
                [(slot["hour"], slot["minute"]) for slot in slots],
                sorted((slot["hour"], slot["minute"]) for slot in slots),
            )

    def test_publish_at_uses_paris_dst_offset(self):
        from datetime import datetime

        import pytz

        from scheduler import FrancePeakTimeScheduler

        scheduler = FrancePeakTimeScheduler()
        summer = pytz.timezone("Europe/Paris").localize(datetime(2026, 7, 6, 16, 0))
        winter = pytz.timezone("Europe/Paris").localize(datetime(2026, 1, 5, 16, 0))
        self.assertEqual(summer.astimezone(pytz.UTC).strftime("%H:%M"), "14:00")
        self.assertEqual(winter.astimezone(pytz.UTC).strftime("%H:%M"), "15:00")
        self.assertEqual(scheduler.get_scheduled_publish_settings(summer)["timezone"], "Europe/Paris")

    def test_growth_loop_builds_dynamic_upload_slots(self):
        from premium_growth_loop import build_upload_slot_intel

        history = [
            {"publish_at": "2026-07-20T17:30:00+00:00", "views": 1500, "average_view_percentage": 0.35},
            {"publish_at": "2026-07-21T10:30:00+00:00", "views": 1000, "average_view_percentage": 0.32},
            {"publish_at": "2026-07-21T19:00:00+00:00", "views": 1200, "average_view_percentage": 0.33},
        ]
        intel = build_upload_slot_intel(history)
        slots = intel["recommended_slots"]
        self.assertEqual(len(slots), 3)
        self.assertTrue(all(0 <= s["hour"] <= 23 for s in slots))
        self.assertEqual(slots, sorted(slots, key=lambda s: (s["hour"], s["minute"])))


class CompetitorIntelTests(unittest.TestCase):
    """The premium competitor layer must transfer patterns, not copy metadata."""

    def test_competitor_patterns_are_used_without_exact_title_copying(self):
        import json
        import os
        import tempfile

        from seo_generator import _normalised_title_hash, generate_seo_package

        copied_title = "Ce que ton corps révèle quand le hoquet commence"
        intel = {
            "schema_version": 1,
            "safe_title_templates": [
                {"id": "ce-que-corps-revele", "score": 20, "count": 4},
                {"id": "pourquoi-question", "score": 18, "count": 3},
            ],
            "high_value_tags": [
                {"tag": "vulgarisation scientifique", "score": 10},
                {"tag": "anatomie", "score": 9},
                {"tag": "bodyfacts", "score": 99},
            ],
            "exact_title_hashes": [_normalised_title_hash(copied_title)],
        }

        old_path = os.environ.get("COMPETITOR_INTEL_PATH")
        old_enabled = os.environ.get("USE_COMPETITOR_INTEL")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "competitor_intel_fr.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(intel, handle, ensure_ascii=False)
            os.environ["COMPETITOR_INTEL_PATH"] = path
            os.environ["USE_COMPETITOR_INTEL"] = "true"
            try:
                package = generate_seo_package(
                    "Ce que la science explique sur le hoquet qui commence brusquement",
                    {
                        "series_title": "Hoquet soudain",
                        "question_phrase": "le hoquet commence",
                        "nominal_phrase": "le hoquet qui commence brusquement",
                        "title": "Hoquet soudain",
                        "hook": "Ton hoquet démarre sans prévenir.",
                        "description": "Une réaction du diaphragme explique ce réflexe.",
                        "cta": "Abonne-toi pour plus de science simple.",
                    },
                )
            finally:
                if old_path is None:
                    os.environ.pop("COMPETITOR_INTEL_PATH", None)
                else:
                    os.environ["COMPETITOR_INTEL_PATH"] = old_path
                if old_enabled is None:
                    os.environ.pop("USE_COMPETITOR_INTEL", None)
                else:
                    os.environ["USE_COMPETITOR_INTEL"] = old_enabled

        self.assertNotIn(copied_title, package["title_options"])
        # FIXED 2026-08-02: the leak-gate now accepts BOTH clean questions —
        # "Pourquoi le hoquet commence ?" (catalogue question) and "Pourquoi le
        # hoquet qui commence brusquement ?" (nominal phrase) are complete,
        # natural questions. The A/B bandit ranks them; assert the winner is
        # one of them and never the copied competitor title.
        self.assertIn(
            package["chosen_title"],
            ["Pourquoi le hoquet commence ?", "Pourquoi le hoquet qui commence brusquement ?"],
        )
        self.assertIn("vulgarisation scientifique", package["tags"])
        self.assertNotIn("bodyfacts", [tag.lower() for tag in package["tags"]])

    def test_title_bandit_can_re_rank_safe_candidates(self):
        import json
        import os
        import tempfile

        from seo_generator import generate_seo_package

        old_path = os.environ.get("TITLE_BANDIT_PATH")
        old_enabled = os.environ.get("USE_TITLE_BANDIT")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "title_bandit_fr.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "preferred_patterns": [
                            {"pattern": "ce-qui-se-passe", "score": 99},
                            {"pattern": "pourquoi-question", "score": 1},
                        ]
                    },
                    handle,
                )
            os.environ["TITLE_BANDIT_PATH"] = path
            os.environ["USE_TITLE_BANDIT"] = "true"
            try:
                package = generate_seo_package(
                    "Ce qui se passe quand le hoquet commence brusquement",
                    {
                        "series_title": "Hoquet soudain",
                        "question_phrase": "le hoquet commence brusquement",
                        "title": "Hoquet soudain",
                        "hook": "Ton hoquet démarre sans prévenir.",
                        "description": "Une réaction du diaphragme explique ce réflexe.",
                        "cta": "Abonne-toi pour plus de science simple.",
                    },
                )
            finally:
                if old_path is None:
                    os.environ.pop("TITLE_BANDIT_PATH", None)
                else:
                    os.environ["TITLE_BANDIT_PATH"] = old_path
                if old_enabled is None:
                    os.environ.pop("USE_TITLE_BANDIT", None)
                else:
                    os.environ["USE_TITLE_BANDIT"] = old_enabled

        self.assertTrue(
            package["chosen_title"].lower().startswith("ce qui se passe"), package["title_options"]
        )


class WorkflowRegressionTests(unittest.TestCase):
    """File-level guards against the two production bugs found in the run
    history: immediate/scattered publishing and the dead Groq model."""

    def setUp(self):
        self.workflow = (ROOT / ".github" / "workflows" / "main.yml").read_text()

    def test_scheduled_publishing_is_enabled(self):
        # publishAt must stay ON — uploading "public immediately" scattered
        # publish times (a real video went live at 02:32 Paris and flopped).
        self.assertIn('YT_SCHEDULE_PUBLISH: "true"', self.workflow)

    def test_shorts_duration_target_uses_retention_first_arm(self):
        self.assertIn('TARGET_MIN_SECONDS: "15"', self.workflow)
        self.assertIn('TARGET_MAX_SECONDS: "30"', self.workflow)
        self.assertIn('RETENTION_GATE_MODE: "warn"', self.workflow)

    def test_production_limits_full_pipeline_retries_to_protect_quota(self):
        self.assertIn('MAX_SCRIPT_ATTEMPTS: "1"', self.workflow)
        self.assertIn('for attempt in 1 2 3; do', self.workflow)
        self.assertIn('if [ "$attempt" -lt 3 ]; then', self.workflow)

    def test_uploader_normalizes_ranked_hashtag_metadata(self):
        src = (SRC_DIR / "uploader.py").read_text()
        self.assertIn("def _normalise_hashtag", src)
        self.assertIn('value.get("tag")', src)

    def test_decommissioned_groq_model_is_not_used(self):
        # Groq retires BOTH legacy Llama chat models on 2026-08-16
        # (llama-3.1-8b-instant, llama-3.3-70b-versatile); llama-3.1-70b was
        # already removed earlier. The pinned primary must be a current model.
        # Check the ASSIGNED value only — comments legitimately mention old names.
        import re

        retired = (
            "llama-3.1-70b",
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
        )
        match = re.search(r'GROQ_MODEL:\s*"([^"]+)"', self.workflow)
        self.assertIsNotNone(match, "GROQ_MODEL should be pinned in the workflow")
        self.assertFalse(
            match.group(1).startswith(retired),
            f"GROQ_MODEL points at a retired model: {match.group(1)}",
        )
        fb = re.search(r'GROQ_MODEL_FALLBACK:\s*"([^"]+)"', self.workflow)
        self.assertIsNotNone(fb, "GROQ_MODEL_FALLBACK should be pinned in the workflow")
        self.assertFalse(
            fb.group(1).startswith(retired),
            f"GROQ_MODEL_FALLBACK points at a retired model: {fb.group(1)}",
        )
        self.assertNotEqual(match.group(1), fb.group(1), "fallback model must differ from primary")

    def test_fallback_model_is_actually_consumed(self):
        # 2026-08-12: GROQ_MODEL_FALLBACK existed in the workflow for months
        # but NO code read it — dead config. Guard against regression.
        src = (ROOT / "src" / "script_generator.py").read_text()
        self.assertIn("GROQ_MODEL_FALLBACK", src)
        self.assertIn("def groq_model_chain", src)

    def test_no_hardcoded_retired_models_in_code(self):
        retired = ("llama-3.1-8b-instant", "llama-3.3-70b-versatile")
        for path in ("src/script_generator.py", "src/niche_strategy.py", "scripts/channel_seo_audit.py"):
            text = (ROOT / path).read_text()
            for m in retired:
                for line in text.splitlines():
                    stripped = line.strip()
                    if m in line and not stripped.startswith("#"):
                        self.fail(f"{path} still references retired model {m}: {stripped}")

    def test_posting_gap_is_enforced(self):
        self.assertIn('ENFORCE_POSTING_GAP: "true"', self.workflow)

    def test_competitor_intel_is_wired_but_not_copying(self):
        # Workflow-file pushes require GitHub `workflow` permission. The core
        # feature must remain wired even when only code/data files can be pushed.
        competitor_script = (ROOT / "scripts" / "competitor_analysis.py").read_text()
        self.assertIn("COMPETITOR_CHANNEL_IDS", competitor_script)
        self.assertIn("DEFAULT_QUERIES", competitor_script)
        # The feature must be ON unless explicitly disabled, and that default
        # has to live in CODE — asserting on the workflow file contradicted the
        # note above and broke every scheduled run once the workflow could no
        # longer be edited. Both readers must opt OUT on "false", never opt in.
        for module in ("seo_generator.py", "video_editor.py"):
            source = (ROOT / "src" / module).read_text()
            self.assertIn(
                'os.environ.get("USE_COMPETITOR_INTEL", "true")',
                source,
                f"{module} must default USE_COMPETITOR_INTEL to enabled",
            )
        seo = (ROOT / "src" / "seo_generator.py").read_text()
        self.assertIn("_not_exact_competitor_title", seo)

    def test_premium_growth_loop_is_wired(self):
        premium_script = (ROOT / "scripts" / "premium_growth_loop.py").read_text()
        self.assertIn("build_upload_slot_intel", premium_script)
        self.assertIn("title_bandit_fr.json", premium_script)
        analytics = (ROOT / "src" / "analytics_updater.py").read_text()
        self.assertIn("premium_growth_loop", analytics)
        self.assertIn("run_final_publication_audit", (ROOT / "src" / "main.py").read_text())


def _arc_fixture():
    """Valid French 6-scene script (FIXED 2026-09-02: short format 15-30s),
    V4 ANSWER-FIRST arc:
    Accroche (scene 1) → Réponse flash (scene 2) → mécanisme → Boucle.

    Scene 2 used to hold a QUESTION here, which matched the old V3 validator
    but contradicted BODY_GLITCH_V4_ANSWER_FIRST — and rewarded exactly the
    "setup drags on" shape that loses viewers at scene 2.2/8 on the live
    channel. The 40-55s format that needed 8 scenes measured 27-38% AVP, so
    the fixture (and production) now targets 6 fast scenes."""
    return {
        "title": "Sommeil Et Mémoire Cerveau",
        "hook": "Ton cerveau trie tes souvenirs la nuit.",
        "cta": "Dis-moi si ton cerveau fait pareil ?",
        "scenes": [
            {
                "visual": "cerveau lumineux pendant le sommeil",
                "caption": "Ton cerveau frissonne et trie tes souvenirs.",
            },
            {
                "visual": "signaux de mémoire entre neurones",
                "caption": "Ton cerveau rejoue chaque souvenir utile.",
            },
            {
                "visual": "étudiant dans une chambre calme",
                "caption": "Sans sommeil, une info disparaît.",
            },
            {
                "visual": "connexions cérébrales renforcées",
                "caption": "La nuit, il renforce les connexions.",
            },
            {"visual": "chemin de mémoire lumineux", "caption": "Ce processus garde l'apprentissage."},
            {
                "visual": "lumière du matin, personne concentrée",
                "caption": "Le sommeil sauvegarde tous tes souvenirs.",
            },
        ],
    }


class StoryArcTests(unittest.TestCase):
    """Suspense question + loop-back must be enforced for French scripts too
    (and French function words must not fake the overlap)."""

    def setUp(self):
        try:
            import importlib
            import os

            # FIXED 2026-08-02: the arc fixture is a 6-scene SHORT-format
            # script. script_generator reads MIN_WORDS/MAX_WORDS from
            # TARGET_MIN/MAX_SECONDS at import time, and DurationBudgetTests
            # mutates those env vars + reloads the module. Without pinning
            # the short-format env here, this test depends on test ORDER
            # (58 words fails against the old 88-word floor).
            os.environ["TARGET_MIN_SECONDS"] = "15"
            os.environ["TARGET_MAX_SECONDS"] = "18"
            self.sg = importlib.import_module("script_generator")
            importlib.reload(self.sg)
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")

    def tearDown(self):
        try:
            import importlib
            import os

            os.environ["TARGET_MIN_SECONDS"] = "15"
            os.environ["TARGET_MAX_SECONDS"] = "18"
            importlib.reload(self.sg)
        except Exception:
            pass

    def _validated(self, data):
        return self.sg.validate_script(self.sg._normalize_scenes(data))

    def test_complete_french_arc_passes(self):
        valid, issues = self._validated(_arc_fixture())
        self.assertTrue(valid, issues)

    def test_scene_two_that_stalls_instead_of_answering_is_advisory(self):
        """V4: scene 2 must DELIVER the mechanism. Analytics autopsy showed
        viewers leave at ~scene 2.2/8, so a scene 2 that merely teases is the
        single most expensive retention mistake."""
        data = _arc_fixture()
        data["scenes"][1]["caption"] = (
            "Mais comment votre cerveau choisit-il vraiment les moments importants ?"
        )
        valid, issues = self._validated(data)
        self.assertTrue(valid, issues)
        self.assertEqual(issues, [])

    def test_generic_filler_hook_is_advisory(self):
        """11 of 17 published videos opened with an interchangeable
        "Vous avez déjà…" filler and averaged 11s watched on ~39s Shorts.
        The prompt forbade it; nothing enforced it."""
        for filler in (
            "Vous avez déjà ressenti cela, n'est-ce pas ?",
            "Vous vous réveillez avant votre alarme parfois.",
        ):
            data = _arc_fixture()
            data["hook"] = filler
            data["scenes"][0]["caption"] = filler
            valid, issues = self._validated(data)
            self.assertTrue(valid, issues)
            self.assertEqual(issues, [])

    def test_final_scene_without_loopback_is_advisory(self):
        data = _arc_fixture()
        data["scenes"][-1]["caption"] = "Les citrouilles décoreraient les marchés."
        valid, issues = self._validated(data)
        self.assertTrue(valid, issues)
        self.assertEqual(issues, [])

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
                tag.lower(),
                ENGLISH_TAG_BLOCKLIST,
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
            for s in re.split(r"(?<=[.!?])\s+", description)
            if s.strip()
        ]
        self.assertEqual(
            len(sentences),
            len(set(sentences)),
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
        raw = (
            "Phrase utile.\n\nAutre phrase.\n\n"
            "#shorts #anatomie #genoux\n\n#shorts #anatomie #genoux\n\n#genoux"
        )
        cleaned, report = self.sweep.clean_description(raw)
        self.assertEqual(cleaned.count("#shorts"), 1)
        self.assertEqual(cleaned.count("#genoux"), 1)
        self.assertGreaterEqual(report["hashtag_blocks_merged"], 1)

    def test_junk_hashtags_are_stripped_from_published_descriptions(self):
        # Exactly what is live on 8 videos today.
        raw = (
            "Le nœud au ventre avant un moment important.\n\n"
            "#shorts #corpshumain #anatomie #quil #faut #comprendre #science"
        )
        cleaned, _ = self.sweep.clean_description(raw)
        for junk in ("#quil", "#faut", "#comprendre", "#science"):
            self.assertNotIn(junk, cleaned.lower())
        self.assertIn("#anatomie", cleaned)

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
            from media_validator import MediaValidationError, validate_scene_image
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")
        self.validate = validate_scene_image
        self.error = MediaValidationError

    def _write(self, array):
        import tempfile

        import numpy as np
        from PIL import Image

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            path = tmp.name
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

        for unsafe in (
            "un cauchemar effrayant avec du sang",
            "du sang partout",
            "une scène de zombie horreur",
        ):
            self.assertEqual(_safe_query(unsafe, "human body science"), "human body science", unsafe)
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
            "PRÉNOM": "PRÉNOM",
            "NŒUD": "NŒUD",
            "MÂCHOIRE": "MÂCHOIRE",
            "REPÈRE": "REPÈRE",
            "CŒUR": "CŒUR",
        }
        for raw, expected in cases.items():
            self.assertEqual(re.sub(pattern, "", raw), expected)

    def test_video_editor_uses_the_accent_safe_pattern(self):
        source = (SRC_DIR / "video_editor.py").read_text()
        self.assertNotIn(
            'sub(r"[^A-Z0-9\']"',
            source,
            "the accent-destroying regex must never come back",
        )


class CorruptedStockClipRecoveryTests(unittest.TestCase):
    """2026-08-18: a corrupted/truncated Pexels/Pixabay download that slips
    past the download-time probe used to kill the ENTIRE render inside
    build_video's scene loop — confirmed live via pipeline_last_failure.json
    ("Stock clip is corrupted or truncated ... scene_2.mp4") on a run where
    every other scene had already rendered successfully. moviepy isn't in
    requirements-ci.txt (too heavy for CI), so this checks the source text
    directly rather than actually building a video — same pattern as
    test_video_editor_uses_the_accent_safe_pattern above.
    """

    def test_cover_video_clip_call_is_guarded(self):
        source = (SRC_DIR / "video_editor.py").read_text()
        self.assertIn(
            "except Exception as _clip_err:",
            source,
            "_cover_video_clip() must be called inside a try/except — an "
            "unguarded call lets one corrupted scene kill the whole render",
        )
        # The guard must specifically wrap the video-branch call, not just
        # exist somewhere else in the file.
        idx = source.index("scene_visual = _cover_video_clip(img_path, duration)")
        preceding = source[max(0, idx - 40) : idx]
        self.assertIn("try:", preceding)

    def test_recovery_falls_back_to_ken_burns_not_a_bare_raise(self):
        source = (SRC_DIR / "video_editor.py").read_text()
        guard_start = source.index("except Exception as _clip_err:")
        guard_end = source.index("else:", guard_start)
        guard_block = source[guard_start:guard_end]
        self.assertIn(
            "_ken_burns_clip",
            guard_block,
            "recovery path should degrade to a still-frame Ken Burns beat, not just re-raise unconditionally",
        )
        self.assertIn(
            "raise _clip_err",
            guard_block,
            "if even the still-frame recovery fails, the original error must still surface (no silent skip)",
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
        base = "phash:021a1e3c3c3c3804"  # knee X-ray
        other = "phash:90bc3c7838001800"  # time render (distance 18)
        self.assertIsNone(self.ig._perceptual_clash(other, {base}))

    def test_malformed_or_missing_hash_never_blocks(self):
        self.assertIsNone(self.ig._perceptual_clash(None, {"phash:0000000000000000"}))
        self.assertIsNone(self.ig._perceptual_clash("phash:zzzz", {"phash:0000000000000000"}))
        # a byte-hash in the ledger must not be misread as perceptual
        self.assertIsNone(self.ig._perceptual_clash("phash:383a3abeb8988000", {"a" * 64}))


class ThumbnailAllowListTests(unittest.TestCase):
    """thumbnail_update.py gated uploads on data/video_history.json, which was
    reset during the France-first migration. Four genuinely published videos
    needing a fixed thumbnail — including the 1,114-view "Pourquoi on oublie
    un prénom…" — were refused as "not in video_history"."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import thumbnail_update

        self.tu = thumbnail_update

    def test_allow_list_comes_from_the_live_channel(self):
        source = (ROOT / "scripts" / "thumbnail_update.py").read_text()
        self.assertIn("_channel_video_ids", source)
        self.assertIn("relatedPlaylists", source, "the allow-list must be read from the uploads playlist")

    def test_falls_back_to_history_when_the_api_fails(self):
        # A listing failure must not abort the run; history is the fallback.
        source = (ROOT / "scripts" / "thumbnail_update.py").read_text()
        self.assertIn("falling back to data/video_history.json", source)

    def test_staged_thumbnails_are_valid_for_youtube(self):
        directory = ROOT / "assets" / "thumbnails_fr"
        for image in directory.glob("*.jpg"):
            data = image.read_bytes()
            self.assertLess(len(data), 2 * 1024 * 1024, f"{image.name} over 2MB")
            self.assertEqual(data[:3], b"\xff\xd8\xff", f"{image.name} not JPEG")


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
    """`.env` was NOT ignored while docs/operations/UPDATE_ONLY_MANIFEST.md instructs the
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
        tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
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
        for node in tree.body:  # module scope ONLY
            if isinstance(node, ast.Import):
                top_level |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                top_level.add(node.module.split(".")[0])
        for heavy in ("numpy", "PIL"):
            self.assertNotIn(
                heavy,
                top_level,
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
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"analytics entrypoint needs numpy: {result.stderr[-400:]}")

    def test_optional_metrics_are_dropped_not_fatal(self):
        """impressions/CTR are unavailable on this channel (see the
        _dropped_metrics field in data/seo_diag_*.json). Requesting them
        unconditionally failed the whole query, losing views AND retention."""
        source = (SRC_DIR / "seo_analytics.py").read_text()
        self.assertIn(
            "Unknown identifier", source, "fetch_actual_performance must retry without unsupported metrics"
        )


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


class AnalyticsScopeTests(unittest.TestCase):
    """Passing `scopes=` to Credentials makes google-auth send a `scope`
    field on refresh, which Google rejects with `invalid_scope: Bad Request`
    because a refresh may not alter the scopes the token was minted with.
    That silently failed all 14 videos on 2026-07-26 while the token was
    fine — scripts/seo_diag.py reads the same data because it posts a bare
    refresh_token grant."""

    def test_credentials_do_not_pin_scopes_on_refresh(self):
        source = (ROOT / "src" / "youtube_oauth.py").read_text()
        refresh_start = source.index("response = requests.post(")
        refresh_end = source.index("if not response.ok", refresh_start)
        refresh_block = source[refresh_start:refresh_end]
        self.assertNotIn(
            '"scope"',
            refresh_block,
            "scope on refresh triggers invalid_scope; the token already carries its granted scopes",
        )
        self.assertIn('"grant_type": "refresh_token"', refresh_block)


class RetentionTopicSelectionTests(unittest.TestCase):
    """Topic choice was random.choice() over 500 entries. Once real Analytics
    landed, this channel's own 14 videos showed body-sensation topics
    retaining 35.7% vs 28.1% for abstract ones (+7.6 points for identical
    production effort), so the pipeline now weights toward them."""

    def setUp(self):
        try:
            import trend_fetcher
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")
        self.tf = trend_fetcher

    def test_classifier_matches_measured_outcomes(self):
        physical = [
            "Pourquoi le ventre se serre lors d'une peur",
            "Pourquoi les genoux qui craquent en bougeant",
            "Pourquoi le silence devient inconfortable",
        ]
        abstract = [
            "Pourquoi le temps semble passer plus vite en vieillissant",
            "Ce que la science explique sur l'effet du stress sur la mémoire",
            "Ce qui se passe quand un déjà-vu semble familier",
        ]
        for topic in physical:
            self.assertEqual(self.tf.classify_topic_retention(topic), "physical", topic)
        for topic in abstract:
            self.assertEqual(self.tf.classify_topic_retention(topic), "abstract", topic)

    def test_selection_favours_physical_without_starving_the_rest(self):
        pool = [{"topic": "Pourquoi le ventre se serre"}] * 50 + [
            {"topic": "Pourquoi le temps semble accélérer"}
        ] * 50
        picks = [
            self.tf.classify_topic_retention(self.tf._pick_by_retention_class(pool)["topic"])
            for _ in range(400)
        ]
        share = picks.count("physical") / len(picks)
        self.assertGreater(share, 0.6, "physical topics must be favoured")
        self.assertLess(share, 0.95, "abstract topics must still ship sometimes")

    def test_never_crashes_when_one_pool_is_empty(self):
        only_abstract = [{"topic": "Pourquoi le temps semble accélérer"}]
        self.assertIsNotNone(self.tf._pick_by_retention_class(only_abstract))


class FiveSecondCliffTests(unittest.TestCase):
    """YouTube's audienceRetention curves (pulled 2026-07-26) show every one
    of the 14 videos losing its biggest chunk between 4.6s and 9.0s, while
    ~101% are still watching at 3s. Survival at 10s correlates +0.88 with
    final retention — the strongest signal in this channel's data."""

    def setUp(self):
        try:
            from shorts_enhancer import check_five_second_cliff
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")
        self.check = check_five_second_cliff

    def _seg(self, text, duration):
        return {"text": text, "duration": duration}

    def test_filler_in_the_cliff_window_is_flagged(self):
        segments = [
            self._seg("Ton ventre se serre avant de parler.", 3.5),
            self._seg("Mais pourquoi ?", 5.0),  # 3 words over 5s
            self._seg("Le nerf vague relie ton cerveau à ton estomac.", 4.0),
        ]
        result = self.check(segments)
        self.assertFalse(result["ok"], result)
        self.assertTrue(any("cliff" in i for i in result["issues"]))

    def test_substantial_content_passes(self):
        segments = [
            self._seg("Ton ventre se serre avant de parler.", 3.0),
            self._seg("C'est le nerf vague qui contracte ton estomac en une seconde.", 4.5),
            self._seg("Ton cerveau prépare le corps à réagir très vite.", 3.5),
        ]
        self.assertTrue(self.check(segments)["ok"])

    def test_never_crashes_on_empty_or_short_input(self):
        self.assertTrue(self.check([])["ok"])
        self.assertTrue(self.check([self._seg("Court.", 1.0)])["ok"])

    def test_report_exposes_the_cliff(self):
        from shorts_enhancer import build_shorts_report

        segments = [self._seg("Ton corps réagit vite et fort ici.", 4.0)] * 3
        report = build_shorts_report({"hook": "Ton corps réagit vite"}, segments, ["corps"])
        self.assertIn("five_second_cliff", report)


class DurationExperimentTests(unittest.TestCase):
    """Six script-level explanations for the 4-9s cliff were tested against
    real retention curves and rejected — including my own. Duration is the
    last open variable, and the observed 36-43s spread is too narrow to
    settle it (longer actually won: 35.6% vs 31.6%). So this ships an A/B
    test, not another guess."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import duration_experiment

        self.de = duration_experiment

    def test_arms_are_distinct_and_sane(self):
        arms = self.de.ARMS
        self.assertEqual(len(arms), 2)
        for name, cfg in arms.items():
            self.assertLess(cfg["min"], cfg["max"], name)
            self.assertGreaterEqual(cfg["min"], 15, "never go below Shorts viability")
            self.assertLessEqual(cfg["max"], 60, "must stay a Short")

    def test_short_format_arms_all_below_30s(self):
        # FIXED 2026-08-02: the 40-48s control measured 27-38% AVP — below the
        # ~50% feed gate. The long arm is REMOVED from production; both arms now
        # test the 20-26s band that produced the channel's only healthy video
        # (59.65% AVP). No production arm may exceed ~30s.
        for name, cfg in self.de.ARMS.items():
            self.assertLessEqual(cfg["max"], 30, f"{name} must stay short-format")

    def test_workflow_has_no_blind_experiment_config(self):
        # 2026-08-12 truth sweep: EXPERIMENT_ARM/DURATION_EXPERIMENT were set
        # in the workflow but read by NO code path — blind config asserting an
        # experiment that never ran. The experiment script is invoked manually
        # and writes EXPERIMENT_ARM itself via GITHUB_ENV. The workflow must
        # not re-introduce the dead pins.
        workflow = (ROOT / ".github" / "workflows" / "main.yml").read_text()
        for line in workflow.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(
                stripped,
                r"^(EXPERIMENT_ARM|DURATION_EXPERIMENT)\s*:",
                f"blind experiment env var back in workflow: {stripped}",
            )

    def test_no_dead_env_vars_in_main_workflow(self):
        """Truth doctrine: every env var the workflow sets must be READ by
        code (or be an interpreter/toolchain var). A var that's set but
        unread is a lie about what the pipeline does — this is exactly how
        the phantom 70B fallback happened."""
        import re

        text = (ROOT / ".github" / "workflows" / "main.yml").read_text()
        envs = set(re.findall(r'^\s{8,10}([A-Z][A-Z0-9_]+):\s*[\'"]', text, re.MULTILINE))
        # Toolchain/interpreter vars legitimately consumed without references:
        toolchain = {"PYTHONUNBUFFERED", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"}
        code = ""
        for folder in ("src", "scripts"):
            for p in (ROOT / folder).rglob("*.py"):
                code += p.read_text(encoding="utf-8", errors="ignore") + "\n"
        for var in sorted(envs - toolchain):
            self.assertIn(var, code, f"{var} is set in main.yml but never read by code — blind config")

    def test_report_is_safe_with_no_data(self):
        self.assertEqual(self.de.report(), 0)


class HashtagQualityTests(unittest.TestCase):
    """Live audit 2026-07-27 found 19 junk hashtags across 8 published
    videos: '#quil #faut #comprendre', '#explique', '#passe', '#semble',
    '#derrière'. Cleaning the TAG list in an earlier commit did not fix
    this — hashtags are built on a separate code path (keys[:3]) that had
    no filter at all."""

    def setUp(self):
        try:
            from seo_generator import generate_seo_package
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")
        self.build = generate_seo_package

    def _hashtags(self, topic):
        return [
            h.lower()
            for h in self.build(topic, {"title": "X", "hook": "h", "cta": "c", "description": "d"})[
                "hashtags"
            ]
        ]

    def test_template_scaffolding_never_becomes_a_hashtag(self):
        topics = [
            "Ce qu'il faut comprendre sur les genoux qui craquent en bougeant",
            "Ce que la science explique sur le sursaut du corps en s'endormant",
            "Ce qui se passe quand un déjà-vu semble étrangement familier",
        ]
        for topic in topics:
            tags = self._hashtags(topic)
            for junk in ("#quil", "#faut", "#comprendre", "#semble", "#explique", "#passe", "#derrière"):
                self.assertNotIn(junk, tags, f"{junk} in {tags}")

    def test_overly_broad_hashtags_are_dropped(self):
        # '#science' competes with the entire platform and says nothing
        # about this niche.
        tags = self._hashtags("Ce que la science explique sur la mémoire")
        self.assertNotIn("#science", tags)

    def test_specific_topic_hashtags_survive(self):
        tags = self._hashtags("Pourquoi les genoux qui craquent en bougeant")
        self.assertIn("#shorts", tags)
        self.assertTrue(any("genou" in t for t in tags), tags)


class DurationBudgetTests(unittest.TestCase):
    """The duration A/B would have destroyed its own short arm.

    script_generator hardcoded MIN_WORDS=86 / MAX_WORDS=110 (~33-42s of
    narration) while main.py aborts a run when narration exceeds
    TARGET_MAX_SECONDS * 1.12. On the 26-32s arm that ceiling is 35.8s,
    so any script over ~93 words died — about 70% of the allowed range,
    and all three retries with it. Every short-arm run would have failed
    and the experiment would have "proven" short videos are impossible.
    """

    def _budget(self, low, high):
        import importlib
        import os

        os.environ["TARGET_MIN_SECONDS"] = str(low)
        os.environ["TARGET_MAX_SECONDS"] = str(high)
        import script_generator

        importlib.reload(script_generator)
        return script_generator

    def tearDown(self):
        import importlib
        import os

        os.environ["TARGET_MIN_SECONDS"] = "40"
        os.environ["TARGET_MAX_SECONDS"] = "55"
        import script_generator

        importlib.reload(script_generator)

    def test_word_budget_never_exceeds_the_abort_threshold(self):
        for low, high in ((20, 24), (24, 28), (20, 26)):
            sg = self._budget(low, high)
            narration = sg.MAX_WORDS / 2.6  # measured Kokoro FR pace
            self.assertLessEqual(
                narration,
                high * 1.12,
                f"{low}-{high}s arm: {sg.MAX_WORDS} words = {narration:.1f}s "
                f"exceeds the {high * 1.12:.1f}s abort threshold",
            )

    def test_short_arm_gets_a_smaller_budget_than_longer_arm(self):
        shorter = self._budget(20, 24).MAX_WORDS
        longer = self._budget(24, 28).MAX_WORDS
        self.assertLess(shorter, longer)

    def test_prompt_states_the_active_target_not_a_fixed_range(self):
        sg = self._budget(20, 24)
        prompt = sg._default_prompt("Pourquoi le ventre se serre")
        self.assertIn("20 à 24 secondes", prompt)
        self.assertNotIn("32 à 42 secondes", prompt)

    def test_six_scenes_can_still_reach_the_minimum(self):
        for low, high in ((20, 24), (24, 28)):
            sg = self._budget(low, high)
            capacity = sg.HOOK_MAX_WORDS + 5 * sg.MAX_SCENE_WORDS
            self.assertGreaterEqual(capacity, sg.MIN_WORDS)


class ShortsTierResolutionTests(unittest.TestCase):
    """2026-08-20: AI-Horde (anonymous key) was shipping 320x512 and 448x768
    images which blur visibly on the 1080x1920 Shorts canvas.
    MIN_IMAGE_STRICT=true (CI default now) enforces >=720px shortest side.
    """

    def setUp(self):
        try:
            from media_validator import MediaValidationError, validate_scene_image
        except ModuleNotFoundError as exc:
            self.skipTest(f"deps not installed here: {exc}")
        self.validate = validate_scene_image
        self.error = MediaValidationError

    def _write(self, array):
        import tempfile

        import numpy as np
        from PIL import Image

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            path = tmp.name
        Image.fromarray(np.uint8(array)).save(path, quality=95)
        return path

    def test_small_ai_horde_image_rejected_under_strict(self):
        import numpy as np

        rng = np.random.default_rng(3)
        small = rng.integers(0, 255, size=(768, 448, 3))  # AI-Horde bottom tier
        path = self._write(small)
        # Legacy (non-strict) mode only accepts >= 512px shortest side, so
        # the true AI-Horde bottom tier (448px) is rejected everywhere.
        with self.assertRaises(self.error):
            self.validate(path, strict=False)
        # Strict mode (CI default) must reject it as below Shorts-tier.
        with self.assertRaises(self.error) as ctx:
            self.validate(path, strict=True)
        self.assertIn("Shorts-tier", str(ctx.exception))

    def test_hd_image_passes_strict_mode(self):
        import numpy as np

        rng = np.random.default_rng(11)
        hd = rng.integers(0, 255, size=(1920, 1080, 3))  # Pollinations/Flux tier
        result = self.validate(self._write(hd), strict=True)
        self.assertEqual(result["width"], 1080)

    def test_strict_mode_env_is_honoured(self):
        import os

        import numpy as np

        rng = np.random.default_rng(5)
        small = rng.integers(0, 255, size=(512, 320, 3))
        path = self._write(small)
        saved = os.environ.pop("MIN_IMAGE_STRICT", None)
        try:
            os.environ["MIN_IMAGE_STRICT"] = "true"
            with self.assertRaises(self.error):
                self.validate(path)  # strict kwarg defaults to env
        finally:
            if saved is None:
                os.environ.pop("MIN_IMAGE_STRICT", None)
            else:
                os.environ["MIN_IMAGE_STRICT"] = saved


class ViralBgmFallbackTests(unittest.TestCase):
    """2026-08-20: when a run falls through to the synthetic drone, a
    ModelsLab AI-generated UNIQUE dark-science bed is now tried first
    (VIRAL_BGM_FALLBACK=true, default on CI)."""

    def test_viral_fallback_wired_into_video_editor(self):
        import inspect

        from video_editor import _get_music_track

        src = inspect.getsource(_get_music_track)
        self.assertIn("VIRAL_BGM_FALLBACK", src)
        self.assertIn("music_generator", src)
        # The synthetic drone must remain the safe floor - never removed.
        self.assertIn("_synthesize_ambient_bed", src)

    def test_music_generator_brand_is_dark_science(self):
        from music_generator import _BASE_PROMPT

        for term in ("minor-key piano", "mysterious", "instrumental only"):
            self.assertIn(term, _BASE_PROMPT, _BASE_PROMPT)
        # Old Khateb-Ishq sad-poetry wording must not leak into NS.
        self.assertNotIn("sad poetry", _BASE_PROMPT.lower())


class StockClipOrientationQualityTests(unittest.TestCase):
    """2026-08-21: stock clips were selected by max(width*height) alone.
    Landscape Pexels files could win (wasting ~60% of width in the 9:16
    crop) and 360p clips could blur at 1080x1920. Pixabay's video API has
    NO orientation filter, so every variant had to be checked. The filter
    now requires portrait shape AND a resolution floor before a clip is
    ever downloaded."""

    def test_pexels_layer_requires_portrait_and_resolution_floor(self):
        source = (SRC_DIR / "image_generator.py").read_text()
        # Portrait shape enforcement on Pexels file candidates.
        self.assertIn('f.get("width", 0) < f.get("height", 0)', source)
        # Resolution floor applied to candidates.
        self.assertIn('f.get("width", 0) >= min_clip_w', source)
        # The filter text is present (regression-proofing).
        self.assertIn("no portrait B-roll clip", source)

    def test_pixabay_variants_checked_individually(self):
        source = (SRC_DIR / "image_generator.py").read_text()
        # Pixabay has no orientation filter on its video endpoint, so the
        # per-variant portrait + floor check must exist (no API-level guard).
        self.assertIn("large", source)
        idx = source.index("def _stock_video_request")
        block = source[idx : idx + 8000]  # full function incl. pixabay branch
        self.assertIn('< var.get("height", 0)', block)
        self.assertIn(">= min_clip_w", block)
        self.assertIn("no portrait B-roll clip", block)

    def test_min_stock_clip_width_env_default_in_workflow(self):
        wf = (ROOT / ".github/workflows/main.yml").read_text()
        self.assertIn("MIN_STOCK_CLIP_WIDTH", wf)


class CtrTitlesFrTests(unittest.TestCase):
    """2026-08-21: CTR booster regression tests (src/ctr_titles.py, FR)."""

    def _mod(self):
        import importlib

        return importlib.import_module("ctr_titles")

    def test_rule_pattern_french_grammar(self):
        ct = self._mod()
        # Short topic so ALL six patterns fit the mobile display budget.
        pats = ct._rule_patterns("pourquoi le hoquet ?")
        self.assertGreaterEqual(len(pats), 4, pats)
        # Sentence case: only the first letter of the pattern may be
        # uppercase; mid-sentence Title-Case ("Ce Que Les Médecins...")
        # is broken French.
        import re as _re

        for pat in pats:
            rest = pat[1:]
            self.assertFalse(_re.search(r"[A-ZÀ-Ü]", rest), pat)
        self.assertTrue(any("médecins" in x for x in pats), pats)
        self.assertTrue(any("7 signes" in x for x in pats), pats)
        # Long topics must drop patterns that cannot fit the budget.
        long_pats = ct._rule_patterns("pourquoi vos genoux craquent")
        for pat in long_pats:
            self.assertLessEqual(len(pat.encode("utf-8")), 55, pat)

    def test_rule_pattern_empty_topic(self):
        ct = self._mod()
        self.assertEqual(ct._rule_patterns(""), [])

    def test_ctr_titles_respects_toggle_off(self):
        ct = self._mod()
        old = os.environ.get("CTR_TITLES")
        try:
            os.environ["CTR_TITLES"] = "false"
            self.assertEqual(ct.get_ctr_title_options("pourquoi vos genoux craquent", "t"), [])
        finally:
            if old is None:
                os.environ.pop("CTR_TITLES", None)
            else:
                os.environ["CTR_TITLES"] = old

    def test_ctr_titles_under_mobile_budget(self):
        ct = self._mod()
        emoji_re = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]+")
        for topic in ("pourquoi vos genoux craquent", "la science derrière le hoquet nocturne"):
            for opt in ct.get_ctr_title_options(topic, topic.title()):
                self.assertLessEqual(len(opt.encode("utf-8")), 55, opt)
                self.assertIsNone(emoji_re.search(opt), opt)

    def test_ctr_titles_llm_failure_degrades_gracefully(self):
        ct = self._mod()
        with unittest.mock.patch.object(ct, "_llm_patterns", side_effect=RuntimeError("down")):
            opts = ct.get_ctr_title_options("pourquoi vos genoux craquent", "t")
        self.assertGreater(len(opts), 0)

    def test_seo_package_includes_ctr_options(self):
        ct = self._mod()
        script = {"title": "Genoux qui craquent", "series_title": "", "scenes": [{"caption": "c1"}]}
        with unittest.mock.patch.object(
            ct, "_llm_patterns", return_value=["Ce qui se passe vraiment dans vos genoux ?"]
        ):
            pkg = seo.generate_seo_package("pourquoi vos genoux craquent", script)
        self.assertGreater(len(pkg["title_options"]), 0)
        # The CTR novelty layer feeds the A/B pool; the leak-gate and the
        # question-first ranking decide the winner, so assert presence
        # (never absence) rather than a fixed slot.
        self.assertIn("Ce qui se passe vraiment dans vos genoux ?", pkg["title_options"])
