"""Threads video support.

yt-dlp has no Threads extractor, and Threads only reveals a post's video files after its JavaScript
has run. So ytdl asks a Chrome-family browser that is already installed (Chrome, Edge, Brave or
Chromium) to load the post in the background, reads the video links out of the finished page, and
then downloads them like any other file. Nothing is logged in or installed.
"""
import html as htmllib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

POST_URL = re.compile(r"^https?://(?:www\.)?threads\.(?:net|com)/@([\w.]+)/post/([\w-]+)", re.I)
SHORT_URL = re.compile(r"^https?://(?:www\.)?threads\.(?:net|com)/t/([\w-]+)", re.I)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
             "track", "wbr"}


class ThreadsError(Exception):
    """Threads video couldn't be read. The message is written for the user."""


def is_threads_url(url):
    return bool(POST_URL.match(url.strip()) or SHORT_URL.match(url.strip()))


def find_browser():
    """Path to an installed Chrome-family browser, or None. YTDL_BROWSER overrides the search."""
    override = os.environ.get("YTDL_BROWSER")
    if override and Path(override).exists():
        return override
    candidates = []
    if sys.platform == "darwin":
        for app, binary in [("Google Chrome", "Google Chrome"), ("Microsoft Edge", "Microsoft Edge"),
                            ("Brave Browser", "Brave Browser"), ("Chromium", "Chromium")]:
            candidates.append(f"/Applications/{app}.app/Contents/MacOS/{binary}")
            candidates.append(str(Path.home() / f"Applications/{app}.app/Contents/MacOS/{binary}"))
    elif sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for root in filter(None, roots):
            for rel in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe",
                        r"BraveSoftware\Brave-Browser\Application\brave.exe", r"Chromium\Application\chrome.exe"):
                candidates.append(os.path.join(root, rel))
    for path in candidates:
        if Path(path).exists():
            return path
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def render(url, browser=None, timeout=90):
    """The page after its JavaScript has run, as HTML."""
    browser = browser or find_browser()
    if not browser:
        raise ThreadsError("Threads videos need Google Chrome, Microsoft Edge, Brave or Chromium installed "
                           "(ytdl uses it in the background to read the post).")
    last = None
    for attempt in range(2):  # the first load occasionally stalls; a second try almost always works
        profile = tempfile.mkdtemp(prefix="ytdl-browser-")
        try:
            result = subprocess.run(
                [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                 "--mute-audio", f"--user-data-dir={profile}", "--virtual-time-budget=12000", "--dump-dom", url],
                capture_output=True, timeout=timeout,
                creationflags=0x08000000 if sys.platform == "win32" else 0)  # no console window on Windows
            page = result.stdout.decode("utf-8", errors="replace")
            if len(page) >= 2000:
                return page
            last = ThreadsError("Couldn't load the Threads post (is the link correct and public?).")
        except subprocess.TimeoutExpired:
            last = ThreadsError("The browser took too long to load the Threads post.")
        finally:
            shutil.rmtree(profile, ignore_errors=True)
    raise last


class _PostReader(HTMLParser):
    """Collects the videos inside the first post container, which is the post the link points to.

    Replies and suggested posts further down the page have their own containers and are ignored.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.post_depth = None   # depth at which the main post's container opened
        self.post_done = False
        self.videos = []
        self.title = None
        self.in_title = False
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and a.get("property"):
            self.meta[a["property"]] = a.get("content", "")
        if tag not in VOID_TAGS:
            self.depth += 1
        if tag == "div" and a.get("data-pressable-container") == "true" and self.post_depth is None:
            self.post_depth = self.depth
        if self.post_depth is not None and not self.post_done and tag in ("video", "source"):
            src = a.get("src") or ""
            if src.startswith("http") and src not in self.videos:
                self.videos.append(src)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in VOID_TAGS:
            return
        if self.post_depth is not None and self.depth == self.post_depth:
            self.post_done = True
        self.depth -= 1

    def handle_data(self, data):
        if self.in_title and self.title is None and data.strip():
            self.title = data.strip()


def parse(page):
    """(video links, caption, thumbnail) from a rendered Threads page."""
    reader = _PostReader()
    reader.feed(page)
    caption = reader.meta.get("og:description") or reader.title or ""
    return reader.videos, htmllib.unescape(caption).strip(), reader.meta.get("og:image")


def extract(url, playlist=False, browser=None):
    """An info dict that yt-dlp can download. Every video of a multi-video post, or only the first."""
    url = url.strip()
    if SHORT_URL.match(url):  # share links like threads.com/t/CODE redirect to the full post address
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
                url = r.geturl()
        except Exception:
            pass
    match = POST_URL.match(url)
    if not match:
        raise ThreadsError("Open the post in your browser and copy its full link (it looks like "
                           "threads.com/@name/post/...).")
    user, code = match.group(1), match.group(2)
    videos, caption, thumbnail = parse(render(url, browser))
    if not videos:
        raise ThreadsError("No video found in that Threads post. It may only have pictures or text, "
                           "or it may not be public.")
    title = (caption[:80] or f"Threads post {code}").replace("\n", " ")
    chosen = videos if playlist else videos[:1]

    def entry(i, link):
        suffix = f" ({i + 1}-of-{len(videos)})" if len(videos) > 1 else ""
        return {"id": code if len(videos) == 1 else f"{code}-{i + 1}", "title": title + suffix, "url": link,
                "ext": "mp4", "uploader": user, "channel": user, "preview_thumbnail": thumbnail,
                "extractor": "threads", "extractor_key": "Threads", "webpage_url": url}

    entries = [entry(i, link) for i, link in enumerate(chosen)]
    if len(entries) == 1:
        return entries[0]
    return {"_type": "playlist", "id": code, "title": title, "uploader": user, "entries": entries,
            "extractor": "threads", "extractor_key": "Threads", "webpage_url": url}
