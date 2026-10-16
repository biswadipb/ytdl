"""Regenerate every icon from the master design (same geometry as logo.svg).

    pip install pillow && python assets/make_icons.py
The .icns step needs macOS (iconutil); it is skipped elsewhere.
"""
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
BG, FG = (15, 23, 42), (163, 230, 53)
SS = 4  # supersampling factor for smooth edges


def render(size):
    n = size * SS
    k = n / 160
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, n - 1, n - 1), radius=36 * k, fill=BG)
    w = 14 * k

    def stroke(points):
        pts = [(x * k, y * k) for x, y in points]
        d.line(pts, fill=FG, width=round(w), joint="curve")
        for x, y in pts:  # round caps and joins
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=FG)

    stroke([(80, 34), (80, 88)])
    stroke([(54, 66), (80, 92), (106, 66)])
    stroke([(44, 108), (44, 126), (116, 126), (116, 108)])
    return img.resize((size, size), Image.LANCZOS)


def main():
    render(1024).save(HERE / "logo.png")
    render(256).save(HERE / "icon.png")
    render(256).save(HERE / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = HERE / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            render(s).save(iconset / f"icon_{s}x{s}.png")
            render(s * 2).save(iconset / f"icon_{s}x{s}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "icon.icns")], check=True)
        shutil.rmtree(iconset)


if __name__ == "__main__":
    main()
