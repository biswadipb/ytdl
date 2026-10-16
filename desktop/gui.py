"""Simple desktop window for ytdl (tkinter, ships with Python)."""
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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
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
        self.urls = tk.Text(frm, height=4, wrap="none")
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
        ttk.Combobox(opts2, textvariable=self.browser, values=["none"] + ytdl.BROWSERS,
                     width=9, state="readonly").pack(side="left", padx=6)

        self.btn = ttk.Button(frm, text="Download", command=self.start)
        self.btn.grid(row=5, column=0, **pad, sticky="w")
        ttk.Button(frm, text="Open folder", command=self.open_folder).grid(row=5, column=1, **pad, sticky="w")

        self.bar = ttk.Progressbar(frm, maximum=100)
        self.bar.grid(row=6, column=0, columnspan=3, sticky="ew", **pad)
        self.log = tk.Text(frm, height=8, state="disabled", wrap="word")
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(7, weight=1)

        self.after(100, self.poll)

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
