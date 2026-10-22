"""Reddit picture posts: a single image, a GIF, or a gallery of several.

yt-dlp only knows Reddit videos, so for a link to a picture post ytdl reads the post's public data itself
and saves the original image files. Video posts, and anything that can't be read, are left to yt-dlp.
Nothing is logged in. Reddit sometimes refuses anonymous requests; the error then says so.
"""
import html as htmllib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import threads

POST = re.compile(r"^https?://(?:[\w-]+\.)?reddit\.com/(?:r|user|u)/[\w-]+/comments/(\w+)", re.I)
BARE = re.compile(r"^https?://(?:[\w-]+\.)?reddit\.com/comments/(\w+)", re.I)
SHORT = re.compile(r"^https?://redd\.it/(\w+)", re.I)
SHARE = re.compile(r"^https?://(?:[\w-]+\.)?reddit\.com/r/[\w-]+/s/\w+", re.I)
IMAGE_EXT = re.compile(r"\.(jpe?g|png|gif|webp)(?:\?|$)", re.I)
IMAGE_HOSTS = ("i.redd.it", "i.imgur.com", "preview.redd.it")
USER_AGENT = "Mozilla/5.0 (compatible; ytdl; +https://github.com/biswadipb/ytdl)"
MIME_EXT = {"image/jpg": "jpg", "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}


class RedditError(threads.ThreadsError):
    """A Reddit post couldn't be read. The message is written for the user."""


def is_reddit_url(url):
    url = url.strip()
    return any(p.match(url) for p in (POST, BARE, SHORT, SHARE))


def get(url, timeout=20):
    """One HTTP GET. Returns (final_url, bytes). A single place to replace in tests."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read()


def post_data(url):
    """The post's data as a dict, or raises RedditError."""
    url = url.strip()
    if SHARE.match(url):                        # share links redirect to the real post
        try:
            url, _ = get(url)
        except (urllib.error.URLError, OSError):
            raise RedditError("Couldn't open that Reddit link. Check your connection.") from None
    m = POST.match(url) or BARE.match(url) or SHORT.match(url)
    if not m:
        raise RedditError("That doesn't look like a Reddit post link.")
    post_id = m.group(1)
    blocked = False
    for host in ("www.reddit.com", "old.reddit.com"):
        try:
            _, body = get(f"https://{host}/comments/{post_id}.json?raw_json=1")
            return json.loads(body)[0]["data"]["children"][0]["data"]
        except urllib.error.HTTPError as e:
            blocked = blocked or e.code in (401, 403, 429)
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
            pass
    raise RedditError("Reddit wouldn't let ytdl read that post" + (" (it is blocking anonymous requests)." if blocked
                      else ". Check your connection and try again."))


def image_urls(post):
    """[(url choices, extension)] for a picture post. [] when the post is a video or has no picture."""
    for parent in post.get("crosspost_parent_list") or []:
        return image_urls(parent)
    if post.get("is_video") or "video" in str(post.get("post_hint", "")) or \
            (post.get("media") or {}).get("reddit_video"):
        return []
    found = []
    if post.get("is_gallery"):
        meta = post.get("media_metadata") or {}
        for item in (post.get("gallery_data") or {}).get("items", []):
            m = meta.get(item.get("media_id"), {})
            if m.get("status") not in (None, "valid"):
                continue
            mid, ext = item.get("media_id"), MIME_EXT.get(m.get("m", ""), "")
            if m.get("e") == "AnimatedImage" and (m.get("s") or {}).get("gif"):
                found.append(([htmllib.unescape(m["s"]["gif"])], "gif"))
            elif m.get("e") == "Image" and mid and ext:
                choices = [f"https://i.redd.it/{mid}.{ext}"]
                if (m.get("s") or {}).get("u"):
                    choices.append(htmllib.unescape(m["s"]["u"]))
                found.append((choices, ext))
        return found
    link = htmllib.unescape(post.get("url_overridden_by_dest") or post.get("url") or "")
    host = re.sub(r"^https?://([^/]+)/.*$", r"\1", link).lower()
    ext = IMAGE_EXT.search(link)
    if ext and host in IMAGE_HOSTS:
        return [([link], ext.group(1).lower().replace("jpeg", "jpg"))]
    return []


def safe_name(text, limit=100):
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", text or "").strip(" .")
    return text[:limit].rstrip(" .") or "reddit"


def save(choices, dest, report):
    """Downloads the first choice that works to `dest`. Calls report(done, total) as bytes arrive."""
    last = None
    for url in choices:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                total, done = int(r.headers.get("Content-Length") or 0), 0
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    report(done, total)
            return
        except (urllib.error.URLError, OSError) as e:
            last = e
            Path(dest).unlink(missing_ok=True)
    raise RedditError(f"Couldn't download the picture ({last}).")


def download(url, output, hooks=(), audio=False):
    """Saves a Reddit post's pictures into `output`. Returns the file paths, or None if it isn't a picture post.

    Progress goes to `hooks` in yt-dlp's format. A hook raising stops the download (that is how Cancel works).
    """
    post = post_data(url)
    images = image_urls(post)
    if not images:
        return None
    if audio:
        raise RedditError("That post is a picture, so there is no audio to save. Choose Video to save the picture.")
    folder = Path(output).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{safe_name(post.get('title'))} [{post.get('id') or 'reddit'}]"
    files = []
    for i, (choices, ext) in enumerate(images, 1):
        name = f"{base}.{ext}" if len(images) == 1 else f"{base} ({i} of {len(images)}).{ext}"
        dest = folder / name
        info = {"title": post.get("title") or base, "requested_formats": [0] * len(images)}

        def report(done, total, status="downloading", dest=dest, info=info):
            for hook in hooks:
                hook({"status": status, "filename": str(dest), "downloaded_bytes": done,
                      "total_bytes": total or None, "info_dict": info})
        report(0, 0)
        save(choices, dest, report)
        size = dest.stat().st_size
        report(size, size, "finished")
        files.append(str(dest))
    return files
