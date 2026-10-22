#!/usr/bin/env python3
"""ytdl core + command-line interface, built on yt-dlp.

Downloads from YouTube, Instagram, X/Twitter, Facebook and other sites yt-dlp supports.
Runs entirely on your machine. Used by the GUI (gui.py) and directly:

    python ytdl.py URL [-F mp4|mkv|webm|mp3|m4a|opus|wav|flac] [-q 720] [-o FOLDER]
                       [-c 1:30-2:45] [-p] [-s en [--embed-subs]] [-b chrome | --cookies cookies.txt]
                       [--naming title-id|title|channel-title|date-title]
                       [--folders flat|channel|site|site-channel] [--limit-rate 1M] [--retry N]
                       [--no-extras] [--info] [-f urls.txt] [--update-engine]

    Channel subscriptions (new uploads download automatically):
    ytdl.py --subscribe CHANNEL_URL [--backfill 3] [format options]    follow a channel or playlist
    ytdl.py --subscriptions | --unsubscribe ID | --check-subscriptions
    ytdl.py --schedule install|remove|status                         check every hour, even when closed
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import reddit_images
import threads
import time
import urllib.request
import zipfile
from pathlib import Path

# yt-dlp breaks whenever a site changes, so a newer copy downloaded into this folder
# takes priority over the one bundled with the app (see update_engine below).
ENGINE_DIR = Path.home() / ".ytdl" / "engine"


def _import_ytdl():
    global yt_dlp
    if (ENGINE_DIR / "yt_dlp" / "__init__.py").exists():
        sys.path.insert(0, str(ENGINE_DIR))
        try:
            import yt_dlp
            return
        except Exception:  # broken download: fall back to the bundled copy
            sys.path.remove(str(ENGINE_DIR))
            for name in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
                del sys.modules[name]
    import yt_dlp


class _Engine:
    """Stands in for the yt_dlp module until it is first used.

    Importing yt-dlp takes a quarter of a second or more, so the windows open first and it loads in the
    background (see warm). Anything that needs it before then simply waits for the import to finish.
    """

    def __getattr__(self, name):
        try:
            _import_ytdl()
        except ImportError:
            sys.exit("yt-dlp is not installed. Run: pip install -r requirements.txt")
        return getattr(globals()["yt_dlp"], name)


yt_dlp = _Engine()


def warm():
    """Loads yt-dlp and ffmpeg's location ahead of time. Call from a background thread after the window shows."""
    try:
        yt_dlp.version
        find_ffmpeg()
    except Exception:
        pass

QUALITIES = ["best", "2160", "1440", "1080", "720", "480", "360"]
VIDEO_FORMATS = ["mp4", "mkv", "webm"]
AUDIO_FORMATS = ["mp3", "m4a", "opus", "wav", "flac"]
FORMATS = VIDEO_FORMATS + AUDIO_FORMATS
BROWSERS = ["chrome", "firefox", "safari", "edge", "brave"]
SUB_LANGS = ["en", "es", "fr", "de", "pt", "it", "ru", "ja", "ko", "zh", "ar", "hi", "bn", "tr", "nl", "pl", "id"]
NAMING = {  # key: (label, yt-dlp template without extension)
    "title-id": ("Title [id]", "%(title).150B [%(id)s]"),
    "title": ("Title only", "%(title).150B"),
    "channel-title": ("Channel - Title", "%(uploader,channel|Unknown)s - %(title).120B"),
    "date-title": ("Date - Title", "%(upload_date>%Y-%m-%d|undated)s - %(title).120B"),
}
FOLDER_RULES = {  # key: (label, sub-folder template)
    "flat": ("One folder", ""),
    "channel": ("Folder per channel", "%(uploader,channel|Unknown)s/"),
    "site": ("Folder per site", "%(extractor_key)s/"),
    "site-channel": ("Site, then channel", "%(extractor_key)s/%(uploader,channel|Unknown)s/"),
}
SPEEDS = {"Unlimited": None, "500 KB/s": 500_000, "1 MB/s": 1_000_000, "2 MB/s": 2_000_000,
          "5 MB/s": 5_000_000, "10 MB/s": 10_000_000}
# Errors that retrying can't fix.
PERMANENT_ERRORS = ("unsupported url", "private", "sign in", "log in", "login", "not available", "unavailable",
                    "removed", "copyright", "age-restricted", "members-only", "no video could be found",
                    "requested format", "does not exist", "not a valid url", "ffmpeg", "no video found",
                    "google chrome", "geo-restricted")
THUMBNAIL_FORMATS = {"mp3", "m4a", "opus", "flac", "mp4", "mkv"}  # containers that can hold cover art
SITE_PATTERN = re.compile(
    r"https?://([\w-]+\.)*(youtube\.com|youtu\.be|instagram\.com|x\.com|twitter\.com|"
    r"facebook\.com|fb\.watch|threads\.(net|com)|dailymotion\.com|dai\.ly|tiktok\.com|reddit\.com|redd\.it|vimeo\.com|twitch\.tv|soundcloud\.com)/\S+", re.I)


class Cancelled(Exception):
    """Raised from a progress hook to stop a download."""


def find_ffmpeg():
    """System ffmpeg if present, else the static binary shipped by imageio-ffmpeg.

    yt-dlp only recognises a binary literally named "ffmpeg" on PATH for some features
    (clipping), so the bundled one is exposed under that name in ~/.ytdl/bin.
    """
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None
    bindir = Path.home() / ".ytdl" / "bin"
    link = bindir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    try:
        if not link.exists() or (link.is_symlink() and link.resolve() != exe.resolve()) \
                or (not link.is_symlink() and link.stat().st_size != exe.stat().st_size):
            bindir.mkdir(parents=True, exist_ok=True)
            link.unlink(missing_ok=True)
            try:
                link.symlink_to(exe)
            except OSError:  # Windows without symlink rights
                shutil.copy2(exe, link)
        os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")
        return str(link)
    except OSError:
        return str(exe)


def default_folder():
    return str(Path.home() / "Downloads" / "ytdl")


def parse_time(text):
    """'90', '1:30' or '1:02:03' -> seconds (float). Empty -> None."""
    text = (text or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(f"Bad time: {text}")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + float(p)
    return seconds


def parse_clip(text):
    """'1:30-2:45' -> (90.0, 165.0); '1:30-' -> (90.0, None); empty -> None."""
    text = (text or "").strip()
    if not text:
        return None
    if "-" not in text:
        raise ValueError("Clip looks like 1:30-2:45")
    start, end = text.split("-", 1)
    return parse_time(start) or 0.0, parse_time(end)


def _label(seconds):
    return "" if seconds is None else f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


def label_for(key, table):
    return table[key][0]


def key_for_label(label, table, default):
    return next((k for k, v in table.items() if v[0] == label), default)


def is_transient(message):
    """True when an error is worth retrying (network hiccup, rate limit, server error)."""
    m = message.lower()
    return not any(p in m for p in PERMANENT_ERRORS)


def build_options(output, fmt="mp4", quality="best", playlist=False, sub_lang=None, sub_embed=False,
                  browser=None, cookies_file=None, clip=None, extras=True, naming="title-id",
                  folders="flat", ratelimit=None, hooks=(), quiet=False):
    """clip: (start, end) seconds or None. extras: embed cover art and tags.

    ratelimit: bytes per second or None. sub_lang: subtitle language code or None.
    """
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format: {fmt}")
    ffmpeg = find_ffmpeg()
    name = NAMING[naming][1]
    if clip:
        name += f" [clip {_label(clip[0])}-{_label(clip[1]) or 'end'}]"
    if fmt in AUDIO_FORMATS:
        # Suffix avoids clobbering a same-named video (audio extraction deletes its source file).
        name += " (audio)"
    opts = {
        "outtmpl": str(Path(output).expanduser() / (FOLDER_RULES[folders][1] + name + ".%(ext)s")),
        "noplaylist": not playlist,
        "windowsfilenames": True,
        "continuedl": True,
        "retries": 5,
        "quiet": quiet,
        "noprogress": quiet,
        "no_warnings": True,
        "progress_hooks": list(hooks),
    }
    if ratelimit:
        opts["ratelimit"] = ratelimit
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if cookies_file:
        opts["cookiefile"] = str(Path(cookies_file).expanduser())
    elif browser:
        opts["cookiesfrombrowser"] = (browser,)
    if clip:
        opts["download_ranges"] = yt_dlp.utils.download_range_func(
            None, [(clip[0], clip[1] if clip[1] is not None else float("inf"))])
        opts["force_keyframes_at_cuts"] = True

    post = []
    if fmt in AUDIO_FORMATS:
        if not ffmpeg:
            raise RuntimeError("Audio extraction needs ffmpeg (pip install imageio-ffmpeg).")
        opts["format"] = "bestaudio/best"
        post.append({"key": "FFmpegExtractAudio", "preferredcodec": fmt,
                     "preferredquality": "192" if fmt in ("mp3", "m4a") else None})
    else:
        height = f"[height<={quality}]" if quality != "best" else ""
        if ffmpeg:
            opts["format"] = f"bv*{height}+ba/b{height}"
            opts["merge_output_format"] = fmt
            # Single-file sources (Instagram, X, ...) are not merged, so convert them too.
            key = "FFmpegVideoConvertor" if fmt == "webm" else "FFmpegVideoRemuxer"
            post.append({"key": key, "preferedformat": fmt})
        else:
            opts["format"] = f"b{height}"
    if extras and ffmpeg:
        post.append({"key": "FFmpegMetadata", "add_metadata": True})
        if fmt in THUMBNAIL_FORMATS:
            opts["writethumbnail"] = True
            post.insert(0, {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
            post.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    if sub_lang and fmt in VIDEO_FORMATS:
        opts.update(writesubtitles=True, writeautomaticsub=True, subtitleslangs=[sub_lang],
                    subtitlesformat="srt/best")
        post.insert(0, {"key": "FFmpegSubtitlesConvertor", "format": "srt", "when": "before_dl"})
    if post:
        opts["postprocessors"] = post
    return opts


def _auth(opts, browser, cookies_file):
    if cookies_file:
        opts["cookiefile"] = str(Path(cookies_file).expanduser())
    elif browser:
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def video_info(url, browser=None, cookies_file=None):
    """Details for a link without downloading it."""
    if threads.is_threads_url(url):
        info = threads.extract(url, playlist=True)
        first = (info.get("entries") or [info])[0]
        return {"title": info["title"], "channel": info["uploader"], "duration": 0, "heights": [],
                "thumbnail": first.get("preview_thumbnail")}
    opts = _auth({"quiet": True, "no_warnings": True, "noplaylist": True}, browser, cookies_file)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False, process=False)
    if info.get("_type") == "playlist":
        entries = list(info.get("entries") or [])
        first = entries[0] if entries else {}
        return {"title": f"{info.get('title')} ({len(entries)} videos)", "channel": info.get("uploader"),
                "duration": 0, "heights": [], "thumbnail": first.get("thumbnail") or info.get("thumbnail")}
    heights = sorted({f["height"] for f in info.get("formats", []) if f.get("height")})
    return {
        "title": info.get("title"),
        "channel": info.get("uploader"),
        "duration": int(info.get("duration") or 0),
        "heights": heights,
        "thumbnail": info.get("thumbnail"),
    }


def playlist_entries(url, browser=None, cookies_file=None):
    """Videos inside a playlist/post as [{title, url, duration}], or [] when the link is a single video."""
    opts = _auth({"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}, browser, cookies_file)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") != "playlist":
        return []
    out = []
    for e in info.get("entries") or []:
        link = (e or {}).get("url") or (e or {}).get("webpage_url")
        if link and link.startswith("http"):
            out.append({"title": e.get("title") or link, "url": link, "duration": int(e.get("duration") or 0)})
    return out


def _final_files(info):
    files = []
    for entry in info.get("entries") or [info]:
        for d in (entry or {}).get("requested_downloads") or []:
            if d.get("filepath"):
                files.append(d["filepath"])
    return files


SUBTITLE_CODEC = {"mp4": "mov_text", "mkv": "srt", "webm": "webvtt"}


def embed_subtitles(video, fmt):
    """Mux a downloaded .srt next to `video` into it, then delete the .srt.

    Done with ffmpeg directly because yt-dlp's own embedder needs ffprobe, which isn't bundled.
    """
    video = Path(video)
    srts = sorted(video.parent.glob(glob_escape(video.stem) + ".*.srt"))
    ffmpeg = find_ffmpeg()
    if not srts or not ffmpeg or fmt not in SUBTITLE_CODEC:
        return
    tmp = video.with_name(video.stem + ".embedding" + video.suffix)
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-i", str(srts[0]),
           "-map", "0", "-map", "1", "-c", "copy", "-c:s", SUBTITLE_CODEC[fmt], str(tmp)]
    flags = 0x08000000 if sys.platform == "win32" else 0  # no console window flash
    result = subprocess.run(cmd, capture_output=True, creationflags=flags)
    if result.returncode == 0:
        tmp.replace(video)
        srts[0].unlink()
    else:
        tmp.unlink(missing_ok=True)  # keep the separate .srt rather than failing the download


def glob_escape(text):
    return re.sub(r"([\[\]*?])", r"[\1]", text)


class Progress:
    """Turns yt-dlp's per-file progress reports into one number for the whole download.

    yt-dlp reports video and audio separately (each 0 to 100%), and sizes it only estimates keep changing,
    which makes a naive percentage jump back and forth. This adds the files up, treats the ones it hasn't met
    yet as average-sized, never goes backwards, and holds at 99% until the download is truly finished.
    """

    def __init__(self):
        self.files = {}      # filename -> (bytes done, bytes total)
        self.expected = 1    # how many files this download is made of (video + audio = 2)
        self.value = 0.0

    def update(self, d):
        """Feed one yt-dlp progress report. Returns the overall fraction, 0..0.99."""
        info = d.get("info_dict") or {}
        self.expected = max(self.expected, len(info.get("requested_formats") or []), 1)
        key = d.get("filename") or d.get("tmpfilename") or "?"
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        done = d.get("downloaded_bytes") or 0
        count, index = d.get("fragment_count"), d.get("fragment_index")
        if not total and count and index is not None:     # fragmented streams: count pieces instead of bytes
            total, done = 1000, 1000 * index / count
        if d.get("status") == "finished":
            done = total = max(total, done, 1)
        if total:
            self.files[key] = (min(done, total), total)
        if not self.files:
            return self.value
        known = sum(t for _, t in self.files.values())
        average = known / len(self.files)
        everything = known + max(0, self.expected - len(self.files)) * average
        fraction = min(0.99, sum(x for x, _ in self.files.values()) / everything) if everything else 0.0
        self.value = max(self.value, fraction)
        return self.value


def download_one(url, **kwargs):
    """Download one link. Returns the saved file paths; raises DownloadError or Cancelled."""
    Path(kwargs["output"]).expanduser().mkdir(parents=True, exist_ok=True)
    if reddit_images.is_reddit_url(url):       # picture posts; videos (and anything unreadable) go on to yt-dlp
        try:
            files = reddit_images.download(url, kwargs["output"], hooks=kwargs.get("hooks", ()),
                                           audio=kwargs.get("fmt", "mp4") in AUDIO_FORMATS)
        except reddit_images.RedditError as e:
            if "picture" in str(e) or "download the picture" in str(e):
                raise
            files = None                       # couldn't read the post: let yt-dlp try (it handles videos)
        if files:
            return files
    with yt_dlp.YoutubeDL(build_options(**kwargs)) as ydl:
        try:
            if threads.is_threads_url(url):  # yt-dlp can't read Threads, so ytdl finds the video links itself
                files = _final_files(ydl.process_ie_result(
                    threads.extract(url, playlist=kwargs.get("playlist", False)), download=True))
            else:
                files = _final_files(ydl.extract_info(url, download=True))
        except yt_dlp.utils.DownloadError as e:
            if isinstance(e.exc_info[1] if e.exc_info else None, Cancelled):
                raise Cancelled() from e
            raise
    if kwargs.get("sub_lang") and kwargs.get("sub_embed") and kwargs.get("fmt", "mp4") in VIDEO_FORMATS:
        for f in files:
            embed_subtitles(f, kwargs.get("fmt", "mp4"))
    return files


def download(urls, retries=0, **kwargs):
    """Download each URL, retrying temporary failures. Returns a list of (url, error_message)."""
    failures = []
    for url in urls:
        attempt = 0
        while True:
            try:
                download_one(url, **kwargs)
                break
            except yt_dlp.utils.DownloadError as e:
                if attempt < retries and is_transient(str(e)):
                    attempt += 1
                    time.sleep(2 * attempt)
                    continue
                failures.append((url, str(e)))
                break
            except Cancelled:
                failures.append((url, "cancelled"))
                break
            except threads.ThreadsError as e:
                failures.append((url, str(e)))
                break
    return failures


# ---- engine updates ---------------------------------------------------------

def _version_key(v):
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-]", v))


def installed_engine_version():
    try:
        return (ENGINE_DIR / "VERSION").read_text().strip()
    except OSError:
        return None


def engine_version():
    return yt_dlp.version.__version__


def update_engine():
    """Fetch the newest yt-dlp from PyPI. Returns (changed, message).

    A new copy takes effect the next time ytdl starts.
    """
    with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=20) as r:
        data = json.load(r)
    latest = data["info"]["version"]
    have = max([engine_version(), installed_engine_version() or "0"], key=_version_key)
    if _version_key(latest) <= _version_key(have):
        return False, f"Already up to date (yt-dlp {have})."
    wheel = next(u for u in data["urls"] if u["packagetype"] == "bdist_wheel")
    with urllib.request.urlopen(wheel["url"], timeout=120) as r:
        blob = r.read()
    if hashlib.sha256(blob).hexdigest() != wheel["digests"]["sha256"]:
        raise RuntimeError("Download was corrupted (checksum mismatch). Try again.")
    ENGINE_DIR.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=ENGINE_DIR.parent))
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            z.extractall(tmp, [n for n in z.namelist() if n.startswith("yt_dlp/")])
        (tmp / "VERSION").write_text(latest)
        shutil.rmtree(ENGINE_DIR, ignore_errors=True)
        shutil.move(str(tmp), str(ENGINE_DIR))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return True, f"Updated yt-dlp {have} to {latest}. Restart ytdl to use it."


# ---- command line -----------------------------------------------------------

def read_urls(args):
    urls = list(args.urls)
    if args.file:
        for line in Path(args.file).expanduser().read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def cli(argv):
    p = argparse.ArgumentParser(prog="ytdl", description="Download videos and audio locally.")
    p.add_argument("urls", nargs="*", help="links to videos or posts (YouTube, Instagram, X/Twitter, Facebook, ...)")
    p.add_argument("-f", "--file", help="text file with one URL per line")
    p.add_argument("-o", "--output", default=default_folder(),
                   help="output folder (default: ~/Downloads/ytdl)")
    p.add_argument("-q", "--quality", default="best", choices=QUALITIES,
                   help="max video height (default: best)")
    p.add_argument("-F", "--format", default="mp4", choices=FORMATS,
                   help="video: mp4 mkv webm | audio only: mp3 m4a opus wav flac (default: mp4)")
    p.add_argument("-a", "--audio", action="store_true", help="shortcut for -F mp3")
    p.add_argument("-c", "--clip", metavar="START-END", help="save only a section, e.g. 1:30-2:45 or 90-")
    p.add_argument("--no-extras", action="store_true", help="skip embedding cover art and tags")
    p.add_argument("-p", "--playlist", action="store_true",
                   help="download everything in a playlist or multi-video post")
    p.add_argument("-b", "--browser", choices=BROWSERS,
                   help="use your login from this browser (for private/age-gated/login-only posts)")
    p.add_argument("--cookies", metavar="FILE", help="use a cookies.txt file for login-only posts")
    p.add_argument("-s", "--subs", metavar="LANG", help="also fetch subtitles (video only), e.g. en")
    p.add_argument("--embed-subs", action="store_true", help="put subtitles inside the video instead of a .srt file")
    p.add_argument("--naming", default="title-id", choices=list(NAMING), help="file name style")
    p.add_argument("--folders", default="flat", choices=list(FOLDER_RULES), help="how to organize into folders")
    p.add_argument("--limit-rate", metavar="RATE", help="speed limit, e.g. 500K or 2M")
    p.add_argument("--retry", type=int, default=0, metavar="N", help="retry failed downloads up to N times")
    p.add_argument("--info", action="store_true", help="show video details and exit")
    p.add_argument("--update-engine", action="store_true", help="fetch the newest yt-dlp and exit")
    p.add_argument("--subscribe", metavar="URL", help="follow a channel or playlist and download new uploads")
    p.add_argument("--backfill", type=int, default=0, metavar="N", help="with --subscribe: also download the latest N videos now")
    p.add_argument("--subscriptions", action="store_true", help="list followed channels")
    p.add_argument("--unsubscribe", metavar="ID", help="stop following (ID from --subscriptions)")
    p.add_argument("--check-subscriptions", action="store_true", help="download new uploads from followed channels now")
    p.add_argument("--schedule", choices=["install", "remove", "status"],
                   help="run subscription checks every hour in the background, even when ytdl is closed")
    args = p.parse_args(argv)

    if args.update_engine:
        try:
            print(update_engine()[1])
            return 0
        except Exception as e:
            sys.exit(f"Update failed: {e}")

    if args.subscribe or args.subscriptions or args.unsubscribe or args.check_subscriptions or args.schedule:
        import subscriptions
        options = dict(output=args.output, fmt="mp3" if args.audio else args.format, quality=args.quality,
                       naming=args.naming, folders=args.folders, sub_lang=args.subs, sub_embed=args.embed_subs,
                       extras=not args.no_extras, browser=args.browser, cookies_file=args.cookies)
        try:
            return subscriptions.cli(args, options)
        except (ValueError, RuntimeError) as e:
            sys.exit(str(e))

    urls = read_urls(args)
    if not urls:
        p.error("give at least one URL or --file")

    if args.info:
        for url in urls:
            try:
                i = video_info(url, args.browser, args.cookies)
            except (yt_dlp.utils.DownloadError, threads.ThreadsError) as e:
                sys.exit(f"failed: {url}\n  {e}")
            m, s = divmod(i["duration"], 60)
            print(f"Title:     {i['title']}\nChannel:   {i['channel']}\nDuration:  {m}:{s:02d}")
            print(f"Qualities: {', '.join(f'{h}p' for h in i['heights']) or 'unknown'}")
        return 0

    try:
        rate = yt_dlp.utils.parse_bytes(args.limit_rate) if args.limit_rate else None
        failures = download(urls, retries=args.retry, output=args.output,
                            fmt="mp3" if args.audio else args.format,
                            quality=args.quality, playlist=args.playlist, sub_lang=args.subs,
                            sub_embed=args.embed_subs, browser=args.browser, cookies_file=args.cookies,
                            clip=parse_clip(args.clip), extras=not args.no_extras, naming=args.naming,
                            folders=args.folders, ratelimit=rate)
    except (RuntimeError, ValueError) as e:
        sys.exit(str(e))
    for url, err in failures:
        print(f"failed: {url}\n  {err}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(cli(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit("\ninterrupted (partial files resume when you re-run)")
