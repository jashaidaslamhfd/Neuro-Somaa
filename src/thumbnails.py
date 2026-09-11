from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 1080, 1920


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


# Keyword -> hand-tuned hook text for the handful of topics we have a bespoke
# line for. Anything not in this table falls through to _hook()'s dynamic
# title-derived text below instead of a generic placeholder, so every topic
# — not just these launch topics — gets thumbnail text that matches the video.
_BESPOKE_HOOKS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("odeur", "souvenir"), "ODEUR\n= SOUVENIR ?"),
    (("stress", "jambes"), "TON CORPS\nRÉAGIT AU STRESS"),
    (("bâill",), "POURQUOI\nLE BÂILLEMENT ?"),
    (("cœur", "decision", "décision"), "TON CŒUR\nACCÉLÈRE POURQUOI ?"),
)

# Same idea for the hand-made background assets: keep the bespoke matches as
# a quality upgrade for topics we've specifically designed art for, but never
# fall back to a fixed asset for everything else.
_BESPOKE_ASSETS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("odeur", "souvenir"), "ai_odeur_memoire.jpg"),
    (("stress", "jambes"), "ai_stress_corps.jpg"),
    (("bâill",), "ai_baillement_cerveau.jpg"),
)


def _hook(title: str) -> str:
    """Thumbnail hook text: bespoke line if we have one, otherwise derived
    straight from the generated title so it always matches the video.

    Previously anything outside 4 hardcoded topics fell back to the generic
    "LE DÉTAIL QUI CHANGE TOUT" — since the topic queue covers far more than
    those 4 subjects, most thumbnails were topic-mismatched. This derives the
    hook from the real title instead of a fixed keyword table.
    """
    clean = re.sub(r"\s+", " ", title).strip().rstrip("?").lower()
    for keywords, hook in _BESPOKE_HOOKS:
        if any(kw in clean for kw in keywords):
            return hook
    words = re.sub(r"\s+", " ", title).strip().rstrip("?").upper().split()
    if not words:
        return "LE DÉTAIL\nQUI CHANGE TOUT"
    short: list[str] = []
    length = 0
    for word in words:
        if length + len(word) > 28 and short:
            break
        short.append(word)
        length += len(word) + 1
    if len(short) <= 2:
        return "\n".join(short) if short else "LE DÉTAIL\nQUI CHANGE TOUT"
    mid = (len(short) + 1) // 2
    return " ".join(short[:mid]) + "\n" + " ".join(short[mid:])


def _asset_for(title: str, assets_dir: Path) -> Path | None:
    clean = title.lower()
    for keywords, name in _BESPOKE_ASSETS:
        if any(kw in clean for kw in keywords):
            candidate = assets_dir / name
            if candidate.exists():
                return candidate
    all_assets = sorted(assets_dir.glob("ai_*.jpg"))
    if not all_assets:
        return None
    # Deterministic per-title pick instead of always the same first asset
    # alphabetically, so at minimum the fallback isn't visually identical
    # across every non-bespoke video.
    index = int(hashlib.sha256(title.lower().encode()).hexdigest()[:8], 16) % len(all_assets)
    return all_assets[index]


def _duration_label(settings: Any) -> str:
    """Round the configured max duration for the thumbnail badge instead of a
    hardcoded '30 S' — the channel actually renders 15-22s videos
    (TARGET_MIN_SECONDS/TARGET_MAX_SECONDS), so the old label overpromised."""
    try:
        seconds = round(float(getattr(settings, "max_seconds", 20)))
    except (TypeError, ValueError):
        seconds = 20
    return f"EXPLIQUE EN {seconds} S"


def build_thumbnail(script: dict[str, Any], settings: Any) -> Path:
    title = str(script.get("title", "Science du quotidien"))
    assets_dir = Path(__file__).parents[1] / "assets" / "thumbnails_fr"
    background = _asset_for(title, assets_dir)
    if background:
        with Image.open(background) as source:
            image = ImageOps.fit(source.convert("RGB"), (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    else:
        image = Image.new("RGB", (WIDTH, HEIGHT), "#101827")
    overlay = Image.new("RGBA", image.size, (4, 10, 24, 70))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(image)
    # A dark left rail keeps the exact French hook legible on mobile.
    draw.rounded_rectangle((48, 52, 1032, 214), radius=42, fill="#07111fe8", outline="#6ee7d8", width=4)
    draw.text((88, 92), "NEURO-SOMAA", font=_font(48, True), fill="#ffffff")
    draw.text((88, 155), "SCIENCE DU QUOTIDIEN", font=_font(25, True), fill="#6ee7d8")
    hook = _hook(title)
    hook_font = _font(78, True)
    hook_box = draw.multiline_textbbox((0, 0), hook, font=hook_font, spacing=20)
    hook_height = hook_box[3] - hook_box[1]
    card_left, card_top = 58, 600
    card_right = min(990, 120 + hook_box[2] - hook_box[0])
    card_bottom = card_top + hook_height + 130
    draw.rounded_rectangle((card_left, card_top, card_right, card_bottom), radius=42, fill="#07111fe8", outline="#ffffff", width=3)
    draw.multiline_text((card_left + 48, card_top + 65), hook, font=hook_font, fill="#ffffff", spacing=20, stroke_width=2, stroke_fill="#07111f")
    draw.rounded_rectangle((78, card_bottom + 70, 560, card_bottom + 150), radius=30, fill="#6ee7d8")
    draw.text((112, card_bottom + 88), _duration_label(settings), font=_font(30, True), fill="#07111f")
    output = settings.output_dir / "thumbnail.jpg"
    image.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
    return output
