import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from seo_analytics import score_thumbnail
from video_editor import generate_thumbnail_variants

source = ROOT / "output" / "calibration_source.jpg"
source.parent.mkdir(parents=True, exist_ok=True)
image = Image.new("RGB", (720, 1280), (12, 24, 48))
draw = ImageDraw.Draw(image)
draw.ellipse((90, 180, 630, 760), fill=(238, 96, 74))
draw.rectangle((220, 760, 500, 1180), fill=(60, 185, 220))
image.save(source)

paths = generate_thumbnail_variants(
    str(source),
    "TEMPS RALENTI ?",
    output_dir=str(ROOT / "output" / "calibration_variants"),
    category="Brain",
    count=4,
)
for path in paths:
    score = score_thumbnail(path, "TEMPS RALENTI ?")
    print(Path(path).name, score["overall_thumbnail_score"], score)
