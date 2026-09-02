from __future__ import annotations

import pytest

import main


def test_non_critical_gate_warn_mode_does_not_raise(monkeypatch):
    monkeypatch.setattr(main, "NON_CRITICAL_GATES_MODE", "warn")
    main._handle_non_critical_gate("thumbnail score below threshold")


def test_non_critical_gate_strict_mode_still_raises(monkeypatch):
    monkeypatch.setattr(main, "NON_CRITICAL_GATES_MODE", "strict")
    with pytest.raises(RuntimeError, match="quality failure"):
        main._handle_non_critical_gate("quality failure")
