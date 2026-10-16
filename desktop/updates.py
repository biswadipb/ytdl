"""Tells you when a newer ytdl release exists on GitHub (it never installs anything by itself)."""
import json
import re
import urllib.request

REPO = "biswadipb/ytdl"


def parse_version(text):
    """'v2.1.0' -> (2, 1, 0); anything without digits (like 'dev') -> None."""
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3])) if nums else None


def is_newer(current, latest):
    c, l = parse_version(current), parse_version(latest)
    return c is not None and l is not None and l > c


def check(current, timeout=10):
    """{'version': '2.2.0', 'url': release page} when a newer release exists, else None."""
    if parse_version(current) is None:
        return None  # running from source
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"User-Agent": "ytdl-update-check", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    tag = data.get("tag_name", "")
    if is_newer(current, tag):
        return {"version": tag.lstrip("v"), "url": data.get("html_url", f"https://github.com/{REPO}/releases/latest")}
    return None
