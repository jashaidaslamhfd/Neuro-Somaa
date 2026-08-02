#!/usr/bin/env python3
"""SKILLOR — Pillow compatibility shim.

MoviePy 1.0.3 was built against older Pillow and uses Image.ANTIALIAS, which
was REMOVED in Pillow 10+. Importing this module first restores the alias so
moviepy works with modern Pillow. (Same fix as the 2026-08-02 audit of the
sister repos.)
"""

from PIL import Image

if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS
