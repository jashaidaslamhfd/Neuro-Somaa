from __future__ import annotations

import ast
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _has_main_guard(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.Eq)
        and len(node.test.comparators) == 1
        and isinstance(node.test.comparators[0], ast.Constant)
        and node.test.comparators[0].value == "__main__"
        for node in tree.body
    )


def test_probe_autocomplete_is_import_safe():
    source = (ROOT / "scripts" / "probe_fr_autocomplete.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert _has_main_guard(tree)
    module = importlib.import_module("scripts.probe_fr_autocomplete")
    assert callable(module.main)
    assert callable(module.fetch_suggestions)


def test_thumbnail_calibration_is_import_safe():
    source = (ROOT / "scripts" / "calibrate_thumbnail_variants.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert _has_main_guard(tree)
    module = importlib.import_module("scripts.calibrate_thumbnail_variants")
    assert callable(module.main)
