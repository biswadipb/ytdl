"""Disk-space controls for downloads made by subscriptions.

ytdl only ever deletes files it downloaded for a subscription and recorded here. Anything else in your
folders, including videos you downloaded yourself, is never touched.
"""
import os
import shutil
import time
from pathlib import Path

import subscriptions

DEFAULTS = {"keep_days": 0, "max_gb": 0, "min_free_gb": 1}   # 0 = no limit / off
KEEP_CHOICES = [0, 7, 30, 90]
MAX_CHOICES = [0, 5, 10, 20, 50, 100]
FREE_CHOICES = [0, 1, 2, 5]
GB = 1024 ** 3


def settings():
    return {**DEFAULTS, **subscriptions.load().get("storage", {})}


def set_setting(key, value):
    data = subscriptions.load()
    data.setdefault("storage", {})[key] = value
    subscriptions.save(data)


def free_bytes(path):
    """Free space on the disk holding `path` (which may not exist yet)."""
    p = Path(path).expanduser()
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def low_space(path, min_free_gb=None):
    """(is_low, free_bytes). Never low when the warning is switched off."""
    limit = settings()["min_free_gb"] if min_free_gb is None else min_free_gb
    free = free_bytes(path)
    return (limit > 0 and free < limit * GB), free


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def plan_cleanup(files, keep_days, max_gb, now=None):
    """Which recorded files to delete: ones older than keep_days, then the oldest until the total fits max_gb."""
    now = now or time.time()
    doomed, kept = [], []
    for f in files:
        (doomed if keep_days and now - f["time"] > keep_days * 86400 else kept).append(f)
    if max_gb:
        kept.sort(key=lambda f: f["time"])           # oldest first
        total = sum(f["size"] for f in kept)
        while kept and total > max_gb * GB:
            victim = kept.pop(0)
            doomed.append(victim)
            total -= victim["size"]
    return doomed


def pending(now=None):
    s = settings()
    return plan_cleanup(subscriptions.load().get("files", []), s["keep_days"], s["max_gb"], now)


def cleanup(dry_run=False, now=None):
    """Delete the files the settings call for. Returns (count, bytes_freed)."""
    doomed = pending(now)
    if dry_run:
        return len(doomed), sum(f["size"] for f in doomed if os.path.exists(f["path"]))
    count = freed = 0
    for f in doomed:
        try:
            size = os.path.getsize(f["path"])
            os.remove(f["path"])
            count += 1
            freed += size
        except FileNotFoundError:
            pass            # already gone: just forget it
        except OSError:
            continue        # in use or protected: keep the record and try later
    gone = {f["path"] for f in doomed if not os.path.exists(f["path"])}
    data = subscriptions.load()
    data["files"] = [f for f in data.get("files", []) if f["path"] not in gone]
    subscriptions.save(data)
    return count, freed
