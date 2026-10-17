"""Real screenshots of the minimal desktop window with demo downloads. Run by CI under a virtual display."""
import os
import sys
import tempfile
import threading
from pathlib import Path

os.environ["HOME"] = tempfile.mkdtemp(prefix="ytdl-min-shots-")
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "minimal" / "desktop"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as minimal  # noqa: E402
import shotkit  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
out.mkdir(parents=True, exist_ok=True)
minimal.ytdl.update_engine = lambda: (False, "")   # no network calls while taking pictures

w = minimal.App()
w.geometry("420x%d+40+10" % (560 if sys.platform == "win32" else 640))
w.field.set("https://youtu.be/jNQXAC9IVRw")
demo = [("Me at the zoo", "running", 0.62), ("Autumn forest in 4K", "done", 1.0), ("Podcast episode 41", "done", 1.0)]
for i, (title, status, progress) in enumerate(demo, 1):
    job = dict(id=i, url="", title=title, status=status, progress=progress, files=[], error="",
               cancel=threading.Event(), kwargs={})
    row = minimal.Row(w.list_frame, w, job)
    row.pack(fill="x")
    w.rows[i] = row

for mode in ("light", "dark"):
    w.mode, w.p = mode, minimal.PALETTES[mode]
    w.apply_theme()
    shot = shotkit.grab(w)
    shotkit.framed(shot, mode == "dark", "ytdl").save(out / f"minimal-desktop-{mode}.png")
    print("saved", mode, shot.size)
w.destroy()
