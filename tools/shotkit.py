"""Shared helpers for the screenshot scripts: grab a window and put it in a title bar with a soft shadow."""
import os
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageGrab


def font(size, bold=False):
    for name in ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def grab(window):
    window.update_idletasks()
    window.update()
    time.sleep(0.6)
    window.update()
    x, y, w, h = window.winfo_rootx(), window.winfo_rooty(), window.winfo_width(), window.winfo_height()
    return ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ.get("DISPLAY"))


def framed(img, dark, title="ytdl"):
    bar_h, pad = 34, 36
    w, h = img.width, img.height + bar_h
    bar_bg, fg = ((43, 43, 54), (230, 230, 240)) if dark else ((236, 236, 244), (50, 50, 66))
    win = Image.new("RGB", (w, h), bar_bg)
    d = ImageDraw.Draw(win)
    for i, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
        d.ellipse((14 + i * 22, 11, 26 + i * 22, 23), fill=c)
    d.text((w // 2, bar_h // 2), title, fill=fg, font=font(14, True), anchor="mm")
    win.paste(img, (0, bar_h))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=10, fill=255)
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 8, pad + w, pad + h + 8), radius=10, fill=(0, 0, 0, 90))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(14)))
    canvas.paste(win, (pad, pad), mask)
    return canvas
