"""Real downloads of a local test video through every format and option."""
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import pytest

import ytdl
from conftest import duration, probe


@pytest.mark.parametrize("fmt", ytdl.FORMATS)
def test_each_format_downloads_with_the_right_streams(fmt, media_url, ffmpeg, tmp_path):
    files = ytdl.download_one(media_url, output=str(tmp_path), fmt=fmt)
    assert len(files) == 1
    path = Path(files[0])
    assert path.exists() and path.suffix == f".{fmt}" and path.stat().st_size > 1000
    info = probe(ffmpeg, path)
    if fmt in ytdl.VIDEO_FORMATS:
        assert "Video:" in info and "Audio:" in info
    else:
        assert "Video:" not in info
        assert {"mp3": "mp3", "m4a": "aac", "opus": "opus", "wav": "pcm", "flac": "flac"}[fmt] in info
    assert 5 < duration(ffmpeg, path) < 7


def test_clip_saves_only_the_requested_section(media_url, ffmpeg, tmp_path):
    (path,) = ytdl.download_one(media_url, output=str(tmp_path), fmt="mp4", clip=(1, 4))
    assert "[clip 0m01s-0m04s]" in path
    assert 2.0 < duration(ffmpeg, path) < 5.0


def test_tags_are_embedded_unless_turned_off(media_url, ffmpeg, tmp_path):
    (tagged,) = ytdl.download_one(media_url, output=str(tmp_path / "on"), fmt="mp3", extras=True)
    assert "title" in probe(ffmpeg, tagged).lower()
    (plain,) = ytdl.download_one(media_url, output=str(tmp_path / "off"), fmt="mp3", extras=False)
    assert "title" not in probe(ffmpeg, plain).lower().split("duration")[0]


def test_naming_and_folder_rules(media_url, tmp_path):
    (path,) = ytdl.download_one(media_url, output=str(tmp_path), fmt="mp4",
                                naming="channel-title", folders="site-channel")
    rel = Path(path).relative_to(tmp_path).parts
    assert rel[0] == "Generic" and rel[1] == "Unknown" and rel[2].startswith("Unknown - sample")


def test_speed_limit_slows_the_download(media_url, tmp_path):
    started = time.time()
    ytdl.download_one(media_url, output=str(tmp_path), fmt="mp4", ratelimit=20_000)
    assert time.time() - started > 2  # the test file is ~100 KB, so 20 KB/s takes seconds


def test_cancel_stops_a_download(media_url, tmp_path):
    def hook(_):
        raise ytdl.Cancelled()
    with pytest.raises(ytdl.Cancelled):
        ytdl.download_one(media_url, output=str(tmp_path), fmt="mp4", hooks=[hook], ratelimit=20_000)


def test_temporary_failures_are_retried_then_reported(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(ytdl.time, "sleep", sleeps.append)
    failures = ytdl.download(["http://127.0.0.1:9/missing.mp4"], retries=2, output=str(tmp_path), fmt="mp4")
    assert len(failures) == 1 and failures[0][0].endswith("missing.mp4")
    assert sleeps == [2, 4]  # two retries with growing waits


def test_permanent_failures_are_not_retried(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(ytdl.time, "sleep", sleeps.append)
    failures = ytdl.download(["notaurl"], retries=3, output=str(tmp_path), fmt="mp4")
    assert failures and sleeps == []


def test_subtitles_can_be_muxed_into_a_video(media_url, ffmpeg, tmp_path):
    (video,) = ytdl.download_one(media_url, output=str(tmp_path), fmt="mkv")
    srt = Path(video).with_suffix("").with_name(Path(video).stem + ".en.srt")
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n")
    ytdl.embed_subtitles(video, "mkv")
    assert "Subtitle:" in probe(ffmpeg, video)
    assert not srt.exists()


# ---- engine updates, with PyPI replaced by a fake ---------------------------

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_pypi(monkeypatch, tmp_path, version, corrupt=False):
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("yt_dlp/__init__.py", "# fake")
        z.writestr("yt_dlp-info/METADATA", "ignored")
    blob = wheel.getvalue()
    digest = "0" * 64 if corrupt else hashlib.sha256(blob).hexdigest()
    index = {"info": {"version": version},
             "urls": [{"packagetype": "bdist_wheel", "url": "https://fake/yt_dlp.whl", "digests": {"sha256": digest}}]}

    def fake_urlopen(url, timeout=None):
        return _FakeResponse(json.dumps(index).encode() if "pypi.org" in url else blob)

    monkeypatch.setattr(ytdl.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(ytdl, "ENGINE_DIR", tmp_path / "engine")


def test_engine_update_installs_a_newer_version(monkeypatch, tmp_path):
    _fake_pypi(monkeypatch, tmp_path, "9999.1.1")
    changed, message = ytdl.update_engine()
    assert changed and "9999.1.1" in message
    assert (tmp_path / "engine" / "yt_dlp" / "__init__.py").exists()
    assert ytdl.installed_engine_version() == "9999.1.1"
    assert ytdl.update_engine()[0] is False  # second run: already current


def test_engine_update_rejects_a_corrupted_download(monkeypatch, tmp_path):
    _fake_pypi(monkeypatch, tmp_path, "9999.1.1", corrupt=True)
    with pytest.raises(RuntimeError, match="checksum"):
        ytdl.update_engine()
    assert not (tmp_path / "engine").exists()


def test_engine_update_ignores_an_older_release(monkeypatch, tmp_path):
    _fake_pypi(monkeypatch, tmp_path, "2000.1.1")
    changed, message = ytdl.update_engine()
    assert not changed and "up to date" in message


# ---- optional: the real YouTube, which can block automated machines ---------

@pytest.mark.skipif(not __import__("os").environ.get("YTDL_NETWORK_TESTS"), reason="set YTDL_NETWORK_TESTS=1")
def test_youtube_smoke(ffmpeg, tmp_path):
    try:
        (path,) = ytdl.download_one("https://www.youtube.com/watch?v=jNQXAC9IVRw", output=str(tmp_path),
                                    fmt="mp3")
    except ytdl.yt_dlp.utils.DownloadError as e:
        text = str(e).lower()
        if any(s in text for s in ("sign in to confirm", "bot", "429", "unable to download")):
            pytest.skip(f"YouTube blocked or unreachable from this machine: {text[:100]}")
        raise
    assert 15 < duration(ffmpeg, path) < 25
