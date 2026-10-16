"""Desktop window for ytdl (tkinter, ships with Python)."""
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, simpledialog, ttk

import subscriptions
import updates
import webbrowser
import ytdl
from version import __version__

try:
    from PIL import Image, ImageTk
except ImportError:  # thumbnails are optional
    Image = ImageTk = None


def asset_path(name):
    """Bundled copy when packaged by PyInstaller, repo copy when run from source."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "assets", name)
    return os.path.join(os.path.dirname(__file__), "..", "assets", name)


SETTINGS = os.path.join(os.path.expanduser("~"), ".ytdl_settings.json")
THEME_CHOICES = ["System", "Light", "Dark"]
HISTORY_LIMIT = 100

PALETTES = {
    "light": dict(bg="#F7F7FB", fg="#1F1F2E", muted="#55556B", field="#FFFFFF", border="#C9C9D9",
                  trough="#E4E4EE", button="#ECECF4", button_hover="#E0E0EC",
                  accent="#4F46E5", accent_dark="#4338CA", accent_soft="#A5A1F0", banner="#E8E7FD"),
    "dark": dict(bg="#16161F", fg="#EDEDF5", muted="#A0A0B8", field="#1F1F2B", border="#3A3A4D",
                 trough="#2A2A3A", button="#2A2A3A", button_hover="#34344A",
                 accent="#6D64F0", accent_dark="#5B52E0", accent_soft="#47427F", banner="#26254A"),
}


def load_settings():
    try:
        with open(SETTINGS) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        with open(SETTINGS, "w") as f:
            json.dump(data, f)
    except OSError:
        pass  # remembering settings is a convenience only


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


def resolve_mode(choice):
    return system_mode() if choice == "System" else choice.lower()


def find_widgets(parent, kind):
    found = []
    for child in parent.winfo_children():
        if isinstance(child, kind):
            found.append(child)
        found.extend(find_widgets(child, kind))
    return found


def apply_theme(root, mode):
    """Purple 'clam' theme so the window looks the same on Mac and Windows (native themes force blue)."""
    p = PALETTES[mode]
    s = ttk.Style(root)
    s.theme_use("clam")
    root.configure(bg=p["bg"])
    s.configure(".", background=p["bg"], foreground=p["fg"])
    for w in ("TFrame", "TLabel", "TCheckbutton"):
        s.configure(w, background=p["bg"], foreground=p["fg"])
    s.configure("Muted.TLabel", foreground=p["muted"])
    s.configure("Banner.TFrame", background=p["banner"])
    s.configure("Banner.TLabel", background=p["banner"], foreground=p["fg"])
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
    s.configure("Treeview", background=p["field"], fieldbackground=p["field"], foreground=p["fg"],
                bordercolor=p["border"], rowheight=24)
    s.map("Treeview", background=[("selected", p["accent"])], foreground=[("selected", "white")])
    s.configure("Treeview.Heading", background=p["button"], foreground=p["fg"], bordercolor=p["border"])
    s.configure("TNotebook", background=p["bg"], bordercolor=p["border"])
    s.configure("TNotebook.Tab", background=p["button"], foreground=p["fg"], padding=(14, 5))
    s.map("TNotebook.Tab", background=[("selected", p["field"])])
    root.option_add("*TCombobox*Listbox.background", p["field"])
    root.option_add("*TCombobox*Listbox.foreground", p["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    return p


def fmt_duration(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        choice = self.settings.get("theme", "System")
        self.theme_choice = tk.StringVar(value=choice if choice in THEME_CHOICES else "System")
        self.mode = resolve_mode(self.theme_choice.get())
        apply_theme(self, self.mode)
        self.title("ytdl")
        try:
            self.icon = tk.PhotoImage(file=asset_path("icon.png"))
            self.iconphoto(True, self.icon)
        except tk.TclError:
            pass  # missing icon is cosmetic only
        self.minsize(760, 720)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.events = queue.Queue()
        self.jobs = queue.Queue()
        self.items = {}
        self.next_id = 1
        self.last_clip = None
        self.preview_image = None
        self.picker_url = None
        self.picker_entries = []
        self.cfg = dict(speed=None, parallel=2, retries=2)  # read by worker threads
        self.running = 0
        self.cv = threading.Condition()

        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)
        self.main = main

        self.clip_bar = ttk.Frame(main, style="Banner.TFrame", padding=(10, 6))
        self.clip_label = ttk.Label(self.clip_bar, style="Banner.TLabel")
        self.clip_label.pack(side="left", fill="x", expand=True)
        ttk.Button(self.clip_bar, text="Dismiss", command=self.dismiss_clip).pack(side="right", padx=(6, 0))
        ttk.Button(self.clip_bar, text="Paste link", command=self.paste_clip).pack(side="right")

        self.update_bar = ttk.Frame(main, style="Banner.TFrame", padding=(10, 6))
        self.update_label = ttk.Label(self.update_bar, style="Banner.TLabel")
        self.update_label.pack(side="left", fill="x", expand=True)
        ttk.Button(self.update_bar, text="Later", command=self.update_bar.pack_forget).pack(side="right", padx=(6, 0))
        self.update_btn = ttk.Button(self.update_bar, text="Download")
        self.update_btn.pack(side="right")

        self.urls_frame = ttk.Frame(main)
        self.urls_frame.pack(fill="x")
        self.urls_frame.columnconfigure(0, weight=1)
        ttk.Label(self.urls_frame, text="Links to videos or posts: YouTube, Instagram, X, Facebook, Threads, Dailymotion (one per line)"
                  ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.urls = tk.Text(self.urls_frame, height=3, wrap="none", relief="solid", borderwidth=1, highlightthickness=0)
        self.urls.grid(row=1, column=0, sticky="ew")
        self.preview_btn = ttk.Button(self.urls_frame, text="Preview", command=self.preview)
        self.preview_btn.grid(row=1, column=1, sticky="n", padx=(8, 0))

        self.preview_frame = ttk.Frame(main, padding=(0, 8, 0, 0))
        self.thumb = ttk.Label(self.preview_frame)
        self.thumb.pack(side="left", padx=(0, 10))
        self.preview_text = ttk.Label(self.preview_frame, justify="left", wraplength=480)
        self.preview_text.pack(side="left", anchor="n")

        self.picker = ttk.Frame(main, padding=(0, 8, 0, 0))
        self.picker_title = ttk.Label(self.picker)
        self.picker_title.pack(anchor="w")
        pick_body = ttk.Frame(self.picker)
        pick_body.pack(fill="x", pady=(4, 0))
        self.picker_list = tk.Listbox(pick_body, selectmode="extended", height=7, activestyle="none",
                                      relief="solid", borderwidth=1, highlightthickness=0, exportselection=False)
        scroll = ttk.Scrollbar(pick_body, command=self.picker_list.yview)
        self.picker_list.configure(yscrollcommand=scroll.set)
        self.picker_list.pack(side="left", fill="x", expand=True)
        scroll.pack(side="left", fill="y")
        pick_btns = ttk.Frame(self.picker)
        pick_btns.pack(fill="x", pady=(4, 0))
        ttk.Button(pick_btns, text="Select all", command=lambda: self.picker_list.select_set(0, "end")).pack(side="left")
        ttk.Button(pick_btns, text="Select none", command=lambda: self.picker_list.select_clear(0, "end")).pack(side="left", padx=6)

        opts = ttk.Frame(main, padding=(0, 10, 0, 0))
        self.opts_frame = self.more_anchor = opts
        opts.pack(fill="x")
        opts.columnconfigure(1, weight=1)
        ttk.Label(opts, text="Save to").grid(row=0, column=0, sticky="w", pady=3)
        self.folder = tk.StringVar(value=self.settings.get("folder", ytdl.default_folder()))
        ttk.Entry(opts, textvariable=self.folder).grid(row=0, column=1, sticky="ew", padx=8, pady=3)
        ttk.Button(opts, text="Browse…", command=self.pick_folder).grid(row=0, column=2, pady=3)

        row1 = ttk.Frame(opts)
        row1.grid(row=1, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Label(row1, text="Format").pack(side="left")
        self.fmt_box = ttk.Combobox(row1, state="readonly", width=12,
                                    values=[f"{f} (video)" for f in ytdl.VIDEO_FORMATS]
                                           + [f"{f} (audio)" for f in ytdl.AUDIO_FORMATS])
        self.fmt_box.set("mp4 (video)")
        self.fmt_box.pack(side="left", padx=(6, 16))
        ttk.Label(row1, text="Quality").pack(side="left")
        self.quality = tk.StringVar(value="best")
        ttk.Combobox(row1, textvariable=self.quality, values=ytdl.QUALITIES, width=7,
                     state="readonly").pack(side="left", padx=(6, 16))
        ttk.Label(row1, text="Clip").pack(side="left")
        self.clip_start, self.clip_end = tk.StringVar(), tk.StringVar()
        ttk.Entry(row1, textvariable=self.clip_start, width=7).pack(side="left", padx=(6, 2))
        ttk.Label(row1, text="to").pack(side="left")
        ttk.Entry(row1, textvariable=self.clip_end, width=7).pack(side="left", padx=(2, 0))
        ttk.Label(row1, text="(e.g. 1:30; blank = whole video)", style="Muted.TLabel").pack(side="left", padx=8)

        row2 = ttk.Frame(opts)
        row2.grid(row=2, column=0, columnspan=3, sticky="w", pady=3)
        self.playlist = tk.BooleanVar()
        ttk.Checkbutton(row2, text="All videos in playlist/post", variable=self.playlist).pack(side="left", padx=(0, 16))
        self.extras = tk.BooleanVar(value=self.settings.get("extras", True))
        ttk.Checkbutton(row2, text="Embed cover art and tags", variable=self.extras).pack(side="left")

        row3 = ttk.Frame(opts)
        row3.grid(row=3, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Label(row3, text="Login for private posts").pack(side="left")
        self.browser = tk.StringVar(value=self.settings.get("browser", "none"))
        ttk.Combobox(row3, textvariable=self.browser, values=["none"] + ytdl.BROWSERS, width=9,
                     state="readonly").pack(side="left", padx=6)
        self.cookies_file = self.settings.get("cookies_file") or ""
        self.cookies_btn = ttk.Button(row3, command=self.pick_cookies)
        self.cookies_btn.pack(side="left", padx=(0, 16))
        ttk.Label(row3, text="Theme").pack(side="left")
        theme_box = ttk.Combobox(row3, textvariable=self.theme_choice, values=THEME_CHOICES, width=7,
                                 state="readonly")
        theme_box.pack(side="left", padx=6)
        theme_box.bind("<<ComboboxSelected>>", self.on_theme_change)
        self.update_cookies_label()

        self.more = ttk.Frame(main, padding=(0, 4, 0, 0))
        mr1 = ttk.Frame(self.more)
        mr1.pack(anchor="w", pady=3)
        ttk.Label(mr1, text="Name files").pack(side="left")
        self.naming = tk.StringVar(value=ytdl.label_for(self.settings.get("naming", "title-id"), ytdl.NAMING))
        ttk.Combobox(mr1, textvariable=self.naming, values=[v[0] for v in ytdl.NAMING.values()], width=16,
                     state="readonly").pack(side="left", padx=(6, 16))
        ttk.Label(mr1, text="Folders").pack(side="left")
        self.folders = tk.StringVar(value=ytdl.label_for(self.settings.get("folders", "flat"), ytdl.FOLDER_RULES))
        ttk.Combobox(mr1, textvariable=self.folders, values=[v[0] for v in ytdl.FOLDER_RULES.values()], width=18,
                     state="readonly").pack(side="left", padx=6)
        mr2 = ttk.Frame(self.more)
        mr2.pack(anchor="w", pady=3)
        ttk.Label(mr2, text="Subtitles").pack(side="left")
        self.sub_lang = tk.StringVar(value=self.settings.get("sub_lang", "Off"))
        ttk.Combobox(mr2, textvariable=self.sub_lang, values=["Off"] + ytdl.SUB_LANGS, width=6,
                     state="readonly").pack(side="left", padx=(6, 16))
        self.sub_embed = tk.BooleanVar(value=self.settings.get("sub_embed", False))
        ttk.Checkbutton(mr2, text="Put inside the video (otherwise a separate .srt file)",
                        variable=self.sub_embed).pack(side="left")
        ttk.Label(mr2, text="  (video formats only)", style="Muted.TLabel").pack(side="left")
        mr3 = ttk.Frame(self.more)
        mr3.pack(anchor="w", pady=3)
        ttk.Label(mr3, text="Speed limit").pack(side="left")
        self.speed = tk.StringVar(value=self.settings.get("speed", "Unlimited"))
        speed_box = ttk.Combobox(mr3, textvariable=self.speed, values=list(ytdl.SPEEDS), width=10, state="readonly")
        speed_box.pack(side="left", padx=(6, 16))
        ttk.Label(mr3, text="At once").pack(side="left")
        self.parallel = tk.StringVar(value=str(self.settings.get("parallel", 2)))
        par_box = ttk.Combobox(mr3, textvariable=self.parallel, values=["1", "2", "3"], width=3, state="readonly")
        par_box.pack(side="left", padx=(6, 16))
        ttk.Label(mr3, text="Auto-retry").pack(side="left")
        self.retries = tk.StringVar(value=str(self.settings.get("retries", 2)))
        ret_box = ttk.Combobox(mr3, textvariable=self.retries, values=["0", "1", "2", "3"], width=3, state="readonly")
        ret_box.pack(side="left", padx=6)
        ttk.Label(mr3, text="(speed limit is shared by downloads running at once)",
                  style="Muted.TLabel").pack(side="left", padx=6)
        for box in (speed_box, par_box, ret_box):
            box.bind("<<ComboboxSelected>>", self.on_limits_change)
        self.on_limits_change()

        actions = ttk.Frame(main, padding=(0, 10, 0, 6))
        actions.pack(fill="x")
        ttk.Button(actions, text="Add to queue", style="Accent.TButton", command=self.add_to_queue).pack(side="left")
        self.more_btn = ttk.Button(actions, text="More options \u25be", command=self.toggle_more)
        self.more_btn.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Follow channel", command=self.follow_channel).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open folder", command=self.open_folder).pack(side="left", padx=8)
        ttk.Button(actions, text="Update engine", command=lambda: self.start_engine_update(True)).pack(side="left")
        self.status = ttk.Label(actions, style="Muted.TLabel")
        self.status.pack(side="left", padx=12)

        tabs = ttk.Notebook(main)
        tabs.pack(fill="both", expand=True)
        qtab, htab = ttk.Frame(tabs, padding=6), ttk.Frame(tabs, padding=6)
        tabs.add(qtab, text="Queue")
        tabs.add(htab, text="History")
        stab = ttk.Frame(tabs, padding=6)
        tabs.add(stab, text="Subscriptions")
        self.build_subscriptions_tab(stab)

        self.tree = ttk.Treeview(qtab, columns=("status", "progress"), height=6)
        self.tree.heading("#0", text="Download")
        self.tree.heading("status", text="Status")
        self.tree.heading("progress", text="Progress")
        self.tree.column("#0", width=380)
        self.tree.column("status", width=120, anchor="w")
        self.tree.column("progress", width=80, anchor="e")
        self.tree.pack(fill="both", expand=True)
        qbtn = ttk.Frame(qtab, padding=(0, 6, 0, 0))
        qbtn.pack(fill="x")
        ttk.Button(qbtn, text="Cancel selected", command=self.cancel_selected).pack(side="left")
        ttk.Button(qbtn, text="Retry selected", command=self.retry_selected).pack(side="left", padx=(8, 0))
        ttk.Button(qbtn, text="Clear finished", command=self.clear_finished).pack(side="left", padx=8)

        self.history = ttk.Treeview(htab, columns=("when",), height=6)
        self.history.heading("#0", text="Saved file")
        self.history.heading("when", text="When")
        self.history.column("#0", width=470)
        self.history.column("when", width=130, anchor="w")
        self.history.pack(fill="both", expand=True)
        self.history.bind("<Double-1>", self.reveal_history)
        hbtn = ttk.Frame(htab, padding=(0, 6, 0, 0))
        hbtn.pack(fill="x")
        ttk.Button(hbtn, text="Show in folder", command=self.reveal_history).pack(side="left")
        ttk.Button(hbtn, text="Clear history", command=self.clear_history).pack(side="left", padx=8)
        for rec in self.settings.get("history", []):
            self.history.insert("", "end", text=os.path.basename(rec["file"]), values=(rec["when"],),
                                tags=(rec["file"],))

        self.comboboxes = find_widgets(self, ttk.Combobox)
        self.restyle_widgets()
        for _ in range(3):  # how many run at once is limited by the "At once" setting
            threading.Thread(target=self.worker, daemon=True).start()
        self.bind("<FocusIn>", lambda e: self.check_clipboard() if e.widget is self else None)
        self.after(100, self.poll)
        self.after(600, self.check_clipboard)
        self.after(5000, self.follow_system)
        self.after(1500, lambda: self.start_engine_update(False))
        self.after(2500, self.check_for_app_update)
        self.after(4000, self.start_subscription_tick)

    # ---- theme -----------------------------------------------------------
    def restyle_widgets(self):
        """Colors that ttk styles don't reach: the plain Text box and combobox dropdown lists."""
        p = PALETTES[self.mode]
        self.urls.configure(bg=p["field"], fg=p["fg"], insertbackground=p["fg"], selectbackground=p["accent"],
                            selectforeground="white", highlightbackground=p["border"])
        self.picker_list.configure(bg=p["field"], fg=p["fg"], selectbackground=p["accent"],
                                   selectforeground="white", highlightbackground=p["border"])
        for cb in self.comboboxes:
            try:
                pop = self.tk.call("ttk::combobox::PopdownWindow", str(cb))
                self.tk.call(f"{pop}.f.l", "configure", "-background", p["field"], "-foreground", p["fg"],
                             "-selectbackground", p["accent"], "-selectforeground", "white")
            except tk.TclError:
                pass

    def on_theme_change(self, _event=None):
        self.settings["theme"] = self.theme_choice.get()
        save_settings(self.settings)
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

    def toggle_more(self):
        if self.more.winfo_ismapped():
            self.more.pack_forget()
            self.more_btn.configure(text="More options \u25be")
        else:
            self.more.pack(fill="x", after=self.more_anchor)
            self.more_btn.configure(text="More options \u25b4")

    def on_limits_change(self, _event=None):
        self.cfg.update(speed=ytdl.SPEEDS[self.speed.get()], parallel=int(self.parallel.get()),
                        retries=int(self.retries.get()))

    def check_for_app_update(self):
        def run():
            try:
                info = updates.check(__version__)
                if info:
                    self.events.put(("app_update", info))
            except Exception:
                pass  # offline or rate-limited: try again next launch

        threading.Thread(target=run, daemon=True).start()

    # ---- subscriptions ---------------------------------------------------
    def build_subscriptions_tab(self, tab):
        ttk.Label(tab, text="Follow a channel or playlist (paste its link, then Follow channel) and new uploads "
                  "download by themselves.", style="Muted.TLabel", wraplength=640).pack(anchor="w")
        self.subs_tree = ttk.Treeview(tab, columns=("state", "checked"), height=4)
        self.subs_tree.heading("#0", text="Following")
        self.subs_tree.heading("state", text="State")
        self.subs_tree.heading("checked", text="Last checked")
        self.subs_tree.column("#0", width=320)
        self.subs_tree.column("state", width=90, anchor="w")
        self.subs_tree.column("checked", width=150, anchor="w")
        self.subs_tree.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(tab, padding=(0, 6, 0, 0))
        row.pack(fill="x")
        ttk.Button(row, text="Check now", command=lambda: self.check_subscriptions(True)).pack(side="left")
        ttk.Button(row, text="Pause / resume", command=self.toggle_subscription).pack(side="left", padx=6)
        ttk.Button(row, text="Unfollow", command=self.unfollow_selected).pack(side="left")
        sched = ttk.Frame(tab, padding=(0, 8, 0, 0))
        sched.pack(fill="x")
        ttk.Label(sched, text="Check every").pack(side="left")
        self.sub_interval = tk.StringVar(value=str(subscriptions.interval_hours()))
        box = ttk.Combobox(sched, textvariable=self.sub_interval, values=[str(h) for h in subscriptions.INTERVALS],
                           width=4, state="readonly")
        box.pack(side="left", padx=6)
        box.bind("<<ComboboxSelected>>", lambda e: subscriptions.set_interval_hours(int(self.sub_interval.get())))
        ttk.Label(sched, text="hours").pack(side="left")
        self.sched_btn = ttk.Button(sched, command=self.toggle_schedule)
        self.sched_btn.pack(side="left", padx=12)
        self.sched_label = ttk.Label(sched, style="Muted.TLabel")
        self.sched_label.pack(side="left")
        ttk.Label(tab, text="Recently downloaded by subscriptions", padding=(0, 8, 0, 2)).pack(anchor="w")
        self.recent_tree = ttk.Treeview(tab, columns=("sub", "when"), height=4)
        self.recent_tree.heading("#0", text="Video")
        self.recent_tree.heading("sub", text="Channel")
        self.recent_tree.heading("when", text="When")
        self.recent_tree.column("#0", width=300)
        self.recent_tree.column("sub", width=170, anchor="w")
        self.recent_tree.column("when", width=100, anchor="w")
        self.recent_tree.pack(fill="both", expand=True)
        self.recent_tree.bind("<Double-1>", self.reveal_recent)
        self.checking = False
        self.refresh_subscriptions()

    def refresh_subscriptions(self):
        data = subscriptions.load()
        self.subs_tree.delete(*self.subs_tree.get_children())
        for s in data["subs"]:
            when = time.strftime("%b %d, %H:%M", time.localtime(s["last_checked"])) if s["last_checked"] else "never"
            if s.get("last_error"):
                when += " (error)"
            self.subs_tree.insert("", "end", iid=s["id"], text=s["name"],
                                  values=("On" if s["enabled"] else "Paused", when))
        self.recent_tree.delete(*self.recent_tree.get_children())
        for r in data["recent"]:
            self.recent_tree.insert("", "end", text=r["title"], values=(r["sub"], r["when"]), tags=(r["file"],))
        on = subscriptions.schedule_installed()
        self.sched_btn.configure(text="Turn off background checks" if on else "Turn on background checks")
        self.sched_label.configure(text="On: checks happen hourly even when ytdl is closed." if on
                                   else "Off: checks only happen while this window is open.")

    def subscription_options(self):
        browser, cookies = self.current_auth()
        sub = self.sub_lang.get()
        return dict(output=self.folder.get(), quality=self.quality.get(), fmt=self.fmt_box.get().split()[0],
                    naming=ytdl.key_for_label(self.naming.get(), ytdl.NAMING, "title-id"),
                    folders=ytdl.key_for_label(self.folders.get(), ytdl.FOLDER_RULES, "flat"),
                    sub_lang=None if sub == "Off" else sub, sub_embed=self.sub_embed.get(),
                    extras=self.extras.get(), browser=browser, cookies_file=cookies)

    def follow_channel(self):
        lines = [u.strip() for u in self.urls.get("1.0", "end").splitlines() if u.strip()]
        if not lines:
            messagebox.showinfo("ytdl", "Paste a channel or playlist link, then choose Follow channel.")
            return
        backfill = simpledialog.askinteger(
            "Follow channel", "Also download the latest videos right now?\n\n0 = only new uploads from now on",
            initialvalue=0, minvalue=0, maxvalue=10, parent=self)
        if backfill is None:
            return
        options, url = self.subscription_options(), lines[0]
        self.set_status("Following…")

        def run():
            try:
                sub, first = subscriptions.follow(url, options, backfill)
                self.events.put(("followed", sub, first))
            except Exception as e:
                self.events.put(("sub_error", str(e).replace("ERROR: ", "").splitlines()[0][:200]))

        threading.Thread(target=run, daemon=True).start()

    def check_subscriptions(self, force=False):
        if self.checking:
            return
        self.checking = True
        if force:
            self.set_status("Checking subscriptions…")

        def run():
            try:
                self.events.put(("sub_new", subscriptions.collect_new(force=force), force))
            except Exception as e:
                self.events.put(("sub_error", str(e).splitlines()[0][:200]))
            self.events.put(("sub_done", None))

        threading.Thread(target=run, daemon=True).start()

    def start_subscription_tick(self):
        """While the window is open, look for due subscriptions every few minutes."""
        if subscriptions.schedule_is_stale():
            try:
                subscriptions.install_schedule()  # the app moved: point the background job at its new location
            except RuntimeError:
                pass
        self.tick_subscriptions()

    def tick_subscriptions(self):
        if subscriptions.due():
            self.check_subscriptions()
        self.after(5 * 60 * 1000, self.tick_subscriptions)

    def selected_sub(self):
        sel = self.subs_tree.selection()
        return sel[0] if sel else None

    def toggle_subscription(self):
        sid = self.selected_sub()
        if sid:
            enabled = self.subs_tree.set(sid, "state") == "Paused"
            subscriptions.set_enabled(sid, enabled)
            self.refresh_subscriptions()

    def unfollow_selected(self):
        sid = self.selected_sub()
        if sid and messagebox.askyesno("ytdl", f"Stop following {self.subs_tree.item(sid, 'text')}?\nFiles already downloaded are kept."):
            subscriptions.unfollow(sid)
            self.refresh_subscriptions()

    def toggle_schedule(self):
        try:
            if subscriptions.schedule_installed():
                subscriptions.remove_schedule()
            else:
                subscriptions.install_schedule()
        except RuntimeError as e:
            messagebox.showerror("ytdl", f"Couldn't change background checks.\n\n{e}")
        self.refresh_subscriptions()

    def reveal_recent(self, _event=None):
        sel = self.recent_tree.selection()
        if sel:
            path = self.recent_tree.item(sel[0], "tags")[0]
            if os.path.exists(path):
                self.reveal(path, select=True)

    def enqueue_new_uploads(self, found):
        count = 0
        for sub, entries in found:
            for e in entries:
                self.enqueue(e["url"], dict(sub["options"], playlist=False), e["title"])
                count += 1
        return count

    # ---- small helpers ---------------------------------------------------
    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder.get())
        if d:
            self.folder.set(d)

    def open_folder(self):
        path = os.path.expanduser(self.folder.get())
        os.makedirs(path, exist_ok=True)
        self.reveal(path)

    @staticmethod
    def reveal(path, select=False):
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", path] if select else ["open", path])
        elif sys.platform == "win32":
            if select:
                subprocess.run(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(path)
        else:
            subprocess.run(["xdg-open", os.path.dirname(path) if select else path])

    def pick_cookies(self):
        if self.cookies_file:  # second click clears it
            self.cookies_file = ""
        else:
            path = filedialog.askopenfilename(title="Choose a cookies.txt file",
                                              filetypes=[("Cookies", "*.txt"), ("All files", "*.*")])
            if not path:
                return
            self.cookies_file = path
        self.update_cookies_label()

    def update_cookies_label(self):
        self.cookies_btn.configure(
            text=f"Cookies file: {os.path.basename(self.cookies_file)} (click to remove)"
            if self.cookies_file else "Use cookies.txt…")

    def set_status(self, text):
        self.status.configure(text=text)

    # ---- clipboard -------------------------------------------------------
    def check_clipboard(self):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        m = ytdl.SITE_PATTERN.search(text)
        if not m:
            return
        url = m.group(0)
        if url == self.last_clip or url in self.urls.get("1.0", "end"):
            return
        self.last_clip = url
        shown = url if len(url) <= 70 else url[:67] + "…"
        self.clip_label.configure(text=f"Link copied: {shown}")
        self.clip_bar.pack(fill="x", pady=(0, 8), before=self.urls_frame)

    def paste_clip(self):
        self.urls.insert("end", ("\n" if self.urls.get("1.0", "end").strip() else "") + self.last_clip)
        self.dismiss_clip()

    def dismiss_clip(self):
        self.clip_bar.pack_forget()

    # ---- preview ---------------------------------------------------------
    def current_auth(self):
        browser = self.browser.get()
        return (None if browser == "none" else browser), (self.cookies_file or None)

    def preview(self):
        urls = [u.strip() for u in self.urls.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo("ytdl", "Paste a link to preview.")
            return
        self.preview_btn.configure(state="disabled")
        self.set_status("Loading preview…")
        browser, cookies = self.current_auth()
        want_list = self.playlist.get()

        def run():
            try:
                if want_list:  # playlist mode: list the videos so the user can tick the ones they want
                    entries = ytdl.playlist_entries(urls[0], browser, cookies)
                    if entries:
                        self.events.put(("picker", urls[0], entries))
                        return
                info = ytdl.video_info(urls[0], browser, cookies)
                img = None
                if info.get("thumbnail") and Image:
                    try:
                        with urllib.request.urlopen(info["thumbnail"], timeout=15) as r:
                            img = r.read()
                    except Exception:
                        img = None
                self.events.put(("preview", info, img))
            except Exception as e:
                self.events.put(("preview_error", str(e).replace("ERROR: ", ""), None))

        threading.Thread(target=run, daemon=True).start()

    def show_preview(self, info, img_bytes):
        self.preview_btn.configure(state="normal")
        self.set_status("")
        self.hide_picker()
        self.preview_image = None
        if img_bytes and Image:
            try:
                im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                im.thumbnail((192, 108))
                self.preview_image = ImageTk.PhotoImage(im)
            except Exception:
                pass
        self.thumb.configure(image=self.preview_image or "")
        lines = [info["title"] or "Untitled"]
        if info.get("channel"):
            lines.append(f"by {info['channel']}")
        if info.get("duration"):
            lines.append(f"Length {fmt_duration(info['duration'])}")
        if info.get("heights"):
            lines.append("Qualities: " + ", ".join(f"{h}p" for h in info["heights"]))
        self.preview_text.configure(text="\n".join(lines))
        self.preview_frame.pack(fill="x", before=self.opts_frame)

    def show_picker(self, url, entries):
        self.preview_btn.configure(state="normal")
        self.set_status("")
        self.preview_frame.pack_forget()
        self.picker_url, self.picker_entries = url, entries
        self.picker_list.delete(0, "end")
        for i, e in enumerate(entries, 1):
            dur = f"  [{fmt_duration(e['duration'])}]" if e["duration"] else ""
            self.picker_list.insert("end", f"{i}. {e['title']}{dur}")
        self.picker_list.select_set(0, "end")
        self.picker_title.configure(text=f"{len(entries)} videos found. Untick none, select the ones you want:")
        self.picker.pack(fill="x", before=self.opts_frame)

    def hide_picker(self):
        self.picker_url, self.picker_entries = None, []
        self.picker.pack_forget()

    # ---- queue -----------------------------------------------------------
    def enqueue(self, url, kwargs, title=None):
        iid = str(self.next_id)
        self.next_id += 1
        item = dict(id=iid, url=url, title=title or url, cancel=threading.Event(), kwargs=kwargs)
        self.items[iid] = item
        self.tree.insert("", "end", iid=iid, text=item["title"], values=("Queued", ""))
        self.jobs.put(item)

    def add_to_queue(self):
        lines = [u.strip() for u in self.urls.get("1.0", "end").splitlines() if u.strip()]
        if not lines:
            messagebox.showinfo("ytdl", "Paste at least one video link.")
            return
        start, end = self.clip_start.get().strip(), self.clip_end.get().strip()
        try:
            clip = None
            if start or end:
                s, e = ytdl.parse_time(start) or 0.0, ytdl.parse_time(end)
                if e is not None and e <= s:
                    raise ValueError("Clip end must be after its start.")
                clip = (s, e)
        except ValueError as e:
            messagebox.showerror("ytdl", f"Check the clip times: {e}")
            return
        chosen = [self.picker_entries[i] for i in self.picker_list.curselection()] if self.picker_entries else []
        if self.picker_entries and self.picker_url in lines and not chosen:
            messagebox.showinfo("ytdl", "Select at least one video from the list.")
            return
        browser, cookies = self.current_auth()
        sub = self.sub_lang.get()
        naming = ytdl.key_for_label(self.naming.get(), ytdl.NAMING, "title-id")
        folders = ytdl.key_for_label(self.folders.get(), ytdl.FOLDER_RULES, "flat")
        self.settings.update(folder=self.folder.get(), browser=self.browser.get(), cookies_file=self.cookies_file,
                             extras=self.extras.get(), naming=naming, folders=folders, sub_lang=sub,
                             sub_embed=self.sub_embed.get(), speed=self.speed.get(),
                             parallel=int(self.parallel.get()), retries=int(self.retries.get()))
        save_settings(self.settings)
        kwargs = dict(output=self.folder.get(), quality=self.quality.get(), fmt=self.fmt_box.get().split()[0],
                      playlist=self.playlist.get(), browser=browser, cookies_file=cookies, clip=clip,
                      extras=self.extras.get(), naming=naming, folders=folders,
                      sub_lang=None if sub == "Off" else sub, sub_embed=self.sub_embed.get())
        for url in lines:
            if chosen and url == self.picker_url:
                # Picked videos become separate downloads, so each can be cancelled or retried on its own.
                for e in chosen:
                    self.enqueue(e["url"], dict(kwargs, playlist=False), e["title"])
            else:
                self.enqueue(url, kwargs)
        self.urls.delete("1.0", "end")
        self.hide_picker()
        self.dismiss_clip()

    def cancel_selected(self):
        for iid in self.tree.selection():
            item = self.items.get(iid)
            if item and self.tree.set(iid, "status").split(" (")[0] in ("Queued", "Downloading", "Retrying"):
                item["cancel"].set()
                self.tree.set(iid, "status", "Cancelling…")

    def retry_selected(self):
        for iid in self.tree.selection():
            item = self.items.get(iid)
            if item and self.tree.set(iid, "status") in ("Failed", "Cancelled"):
                item["cancel"] = threading.Event()
                self.tree.item(iid, text=item["title"])
                self.tree.set(iid, "status", "Queued")
                self.tree.set(iid, "progress", "")
                self.jobs.put(item)

    def clear_finished(self):
        for iid in list(self.tree.get_children()):
            if self.tree.set(iid, "status") in ("Done", "Failed", "Cancelled"):
                self.tree.delete(iid)
                self.items.pop(iid, None)

    def active_count(self):
        return sum(1 for i in self.tree.get_children()
                   if self.tree.set(i, "status").split(" (")[0] in ("Queued", "Downloading", "Cancelling…", "Retrying"))

    def on_close(self):
        if self.active_count() and not messagebox.askyesno(
                "ytdl", "Downloads are still running. Quit anyway?\n(Partial files resume if you start them again.)"):
            return
        self.destroy()

    def worker(self):
        """Pulls queued downloads; how many run at once is the 'At once' setting."""
        while True:
            item = self.jobs.get()
            with self.cv:
                while self.running >= self.cfg["parallel"] and not item["cancel"].is_set():
                    self.cv.wait(0.5)
                self.running += 1
            try:
                self.run_item(item)
            finally:
                with self.cv:
                    self.running -= 1
                    self.cv.notify_all()

    def run_item(self, item):
        iid, attempt = item["id"], 0
        put = self.events.put

        def hook(d):
            if item["cancel"].is_set():
                raise ytdl.Cancelled()
            title = (d.get("info_dict") or {}).get("title")
            if title:
                put(("title", iid, title))
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                if total:
                    put(("progress", iid, d["downloaded_bytes"] * 100 / total))

        while True:
            if item["cancel"].is_set():
                put(("status", iid, "Cancelled"))
                return
            put(("status", iid, "Downloading"))
            rate = self.cfg["speed"]
            kwargs = dict(item["kwargs"], ratelimit=rate // self.cfg["parallel"] if rate else None)
            try:
                files = ytdl.download_one(item["url"], hooks=[hook], quiet=True, **kwargs)
                put(("done", iid, files))
                return
            except ytdl.Cancelled:
                put(("status", iid, "Cancelled"))
                return
            except Exception as e:
                message = str(e).replace("ERROR: ", "")
                if item["cancel"].is_set():
                    put(("status", iid, "Cancelled"))
                    return
                if attempt < self.cfg["retries"] and ytdl.is_transient(message):
                    attempt += 1
                    put(("status", iid, f"Retrying ({attempt}/{self.cfg['retries']})"))
                    for _ in range(int(3 * attempt / 0.25)):  # wait 3s, 6s, 9s but react to Cancel
                        if item["cancel"].is_set():
                            break
                        time.sleep(0.25)
                    continue
                put(("failed", iid, message))
                return

    # ---- history ---------------------------------------------------------
    def record_history(self, files):
        when = time.strftime("%b %d, %H:%M")
        for path in files:
            self.settings.setdefault("history", []).insert(0, {"file": path, "when": when})
            self.history.insert("", 0, text=os.path.basename(path), values=(when,), tags=(path,))
        self.settings["history"] = self.settings["history"][:HISTORY_LIMIT]
        for extra in self.history.get_children()[HISTORY_LIMIT:]:
            self.history.delete(extra)
        save_settings(self.settings)

    def reveal_history(self, _event=None):
        sel = self.history.selection()
        if sel:
            path = self.history.item(sel[0], "tags")[0]
            if os.path.exists(path):
                self.reveal(path, select=True)
            else:
                messagebox.showinfo("ytdl", "That file has been moved or deleted.")

    def clear_history(self):
        self.history.delete(*self.history.get_children())
        self.settings["history"] = []
        save_settings(self.settings)

    # ---- engine ----------------------------------------------------------
    def start_engine_update(self, manual):
        if manual:
            self.set_status("Checking for a newer engine…")

        def run():
            try:
                changed, msg = ytdl.update_engine()
                if manual or changed:
                    self.events.put(("engine", msg))
            except Exception as e:
                if manual:
                    self.events.put(("engine", f"Update failed: {e}"))

        threading.Thread(target=run, daemon=True).start()

    # ---- event loop ------------------------------------------------------
    def poll(self):
        try:
            while True:
                kind, a, *rest = self.events.get_nowait()
                b = rest[0] if rest else None
                if kind == "progress" and self.tree.exists(a):
                    self.tree.set(a, "progress", f"{b:.0f}%")
                elif kind == "title" and self.tree.exists(a):
                    self.tree.item(a, text=b)
                    self.items[a]["title"] = b
                elif kind == "status" and self.tree.exists(a):
                    self.tree.set(a, "status", b)
                elif kind == "done":
                    if self.tree.exists(a):
                        self.tree.set(a, "status", "Done")
                        self.tree.set(a, "progress", "100%")
                    self.record_history(b)
                elif kind == "failed" and self.tree.exists(a):
                    self.tree.set(a, "status", "Failed")
                    self.tree.item(a, text=f"{self.items[a]['title']}  -  {b.splitlines()[0][:90]}")
                elif kind == "followed":
                    n = self.enqueue_new_uploads([(a, b)])
                    self.set_status(f"Following {a['name']}." + (f" Downloading the latest {n}." if n else
                                    " New uploads will download automatically."))
                    self.refresh_subscriptions()
                elif kind == "sub_new":
                    n = self.enqueue_new_uploads(a)
                    if n or b:
                        self.set_status(f"{n} new upload(s) added to the queue." if n else "No new uploads.")
                    self.refresh_subscriptions()
                elif kind == "sub_error":
                    self.set_status("")
                    messagebox.showerror("ytdl", f"Subscription problem:\n\n{a}")
                elif kind == "sub_done":
                    self.checking = False
                elif kind == "preview":
                    self.show_preview(a, b)
                elif kind == "picker":
                    self.show_picker(a, b)
                elif kind == "app_update":
                    self.update_label.configure(text=f"ytdl {a['version']} is available.")
                    self.update_btn.configure(command=lambda u=a["url"]: webbrowser.open(u))
                    self.update_bar.pack(fill="x", pady=(0, 8), before=self.urls_frame)
                elif kind == "preview_error":
                    self.preview_btn.configure(state="normal")
                    self.set_status("")
                    messagebox.showerror("ytdl", f"Couldn't load a preview.\n\n{a.splitlines()[0][:200]}")
                elif kind == "engine":
                    self.set_status(a)
        except queue.Empty:
            pass
        self.after(100, self.poll)


def main():
    App().mainloop()
