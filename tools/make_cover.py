"""Render Earful's podcast covers (main feed + Earful Daily) and optionally upload them.

    uv run tools/make_cover.py            # render to out/covers/ for review
    uv run tools/make_cover.py --upload   # render, then upload cover.png + daily/cover.png

Typographic on purpose: podcast apps show covers at ~60-100px, so each cover is one stacked
wordmark on a colour field, and the two feeds differ first by that field (paper vs. ink) so
they're distinguishable before a single letter is legible. The font is Fraunces (OFL),
fetched once into out/fonts/.
"""
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import load_config  # noqa: E402
from storage import Storage  # noqa: E402

SIZE = 3000  # Apple's maximum; apps downscale from here
MARGIN = 260
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/fraunces/Fraunces%5BSOFT,WONK,opsz,wght%5D.ttf"
FONT_PATH = Path("out/fonts/Fraunces.ttf")

PAPER = (243, 236, 221)
INK = (27, 26, 23)
VERMILION = (226, 72, 43)


def font(size: int, weight: int) -> ImageFont.FreeTypeFont:
    if not FONT_PATH.exists():
        FONT_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(FONT_URL, FONT_PATH)
    f = ImageFont.truetype(str(FONT_PATH), size)
    # axes: optical size, weight, softness, wonky — display optical size, soft corners
    f.set_variation_by_axes([144, weight, 50, 1])
    return f


def stack(draw: ImageDraw.ImageDraw, lines: list[list[tuple[str, tuple]]]) -> None:
    """Set lines of (text, colour) runs flush left, as large as fits inside the margins, and
    centred vertically on the ink actually drawn (lowercase tops, not the font's ascent)."""
    def metrics(f: ImageFont.FreeTypeFont) -> tuple[float, int, int, int]:
        widest = max(sum(draw.textlength(t, font=f) for t, _ in line) for line in lines)
        gap = int(f.size * 0.86)  # baseline-to-baseline; tight, ascenders nearly touch the line above
        first_top = min(draw.textbbox((0, 0), t, font=f, anchor="ls")[1] for t, _ in lines[0])
        last_bottom = max(draw.textbbox((0, 0), t, font=f, anchor="ls")[3] for t, _ in lines[-1])
        return widest, gap, first_top, -first_top + gap * (len(lines) - 1) + last_bottom

    widest, _, _, height = metrics(font(1000, 900))
    f = font(int(1000 * min((SIZE - 2 * MARGIN) / widest, (SIZE - 2 * MARGIN) / height)), 900)
    _, gap, first_top, height = metrics(f)
    baseline = (SIZE - height) // 2 - first_top
    for line in lines:
        x = MARGIN
        for text, colour in line:
            draw.text((x, baseline), text, font=f, fill=colour, anchor="ls")
            x += draw.textlength(text, font=f)
        baseline += gap


def render(variant: str) -> Image.Image:
    bg, ink = (PAPER, INK) if variant == "main" else (INK, PAPER)
    img = Image.new("RGB", (SIZE, SIZE), bg)
    draw = ImageDraw.Draw(img)
    if variant == "main":
        stack(draw, [[("ear", ink)], [("ful", ink), (".", VERMILION)]])
    else:
        stack(draw, [[("ear", ink)], [("ful", ink)], [("daily", VERMILION)]])
    return img


if __name__ == "__main__":
    out = Path("out/covers")
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for variant in ("main", "daily"):
        paths[variant] = out / f"{variant}.png"
        render(variant).save(paths[variant], "PNG", optimize=True)
        print("rendered", paths[variant])
    if "--upload" in sys.argv:
        storage = Storage(load_config().r2)
        print("uploaded", storage.upload_file(str(paths["main"]), "cover.png", "image/png"))
        print("uploaded", storage.upload_file(str(paths["daily"]), "daily/cover.png", "image/png"))
