"""ytdl minimal: paste a link, choose video or audio, download. Nothing else.

Uses the same download engine as the full app (desktop/ytdl.py).
"""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "desktop"))   # the shared engine (also bundled by PyInstaller)

import ytdl  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    Image = ImageDraw = ImageTk = None

SETTINGS = Path.home() / ".ytdl_minimal.json"

PALETTES = {
    "light": dict(bg="#FFFFFF", fg="#17172B", muted="#6B6B85", field="#FFFFFF", ring="#E8E7FD", accent="#4F46E5",
                  btn="#4F46E5", btn_hover="#4338CA", btn_fg="#FFFFFF", seg="#F0F0F7", seg_on="#FFFFFF",
                  seg_on_fg="#17172B", seg_fg="#6B6B85", drop="#F0F0F7", line="#EEEEF6", track="#E3E3EE",
                  tick_fg="#FFFFFF", bad="#D93F3F", placeholder="#6B6B85"),
    "dark": dict(bg="#14141D", fg="#ECECF6", muted="#8D8DA8", field="#1F1F2D", ring="#2D2A66", accent="#7B73F5",
                 btn="#7B73F5", btn_hover="#6A62E8", btn_fg="#14141D", seg="#1F1F2D", seg_on="#2D2A66",
                 seg_on_fg="#C9C5FF", seg_fg="#A3A3BB", drop="#1F1F2D", line="#26263A", track="#26263A",
                 tick_fg="#14141D", bad="#FF7B7B", placeholder="#8D8DA8"),
}
VIDEO_CHOICES = [("Best", "best"), ("1080p", "1080"), ("720p", "720"), ("480p", "480")]
AUDIO_CHOICES = [("MP3", "mp3"), ("M4A", "m4a")]
NOT_SINGLE = re.compile(
    r"(youtube\.com/(?:@[^/?#]+|channel/|c/|user/)[^?#]*$|youtube\.com/playlist|/sets/|instagram\.com/[^/?#]+/?$)", re.I)


def system_mode():
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True, timeout=2)
            return "dark" if r.returncode == 0 and "dark" in r.stdout.lower() else "light"
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except Exception:
        pass
    return "light"


def asset(name):
    base = getattr(sys, "_MEIPASS", None)
    return str(Path(base) / "assets" / name) if base else str(HERE.parent.parent / "assets" / name)


THEMES = ["auto", "light", "dark"]


def load_settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        SETTINGS.write_text(json.dumps(data))
    except OSError:
        pass


def shown_path(folder):
    """A folder as a person would write it: ~/Downloads/ytdl instead of /Users/name/Downloads/ytdl."""
    home = str(Path.home())
    text = str(folder)
    return "~" + text[len(home):] if text == home or text.startswith(home + os.sep) else text


def short_middle(text, n=34):
    """Keeps the end of a long path, since that's the part that tells folders apart."""
    return text if len(text) <= n else "…" + text[-(n - 1):]


def short(text, n=44):
    return text if len(text) <= n else text[:n - 1] + "…"


# ---- drawing --------------------------------------------------------------------------------------------
def pill(canvas, x1, y1, x2, y2, r, fill, outline="", width=1, tag="bg"):
    """A rounded rectangle. Vector on Mac (crisp on Retina); anti-aliased image elsewhere."""
    if x2 - x1 < 2 or y2 - y1 < 2:      # the widget hasn't been given its real size yet
        return None
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    if sys.platform == "darwin" or Image is None:
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2,
               x1, y2 - r, x1, y1 + r, x1, y1]
        return canvas.create_polygon(pts, smooth=True, fill=fill, outline=outline, width=width, tags=tag)
    w, h = int(x2 - x1), int(y2 - y1)
    key = (w, h, r, fill, outline, width)
    cache = canvas._root().__dict__.setdefault("_pill_cache", {})   # images belong to one window, so cache per window
    if key not in cache:
        s = 4
        img = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if outline:
            d.rounded_rectangle((0, 0, w * s - 1, h * s - 1), radius=r * s, fill=outline)
            i = width * s
            d.rounded_rectangle((i, i, w * s - 1 - i, h * s - 1 - i), radius=max(0, r - width) * s, fill=fill)
        else:
            d.rounded_rectangle((0, 0, w * s - 1, h * s - 1), radius=r * s, fill=fill)
        cache[key] = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS), master=canvas)
    return canvas.create_image(x1, y1, image=cache[key], anchor="nw", tags=tag)


class Surface(tk.Canvas):
    """A canvas that redraws itself when resized or re-themed."""

    def __init__(self, parent, app, height, **kw):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, **kw)
        self.app = app
        self.bind("<Configure>", lambda e: self.redraw())

    def redraw(self):
        self.configure(bg=self.app.p["bg"])
        self.delete("all")
        self.paint(self.winfo_width(), self.winfo_height())

    def paint(self, w, h):
        raise NotImplementedError


class Button(Surface):
    def __init__(self, parent, app, text, command, height=48):
        super().__init__(parent, app, height, cursor="hand2")
        self.text, self.command, self.hover, self.enabled = text, command, False, True
        self.bind("<Button-1>", lambda e: self.enabled and self.command())
        self.bind("<Enter>", lambda e: self.set_hover(True))
        self.bind("<Leave>", lambda e: self.set_hover(False))

    def set_hover(self, on):
        self.hover = on
        self.redraw()

    def paint(self, w, h):
        p = self.app.p
        pill(self, 0, 0, w, h, 14, p["btn_hover"] if self.hover else p["btn"])
        self.create_text(w / 2, h / 2, text=self.text, fill=p["btn_fg"], font=self.app.font_bold)


class Field(Surface):
    """The paste box: a rounded outline with the link inside and a Paste button on the right.

    Once a link is in the box that button becomes Clear. The hint ("Paste a video link") is drawn on the
    canvas, never typed into the entry, so it can't be left behind as text you have to erase.
    """

    def __init__(self, parent, app, on_paste, height=48):
        super().__init__(parent, app, height)
        self.on_paste = on_paste
        self.var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, relief="flat", bd=0, highlightthickness=0, font=app.font)
        self.entry.bind("<FocusIn>", lambda e: self.focus_changed(True))
        self.entry.bind("<FocusOut>", lambda e: self.focus_changed(False))
        self.entry.bind("<Return>", lambda e: app.start_download())
        self.hint = tk.Label(self, text="Paste a video link", anchor="w", bd=0, font=app.font, cursor="xterm")
        self.hint.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.var.trace_add("write", lambda *a: self.sync())
        self.focused = False

    def focus_changed(self, focused):
        self.focused = focused
        self.redraw()

    def get(self):
        return self.var.get().strip()

    def set(self, text):
        self.var.set(text or "")
        self.entry.icursor("end")

    @property
    def placeholder_on(self):
        return not self.var.get()

    def act(self):
        """Clear when there is a link in the box, otherwise paste one."""
        if self.var.get():
            self.set("")
            self.entry.focus_set()
        else:
            self.on_paste()

    def sync(self):
        """Keeps the hint and the Paste / Clear word in step with what is typed, without redrawing the box."""
        try:
            has = bool(self.var.get())
            self.itemconfigure("hint", state="hidden" if has else "normal")
            self.itemconfigure("paste", text="Clear" if has else "Paste")
        except tk.TclError:
            pass
        else:
            if bool(self.var.get()) != getattr(self, "_had", None):
                self._had = bool(self.var.get())
                self.redraw()          # the outline turns purple once there is a link

    def paint(self, w, h):
        p = self.app.p
        ring = p["accent"] if (self.focused or self.get()) else p["field"]
        if self.focused:
            pill(self, 0, 0, w, h, 16, p["ring"])
        pill(self, 2, 2, w - 2, h - 2, 14, p["field"], outline=ring, width=2 if self.focused else 1)
        self.entry.configure(bg=p["field"], fg=p["fg"], insertbackground=p["fg"])
        self.delete("entry", "hint", "paste")
        self.create_window(16, h / 2, window=self.entry, anchor="w", width=max(40, w - 100), tags="entry")
        self.hint.configure(bg=p["field"], fg=p["placeholder"])
        self.create_window(16, h / 2, window=self.hint, anchor="w", tags="hint")     # above the entry, so it shows through
        self.create_text(w - 18, h / 2, text="Paste", fill=p["accent"], font=self.app.font_bold, anchor="e", tags="paste")
        self.tag_bind("paste", "<Button-1>", lambda e: self.act())
        self.tag_bind("paste", "<Enter>", lambda e: self.configure(cursor="hand2"))
        self.tag_bind("paste", "<Leave>", lambda e: self.configure(cursor=""))
        self._had = bool(self.var.get())
        self.sync()


class Segmented(Surface):
    """A switch with two or more labels, one of them selected (Video | Audio, Auto | Light | Dark)."""

    def __init__(self, parent, app, labels, on_change, height=40, width=None, small=False):
        extra = {"width": width} if width else {}
        super().__init__(parent, app, height, cursor="hand2", **extra)
        self.labels, self.on_change, self.index, self.small = labels, on_change, 0, small
        self.bind("<Button-1>", self.click)

    def click(self, e):
        i = min(len(self.labels) - 1, max(0, int(e.x / (self.winfo_width() / len(self.labels)))))
        if i != self.index:
            self.index = i
            self.redraw()
            self.on_change(i)

    def paint(self, w, h):
        p = self.app.p
        radius, inner = (9, 7) if self.small else (12, 9)
        pill(self, 0, 0, w, h, radius, p["seg"])
        part = (w - 6) / len(self.labels)
        pill(self, 3 + self.index * part, 3, 3 + (self.index + 1) * part, h - 3, inner, p["seg_on"])
        regular = self.app.font_small if self.small else self.app.font
        bold = self.app.font_small_bold if self.small else self.app.font_bold
        for i, label in enumerate(self.labels):
            on = i == self.index
            self.create_text(3 + part * (i + 0.5), h / 2, text=label, fill=p["seg_on_fg"] if on else p["seg_fg"],
                             font=bold if on else regular)


class Dropdown(Surface):
    def __init__(self, parent, app, on_change, height=40):
        super().__init__(parent, app, height, cursor="hand2")
        self.choices, self.index, self.on_change = [], 0, on_change
        self.bind("<Button-1>", self.open)

    def set_choices(self, choices, index=0):
        self.choices, self.index = choices, min(index, len(choices) - 1)
        self.redraw()

    def open(self, e):
        menu = tk.Menu(self, tearoff=0)
        for i, (label, _) in enumerate(self.choices):
            menu.add_command(label=label, command=lambda i=i: self.pick(i))
        menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())

    def pick(self, i):
        self.index = i
        self.redraw()
        self.on_change(i)

    def paint(self, w, h):
        p = self.app.p
        pill(self, 0, 0, w, h, 12, p["drop"])
        if self.choices:
            self.create_text(14, h / 2, text=self.choices[self.index][0], fill=p["fg"], font=self.app.font, anchor="w")
        self.create_text(w - 14, h / 2, text="▾", fill=p["muted"], font=self.app.font, anchor="e")


class Dot(Surface):
    """The round status marker in front of each download: a ring while working, a tick when done."""

    def __init__(self, parent, app):
        super().__init__(parent, app, 20, width=20)
        self.state = "running"

    def paint(self, w, h):
        p = self.app.p
        if self.state == "running":
            self.create_oval(3, 3, 17, 17, outline=p["accent"], width=2)
            self.create_arc(3, 3, 17, 17, start=60, extent=100, style="arc", outline=p["bg"], width=3)
        elif self.state == "done":
            self.create_oval(2, 2, 18, 18, fill=p["accent"], outline=p["accent"])
            self.create_text(10, 10, text="✓", fill=p["tick_fg"], font=(self.app.font.actual("family"), 9, "bold"))
        else:
            self.create_oval(2, 2, 18, 18, fill=p["bad"], outline=p["bad"])
            self.create_text(10, 10, text="!", fill=p["tick_fg"], font=(self.app.font.actual("family"), 9, "bold"))


class Bar(Surface):
    """The progress line. `target` is where the download really is; `fraction` is what is drawn, eased towards it."""

    def __init__(self, parent, app):
        super().__init__(parent, app, 4)
        self.fraction = 0.0
        self.target = 0.0

    def glide(self):
        """One animation frame. Returns True while still moving."""
        gap = self.target - self.fraction
        if abs(gap) < 0.0005:
            moved = self.fraction != self.target
            self.fraction = self.target
            if moved:
                self.draw_fill()
            return False
        self.fraction += max(gap * 0.12, 0.0004) if gap > 0 else gap       # eases out, and never creeps backwards
        self.draw_fill()
        return True

    def paint(self, w, h):
        pill(self, 0, 0, w, h, 2, self.app.p["track"])
        self.draw_fill()

    def draw_fill(self):
        self.delete("fill")
        w, h = self.winfo_width(), self.winfo_height()
        if self.fraction <= 0 or w < 4:
            return
        x = max(h, w * self.fraction)
        c = self.app.p["accent"]
        r = h / 2
        self.create_oval(0, 0, h, h, fill=c, outline=c, tags="fill")
        self.create_oval(x - h, 0, x, h, fill=c, outline=c, tags="fill")
        self.create_rectangle(r, 0, x - r, h, fill=c, outline=c, tags="fill")


class Row(tk.Frame):
    """One download in this session."""

    def __init__(self, parent, app, job):
        super().__init__(parent, bd=0, highlightthickness=0)
        self.app, self.job = app, job
        self.columnconfigure(1, weight=1)
        self.dot = Dot(self, app)
        self.dot.grid(row=0, column=0, padx=(0, 10), pady=(10, 0), sticky="n")
        self.title = tk.Label(self, anchor="w", bd=0, font=app.font)
        self.title.grid(row=0, column=1, sticky="ew", pady=(10, 0))
        self.right = tk.Label(self, anchor="e", bd=0, font=app.font_small)
        self.right.grid(row=0, column=2, padx=(10, 0), pady=(10, 0))
        self.cancel = tk.Label(self, text="Cancel", anchor="e", bd=0, font=app.font_small, cursor="hand2")
        self.cancel.bind("<Button-1>", lambda e: app.cancel(job))
        self.note = tk.Label(self, anchor="w", bd=0, font=app.font_small)
        self.bar = Bar(self, app)
        self.right.bind("<Button-1>", lambda e: app.row_action(job))
        self.sep = tk.Frame(self, height=1, bd=0, highlightthickness=0)
        self.sep.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.refresh()

    def percent_text(self):
        if self.job["status"] != "running":
            return "Waiting"
        return f"{int(self.bar.fraction * 100)}%" if self.bar.fraction >= 0.01 else "Starting"

    def show_percent(self):
        text = self.percent_text()
        if self.right.cget("text") != text:
            self.right.configure(text=text)

    def refresh(self):
        p, j = self.app.p, self.job
        self.configure(bg=p["bg"])
        for w in (self.title, self.right, self.cancel, self.note):
            w.configure(bg=p["bg"])
        self.title.configure(text=short(j["title"]), fg=p["fg"])
        status = j["status"]
        self.dot.state = {"done": "done", "failed": "failed", "cancelled": "failed"}.get(status, "running")
        self.dot.redraw()
        self.cancel.grid_forget()
        self.note.grid_forget()
        self.bar.grid_forget()
        if status in ("queued", "running"):
            pct = self.percent_text()
            self.right.configure(text=pct, fg=p["muted"], cursor="")
            self.cancel.configure(fg=p["accent"])
            self.cancel.grid(row=0, column=3, padx=(10, 0), pady=(10, 0))
            self.bar.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(5, 0))
            self.bar.target = j["progress"]
            self.bar.redraw()
        elif status == "done":
            self.right.configure(text="Open", fg=p["accent"], cursor="hand2")
        else:
            self.right.configure(text="Retry", fg=p["accent"], cursor="hand2")
            self.note.configure(text=short(j.get("error") or j["status"].capitalize(), 60), fg=p["muted"])
            self.note.grid(row=1, column=1, columnspan=3, sticky="w")
        self.sep.configure(bg=p["line"])


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        self.settings = load_settings()
        saved = self.settings.get("theme", "auto")
        self.theme = saved if saved in THEMES else "auto"
        self.mode = self.resolve_mode()
        self.p = PALETTES[self.mode]
        base = tkfont.nametofont("TkDefaultFont").actual("family")
        self.font = tkfont.Font(family=base, size=13)
        self.font_bold = tkfont.Font(family=base, size=13, weight="bold")
        self.font_small = tkfont.Font(family=base, size=11)
        self.font_small_bold = tkfont.Font(family=base, size=11, weight="bold")
        self.font_title = tkfont.Font(family=base, size=17, weight="bold")
        self.title("ytdl")
        self.geometry("420x680")
        self.minsize(360, 520)
        try:
            self.icon = tk.PhotoImage(file=asset("icon.png"))
            self.iconphoto(True, self.icon)
        except tk.TclError:
            pass

        self.events, self.jobs, self.rows, self.next_id = queue.Queue(), queue.Queue(), {}, 1
        self.is_video = self.settings.get("mode", "video") == "video"
        self.quality_index = {"video": self.settings.get("video_q", 0), "audio": self.settings.get("audio_q", 0)}
        self.folder = self.settings.get("folder", ytdl.default_folder())

        self.body = tk.Frame(self, bd=0, highlightthickness=0)
        self.body.pack(fill="both", expand=True, padx=22, pady=(18, 16))
        self.header = tk.Frame(self.body, bd=0, highlightthickness=0)
        self.header.pack(fill="x", pady=(0, 14))
        self.logo_img = self.small_logo()
        self.logo = tk.Label(self.header, image=self.logo_img, bd=0) if self.logo_img else None
        if self.logo:
            self.logo.pack(side="left", padx=(0, 9))
        self.name = tk.Label(self.header, text="ytdl", font=self.font_title, bd=0)
        self.name.pack(side="left")
        self.theme_seg = Segmented(self.header, self, ["Auto", "Light", "Dark"], self.choose_theme, height=30, width=168, small=True)
        self.theme_seg.index = THEMES.index(self.theme)
        self.theme_seg.pack(side="right")

        self.field = Field(self.body, self, self.paste)
        self.field.pack(fill="x", pady=(0, 12))
        self.go = Button(self.body, self, "Download", self.start_download)
        self.go.pack(fill="x", pady=(0, 12))

        self.opts = tk.Frame(self.body, bd=0, highlightthickness=0)
        self.opts.pack(fill="x")
        self.opts.columnconfigure(0, weight=22, uniform="o")
        self.opts.columnconfigure(1, weight=10, uniform="o")
        self.seg = Segmented(self.opts, self, ["Video", "Audio"], self.mode_changed)
        self.seg.index = 0 if self.is_video else 1
        self.seg.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.drop = Dropdown(self.opts, self, self.quality_changed)
        self.drop.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.load_choices()

        self.where = tk.Frame(self.body, bd=0, highlightthickness=0)
        self.where.pack(fill="x", pady=(10, 0))
        self.where_label = tk.Label(self.where, anchor="w", bd=0, font=self.font_small)
        self.where_label.pack(side="left")
        self.change_link = tk.Label(self.where, text="Change", bd=0, font=self.font_small, cursor="hand2")
        self.change_link.pack(side="right")
        self.change_link.bind("<Button-1>", lambda e: self.choose_folder())
        self.default_link = tk.Label(self.where, text="Default", bd=0, font=self.font_small, cursor="hand2")
        self.default_link.bind("<Button-1>", lambda e: self.use_default_folder())

        self.message = tk.Label(self.body, anchor="w", bd=0, font=self.font_small)
        self.message.pack(fill="x", pady=(6, 0))

        self.list_head = tk.Frame(self.body, bd=0, highlightthickness=0)
        self.list_head.pack(fill="x", pady=(10, 0))
        self.head_label = tk.Label(self.list_head, text="Downloads", font=self.font_small, bd=0)
        self.head_label.pack(side="left")
        self.folder_link = tk.Label(self.list_head, text="Open folder", font=self.font_small, bd=0, cursor="hand2")
        self.folder_link.pack(side="right")
        self.folder_link.bind("<Button-1>", lambda e: self.open_folder())

        self.scroll_canvas = tk.Canvas(self.body, bd=0, highlightthickness=0)
        self.list_frame = tk.Frame(self.scroll_canvas, bd=0, highlightthickness=0)
        self.scroll_canvas.pack(fill="both", expand=True)
        self.window_id = self.scroll_canvas.create_window(0, 0, window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", lambda e: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all")))
        self.scroll_canvas.bind("<Configure>", lambda e: self.scroll_canvas.itemconfigure(self.window_id, width=e.width))
        self.bind_all("<MouseWheel>", lambda e: self.scroll_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        self.apply_theme()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<FocusIn>", lambda e: self.grab_copied_link() if e.widget is self else None)
        threading.Thread(target=self.worker, daemon=True).start()
        threading.Thread(target=self.quiet_engine_update, daemon=True).start()
        self.after(100, self.poll)
        threading.Thread(target=ytdl.warm, daemon=True).start()     # load the download engine while the window is already up
        self.after(100, self.glide)
        self.after(500, self.grab_copied_link)
        self.after(5000, self.follow_system)

    # ---- look ---------------------------------------------------------------
    def small_logo(self):
        if Image is None:
            return None
        try:
            return ImageTk.PhotoImage(Image.open(asset("icon.png")).convert("RGBA").resize((26, 26), Image.LANCZOS))
        except Exception:
            return None

    def resolve_mode(self):
        return system_mode() if self.theme == "auto" else self.theme

    def choose_theme(self, index):
        self.theme = THEMES[index]
        self.settings["theme"] = self.theme
        save_settings(self.settings)
        self.mode = self.resolve_mode()
        self.p = PALETTES[self.mode]
        self.apply_theme()

    def apply_theme(self):
        p = self.p
        self.configure(bg=p["bg"])
        self.theme_seg.index = THEMES.index(self.theme)
        for w in (self.body, self.header, self.opts, self.list_head, self.list_frame, self.where):
            w.configure(bg=p["bg"])
        self.scroll_canvas.configure(bg=p["bg"])
        self.name.configure(bg=p["bg"], fg=p["fg"])
        if self.logo:
            self.logo.configure(bg=p["bg"])
        self.head_label.configure(bg=p["bg"], fg=p["muted"])
        self.folder_link.configure(bg=p["bg"], fg=p["accent"])
        self.message.configure(bg=p["bg"], fg=p["muted"])
        self.where_label.configure(bg=p["bg"], fg=p["muted"])
        self.change_link.configure(bg=p["bg"], fg=p["accent"])
        self.default_link.configure(bg=p["bg"], fg=p["accent"])
        self.show_folder()
        for s in (self.field, self.go, self.seg, self.drop, self.theme_seg):
            s.redraw()
        for row in self.rows.values():
            row.refresh()

    def follow_system(self):
        mode = self.resolve_mode()      # only differs from the current look when the theme is Auto
        if mode != self.mode:
            self.mode, self.p = mode, PALETTES[mode]
            self.apply_theme()
        self.after(5000, self.follow_system)

    def say(self, text):
        self.message.configure(text=text)

    # ---- where files go -----------------------------------------------------
    def is_default_folder(self):
        return os.path.normpath(os.path.expanduser(self.folder)) == os.path.normpath(os.path.expanduser(ytdl.default_folder()))

    def show_folder(self):
        self.where_label.configure(text="Saving to " + short_middle(shown_path(os.path.expanduser(self.folder))))
        self.default_link.pack_forget()
        if not self.is_default_folder():
            self.default_link.pack(side="right", padx=(0, 12))

    def choose_folder(self):
        chosen = filedialog.askdirectory(initialdir=os.path.expanduser(self.folder) if os.path.isdir(os.path.expanduser(self.folder))
                                         else str(Path.home()), title="Choose where to save", mustexist=False)
        if chosen:
            self.folder = chosen
            self.remember()
            self.show_folder()

    def use_default_folder(self):
        self.folder = ytdl.default_folder()
        self.remember()
        self.show_folder()

    # ---- choices ------------------------------------------------------------
    def kind(self):
        return "video" if self.is_video else "audio"

    def load_choices(self):
        self.drop.set_choices(VIDEO_CHOICES if self.is_video else AUDIO_CHOICES, self.quality_index[self.kind()])

    def mode_changed(self, index):
        self.is_video = index == 0
        self.load_choices()
        self.remember()

    def quality_changed(self, index):
        self.quality_index[self.kind()] = index
        self.remember()

    def remember(self):
        self.settings.update(mode=self.kind(), video_q=self.quality_index["video"], audio_q=self.quality_index["audio"],
                             folder=self.folder)
        save_settings(self.settings)

    # ---- link box -----------------------------------------------------------
    def clipboard_link(self):
        try:
            m = ytdl.SITE_PATTERN.search(self.clipboard_get())
            return m.group(0) if m else None
        except tk.TclError:
            return None

    def paste(self):
        link = self.clipboard_link()
        if link:
            self.field.set(link)
            self.say("")
        else:
            try:
                self.field.set(self.clipboard_get().strip())
            except tk.TclError:
                self.say("Nothing to paste. Copy a video link first.")

    def grab_copied_link(self):
        """A copied link fills the box when you come back to the window. It never downloads by itself."""
        link = self.clipboard_link()
        if link and not self.field.get() and not self.field.focused:
            self.field.set(link)

    # ---- downloads ----------------------------------------------------------
    def start_download(self):
        text = self.field.get()
        m = ytdl.SITE_PATTERN.search(text)
        url = m.group(0) if m else (text if text.startswith("http") else "")
        if not url:
            self.say("Paste a video link first.")
            return
        if NOT_SINGLE.search(url):
            self.say("That looks like a channel or playlist. The full ytdl app handles those.")
            return
        self.say("")
        quality = self.drop.choices[self.drop.index][1]
        kwargs = dict(output=self.folder, fmt="mp4" if self.is_video else quality,
                      quality=quality if self.is_video else "best", extras=True)
        self.add_job(url, kwargs)
        self.field.set("")

    def add_job(self, url, kwargs, title=None):
        job = dict(id=self.next_id, url=url, title=title or url, status="queued", progress=0.0, files=[], error="",
                   cancel=threading.Event(), kwargs=kwargs)
        self.next_id += 1
        row = Row(self.list_frame, self, job)
        row.pack(fill="x", before=self.first_row() if self.rows else None)
        self.rows[job["id"]] = row
        self.jobs.put(job)

    def first_row(self):
        slaves = self.list_frame.pack_slaves()   # in on-screen order, so the newest download goes above all others
        return slaves[0] if slaves else None

    def cancel(self, job):
        job["cancel"].set()
        if job["status"] == "queued":
            self.set_status(job, "cancelled")

    def row_action(self, job):
        if job["status"] == "done" and job["files"]:
            self.reveal(job["files"][0], select=True)
        elif job["status"] in ("failed", "cancelled"):
            job.update(status="queued", progress=0.0, error="", cancel=threading.Event())
            self.rows[job["id"]].refresh()
            self.jobs.put(job)

    def set_status(self, job, status, error=""):
        job["status"], job["error"] = status, error
        self.rows[job["id"]].refresh()

    def open_folder(self):
        os.makedirs(os.path.expanduser(self.folder), exist_ok=True)
        self.reveal(os.path.expanduser(self.folder))

    @staticmethod
    def reveal(path, select=False):
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if select else ["open", path])
        elif sys.platform == "win32":
            if select:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path) if select else path])

    def worker(self):
        while True:
            job = self.jobs.get()
            if job["cancel"].is_set():
                self.events.put(("status", job, "cancelled", ""))
                continue
            self.events.put(("status", job, "running", ""))
            self.run_job(job)

    def run_job(self, job):
        overall = ytdl.Progress()

        def hook(d):
            if job["cancel"].is_set():
                raise ytdl.Cancelled()
            title = (d.get("info_dict") or {}).get("title")
            if title:
                self.events.put(("title", job, title))
            self.events.put(("progress", job, overall.update(d)))

        for attempt in range(2):      # one automatic retry for hiccups such as a dropped connection
            try:
                files = ytdl.download_one(job["url"], hooks=[hook], quiet=True, **job["kwargs"])
                self.events.put(("done", job, files))
                return
            except ytdl.Cancelled:
                self.events.put(("status", job, "cancelled", ""))
                return
            except Exception as e:  # noqa: BLE001
                message = str(e).replace("ERROR: ", "").splitlines()[0] if str(e) else "Download failed"
                if job["cancel"].is_set():
                    self.events.put(("status", job, "cancelled", ""))
                    return
                if attempt == 0 and ytdl.is_transient(message):
                    continue
                self.events.put(("status", job, "failed", message))
                return

    def poll(self):
        try:
            while True:
                kind, job, *rest = self.events.get_nowait()
                try:
                    row = self.rows.get(job["id"])
                    if kind == "status":
                        self.set_status(job, rest[0], rest[1])
                    elif kind == "title":
                        job["title"] = rest[0]
                        row and row.refresh()
                    elif kind == "progress":
                        job["progress"] = rest[0]
                        row and row.refresh()
                    elif kind == "done":
                        job["files"], job["progress"] = rest[0], 1.0
                        self.set_status(job, "done")
                except tk.TclError:
                    pass          # one bad redraw must never stop the progress updates
        except queue.Empty:
            pass
        self.after(150, self.poll)

    def glide(self):
        """Eases every running progress line towards its real value, about 30 times a second."""
        try:
            for row in list(self.rows.values()):
                if row.job["status"] == "running" and row.bar.glide():
                    row.show_percent()
        except tk.TclError:
            pass
        self.after(33, self.glide)

    def quiet_engine_update(self):
        try:
            ytdl.update_engine()    # applies the next time ytdl starts
        except Exception:
            pass

    def active(self):
        return sum(1 for r in self.rows.values() if r.job["status"] in ("queued", "running"))

    def on_close(self):
        if self.active() and not messagebox.askyesno("ytdl", "Downloads are still running. Quit anyway?"):
            return
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
