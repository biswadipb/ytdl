"""Following channels: detecting new uploads, downloading each once, and the background scheduler."""
import plistlib
import sys
import time

import pytest

import subscriptions as subs
import ytdl

REAL_SCHEDULE_INSTALLED = subs.schedule_installed


def entry(video_id, url, title=None, upcoming=False):
    return {"id": video_id, "url": url, "title": title or video_id, "upcoming": upcoming}


@pytest.fixture
def channel(monkeypatch, media_url, media_url_2, tmp_path):
    """A fake channel whose listing we control; its videos are real downloadable files."""
    state = {"entries": [entry("old", media_url, "Old video")]}
    monkeypatch.setattr(subs, "list_entries", lambda *a, **k: ("Test Channel", list(state["entries"])))
    monkeypatch.setattr(subs.time, "sleep", lambda s: None)
    state["options"] = dict(output=str(tmp_path / "out"), fmt="mp3", quality="best", naming="title-id",
                            folders="flat", sub_lang=None, sub_embed=False, extras=False)
    state["new_url"] = media_url_2
    return state


def test_following_marks_existing_videos_as_seen(channel):
    sub, first = subs.follow("https://www.youtube.com/@x", channel["options"], backfill=0)
    assert sub["seen"] == ["old"] and first == []
    assert subs.find_new(sub, channel["entries"]) == []


def test_backfill_returns_the_newest_videos_to_download_now(channel, media_url_2):
    channel["entries"] = [entry("new2", media_url_2), entry("new1", media_url_2), entry("old", media_url_2)]
    sub, first = subs.follow("https://www.youtube.com/@x", channel["options"], backfill=2)
    assert [e["id"] for e in first] == ["new2", "new1"]


def test_following_the_same_channel_twice_is_refused(channel):
    subs.follow("https://www.youtube.com/@x", channel["options"])
    with pytest.raises(ValueError, match="already follow"):
        subs.follow("https://www.youtube.com/@x", channel["options"])


def test_new_uploads_are_downloaded_exactly_once(channel):
    sub, _ = subs.follow("https://www.youtube.com/@x", channel["options"])
    channel["entries"].insert(0, entry("fresh", channel["new_url"], "Fresh video"))
    assert subs.check_due(log=lambda m: None) == 1
    saved = subs.load()["recent"]
    assert len(saved) == 1 and saved[0]["title"] == "Fresh video"
    assert "fresh" in subs.load()["subs"][0]["seen"]
    assert subs.check_due(log=lambda m: None, force=True) == 0  # nothing new the second time


def test_several_new_uploads_come_oldest_first(channel):
    sub, _ = subs.follow("https://www.youtube.com/@x", channel["options"])
    channel["entries"] = [entry("c", "u3"), entry("b", "u2"), entry("a", "u1"), entry("old", "u0")]
    assert [e["id"] for e in subs.find_new(sub, channel["entries"])] == ["a", "b", "c"]


def test_scheduled_livestreams_wait_for_a_later_check(channel):
    sub, _ = subs.follow("https://www.youtube.com/@x", channel["options"])
    channel["entries"].insert(0, entry("live", "u", upcoming=True))
    assert subs.find_new(sub, channel["entries"]) == []
    found = subs.collect_new(force=True)
    assert found == [] and "live" not in subs.load()["subs"][0]["seen"]


def test_collect_new_marks_videos_seen_so_the_background_job_skips_them(channel):
    subs.follow("https://www.youtube.com/@x", channel["options"])
    channel["entries"].insert(0, entry("fresh", channel["new_url"]))
    (found,) = subs.collect_new(force=True)
    assert [e["id"] for e in found[1]] == ["fresh"]
    assert subs.collect_new(force=True) == []


def test_a_video_that_keeps_failing_is_given_up_on(channel):
    sub, _ = subs.follow("https://www.youtube.com/@x", channel["options"])
    channel["entries"].insert(0, entry("broken", "http://127.0.0.1:9/gone.mp4"))
    for _ in range(subs.MAX_FAILS):
        subs.check_due(log=lambda m: None, force=True)
    assert "broken" in subs.load()["subs"][0]["seen"]
    calls = []
    log = lambda m: calls.append(m)
    subs.check_due(log=log, force=True)
    assert not any("failed" in m for m in calls)  # no more attempts


def test_paused_and_recently_checked_subscriptions_are_skipped(channel):
    sub, _ = subs.follow("https://www.youtube.com/@x", channel["options"])
    assert [s["id"] for s in subs.due()] == [sub["id"]]
    subs.set_enabled(sub["id"], False)
    assert subs.due() == []
    subs.set_enabled(sub["id"], True)
    subs.record_check(sub["id"])
    assert subs.due() == []
    assert len(subs.due(now=time.time() + 7 * 3600)) == 1   # default interval is 6 hours


def test_only_one_checker_runs_at_a_time(channel):
    subs.follow("https://www.youtube.com/@x", channel["options"])
    channel["entries"].insert(0, entry("fresh", channel["new_url"]))
    messages = []
    with subs.Lock() as got:
        assert got
        assert subs.check_due(log=messages.append) == 0
    assert any("already running" in m for m in messages)
    assert subs.check_due(log=lambda m: None) == 1  # lock released, so it works now


def test_a_stale_lock_from_a_crash_is_ignored(channel):
    subs.HOME_DIR.mkdir(parents=True, exist_ok=True)
    subs.LOCK.write_text("")
    old = time.time() - subs.LOCK_STALE_SECONDS - 10
    import os
    os.utime(subs.LOCK, (old, old))
    with subs.Lock() as got:
        assert got


def test_unfollow(channel):
    sub, _ = subs.follow("https://www.youtube.com/@x", channel["options"])
    subs.unfollow(sub["id"])
    assert subs.load()["subs"] == []


@pytest.mark.parametrize("link,expected", [
    ("https://www.youtube.com/@TED", "https://www.youtube.com/@TED/videos"),
    ("https://www.youtube.com/@TED/", "https://www.youtube.com/@TED/videos"),
    ("https://www.youtube.com/channel/UC123", "https://www.youtube.com/channel/UC123/videos"),
    ("https://www.youtube.com/@TED/shorts", "https://www.youtube.com/@TED/shorts"),
    ("https://www.youtube.com/playlist?list=PL1", "https://www.youtube.com/playlist?list=PL1"),
    ("https://example.com/feed", "https://example.com/feed"),
])
def test_channel_links_point_at_their_videos_tab(link, expected):
    assert subs.listing_url(link) == expected


# ---- scheduler ----------------------------------------------------------------

class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        import subprocess
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.mark.skipif(sys.platform == "win32", reason="uses launchctl and os.getuid")
def test_mac_background_job_is_an_hourly_launch_agent(monkeypatch, tmp_path):
    rec = Recorder()
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subs, "_run", rec)
    monkeypatch.setattr(subs, "_agent_path", lambda: tmp_path / "agent.plist")
    subs.install_schedule()
    plist = plistlib.loads((tmp_path / "agent.plist").read_bytes())
    assert plist["Label"] == subs.LABEL and plist["StartInterval"] == 3600
    assert plist["ProgramArguments"] == subs.check_command()
    assert plist["ProgramArguments"][-1] == "--check-subscriptions"
    assert any(c[:2] == ["launchctl", "bootstrap"] for c in rec.calls)
    # moving the app makes the job stale, which the window repairs on its next start
    monkeypatch.setattr(subs, "schedule_installed", lambda: True)
    assert not subs.schedule_is_stale()
    plist["ProgramArguments"] = ["/old/location/ytdl", "--check-subscriptions"]
    (tmp_path / "agent.plist").write_bytes(plistlib.dumps(plist))
    assert subs.schedule_is_stale()
    subs.remove_schedule()
    assert not (tmp_path / "agent.plist").exists()


def test_windows_background_job_is_an_hourly_scheduled_task(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subs, "_run", rec)
    subs.install_schedule()
    (create,) = rec.calls
    assert create[:2] == ["schtasks", "/Create"] and "HOURLY" in create
    assert "--check-subscriptions" in create[create.index("/TR") + 1]


@pytest.mark.skipif(sys.platform != "win32", reason="real Task Scheduler, only on Windows")
def test_windows_task_scheduler_for_real(monkeypatch):
    monkeypatch.setattr(subs, "schedule_installed", REAL_SCHEDULE_INSTALLED)
    subs.remove_schedule()
    try:
        subs.install_schedule()
        assert subs.schedule_installed()
    finally:
        subs.remove_schedule()
    assert not subs.schedule_installed()


def test_command_line_checks_for_new_uploads(channel, capsys):
    subs.follow("https://www.youtube.com/@x", channel["options"])
    channel["entries"].insert(0, entry("fresh", channel["new_url"]))
    assert ytdl.cli(["--check-subscriptions"]) == 0
    assert "1 new video(s) saved" in capsys.readouterr().out


@pytest.mark.parametrize("link,site", [
    ("https://x.com/NASA", "X"), ("https://twitter.com/NASA", "X"), ("https://www.threads.com/@nasa", "Threads"),
    ("https://www.facebook.com/NASA", "Facebook")])
def test_profiles_that_cannot_be_listed_say_so_clearly(link, site):
    with pytest.raises(ValueError, match=f"{site} doesn't let ytdl list"):
        subs.list_entries(link)


def test_instagram_profile_failures_are_explained_in_plain_language(monkeypatch):
    class Boom:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, *a, **k):
            raise ytdl.yt_dlp.utils.DownloadError("ERROR: [instagram:user] nasa: Unable to extract data; please report this issue")
    monkeypatch.setattr(ytdl.yt_dlp, "YoutubeDL", Boom)
    with pytest.raises(ValueError, match="signed in"):
        subs.list_entries("https://www.instagram.com/nasa/")
