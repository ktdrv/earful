"""Generate a simple square cover and upload it to R2 as cover.png. Run once.

Usage: .venv/bin/python tools/make_cover.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import load_config  # noqa: E402
from storage import Storage  # noqa: E402

SIZE = 1500


def make_cover(title: str, out_path: str) -> None:
    img = Image.new("RGB", (SIZE, SIZE), (22, 28, 38))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 220)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), title, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((SIZE - w) / 2, (SIZE - h) / 2 - bbox[1]), title, fill=(245, 240, 230), font=font)
    img.save(out_path, "PNG")


if __name__ == "__main__":
    c = load_config()
    out = "out/cover.png"
    Path("out").mkdir(exist_ok=True)
    make_cover(c.podcast.title, out)
    url = Storage(c.r2).upload_file(out, "cover.png", "image/png")
    print("uploaded cover:", url)
