#!/usr/bin/env python3
"""ytdl core + command-line interface, built on yt-dlp.

Downloads from YouTube, Instagram, X/Twitter, Facebook and other sites yt-dlp supports.
Runs entirely on your machine. Used by the GUI (gui.py) and directly:

    python ytdl.py URL [-F mp4|mkv|webm|mp3|m4a|opus|wav|flac] [-q 720] [-o FOLDER]
                       [-p] [-s en] [-b chrome] [--info] [-f urls.txt]
"""
import argparse
import shutil
import sys
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    sys.exit("yt-dlp is not installed. Run: pip install -r requirements.txt")

QUALITIES = ["best", "2160", "1440", "1080", "720", "480", "360"]
VIDEO_FORMATS = ["mp4", "mkv", "webm"]
AUDIO_FORMATS = ["mp3", "m4a", "opus", "wav", "flac"]
FORMATS = VIDEO_FORMATS + AUDIO_FORMATS
BROWSERS = ["chrome", "firefox", "safari", "edge", "brave"]


def find_ffmpeg():
    """System ffmpeg if present, else the static binary shipped by imageio-ffmpeg."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def default_folder():
    return str(Path.home() / "Downloads" / "ytdl")


def build_options(output, fmt="mp4", quality="best", playlist=False, subs=None,
                  browser=None, hooks=(), quiet=False):
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format: {fmt}")
    ffmpeg = find_ffmpeg()
    opts = {
        "outtmpl": str(Path(output).expanduser() / "%(title).150B [%(id)s].%(ext)s"),
        "noplaylist": not playlist,
        "windowsfilenames": True,
        "continuedl": True,
        "retries": 5,
        "quiet": quiet,
        "noprogress": quiet,
        "no_warnings": True,
        "progress_hooks": list(hooks),
    }
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    if fmt in AUDIO_FORMATS:
        # Suffix avoids clobbering a same-named video (audio extraction deletes its source file).
        opts["outtmpl"] = str(Path(output).expanduser() / "%(title).150B [%(id)s] (audio).%(ext)s")
        if not ffmpeg:
            raise RuntimeError("Audio extraction needs ffmpeg (pip install imageio-ffmpeg).")
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": fmt,
            "preferredquality": "192" if fmt in ("mp3", "m4a") else None,
        }]
    else:
        height = f"[height<={quality}]" if quality != "best" else ""
        if ffmpeg:
            opts["format"] = f"bv*{height}+ba/b{height}"
            opts["merge_output_format"] = fmt
            # Single-file sources (Instagram, X, ...) are not merged, so convert them too.
            key = "FFmpegVideoConvertor" if fmt == "webm" else "FFmpegVideoRemuxer"
            opts["postprocessors"] = [{"key": key, "preferedformat": fmt}]
        else:
            opts["format"] = f"b{height}"
    if subs:
        opts.update(writesubtitles=True, writeautomaticsub=True, subtitleslangs=[subs])
    return opts


def video_info(url, browser=None):
    opts = {"quiet": True, "no_warnings": True}
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False, process=False)
    heights = sorted({f["height"] for f in info.get("formats", []) if f.get("height")})
    return {
        "title": info.get("title"),
        "channel": info.get("uploader"),
        "duration": int(info.get("duration") or 0),
        "heights": heights,
    }


def download(urls, **kwargs):
    """Download each URL. Returns a list of (url, error_message) for failures."""
    Path(kwargs["output"]).expanduser().mkdir(parents=True, exist_ok=True)
    failures = []
    with yt_dlp.YoutubeDL(build_options(**kwargs)) as ydl:
        for url in urls:
            try:
                ydl.download([url])
            except yt_dlp.utils.DownloadError as e:
                failures.append((url, str(e)))
    return failures


def read_urls(args):
    urls = list(args.urls)
    if args.file:
        for line in Path(args.file).expanduser().read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def cli(argv):
    p = argparse.ArgumentParser(prog="ytdl", description="Download YouTube videos locally.")
    p.add_argument("urls", nargs="*", help="links to videos or posts (YouTube, Instagram, X/Twitter, Facebook, ...)")
    p.add_argument("-f", "--file", help="text file with one URL per line")
    p.add_argument("-o", "--output", default=default_folder(),
                   help="output folder (default: ~/Downloads/ytdl)")
    p.add_argument("-q", "--quality", default="best", choices=QUALITIES,
                   help="max video height (default: best)")
    p.add_argument("-F", "--format", default="mp4", choices=FORMATS,
                   help="video: mp4 mkv webm | audio only: mp3 m4a opus wav flac (default: mp4)")
    p.add_argument("-a", "--audio", action="store_true", help="shortcut for -F mp3")
    p.add_argument("-p", "--playlist", action="store_true",
                   help="download everything in a playlist or multi-video post")
    p.add_argument("-b", "--browser", choices=BROWSERS,
                   help="use your login from this browser (for private/age-gated/login-only posts)")
    p.add_argument("-s", "--subs", metavar="LANG", help="also fetch subtitles, e.g. en")
    p.add_argument("--info", action="store_true", help="show video details and exit")
    args = p.parse_args(argv)

    urls = read_urls(args)
    if not urls:
        p.error("give at least one URL or --file")

    if args.info:
        for url in urls:
            try:
                i = video_info(url, args.browser)
            except yt_dlp.utils.DownloadError as e:
                sys.exit(f"failed: {url}\n  {e}")
            m, s = divmod(i["duration"], 60)
            print(f"Title:     {i['title']}\nChannel:   {i['channel']}\nDuration:  {m}:{s:02d}")
            print(f"Qualities: {', '.join(f'{h}p' for h in i['heights']) or 'unknown'}")
        return 0

    try:
        failures = download(urls, output=args.output, fmt="mp3" if args.audio else args.format,
                            quality=args.quality, playlist=args.playlist, subs=args.subs,
                            browser=args.browser)
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
