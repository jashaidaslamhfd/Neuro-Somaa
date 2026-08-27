"""Model-chain tests — the truth-gate lesson applied to config: a fallback
that exists in YAML but is never read by code is NOT a fallback. These tests
prove the chain is real (2026-08-12)."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import script_generator


class GroqModelChainTests(unittest.TestCase):
    def _chain(self, env):
        clean = {k: v for k, v in os.environ.items() if not k.startswith("GROQ_MODEL")}
        clean.update(env)
        with mock.patch.dict(os.environ, clean, clear=True):
            return script_generator.groq_model_chain()

    def test_default_is_advanced_model_with_fast_fallback(self):
        chain = self._chain({})
        self.assertEqual(chain[0], "openai/gpt-oss-120b")
        self.assertEqual(chain[-1], "openai/gpt-oss-20b")

    def test_no_retired_llama_defaults(self):
        chain = self._chain({})
        for m in chain:
            self.assertNotIn("llama-3.1-8b-instant", m)
            self.assertNotIn("llama-3.3-70b-versatile", m)

    def test_env_override_wins(self):
        chain = self._chain({"GROQ_MODEL": "qwen/qwen3.6-27b"})
        self.assertEqual(chain[0], "qwen/qwen3.6-27b")

    def test_empty_string_env_is_treated_as_unset(self):
        # seo_repair.yml passes ${{ secrets.GROQ_MODEL }} which is '' when
        # the secret is missing — must NOT become the model name.
        chain = self._chain({"GROQ_MODEL": ""})
        self.assertEqual(chain[0], "openai/gpt-oss-120b")

    def test_duplicate_fallback_deduped(self):
        chain = self._chain(
            {"GROQ_MODEL": "openai/gpt-oss-120b", "GROQ_MODEL_FALLBACK": "openai/gpt-oss-120b"}
        )
        self.assertEqual(chain, ["openai/gpt-oss-120b"])

    def test_gemini_contents_normalize_openai_roles(self):
        contents = script_generator._gemini_contents(
            [
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": "Create a script."},
                {"role": "assistant", "content": "Previous draft."},
            ]
        )
        self.assertEqual([item["role"] for item in contents], ["user", "model"])
        self.assertIn("SYSTEM INSTRUCTIONS", contents[0]["parts"][0]["text"])

    def test_lenient_validator_call_is_supported(self):
        valid, issues = script_generator._validate_script({}, lenient=True)
        self.assertFalse(valid)
        self.assertTrue(any(issue.startswith("Missing required field:") for issue in issues))


if __name__ == "__main__":
    unittest.main()
