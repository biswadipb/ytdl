"""Simple desktop window for ytdl (tkinter, ships with Python)."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ytdl


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ytdl")
        self.minsize(560, 380)
        self.events = queue.Queue()
        self.busy = False

        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Video links (one per line)").grid(row=0, column=0, columnspan=3, sticky="w", **pad)
        self.urls = tk.Text(frm, height=4, wrap="none")
        self.urls.grid(row=1, column=0, columnspan=3, sticky="ew", **pad)

        ttk.Label(frm, text="Save to").grid(row=2, column=0, sticky="w", **pad)
        self.folder = tk.StringVar(value=ytdl.default_folder())
        ttk.Entry(frm, textvariable=self.folder).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse…", command=self.pick_folder).grid(row=2, column=2, **pad)

        opts = ttk.Frame(frm)
        opts.grid(row=3, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(opts, text="Quality").pack(side="left")
        self.quality = tk.StringVar(value="best")
        ttk.Combobox(opts, textvariable=self.quality, values=ytdl.QUALITIES,
                     width=7, state="readonly").pack(side="left", padx=(6, 16))
        self.audio = tk.BooleanVar()
        ttk.Checkbutton(opts, text="Audio only (mp3)", variable=self.audio).pack(side="left", padx=(0, 16))
        self.playlist = tk.BooleanVar()
        ttk.Checkbutton(opts, text="Whole playlist", variable=self.playlist).pack(side="left")

        self.btn = ttk.Button(frm, text="Download", command=self.start)
        self.btn.grid(row=4, column=0, **pad, sticky="w")
        ttk.Button(frm, text="Open folder", command=self.open_folder).grid(row=4, column=1, **pad, sticky="w")

        self.bar = ttk.Progressbar(frm, maximum=100)
        self.bar.grid(row=5, column=0, columnspan=3, sticky="ew", **pad)
        self.log = tk.Text(frm, height=8, state="disabled", wrap="word")
        self.log.grid(row=6, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(6, weight=1)

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
        kwargs = dict(output=self.folder.get(), quality=self.quality.get(),
                      audio=self.audio.get(), playlist=self.playlist.get())
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
