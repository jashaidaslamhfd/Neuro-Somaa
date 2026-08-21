#!/usr/bin/env python3
"""
Verifies the new Chatterbox-first engine flow WITHOUT downloading any TTS
model (no network, no GPU, no memory pressure). Internal helpers
(_synthesize_chatterbox, _synthesize_edge_french) are mocked so the tests
only exercise the selection/fallback LOGIC.

Coverage:
1. Default engine is Chatterbox (env unset) — never edge-tts anymore.
2. TTS_ENGINE=chatterbox: success path returns a chatterbox_* engine label.
3. TTS_ENGINE=chatterbox + all 3 attempts fail -> falls back to edge-tts
   (runner-safe safety net), NEVER misses a slot.
4. TTS_ENGINE=edge: edge primary path, chirality unchanged (maturing kept).
5. TTS_ENGINE=kokoro: legacy path returns kokoro_fr.
6. Chatterbox path skips maturing (real narrator voice preserved).
"""

import os
import sys
import unittest
from unittest import mock

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)


class EngineSelectionTests(unittest.TestCase):
    """The engine chain decisions in voice_generator._synthesize."""

    def _run_synthesize(self, engine_env, chatterbox_ok=True, edge_ok=True):
        import voice_generator as vg

        with (
            mock.patch.dict(os.environ, {"TTS_ENGINE": engine_env}, clear=False),
            mock.patch.object(vg, "_synthesize_chatterbox") as cb,
            mock.patch.object(vg, "_synthesize_edge_french") as edge,
            mock.patch.object(vg, "_validate_generated_audio"),
        ):
            audio = [0.1] * 44000  # 1s of float32
            if chatterbox_ok:
                cb.return_value = (audio, 24000)
            else:
                cb.side_effect = RuntimeError("chatterbox boom")
            if edge_ok:
                edge.return_value = (audio, 24000)
            else:
                edge.side_effect = RuntimeError("edge boom")
            return vg._synthesize("Une phrase de test.", topic="test", seg_index=0, seg_total=1)

    # --- Rule 1: default engine changed from edge to chatterbox ---
    def test_default_engine_is_chatterbox(self):
        import voice_generator as vg

        audio = [0.1] * 44000
        with (
            mock.patch.object(vg, "_synthesize_chatterbox", return_value=(audio, 24000)),
            mock.patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("TTS_ENGINE", None)
            _, _, engine = vg._synthesize("test", topic="t")
        self.assertIn("chatterbox", engine)

    # --- Rule 2: chatterbox success ---
    def test_chatterbox_success_returns_chatterbox_label(self):
        _, _, engine = self._run_synthesize("chatterbox", chatterbox_ok=True)
        self.assertIn("chatterbox", engine)

    # --- Rule 3: chatterbox fail -> edge safety net, slot not missed ---
    def test_chatterbox_fallback_to_edge_on_total_failure(self):
        _, _, engine = self._run_synthesize("chatterbox", chatterbox_ok=False, edge_ok=True)
        self.assertEqual(engine, "edge_fr")

    def test_all_engines_fail_raises_hard_error(self):
        import voice_generator as vg

        # Chatterbox and the Henri pool both fail; the cloud fallback
        # (edge_tts.Communicate, called directly in _synthesize) must also
        # fail — only then must a hard RuntimeError be raised so no silent
        # segment is ever inserted into a published video.
        with (
            mock.patch.dict(os.environ, {"TTS_ENGINE": "chatterbox"}),
            mock.patch.object(vg, "_synthesize_chatterbox") as cb,
            mock.patch.object(vg, "_synthesize_edge_french") as edge,
            mock.patch.object(vg, "_validate_generated_audio"),
            mock.patch.dict("sys.modules", {"edge_tts": mock.MagicMock()}),
        ):
            cb.side_effect = RuntimeError("chatterbox boom")
            edge.side_effect = RuntimeError("edge boom")
            import types

            # Build a fake edge_tts module whose Communicate stream raises,
            # then install it so the import inside _synthesize uses the mock.
            fake_mod = types.ModuleType("edge_tts")
            fake_comm = mock.MagicMock()
            fake_comm.stream = mock.MagicMock(side_effect=RuntimeError("cloud fallback boom"))
            fake_mod.Communicate = mock.MagicMock(return_value=fake_comm)
            sys.modules["edge_tts"] = fake_mod
            try:
                with self.assertRaises(RuntimeError):
                    vg._synthesize("Une phrase de test.", topic="test", seg_index=0, seg_total=1)
            finally:
                sys.modules.pop("edge_tts", None)

    # --- Rule 4: edge legacy mode untouched ---
    def test_edge_legacy_mode(self):
        _, _, engine = self._run_synthesize("edge", chatterbox_ok=True, edge_ok=True)
        self.assertEqual(engine, "edge_fr")

    def test_edge_legacy_chatterbox_not_used(self):
        """In edge legacy mode Chatterbox must NOT be called."""
        import voice_generator as vg

        audio = [0.1] * 44000
        with (
            mock.patch.dict(os.environ, {"TTS_ENGINE": "edge"}),
            mock.patch.object(vg, "_synthesize_chatterbox") as cb,
            mock.patch.object(vg, "_synthesize_edge_french", return_value=(audio, 24000)),
            mock.patch.object(vg, "_validate_generated_audio"),
        ):
            vg._synthesize("test", topic="t")
        cb.assert_not_called()

    # --- Rule 5: kokoro legacy mode ---
    def test_kokoro_legacy_mode(self):
        import voice_generator as vg

        audio = [0.1] * 44000
        with (
            mock.patch.dict(os.environ, {"TTS_ENGINE": "kokoro"}),
            mock.patch.object(vg, "_synthesize_kokoro", return_value=(audio, 24000)),
        ):
            _, _, engine = vg._synthesize("test", topic="t")
        self.assertEqual(engine, "kokoro_fr")

    # --- Rule 6: maturing skipped on chatterbox path ---
    def test_maturing_skipped_for_chatterbox(self):
        import voice_generator as vg

        audio = [0.1] * 44000
        with (
            mock.patch.dict(os.environ, {"TTS_ENGINE": "chatterbox"}),
            mock.patch.object(vg, "_synthesize_chatterbox", return_value=(audio, 24000)),
            mock.patch.object(vg, "_mature_voice") as mat,
            mock.patch.object(vg, "_validate_generated_audio"),
        ):
            vg._synthesize("test", topic="t")
        mat.assert_not_called()

    def test_maturing_kept_on_edge_path(self):
        """edge-tts synthetic timbre must still be deepened."""
        import voice_generator as vg

        audio = [0.1] * 44000
        with (
            mock.patch.dict(os.environ, {"TTS_ENGINE": "edge"}),
            mock.patch.object(vg, "_synthesize_edge_french", return_value=(audio, 24000)),
            mock.patch.object(vg, "_mature_voice") as mat,
            mock.patch.object(vg, "_validate_generated_audio"),
        ):
            mat.return_value = audio
            vg._synthesize("test", topic="t")
        mat.assert_called()

    # --- Tuning defaults ---
    def test_doc_tone_tuning_defaults(self):
        import voice_generator as vg

        self.assertAlmostEqual(vg.CHATTERBOX_EXAGGERATION, 0.30, places=2)
        self.assertAlmostEqual(vg.CHATTERBOX_CFG_WEIGHT, 0.45, places=2)
        self.assertAlmostEqual(vg.CHATTERBOX_TEMPERATURE, 0.55, places=2)


if __name__ == "__main__":
    unittest.main()
