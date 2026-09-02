from __future__ import annotations

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


def _hook(title: str) -> str:
    clean = re.sub(r"\s+", " ", title).strip().rstrip("?").lower()
    if "odeur" in clean or "souvenir" in clean:
        return "ODEUR\n= SOUVENIR ?"
    if "stress" in clean or "jambes" in clean:
        return "TON CORPS\nRÉAGIT AU STRESS"
    if "bâill" in clean:
        return "POURQUOI\nLE BÂILLEMENT ?"
    if "cœur" in clean or "decision" in clean or "décision" in clean:
        return "TON CŒUR\nACCÉLÈRE POURQUOI ?"
    return "LE DÉTAIL\nQUI CHANGE TOUT"


def _asset_for(title: str, assets_dir: Path) -> Path | None:
    clean = title.lower()
    names = ["ai_odeur_memoire.jpg"] if "odeur" in clean or "souvenir" in clean else []
    if "stress" in clean or "jambes" in clean:
        names = ["ai_stress_corps.jpg"]
    if "bâill" in clean:
        names = ["ai_baillement_cerveau.jpg"]
    for name in names:
        candidate = assets_dir / name
        if candidate.exists():
            return candidate
    all_assets = sorted(assets_dir.glob("ai_*.jpg"))
    return all_assets[0] if all_assets else None


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
    draw.text((112, card_bottom + 88), "EXPLIQUE EN 30 S", font=_font(30, True), fill="#07111f")
    output = settings.output_dir / "thumbnail.jpg"
    image.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
    return output
