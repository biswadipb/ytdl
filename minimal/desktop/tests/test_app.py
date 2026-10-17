"""The minimal desktop app: layout, theme, paste, and real downloads."""
import time
import tkinter as tk
from pathlib import Path

import pytest

import app as minimal


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setattr(minimal, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(minimal.ytdl, "update_engine", lambda: (False, "ok"))   # no network at start-up
    try:
        window = minimal.App()
    except tk.TclError:
        pytest.skip("no display available")
    window.folder = str(tmp_path / "out")
    yield window
    window.destroy()


def pump(w, seconds, until):
    end = time.time() + seconds
    while time.time() < end:
        w.update()
        time.sleep(0.05)
        if until():
            return True
    return False


def statuses(w):
    return [r.job["status"] for r in w.rows.values()]


def test_window_has_the_designed_pieces_in_order(win):
    win.update()
    order = [c for c in win.body.winfo_children() if c in (win.field, win.go, win.opts, win.message)]
    assert order == [win.field, win.go, win.opts, win.message]            # field, Download, options, then the list
    ys = [w.winfo_y() for w in (win.field, win.go, win.opts)]
    assert ys == sorted(ys)
    assert win.seg.winfo_width() > win.drop.winfo_width() * 1.8            # switch gets about two thirds of the row


def test_switching_to_audio_changes_the_dropdown_choices(win):
    assert [c[0] for c in win.drop.choices] == ["Best", "1080p", "720p", "480p"]
    win.seg.index = 1
    win.mode_changed(1)
    assert [c[0] for c in win.drop.choices] == ["MP3", "M4A"]
    win.mode_changed(0)
    assert win.drop.choices[0][0] == "Best"


def test_choices_are_remembered(win, tmp_path):
    win.drop.pick(2)                                                       # 720p
    win.seg.index = 1
    win.mode_changed(1)
    win.drop.pick(1)                                                       # M4A
    saved = minimal.json.loads((tmp_path / "settings.json").read_text())
    assert saved["mode"] == "audio" and saved["video_q"] == 2 and saved["audio_q"] == 1


def test_follows_the_system_light_and_dark_setting(win, monkeypatch):
    monkeypatch.setattr(minimal, "system_mode", lambda: "dark")
    win.follow_system()
    assert win.mode == "dark" and win.cget("bg") == minimal.PALETTES["dark"]["bg"]
    monkeypatch.setattr(minimal, "system_mode", lambda: "light")
    win.follow_system()
    assert win.mode == "light" and win.cget("bg") == minimal.PALETTES["light"]["bg"]


def test_download_needs_a_link_and_refuses_channels_and_playlists(win):
    win.start_download()
    assert "Paste a video link" in win.message.cget("text") and not win.rows
    for link in ["https://www.youtube.com/@TED", "https://www.youtube.com/playlist?list=PL1"]:
        win.field.set(link)
        win.start_download()
        assert "channel or playlist" in win.message.cget("text") and not win.rows


def test_copied_links_fill_the_box_but_never_download(win, monkeypatch):
    monkeypatch.setattr(win, "clipboard_get", lambda: "look at https://youtu.be/jNQXAC9IVRw !")
    win.grab_copied_link()
    assert win.field.get() == "https://youtu.be/jNQXAC9IVRw" and not win.rows
    win.field.set("")
    win.paste()
    assert win.field.get() == "https://youtu.be/jNQXAC9IVRw"


def test_video_download_appears_in_the_session_list_and_finishes(win, media):
    win.field.set(media["one"])
    win.start_download()
    assert len(win.rows) == 1 and win.field.get() == ""                    # box clears, row appears
    assert pump(win, 60, lambda: statuses(win) == ["done"]), statuses(win)
    (row,) = win.rows.values()
    assert row.right.cget("text") == "Open" and Path(row.job["files"][0]).suffix == ".mp4"


def test_audio_download_makes_an_mp3(win, media):
    win.seg.index = 1
    win.mode_changed(1)
    win.field.set(media["one"])
    win.start_download()
    assert pump(win, 60, lambda: statuses(win) == ["done"]), statuses(win)
    assert Path(next(iter(win.rows.values())).job["files"][0]).suffix == ".mp3"


def test_newest_download_is_listed_first(win, media):
    for key in ("one", "two"):
        win.field.set(media[key])
        win.start_download()
    kids = win.list_frame.pack_slaves()
    assert kids[0] is win.rows[2] and kids[1] is win.rows[1]
    assert pump(win, 90, lambda: statuses(win) == ["done", "done"])


def test_failed_download_can_be_retried(win):
    win.field.set("http://127.0.0.1:9/missing.mp4")
    win.start_download()
    assert pump(win, 60, lambda: statuses(win) == ["failed"])
    job = next(iter(win.rows.values())).job
    win.row_action(job)
    assert job["status"] == "queued"
    assert pump(win, 60, lambda: statuses(win) == ["failed"])


def test_a_queued_download_can_be_cancelled(win, media):
    for key in ("one", "two"):
        win.field.set(media[key])
        win.start_download()
    second = win.rows[2].job
    win.cancel(second)
    assert pump(win, 60, lambda: second["status"] == "cancelled")


def test_drawing_a_tiny_or_negative_sized_widget_does_not_crash(win):
    """Regression: before a widget is laid out its size is about 1 pixel, which crashed the image-based drawing."""
    for box in [(0, 0, 1, 1), (2, 2, -2, -2), (0, 0, 0, 40), (5, 5, 5, 5)]:
        minimal.pill(win.field, *box, 10, "#ffffff")
    minimal.pill(win.field, 0, 0, 100, 40, 14, "#ffffff", outline="#000000", width=2)


def test_the_image_based_drawing_path_works_on_every_system(win, monkeypatch):
    """Mac draws with vectors; Windows and Linux use anti-aliased images. Make sure that path is exercised here too."""
    monkeypatch.setattr(minimal.sys, "platform", "linux")
    win.__dict__.pop("_pill_cache", None)
    win.apply_theme()
    win.update()
    assert win.__dict__.get("_pill_cache"), "expected images to be generated"


def test_a_second_window_does_not_reuse_the_first_windows_images(tmp_path, monkeypatch):
    """Regression: a shared image cache raised 'image pyimageN doesn't exist' when a new window was created."""
    monkeypatch.setattr(minimal, "SETTINGS", tmp_path / "s.json")
    monkeypatch.setattr(minimal.ytdl, "update_engine", lambda: (False, "ok"))
    monkeypatch.setattr(minimal.sys, "platform", "linux")
    for _ in range(2):
        window = minimal.App()
        window.update()
        window.destroy()


def test_theme_link_cycles_auto_light_dark_and_is_remembered(win, tmp_path, monkeypatch):
    monkeypatch.setattr(minimal, "system_mode", lambda: "dark")
    win.theme = "auto"
    win.cycle_theme()
    assert win.theme == "light" and win.mode == "light" and win.theme_link.cget("text") == "Theme: Light"
    assert win.cget("bg") == minimal.PALETTES["light"]["bg"]            # Light wins even though the system is dark
    win.cycle_theme()
    assert win.theme == "dark" and win.mode == "dark"
    win.cycle_theme()
    assert win.theme == "auto" and win.mode == "dark" and win.theme_link.cget("text") == "Theme: Auto"
    assert minimal.json.loads((tmp_path / "settings.json").read_text())["theme"] == "auto"


def test_a_chosen_theme_ignores_later_system_changes_but_auto_follows(win, monkeypatch):
    win.theme = "dark"
    win.cycle_theme()                                                   # dark -> auto
    assert win.theme == "auto"
    monkeypatch.setattr(minimal, "system_mode", lambda: "light")
    win.follow_system()
    assert win.mode == "light"                                          # auto follows the system
    win.cycle_theme()                                                   # auto -> light, now fixed
    assert win.theme == "light"
    monkeypatch.setattr(minimal, "system_mode", lambda: "dark")
    win.follow_system()
    assert win.mode == "light"                                          # a chosen theme ignores the system


def test_theme_order_and_unknown_values():
    assert [minimal.next_theme(t) for t in ("auto", "light", "dark")] == ["light", "dark", "auto"]
    assert minimal.next_theme("nonsense") == "auto"


def test_the_saved_theme_is_used_at_start(tmp_path, monkeypatch):
    (tmp_path / "s.json").write_text('{"theme": "dark"}')
    monkeypatch.setattr(minimal, "SETTINGS", tmp_path / "s.json")
    monkeypatch.setattr(minimal.ytdl, "update_engine", lambda: (False, "ok"))
    monkeypatch.setattr(minimal, "system_mode", lambda: "light")
    window = minimal.App()
    try:
        assert window.theme == "dark" and window.mode == "dark"
    finally:
        window.destroy()
