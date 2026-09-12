"""Shared safe-zone geometry for vertical Shorts assets.

The renderer and quality scorer must agree on where copy is allowed to appear.
These values are conservative defaults for a 9:16 Shorts canvas: preserve the
right-side action rail and bottom caption/metadata area.
"""

from __future__ import annotations


def safe_box(width: int, height: int) -> tuple[int, int, int, int]:
    """Return the x/y-safe rectangle for platform overlays."""
    return (
        int(width * 0.05),
        int(height * 0.08),
        int(width * 0.86),
        int(height * 0.82),
    )


def thumbnail_text_band(width: int, height: int) -> tuple[int, int]:
    """Return the preferred headline band, away from platform chrome."""
    return int(height * 0.53), int(height * 0.76)


def thumbnail_action_safe(width: int, height: int) -> tuple[int, int, int, int]:
    """Return the conservative rectangle in which thumbnail copy may render."""
    left, top, right, bottom = safe_box(width, height)
    band_top, band_bottom = thumbnail_text_band(width, height)
    return left, max(top, band_top), right, min(bottom, band_bottom)
