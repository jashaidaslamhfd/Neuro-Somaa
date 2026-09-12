"""Strict quality gate — ADVISORY MODE (non-blocking per audit fixes).
Previously blocked production with RuntimeError for ANY approved=False.
Now logs warning but does NOT block pipeline — aligns with truth audit (uncalibrated scores).
"""

def require_strict_gate(approved: bool, report: dict | None, stage: str) -> bool:
    """Log gate result. Returns approved status WITHOUT blocking pipeline."""
    import logging
    logger = logging.getLogger(__name__)
    if approved:
        logger.info(f"Strict gate PASSED: {stage}")
        return True
    payload = dict(report or {})
    issues = payload.get("issues") or payload.get("errors") or ["quality check advisory — not blocking"]
    if not isinstance(issues, list):
        issues = [str(issues)]
    detail = "; ".join(str(item) for item in issues[:5])
    logger.warning(f"Strict gate ADVISORY (not blocking): {stage} — {detail}")
    # DO NOT raise RuntimeError — pipeline continues (advisory mode)
    return False  # Returns False but pipeline continues
