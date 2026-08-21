"""Hard publication gates for French Neuro-Somaa content.

This module deliberately has no network or media dependencies.  It converts a
structured gate report into a blocking exception, so callers cannot accidentally
log a failed gate and continue to upload.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def require_strict_gate(approved: bool, report: Mapping[str, Any] | None, stage: str) -> None:
    """Raise when a mandatory French/publication gate is not approved.

    ``approved`` must be the boolean returned by the relevant validator.  The
    report is included only for a concise diagnostic; no secrets are logged.
    """
    if approved:
        return
    payload = dict(report or {})
    issues = payload.get("issues") or payload.get("errors") or ["unspecified quality failure"]
    if not isinstance(issues, list):
        issues = [str(issues)]
    detail = "; ".join(str(item) for item in issues[:5])
    raise RuntimeError(f"Strict French quality gate blocked {stage}: {detail}")
