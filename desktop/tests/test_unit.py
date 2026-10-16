"""Fast checks that need no network and no ffmpeg."""
import pytest

import updates
import ytdl


def test_parse_time():
    assert ytdl.parse_time("90") == 90
    assert ytdl.parse_time("1:30") == 90
    assert ytdl.parse_time("1:02:03") == 3723
    assert ytdl.parse_time("") is None
    with pytest.raises(ValueError):
        ytdl.parse_time("1:2:3:4")
    with pytest.raises(ValueError):
        ytdl.parse_time("abc")


def test_parse_clip():
    assert ytdl.parse_clip("1:30-2:45") == (90, 165)
    assert ytdl.parse_clip("90-") == (90, None)
    assert ytdl.parse_clip("") is None
    with pytest.raises(ValueError):
        ytdl.parse_clip("90")


@pytest.mark.parametrize("message,retry", [
    ("Unable to download webpage: connection reset", True),
    ("HTTP Error 503", True),
    ("HTTP Error 429: Too Many Requests", True),
    ("Video unavailable", False),
    ("Unsupported URL: https://example.com", False),
    ("Sign in to confirm your age", False),
    ("This video is private", False),
])
def test_transient_errors(message, retry):
    assert ytdl.is_transient(message) is retry


def test_links_from_supported_sites_are_recognised():
    ok = ["https://www.youtube.com/watch?v=abc", "https://youtu.be/abc", "https://www.instagram.com/reel/xyz/",
          "https://x.com/user/status/1", "https://twitter.com/u/status/1", "https://www.facebook.com/watch/?v=1",
          "https://fb.watch/abc/", "https://www.threads.com/@u/post/abc"]
    for link in ok:
        assert ytdl.SITE_PATTERN.search(f"look at {link} now"), link
    assert not ytdl.SITE_PATTERN.search("https://example.com/video")


@pytest.mark.parametrize("fmt", ytdl.FORMATS)
def test_every_format_builds_options(fmt, tmp_path):
    opts = ytdl.build_options(str(tmp_path), fmt=fmt)
    if fmt in ytdl.AUDIO_FORMATS:
        codecs = [p.get("preferredcodec") for p in opts["postprocessors"]]
        assert fmt in codecs
        assert "(audio)" in opts["outtmpl"]
    else:
        assert opts["merge_output_format"] == fmt


def test_quality_cap_and_speed_limit(tmp_path):
    opts = ytdl.build_options(str(tmp_path), quality="720", ratelimit=500_000)
    assert "height<=720" in opts["format"]
    assert opts["ratelimit"] == 500_000


def test_naming_and_folder_rules_shape_the_path(tmp_path):
    template = lambda **kw: ytdl.build_options(str(tmp_path), **kw)["outtmpl"].replace("\\", "/")  # Windows joins with \\
    nested = template(naming="channel-title", folders="site-channel")
    assert "%(extractor_key)s/%(uploader,channel|Unknown)s/" in nested
    assert "%(title)" in nested
    assert "/%(extractor_key)s" not in template(folders="flat")


def test_clip_adds_range_and_label(tmp_path):
    opts = ytdl.build_options(str(tmp_path), clip=(90, 165))
    assert "download_ranges" in opts and opts["force_keyframes_at_cuts"]
    assert "[clip 1m30s-2m45s]" in opts["outtmpl"]


def test_subtitles_only_apply_to_video(tmp_path):
    video = ytdl.build_options(str(tmp_path), fmt="mp4", sub_lang="en")
    assert video["writesubtitles"] and video["subtitleslangs"] == ["en"]
    audio = ytdl.build_options(str(tmp_path), fmt="mp3", sub_lang="en")
    assert "writesubtitles" not in audio


def test_unknown_format_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        ytdl.build_options(str(tmp_path), fmt="avi")


def test_labels_round_trip():
    for key, (label, _) in ytdl.NAMING.items():
        assert ytdl.key_for_label(label, ytdl.NAMING, "x") == key
    assert ytdl.key_for_label("nonsense", ytdl.NAMING, "fallback") == "fallback"


def test_version_comparison():
    assert updates.is_newer("2.0.0", "v2.1.0")
    assert updates.is_newer("2.9.9", "3.0.0")
    assert not updates.is_newer("2.1.0", "v2.1.0")
    assert not updates.is_newer("2.1.1", "2.1.0")
    assert not updates.is_newer("dev", "9.9.9")
    assert updates.check("dev") is None  # source builds never look
