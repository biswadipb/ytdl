"""Simple desktop window for ytdl (tkinter, ships with Python)."""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ytdl


def asset_path(name):
    """Bundled copy when packaged by PyInstaller, repo copy when run from source."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "assets", name)
    return os.path.join(os.path.dirname(__file__), "..", "assets", name)


SETTINGS = os.path.join(os.path.expanduser("~"), ".ytdl_settings.json")
THEME_CHOICES = ["System", "Light", "Dark"]

PALETTES = {
    "light": dict(bg="#F7F7FB", fg="#1F1F2E", muted="#55556B", field="#FFFFFF", border="#C9C9D9",
                  trough="#E4E4EE", button="#ECECF4", button_hover="#E0E0EC",
                  accent="#4F46E5", accent_dark="#4338CA", accent_soft="#A5A1F0"),
    "dark": dict(bg="#16161F", fg="#EDEDF5", muted="#A0A0B8", field="#1F1F2B", border="#3A3A4D",
                 trough="#2A2A3A", button="#2A2A3A", button_hover="#34344A",
                 accent="#6D64F0", accent_dark="#5B52E0", accent_soft="#47427F"),
}


def load_theme_choice():
    try:
        with open(SETTINGS) as f:
            choice = json.load(f).get("theme", "System")
        return choice if choice in THEME_CHOICES else "System"
    except (OSError, ValueError):
        return "System"


def save_theme_choice(choice):
    try:
        with open(SETTINGS, "w") as f:
            json.dump({"theme": choice}, f)
    except OSError:
        pass  # remembering the theme is a convenience only


def system_mode():
    """'dark' or 'light', following the operating system setting."""
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True, timeout=2)
            return "dark" if r.returncode == 0 and "dark" in r.stdout.lower() else "light"
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
    except Exception:
        pass
    return "light"


def find_widgets(parent, kind):
    found = []
    for child in parent.winfo_children():
        if isinstance(child, kind):
            found.append(child)
        found.extend(find_widgets(child, kind))
    return found


def resolve_mode(choice):
    return system_mode() if choice == "System" else choice.lower()


def apply_theme(root, mode):
    """Purple 'clam' theme so the window looks the same on Mac and Windows (native themes force blue)."""
    p = PALETTES[mode]
    s = ttk.Style(root)
    s.theme_use("clam")
    root.configure(bg=p["bg"])
    s.configure(".", background=p["bg"], foreground=p["fg"])
    for w in ("TFrame", "TLabel", "TCheckbutton"):
        s.configure(w, background=p["bg"], foreground=p["fg"])
    s.configure("TButton", padding=(12, 5), background=p["button"], foreground=p["fg"],
                bordercolor=p["border"], lightcolor=p["button"], darkcolor=p["button"])
    s.map("TButton", background=[("active", p["button_hover"]), ("disabled", p["bg"])],
          foreground=[("disabled", p["muted"])])
    s.configure("Accent.TButton", background=p["accent"], foreground="white", borderwidth=0,
                padding=(16, 6), lightcolor=p["accent"], darkcolor=p["accent"])
    s.map("Accent.TButton", background=[("disabled", p["accent_soft"]), ("active", p["accent_dark"])],
          foreground=[("disabled", "white")])
    s.configure("Horizontal.TProgressbar", background=p["accent"], troughcolor=p["trough"], borderwidth=0)
    s.configure("TCheckbutton", indicatorbackground=p["field"], indicatorforeground="white")
    s.map("TCheckbutton", indicatorcolor=[("selected", p["accent"])], background=[("active", p["bg"])])
    s.configure("TCombobox", fieldbackground=p["field"], background=p["button"], foreground=p["fg"],
                arrowcolor=p["fg"], bordercolor=p["border"], selectbackground=p["field"],
                selectforeground=p["fg"], lightcolor=p["field"], darkcolor=p["field"])
    s.map("TCombobox", fieldbackground=[("readonly", p["field"])], foreground=[("readonly", p["fg"])],
          selectbackground=[("readonly", p["field"])], selectforeground=[("readonly", p["fg"])])
    s.configure("TEntry", fieldbackground=p["field"], foreground=p["fg"], insertcolor=p["fg"],
                bordercolor=p["border"], selectbackground=p["accent"], selectforeground="white",
                lightcolor=p["field"], darkcolor=p["field"])
    root.option_add("*TCombobox*Listbox.background", p["field"])
    root.option_add("*TCombobox*Listbox.foreground", p["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    return p


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.theme_choice = tk.StringVar(value=load_theme_choice())
        self.mode = resolve_mode(self.theme_choice.get())
        apply_theme(self, self.mode)
        self.title("ytdl")
        try:
            self.icon = tk.PhotoImage(file=asset_path("icon.png"))
            self.iconphoto(True, self.icon)
        except tk.TclError:
            pass  # missing icon is cosmetic only
        self.minsize(620, 440)
        self.events = queue.Queue()
        self.busy = False

        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Links to videos or posts: YouTube, Instagram, X, Facebook, Threads (one per line)").grid(row=0, column=0, columnspan=3, sticky="w", **pad)
        self.urls = tk.Text(frm, height=4, wrap="none", relief="solid", borderwidth=1, highlightthickness=0)
        self.urls.grid(row=1, column=0, columnspan=3, sticky="ew", **pad)

        ttk.Label(frm, text="Save to").grid(row=2, column=0, sticky="w", **pad)
        self.folder = tk.StringVar(value=ytdl.default_folder())
        ttk.Entry(frm, textvariable=self.folder).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse…", command=self.pick_folder).grid(row=2, column=2, **pad)

        opts = ttk.Frame(frm)
        opts.grid(row=3, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(opts, text="Format").pack(side="left")
        self.fmt = tk.StringVar(value="mp4")
        fmt_box = ttk.Combobox(opts, textvariable=self.fmt, state="readonly", width=12,
                               values=[f"{f} (video)" for f in ytdl.VIDEO_FORMATS]
                                      + [f"{f} (audio)" for f in ytdl.AUDIO_FORMATS])
        fmt_box.set("mp4 (video)")
        fmt_box.pack(side="left", padx=(6, 16))
        ttk.Label(opts, text="Quality").pack(side="left")
        self.quality = tk.StringVar(value="best")
        ttk.Combobox(opts, textvariable=self.quality, values=ytdl.QUALITIES,
                     width=7, state="readonly").pack(side="left", padx=(6, 16))
        self.fmt_box = fmt_box

        opts2 = ttk.Frame(frm)
        opts2.grid(row=4, column=0, columnspan=3, sticky="w", **pad)
        self.playlist = tk.BooleanVar()
        ttk.Checkbutton(opts2, text="All videos in playlist/post", variable=self.playlist).pack(side="left", padx=(0, 16))
        ttk.Label(opts2, text="Use login from").pack(side="left")
        self.browser = tk.StringVar(value="none")
        browser_box = ttk.Combobox(opts2, textvariable=self.browser, values=["none"] + ytdl.BROWSERS,
                                   width=9, state="readonly")
        browser_box.pack(side="left", padx=(6, 16))
        ttk.Label(opts2, text="Theme").pack(side="left")
        theme_box = ttk.Combobox(opts2, textvariable=self.theme_choice, values=THEME_CHOICES,
                                 width=7, state="readonly")
        theme_box.pack(side="left", padx=6)
        theme_box.bind("<<ComboboxSelected>>", self.on_theme_change)

        self.btn = ttk.Button(frm, text="Download", style="Accent.TButton", command=self.start)
        self.btn.grid(row=5, column=0, **pad, sticky="w")
        ttk.Button(frm, text="Open folder", command=self.open_folder).grid(row=5, column=1, **pad, sticky="w")

        self.bar = ttk.Progressbar(frm, maximum=100)
        self.bar.grid(row=6, column=0, columnspan=3, sticky="ew", **pad)
        self.log = tk.Text(frm, height=8, state="disabled", wrap="word", relief="solid", borderwidth=1, highlightthickness=0)
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(7, weight=1)

        self.comboboxes = find_widgets(self, ttk.Combobox)
        self.restyle_widgets()
        self.after(100, self.poll)
        self.after(5000, self.follow_system)

    def restyle_widgets(self):
        """Colors that ttk styles don't reach: the plain Text boxes and combobox dropdown lists."""
        p = PALETTES[self.mode]
        for t in (self.urls, self.log):
            t.configure(bg=p["field"], fg=p["fg"], insertbackground=p["fg"], selectbackground=p["accent"],
                        selectforeground="white", highlightbackground=p["border"])
            t.configure(relief="solid", borderwidth=1)
        for cb in self.comboboxes:
            try:
                pop = self.tk.call("ttk::combobox::PopdownWindow", str(cb))
                self.tk.call(f"{pop}.f.l", "configure", "-background", p["field"], "-foreground", p["fg"],
                             "-selectbackground", p["accent"], "-selectforeground", "white")
            except tk.TclError:
                pass

    def on_theme_change(self, _event=None):
        save_theme_choice(self.theme_choice.get())
        self.set_mode(resolve_mode(self.theme_choice.get()))

    def set_mode(self, mode):
        self.mode = mode
        apply_theme(self, mode)
        self.restyle_widgets()

    def follow_system(self):
        if self.theme_choice.get() == "System":
            mode = system_mode()
            if mode != self.mode:
                self.set_mode(mode)
        self.after(5000, self.follow_system)

    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder.get())
        if d:
            self.folder.set(d)

    def open_folder(self):
        path = os.path.expanduser(self.folder.get())
        os.makedirs(path, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.run(["open", path])
        elif sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.run(["xdg-open", path])

    def say(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self):
        urls = [u.strip() for u in self.urls.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo("ytdl", "Paste at least one video link.")
            return
        self.busy = True
        self.btn.configure(state="disabled")
        self.bar["value"] = 0
        browser = self.browser.get()
        kwargs = dict(output=self.folder.get(), quality=self.quality.get(),
                      fmt=self.fmt_box.get().split()[0], playlist=self.playlist.get(),
                      browser=None if browser == "none" else browser)
        threading.Thread(target=self.work, args=(urls, kwargs), daemon=True).start()

    def hook(self, d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                self.events.put(("progress", d["downloaded_bytes"] * 100 / total))
        elif d["status"] == "finished":
            self.events.put(("log", "Downloaded, finishing up…"))

    def work(self, urls, kwargs):
        try:
            self.events.put(("log", f"Starting {len(urls)} download(s)…"))
            failures = ytdl.download(urls, hooks=[self.hook], quiet=True, **kwargs)
            for url, err in failures:
                self.events.put(("log", f"Failed: {url}\n  {err}"))
            if not failures:
                self.events.put(("log", "All done."))
        except Exception as e:  # keep the window alive on any error
            self.events.put(("log", f"Error: {e}"))
        self.events.put(("done", None))

    def poll(self):
        try:
            while True:
                kind, val = self.events.get_nowait()
                if kind == "progress":
                    self.bar["value"] = val
                elif kind == "log":
                    self.say(val)
                elif kind == "done":
                    self.busy = False
                    self.btn.configure(state="normal")
        except queue.Empty:
            pass
        self.after(100, self.poll)


def main():
    App().mainloop()
