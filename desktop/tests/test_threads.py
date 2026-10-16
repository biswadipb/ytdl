"""Threads and Dailymotion support. Threads pages are replaced by stand-ins so no browser or network is needed."""
import os
import urllib.request
import json
from pathlib import Path

import pytest

import threads
import ytdl
from conftest import duration

POST = "https://www.threads.com/@zuck/post/DSVRshjkbtK"


def page(*videos_in_main, other_videos=(), caption="My caption"):
    """A page shaped like the real one: the linked post first, replies and suggestions after it."""
    main = "".join(f'<video src="{v}"></video>' for v in videos_in_main)
    other = "".join(f'<video src="{v}"></video>' for v in other_videos)
    return (f'<html><head><title>{caption}</title><meta property="og:image" content="https://img.test/x.jpg"></head>'
            f'<body><div><div data-pressable-container="true"><a href="/@zuck">zuck</a><div><div>{main}'
            f'<img src="https://img.test/pic.jpg"></div></div></div>'
            f'<div data-pressable-container="true"><a href="/@other">other</a>{other}</div></div>'
            f'{"<p>padding</p>" * 400}</body></html>')


def test_threads_links_are_recognised():
    assert threads.is_threads_url(POST)
    assert threads.is_threads_url("https://www.threads.net/@zuck/post/abc-123")
    assert threads.is_threads_url("https://www.threads.com/t/abc123")
    assert not threads.is_threads_url("https://www.threads.com/@zuck")      # a profile, not a post
    assert not threads.is_threads_url("https://example.com/@zuck/post/abc")


def test_only_the_linked_posts_videos_are_picked_up():
    videos, caption, thumb = threads.parse(page("https://v.test/1.mp4", "https://v.test/2.mp4",
                                                 other_videos=["https://v.test/reply.mp4"]))
    assert videos == ["https://v.test/1.mp4", "https://v.test/2.mp4"]
    assert caption == "My caption" and thumb == "https://img.test/x.jpg"


def test_a_post_with_only_pictures_gives_a_clear_error(monkeypatch):
    monkeypatch.setattr(threads, "render", lambda *a, **k: page(other_videos=["https://v.test/reply.mp4"]))
    with pytest.raises(threads.ThreadsError, match="No video found"):
        threads.extract(POST)


def test_missing_browser_explains_what_to_install(monkeypatch):
    monkeypatch.setattr(threads, "find_browser", lambda: None)
    with pytest.raises(threads.ThreadsError, match="Chrome"):
        threads.render(POST)


def test_multi_video_posts_download_first_clip_or_all(monkeypatch):
    monkeypatch.setattr(threads, "render", lambda *a, **k: page("https://v.test/1.mp4", "https://v.test/2.mp4"))
    single = threads.extract(POST)
    assert single["url"] == "https://v.test/1.mp4"   # one clip unless "all videos" is ticked
    both = threads.extract(POST, playlist=True)
    assert [e["id"] for e in both["entries"]] == ["DSVRshjkbtK-1", "DSVRshjkbtK-2"]
    assert both["entries"][0]["title"].endswith("(1-of-2)")


def test_threads_post_downloads_through_the_normal_pipeline(monkeypatch, media_url, ffmpeg, tmp_path):
    monkeypatch.setattr(threads, "render", lambda *a, **k: page(media_url))
    (path,) = ytdl.download_one(POST, output=str(tmp_path), fmt="mp3", folders="channel", naming="channel-title")
    rel = Path(path).relative_to(tmp_path).parts
    assert rel[0] == "zuck" and rel[1].startswith("zuck - My caption")
    assert 5 < duration(ffmpeg, path) < 7


def test_all_clips_of_a_post_become_separate_files(monkeypatch, media_url, media_url_2, tmp_path):
    monkeypatch.setattr(threads, "render", lambda *a, **k: page(media_url, media_url_2))
    files = ytdl.download_one(POST, output=str(tmp_path), fmt="mp4", playlist=True)
    assert len(files) == 2 and all(Path(f).exists() for f in files)


def test_threads_failures_are_reported_not_raised_by_the_batch_helper(monkeypatch, tmp_path):
    monkeypatch.setattr(threads, "render", lambda *a, **k: page())
    failures = ytdl.download([POST], output=str(tmp_path), fmt="mp4")
    assert len(failures) == 1 and "No video found" in failures[0][1]


def test_preview_works_for_threads(monkeypatch):
    monkeypatch.setattr(threads, "render", lambda *a, **k: page("https://v.test/1.mp4"))
    info = ytdl.video_info(POST)
    assert info["title"] == "My caption" and info["channel"] == "zuck"
    assert info["thumbnail"] == "https://img.test/x.jpg"


def test_dailymotion_and_threads_links_are_detected_when_pasted():
    for link in ["https://www.dailymotion.com/video/x7or79x", "https://dai.ly/x7or79x", POST]:
        assert ytdl.SITE_PATTERN.search(f"check this out: {link}"), link


# ---- optional live checks (YTDL_NETWORK_TESTS=1); skipped when the site or a browser isn't available -------------

needs_network = pytest.mark.skipif(not os.environ.get("YTDL_NETWORK_TESTS"), reason="set YTDL_NETWORK_TESTS=1")


@needs_network
def test_real_threads_post(ffmpeg, tmp_path):
    if not threads.find_browser():
        pytest.skip("no Chrome-family browser installed")
    try:
        (path,) = ytdl.download_one(POST, output=str(tmp_path), fmt="mp3", extras=False)
    except threads.ThreadsError as e:
        pytest.skip(f"Threads unreachable from this machine: {e}")
    assert 3 < duration(ffmpeg, path) < 8


@needs_network
def test_real_dailymotion_video(ffmpeg, tmp_path):
    try:
        with urllib.request.urlopen("https://api.dailymotion.com/videos?search=short+film+trailer"
                                    "&fields=id&limit=10&shorter_than=2", timeout=20) as r:
            ids = [v["id"] for v in json.load(r)["list"]]
    except Exception as e:
        pytest.skip(f"Dailymotion API unreachable: {e}")
    for vid in ids:
        try:
            (path,) = ytdl.download_one(f"https://www.dailymotion.com/video/{vid}", output=str(tmp_path),
                                        fmt="mp3", extras=False)
            assert duration(ffmpeg, path) > 5
            return
        except ytdl.yt_dlp.utils.DownloadError:
            continue  # geo-restricted or removed: try the next one
    pytest.skip("no Dailymotion video was downloadable from this location")
