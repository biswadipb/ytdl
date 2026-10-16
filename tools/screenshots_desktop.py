"""Takes real screenshots of the desktop window, filled with demo data. Run by CI under a virtual display:

    xvfb-run -a -s "-screen 0 1500x1200x24" python tools/screenshots_desktop.py docs/screenshots
"""
import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# A private home folder, so the screenshots never contain anyone's real settings or downloads.
HOME = tempfile.mkdtemp(prefix="ytdl-shots-")
os.environ["HOME"] = HOME
os.environ["YTDL_NO_TRAY"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "desktop"))

from tkinter import ttk  # noqa: E402

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageGrab  # noqa: E402

out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
out_dir.mkdir(parents=True, exist_ok=True)

# Demo data for the Subscriptions tab, written before the window opens.
ytdl_home = Path(HOME) / ".ytdl"
ytdl_home.mkdir(parents=True)
now = time.time()
(ytdl_home / "subscriptions.json").write_text(json.dumps({
    "interval_hours": 6,
    "subs": [
        {"id": "a1", "url": "https://www.youtube.com/@example", "name": "Nature Channel", "options": {}, "seen": [],
         "enabled": True, "added": now, "last_checked": now - 3600 * 2, "last_error": "", "fails": {}},
        {"id": "a2", "url": "https://www.youtube.com/@example2", "name": "Cooking Basics", "options": {}, "seen": [],
         "enabled": True, "added": now, "last_checked": now - 3600 * 5, "last_error": "", "fails": {}},
        {"id": "a3", "url": "https://www.youtube.com/@example3", "name": "Daily Podcast", "options": {}, "seen": [],
         "enabled": False, "added": now, "last_checked": now - 86400, "last_error": "", "fails": {}},
    ],
    "recent": [
        {"sub": "Nature Channel", "title": "Autumn forest in 4K", "file": "/x/a.mp4", "when": "Today, 08:15"},
        {"sub": "Cooking Basics", "title": "Perfect scrambled eggs", "file": "/x/b.mp4", "when": "Today, 06:40"},
        {"sub": "Nature Channel", "title": "River at dawn", "file": "/x/c.mp4", "when": "Yesterday, 19:02"},
    ],
    "files": [],
    "storage": {"keep_days": 30, "max_gb": 20, "min_free_gb": 1},
}))

import gui  # noqa: E402


def demo_thumbnail():
    """A plain illustrative picture for the preview (not a real video's artwork)."""
    img = Image.new("RGB", (320, 180))
    d = ImageDraw.Draw(img)
    for y in range(180):
        t = y / 180
        d.line([(0, y), (320, y)], fill=(int(79 + 60 * t), int(70 - 20 * t), int(229 - 40 * t)))
    d.polygon([(135, 60), (135, 120), (190, 90)], fill="white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def font(size, bold=False):
    for name in ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def framed(img, dark):
    """The real window content, with a title bar and soft shadow so it reads as a window on a page."""
    bar_h, pad = 34, 36
    w, h = img.width, img.height + bar_h
    bar_bg, fg = ((43, 43, 54), (230, 230, 240)) if dark else ((236, 236, 244), (50, 50, 66))
    win = Image.new("RGB", (w, h), bar_bg)
    d = ImageDraw.Draw(win)
    for i, c in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
        d.ellipse((14 + i * 22, 11, 26 + i * 22, 23), fill=c)
    d.text((w // 2, bar_h // 2), "ytdl", fill=fg, font=font(14, True), anchor="mm")
    win.paste(img, (0, bar_h))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=10, fill=255)
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 8, pad + w, pad + h + 8), radius=10, fill=(0, 0, 0, 90))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(14)))
    canvas.paste(win, (pad, pad), mask)
    return canvas


def shoot(app, name, dark):
    app.update_idletasks()
    app.update()
    time.sleep(0.6)
    app.update()
    x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    shot = ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ.get("DISPLAY"))
    framed(shot, dark).save(out_dir / f"desktop-{name}.png")
    print("saved", name, shot.size)


app = gui.App()
app.geometry("940x900+40+40")
app.fmt_box.set("mp4 (video)")
app.urls.insert("end", "https://www.youtube.com/watch?v=jNQXAC9IVRw")
app.show_preview({"title": "Me at the zoo", "channel": "jawed", "duration": 19, "heights": [144, 240, 360, 720],
                  "thumbnail": None}, demo_thumbnail())
rows = [("Autumn forest in 4K", "Downloading", "62%"), ("Perfect scrambled eggs", "Downloading", "18%"),
        ("Lofi study mix (audio)", "Queued", ""), ("Interview with a baker", "Done", "100%"),
        ("Short film trailer", "Failed", "")]
for i, (title, status, pct) in enumerate(rows, 1):
    app.tree.insert("", "end", iid=str(100 + i), text=title, values=(status, pct))
for title, when in [("Interview with a baker.mp4", "Today, 09:12"), ("River at dawn.mp4", "Yesterday, 19:02"),
                    ("Podcast episode 41 (audio).mp3", "Yesterday, 07:30")]:
    app.history.insert("", "end", text=title, values=(when,))
app.refresh_subscriptions()
notebook = gui.find_widgets(app, ttk.Notebook)[0]

for dark in (False, True):
    app.theme_choice.set("Dark" if dark else "Light")
    app.on_theme_change()
    suffix = "dark" if dark else "light"
    notebook.select(0)
    shoot(app, f"main-{suffix}", dark)
    if not dark:
        notebook.select(2)
        shoot(app, "subscriptions-light", dark)
        notebook.select(0)
app.destroy()
