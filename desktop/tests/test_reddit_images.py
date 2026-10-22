"""Reddit picture posts, with stand-ins for Reddit so no network is needed."""
import json
import urllib.error
from pathlib import Path

import pytest

import reddit_images as ri
import ytdl

POST = "https://www.reddit.com/r/pics/comments/abc123/a_nice_view/"


def listing(post):
    return json.dumps([{"data": {"children": [{"data": post}]}}]).encode()


GALLERY = {
    "id": "abc123", "title": "Trip: day 1/2?", "is_gallery": True,
    "gallery_data": {"items": [{"media_id": "m1"}, {"media_id": "m2"}, {"media_id": "m3"}]},
    "media_metadata": {
        "m1": {"status": "valid", "e": "Image", "m": "image/jpg", "s": {"u": "https://preview.redd.it/m1.jpg?a=1&amp;b=2"}},
        "m2": {"status": "valid", "e": "Image", "m": "image/png"},
        "m3": {"status": "failed", "e": "Image", "m": "image/jpg"},
    },
}


def test_links_are_recognised():
    for ok in (POST, "https://old.reddit.com/r/a/comments/xyz/t", "https://redd.it/abc123",
               "https://www.reddit.com/r/pics/s/AbCdEf", "https://reddit.com/comments/abc123"):
        assert ri.is_reddit_url(ok), ok
    assert not ri.is_reddit_url("https://www.reddit.com/r/pics/")
    assert not ri.is_reddit_url("https://youtu.be/abc")


def test_gallery_gives_originals_in_order_and_skips_broken_ones():
    imgs = ri.image_urls(GALLERY)
    assert [ext for _, ext in imgs] == ["jpg", "png"]
    assert imgs[0][0] == ["https://i.redd.it/m1.jpg", "https://preview.redd.it/m1.jpg?a=1&b=2"]


def test_single_image_and_not_other_links():
    one = {"url_overridden_by_dest": "https://i.redd.it/x.JPEG"}
    assert ri.image_urls(one) == [(["https://i.redd.it/x.JPEG"], "jpg")]
    assert ri.image_urls({"url": "https://example.com/pic.jpg"}) == []         # someone else's site: not ours
    assert ri.image_urls({"url": "https://www.reddit.com/r/a/comments/1/x"}) == []


def test_video_posts_are_left_to_yt_dlp():
    assert ri.image_urls({"is_video": True, "url": "https://i.redd.it/x.gif"}) == []
    assert ri.image_urls({"post_hint": "hosted:video", "url": "https://v.redd.it/z"}) == []


def test_crossposts_use_the_original_post():
    assert ri.image_urls({"crosspost_parent_list": [{"url": "https://i.redd.it/o.png"}]}) == [(["https://i.redd.it/o.png"], "png")]


def test_file_names_are_safe():
    assert ri.safe_name('a/b:c*d?"e<f>g|h') == "abcdefgh"
    assert ri.safe_name("   ...  ") == "reddit"
    assert len(ri.safe_name("x" * 500)) == 100


def test_download_saves_each_picture_and_reports_steady_progress(tmp_path, media_url, media_url_2, monkeypatch):
    post = {"id": "p1", "title": "Trip: day 1", "is_gallery": True,
            "gallery_data": {"items": [{"media_id": "a"}, {"media_id": "b"}]},
            "media_metadata": {k: {"e": "Image", "m": "image/jpg"} for k in "ab"}}
    monkeypatch.setattr(ri, "get", lambda url, timeout=20: (url, listing(post)))
    monkeypatch.setattr(ri, "image_urls", lambda p: [([media_url], "jpg"), (["http://127.0.0.1:1/dead", media_url_2], "jpg")])
    seen = []
    prog = ytdl.Progress()
    files = ri.download(POST, tmp_path, hooks=[lambda d: seen.append(prog.update(d))])
    assert [Path(f).name for f in files] == ["Trip day 1 [p1] (1 of 2).jpg", "Trip day 1 [p1] (2 of 2).jpg"]
    assert all(Path(f).stat().st_size > 1000 for f in files)   # second one used its fallback
    assert seen == sorted(seen) and 0 < seen[-1] <= 0.99


def test_a_hook_can_cancel(tmp_path, media_url, monkeypatch):
    monkeypatch.setattr(ri, "get", lambda url, timeout=20: (url, listing({"id": "p"})))
    monkeypatch.setattr(ri, "image_urls", lambda p: [([media_url], "jpg")])

    def hook(d):
        raise ytdl.Cancelled()
    with pytest.raises(ytdl.Cancelled):
        ri.download(POST, tmp_path, hooks=[hook])


def test_audio_choice_on_a_picture_post_explains_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(ri, "get", lambda url, timeout=20: (url, listing({"id": "p", "url": "https://i.redd.it/x.png"})))
    with pytest.raises(ri.RedditError, match="no audio"):
        ri.download(POST, tmp_path, audio=True)


def test_video_posts_return_none_so_yt_dlp_takes_over(tmp_path, monkeypatch):
    monkeypatch.setattr(ri, "get", lambda url, timeout=20: (url, listing({"id": "p", "is_video": True})))
    assert ri.download(POST, tmp_path) is None


def test_blocked_reddit_says_so(monkeypatch):
    def refuse(url, timeout=20):
        raise urllib.error.HTTPError(url, 403, "Blocked", {}, None)
    monkeypatch.setattr(ri, "get", refuse)
    with pytest.raises(ri.RedditError, match="blocking"):
        ri.post_data(POST)


def test_download_one_falls_back_to_yt_dlp_when_reddit_cant_be_read(tmp_path, monkeypatch):
    def refuse(url, timeout=20):
        raise urllib.error.HTTPError(url, 403, "Blocked", {}, None)
    monkeypatch.setattr(ri, "get", refuse)
    asked = []

    class Fake:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download):
            asked.append(url)
            return {"requested_downloads": [{"filepath": "/x/v.mp4"}]}
    ytdl.yt_dlp.version                                  # load the engine first, so we patch the real module
    monkeypatch.setattr(ytdl.yt_dlp, "YoutubeDL", Fake)
    assert ytdl.download_one(POST, output=str(tmp_path)) == ["/x/v.mp4"] and asked == [POST]
