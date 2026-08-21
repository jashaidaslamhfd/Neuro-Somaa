from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from strict_quality_gate import require_strict_gate


class StrictQualityGateTests(unittest.TestCase):
    def test_approved_report_does_not_raise(self):
        require_strict_gate(True, {"approved": True, "issues": []}, "unit test")

    def test_failed_report_raises_with_stage_and_issue(self):
        with self.assertRaisesRegex(RuntimeError, r"unit test.*bad French title"):
            require_strict_gate(
                False,
                {"approved": False, "issues": ["bad French title"]},
                "unit test",
            )

    def test_pipeline_uses_strict_helper_at_all_mandatory_stages(self):
        source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("require_strict_gate("), 3)
        final_audit = source.index("require_strict_gate(final_audit_ok")
        final_metadata = source.index("require_strict_gate(final_gate_ok")
        upload = source.index("upload_result = upload_all")
        self.assertLess(final_audit, upload)
        self.assertLess(final_metadata, upload)
        self.assertNotIn("French quality gate issues at upload (non-fatal)", source)
        self.assertNotIn("Final audit issues (non-fatal)", source)


if __name__ == "__main__":
    unittest.main()
