"""Storage controls: cleanup rules, only-our-files safety, and the low-disk-space guard."""
import os
import time

import pytest

import storage
import subscriptions as subs
from conftest import duration  # noqa: F401  (keeps conftest fixtures importable in this module)

DAY = 86400


def record(path, size, age_days, sub="Chan"):
    return {"sub": sub, "path": str(path), "size": size, "time": time.time() - age_days * DAY}


def make(tmp_path, name, size=100):
    p = tmp_path / name
    p.write_bytes(b"x" * size)
    return p


def test_plan_deletes_files_past_the_keep_period_only():
    files = [record("old", 1, 40), record("new", 1, 2)]
    doomed = storage.plan_cleanup(files, keep_days=30, max_gb=0)
    assert [f["path"] for f in doomed] == ["old"]


def test_plan_trims_oldest_first_down_to_the_size_cap():
    gb = storage.GB
    files = [record("a", gb, 10), record("b", gb, 5), record("c", gb, 1)]
    doomed = storage.plan_cleanup(files, keep_days=0, max_gb=2)
    assert [f["path"] for f in doomed] == ["a"]          # only the oldest has to go
    assert storage.plan_cleanup(files, keep_days=0, max_gb=1)[1]["path"] == "b"


def test_nothing_is_planned_when_limits_are_off():
    assert storage.plan_cleanup([record("a", 10**12, 999)], keep_days=0, max_gb=0) == []


def test_cleanup_deletes_recorded_files_and_never_anything_else(tmp_path):
    old, fresh, mine = make(tmp_path, "old.mp4"), make(tmp_path, "fresh.mp4"), make(tmp_path, "my own download.mp4")
    data = subs.load()
    data["files"] = [record(old, 100, 40), record(fresh, 100, 1)]
    subs.save(data)
    storage.set_setting("keep_days", 30)
    assert storage.cleanup(dry_run=True) == (1, 100)
    assert old.exists()                                   # a dry run changes nothing
    assert storage.cleanup() == (1, 100)
    assert not old.exists() and fresh.exists() and mine.exists()
    assert [f["path"] for f in subs.load()["files"]] == [str(fresh)]


def test_files_already_deleted_by_hand_are_just_forgotten(tmp_path):
    ghost = tmp_path / "gone.mp4"
    data = subs.load()
    data["files"] = [record(ghost, 100, 90)]
    subs.save(data)
    storage.set_setting("keep_days", 30)
    assert storage.cleanup() == (0, 0)
    assert subs.load()["files"] == []


def test_size_cap_removes_oldest_subscription_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "GB", 1000)               # pretend a "GB" is 1000 bytes so test files stay tiny
    paths = [make(tmp_path, f"v{i}.mp4", 600) for i in range(3)]
    data = subs.load()
    data["files"] = [record(p, 600, 30 - i * 10) for i, p in enumerate(paths)]   # v0 oldest
    subs.save(data)
    storage.set_setting("max_gb", 1)
    storage.cleanup()
    assert [p.exists() for p in paths] == [False, False, True]


def test_low_space_guard(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "free_bytes", lambda p: 500 * 1024 ** 2)
    assert storage.low_space(tmp_path, min_free_gb=1)[0] is True
    assert storage.low_space(tmp_path, min_free_gb=0)[0] is False   # warning switched off
    monkeypatch.setattr(storage, "free_bytes", lambda p: 50 * storage.GB)
    assert storage.low_space(tmp_path, min_free_gb=1)[0] is False


def test_free_space_works_for_a_folder_that_does_not_exist_yet(tmp_path):
    assert storage.free_bytes(tmp_path / "not" / "created" / "yet") > 0


def test_background_check_skips_downloads_when_the_disk_is_nearly_full(monkeypatch, tmp_path, media_url):
    monkeypatch.setattr(subs, "list_entries", lambda *a, **k: ("Chan", [
        {"id": "x", "url": media_url, "title": "X", "upcoming": False}]))
    options = dict(output=str(tmp_path / "out"), fmt="mp3", quality="best", naming="title-id", folders="flat",
                   sub_lang=None, sub_embed=False, extras=False)
    sub, _ = subs.follow("https://www.youtube.com/@x", options)
    subs.mark_seen(sub["id"], [])                          # nothing seen yet, so the video counts as new
    data = subs.load()
    data["subs"][0]["seen"] = []
    subs.save(data)
    monkeypatch.setattr(storage, "free_bytes", lambda p: 10 * 1024 ** 2)
    messages = []
    assert subs.check_due(log=messages.append, force=True) == 0
    assert any("only" in m and "free" in m for m in messages)


def test_subscription_downloads_are_recorded_for_cleanup(tmp_path, media_url):
    f = make(tmp_path, "a.mp4", 123)
    subs.add_recent("Chan", "A", [str(f)])
    (rec,) = subs.load()["files"]
    assert rec["path"] == str(f) and rec["size"] == 123 and rec["sub"] == "Chan"
