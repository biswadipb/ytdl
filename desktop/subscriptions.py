"""Channel subscriptions: follow a channel or playlist and download new uploads automatically.

A subscription remembers which videos it has already seen. Each check lists the newest videos,
downloads the ones it hasn't seen, and remembers them. Checks run from the window (a timer while it
is open) and from an operating-system scheduled job (so they also happen when ytdl is closed).
"""
import json
import os
import plistlib
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import ytdl

HOME_DIR = Path.home() / ".ytdl"
STORE = HOME_DIR / "subscriptions.json"
LOCK = HOME_DIR / "subscriptions.lock"
INTERVALS = [1, 3, 6, 12, 24]   # hours between checks of one subscription
PEEK = 15                       # how many of the newest videos each check looks at
SEEN_LIMIT = 500                # how many video ids a subscription remembers
MAX_FAILS = 3                   # give up on a video after this many failed checks
LOCK_STALE_SECONDS = 2 * 3600
LABEL = "dev.ytdl.subscriptions"
TASK_NAME = "ytdl-subscriptions"

CHANNEL_ROOT = re.compile(
    r"^(https?://(?:www\.|m\.)?youtube\.com/(?:@[^/?#]+|channel/[^/?#]+|c/[^/?#]+|user/[^/?#]+))/?(?:\?.*)?$")


# ---- storage -----------------------------------------------------------------

def load():
    try:
        data = json.loads(STORE.read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault("subs", [])
    data.setdefault("recent", [])
    return data


def save(data):
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(STORE)


class Lock:
    """One checker at a time, so the window and the scheduled job never download the same video twice."""

    def __enter__(self):
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if LOCK.exists() and time.time() - LOCK.stat().st_mtime > LOCK_STALE_SECONDS:
                LOCK.unlink()  # left behind by a crash
            self.fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            self.fd = None
        return self.fd is not None

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            LOCK.unlink(missing_ok=True)


# ---- listing and detecting new uploads -----------------------------------------

def listing_url(url):
    """A YouTube channel link means its Videos tab; anything else is used as given."""
    url = url.strip()
    m = CHANNEL_ROOT.match(url)
    return m.group(1) + "/videos" if m else url


_NO_PROFILES = {
    "x.com": "X", "twitter.com": "X", "threads.com": "Threads", "threads.net": "Threads", "facebook.com": "Facebook",
}


def unlistable_reason(url):
    """Why a link can't be followed, when we already know (so the user isn't left with a cryptic error). Else None."""
    host = re.sub(r"^(?:www\.|m\.|mobile\.)", "", (re.match(r"https?://([^/]+)", url.strip()) or [None, ""])[1].lower())
    name = _NO_PROFILES.get(host)
    if name:
        return (f"{name} doesn't let ytdl list a profile's posts, so profiles can't be followed. "
                f"You can still download individual {name} posts.")
    return None


def explain_listing_error(url, error):
    """A plain-language message for a failed channel listing."""
    text = str(error).replace("ERROR: ", "").strip()
    if "instagram.com" in url.lower():
        return ("Instagram wouldn't list this profile. It usually needs you to be signed in (see Login for private posts), "
                "and Instagram often blocks profile listing even then. Individual posts and reels still download.")
    if "Unsupported URL" in text:
        return "ytdl can't follow that kind of link. Follow a YouTube channel or playlist, or another playlist-style link."
    return text.splitlines()[0][:200] if text else "Couldn't read that link."


def list_entries(url, browser=None, cookies_file=None, limit=PEEK):
    """(name, [{id, url, title, upcoming}]) for the newest videos of a channel or playlist, newest first."""
    reason = unlistable_reason(url)
    if reason:
        raise ValueError(reason)
    opts = ytdl._auth({"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
                       "playlistend": limit, "lazy_playlist": True}, browser, cookies_file)
    try:
        with ytdl.yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(listing_url(url), download=False)
    except ytdl.yt_dlp.utils.DownloadError as e:
        raise ValueError(explain_listing_error(url, e)) from e
    if info.get("_type") != "playlist":
        raise ValueError("That link is a single video. Follow a channel or playlist link instead.")
    entries = []
    for e in info.get("entries") or []:
        link = (e or {}).get("url") or (e or {}).get("webpage_url")
        if not link or not link.startswith("http"):
            continue
        entries.append({"id": e.get("id") or link, "url": link, "title": e.get("title") or link,
                        "upcoming": e.get("live_status") in ("is_upcoming", "is_live")})
    name = info.get("channel") or info.get("uploader") or re.sub(r"\s*-\s*Videos$", "", info.get("title") or url)
    return name, entries


def find_new(sub, entries):
    """Entries not seen before, oldest first. Scheduled livestreams are left for a later check."""
    seen = set(sub["seen"])
    return [e for e in reversed(entries) if e["id"] not in seen and not e["upcoming"]]


def make_subscription(url, name, options, entries):
    """A new subscription that treats everything currently on the channel as already seen."""
    return {"id": uuid.uuid4().hex[:8], "url": url.strip(), "name": name, "options": options,
            "seen": [e["id"] for e in entries][:SEEN_LIMIT], "enabled": True, "added": time.time(),
            "last_checked": 0, "last_error": "", "fails": {}}


def follow(url, options, backfill=0):
    """Start following a link. Returns (subscription, entries to download now)."""
    name, entries = list_entries(url, options.get("browser"), options.get("cookies_file"))
    sub = make_subscription(url, name, options, entries)
    data = load()
    if any(s["url"] == sub["url"] for s in data["subs"]):
        raise ValueError(f"You already follow {name}.")
    data["subs"].append(sub)
    save(data)
    return sub, entries[:max(0, backfill)]


def unfollow(sub_id):
    data = load()
    data["subs"] = [s for s in data["subs"] if s["id"] != sub_id]
    save(data)


def set_enabled(sub_id, enabled):
    data = load()
    for s in data["subs"]:
        if s["id"] == sub_id:
            s["enabled"] = enabled
    save(data)


def mark_seen(sub_id, ids, error=""):
    data = load()
    for s in data["subs"]:
        if s["id"] == sub_id:
            s["seen"] = (list(ids) + [i for i in s["seen"] if i not in ids])[:SEEN_LIMIT]
            s["last_checked"] = time.time()
            s["last_error"] = error
            for i in ids:
                s["fails"].pop(i, None)
    save(data)


def record_check(sub_id, error=""):
    data = load()
    for s in data["subs"]:
        if s["id"] == sub_id:
            s["last_checked"] = time.time()
            s["last_error"] = error
    save(data)


def record_failure(sub_id, video_id):
    """Count a failed video; after MAX_FAILS checks give up so it isn't retried forever. Returns True if given up."""
    data = load()
    gave_up = False
    for s in data["subs"]:
        if s["id"] == sub_id:
            s["fails"][video_id] = s["fails"].get(video_id, 0) + 1
            if s["fails"][video_id] >= MAX_FAILS:
                s["seen"] = ([video_id] + s["seen"])[:SEEN_LIMIT]
                s["fails"].pop(video_id)
                gave_up = True
    save(data)
    return gave_up


def add_recent(sub_name, title, files):
    """Remember what a subscription downloaded: for the Recent list, and so storage cleanup knows what it may delete."""
    data = load()
    now = time.time()
    for f in files:
        data["recent"].insert(0, {"sub": sub_name, "title": title, "file": f, "when": time.strftime("%b %d, %H:%M")})
        try:
            size = os.path.getsize(f)
        except OSError:
            size = 0
        data.setdefault("files", []).append({"sub": sub_name, "path": f, "size": size, "time": now})
    data["recent"] = data["recent"][:50]
    save(data)


def interval_hours():
    return load().get("interval_hours", 6)


def set_interval_hours(hours):
    data = load()
    data["interval_hours"] = hours
    save(data)


def due(now=None):
    """Enabled subscriptions that haven't been checked within the interval."""
    now = now or time.time()
    data = load()
    wait = data.get("interval_hours", 6) * 3600 - 60
    return [s for s in data["subs"] if s["enabled"] and now - s["last_checked"] >= wait]


# ---- checking (used by the scheduled job; the window enqueues instead) ---------

def notify(title, text):
    if sys.platform == "darwin":
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(["osascript", "-e", f'display notification "{esc(text)}" with title "{esc(title)}"'],
                       capture_output=True)


def download_new(sub, entry, log=print):
    """Download one new video for a subscription with retries. Returns the saved files or None."""
    for attempt in range(3):
        try:
            return ytdl.download_one(entry["url"], **dict(sub["options"], playlist=False))
        except Exception as e:  # noqa: BLE001 - any failure is logged and counted
            if attempt < 2 and ytdl.is_transient(str(e)):
                time.sleep(2 * (attempt + 1))
                continue
            log(f"  failed: {entry['title']}: {str(e).splitlines()[0][:150]}")
            return None


def check_due(log=print, force=False):
    """Check every due subscription and download its new uploads. Returns how many videos were saved."""
    saved = 0
    with Lock() as got:
        if not got:
            log("Another check is already running.")
            return 0
        import storage
        for sub in (load()["subs"] if force else due()):
            if force and not sub["enabled"]:
                continue
            is_low, free = storage.low_space(sub["options"]["output"])
            if is_low:
                log(f"{sub['name']}: skipped, only {storage.human(free)} free (change the warning in Subscriptions).")
                continue
            try:
                _, entries = list_entries(sub["url"], sub["options"].get("browser"), sub["options"].get("cookies_file"))
            except Exception as e:  # noqa: BLE001
                record_check(sub["id"], str(e).splitlines()[0][:200])
                log(f"{sub['name']}: couldn't check ({str(e).splitlines()[0][:120]})")
                continue
            new = find_new(sub, entries)
            log(f"{sub['name']}: {len(new)} new")
            done = []
            for entry in new:
                files = download_new(sub, entry, log)
                if files is not None:
                    done.append(entry["id"])
                    saved += 1
                    add_recent(sub["name"], entry["title"], files)
                    notify(sub["name"], f"Downloaded: {entry['title']}")
                elif record_failure(sub["id"], entry["id"]):
                    log(f"  giving up on {entry['title']}")
            mark_seen(sub["id"], done)
        count, freed = storage.cleanup()
        if count:
            log(f"Storage cleanup removed {count} old file(s), {storage.human(freed)}.")
    return saved


def collect_new(force=False, log=print):
    """For the window: find new uploads and mark them seen, leaving the downloading to the caller.

    Returns [(subscription, [new entries])]. Marking happens here so the background job won't repeat them.
    """
    found = []
    with Lock() as got:
        if not got:
            return found
        for sub in (load()["subs"] if force else due()):
            if force and not sub["enabled"]:
                continue
            try:
                _, entries = list_entries(sub["url"], sub["options"].get("browser"), sub["options"].get("cookies_file"))
            except Exception as e:  # noqa: BLE001
                record_check(sub["id"], str(e).splitlines()[0][:200])
                log(f"{sub['name']}: couldn't check")
                continue
            new = find_new(sub, entries)
            mark_seen(sub["id"], [e["id"] for e in new])
            if new:
                found.append((sub, new))
    return found


# ---- running while ytdl is closed ----------------------------------------------

def check_command():
    """The command an OS scheduler should run."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--check-subscriptions"]
    exe = sys.executable
    if sys.platform == "win32" and exe.lower().endswith("python.exe"):
        pythonw = exe[:-10] + "pythonw.exe"  # no console window flashing every hour
        exe = pythonw if os.path.exists(pythonw) else exe
    return [exe, str(Path(__file__).with_name("main.py")), "--check-subscriptions"]


def _agent_path():
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              creationflags=0x08000000 if sys.platform == "win32" else 0)  # no console flash
    except FileNotFoundError:  # e.g. no crontab on this machine
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]} not found")


def install_schedule():
    """Run a check every hour in the background, even when ytdl is closed. Raises RuntimeError if unsupported."""
    cmd = check_command()
    if sys.platform == "darwin":
        path = _agent_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        log = str(HOME_DIR / "subscriptions.log")
        path.write_bytes(plistlib.dumps({
            "Label": LABEL, "ProgramArguments": cmd, "StartInterval": 3600, "RunAtLoad": False,
            "ProcessType": "Background", "StandardOutPath": log, "StandardErrorPath": log}))
        domain = f"gui/{os.getuid()}"
        _run(["launchctl", "bootout", f"{domain}/{LABEL}"])
        result = _run(["launchctl", "bootstrap", domain, str(path)])
        if result.returncode != 0:
            raise RuntimeError(f"launchctl failed: {result.stderr.strip()}")
    elif sys.platform == "win32":
        task = subprocess.list2cmdline(cmd)
        result = _run(["schtasks", "/Create", "/F", "/SC", "HOURLY", "/MO", "1", "/TN", TASK_NAME, "/TR", task])
        if result.returncode != 0:
            raise RuntimeError(f"schtasks failed: {(result.stderr or result.stdout).strip()}")
    else:
        line = " ".join(f"'{c}'" for c in cmd)
        listed = _run(["crontab", "-l"])
        current = listed.stdout if listed.returncode == 0 else ""
        kept = "".join(l + "\n" for l in current.splitlines() if "ytdl-subscriptions" not in l)
        entry = f"0 * * * * {line} # ytdl-subscriptions\n"
        result = subprocess.run(["crontab", "-"], input=kept + entry, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"crontab failed: {result.stderr.strip()}")


def remove_schedule():
    if sys.platform == "darwin":
        _run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"])
        _agent_path().unlink(missing_ok=True)
    elif sys.platform == "win32":
        _run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME])
    else:
        current = _run(["crontab", "-l"])
        if current.returncode == 0:
            kept = "".join(l + "\n" for l in current.stdout.splitlines() if "ytdl-subscriptions" not in l)
            subprocess.run(["crontab", "-"], input=kept, capture_output=True, text=True)


def schedule_installed():
    if sys.platform == "darwin":
        return _agent_path().exists()
    if sys.platform == "win32":
        return _run(["schtasks", "/Query", "/TN", TASK_NAME]).returncode == 0
    return "ytdl-subscriptions" in _run(["crontab", "-l"]).stdout


def schedule_is_stale():
    """True if the scheduled job points at a different copy of ytdl than this one (e.g. the app was moved)."""
    if not schedule_installed():
        return False
    if sys.platform == "darwin":
        try:
            return plistlib.loads(_agent_path().read_bytes()).get("ProgramArguments") != check_command()
        except Exception:
            return True
    return False


# ---- command line --------------------------------------------------------------

def describe(sub):
    when = time.strftime("%b %d %H:%M", time.localtime(sub["last_checked"])) if sub["last_checked"] else "never"
    state = "on" if sub["enabled"] else "paused"
    return f"{sub['id']}  {sub['name']}  [{state}, last checked {when}]"


def cli(args, options):
    """Handle the subscription flags of ytdl's command line. Returns an exit code, or None if no flag was given."""
    if args.check_subscriptions:
        saved = check_due(log=print)
        print(f"Done. {saved} new video(s) saved.")
        return 0
    if args.subscriptions:
        subs = load()["subs"]
        print("\n".join(describe(s) for s in subs) or "No subscriptions yet. Use --subscribe URL.")
        return 0
    if args.unsubscribe:
        unfollow(args.unsubscribe)
        print("Unfollowed.")
        return 0
    if args.subscribe:
        sub, first = follow(args.subscribe, options, args.backfill)
        print(f"Following {sub['name']} ({len(sub['seen'])} existing videos marked as seen).")
        with Lock() as got:
            for entry in first if got else []:
                files = download_new(sub, entry)
                if files:
                    add_recent(sub["name"], entry["title"], files)
        return 0
    if args.schedule:
        if args.schedule == "install":
            install_schedule()
            print("Background checks are on: ytdl will look for new uploads every hour, even when closed.")
        elif args.schedule == "remove":
            remove_schedule()
            print("Background checks are off.")
        else:
            print("on" if schedule_installed() else "off")
        return 0
    return None
