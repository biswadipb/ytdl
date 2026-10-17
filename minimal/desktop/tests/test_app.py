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


def test_header_has_an_auto_light_dark_switch_built_like_video_audio(win):
    assert win.theme_seg.labels == ["Auto", "Light", "Dark"]
    assert isinstance(win.theme_seg, type(win.seg))                 # the very same kind of control as Video | Audio
    words = [w.cget("text") for w in win.header.winfo_children() if isinstance(w, minimal.tk.Label) and w.cget("text")]
    assert words == ["ytdl"]                                          # no "Theme:" caption, just the switch


def _click(widget, index):
    """Click the middle of segment `index`."""
    widget.update()
    part = widget.winfo_width() / len(widget.labels)
    widget.event_generate("<Button-1>", x=int(part * (index + 0.5)), y=10)
    widget.update()


def test_choosing_a_theme_applies_it_and_remembers_it(win, tmp_path, monkeypatch):
    monkeypatch.setattr(minimal, "system_mode", lambda: "dark")
    _click(win.theme_seg, 1)                                          # Light, even though the system is dark
    assert win.theme == "light" and win.mode == "light" and win.cget("bg") == minimal.PALETTES["light"]["bg"]
    _click(win.theme_seg, 2)
    assert win.theme == "dark" and win.mode == "dark"
    _click(win.theme_seg, 0)
    assert win.theme == "auto" and win.mode == "dark"                 # Auto follows the (dark) system
    assert win.theme_seg.index == 0
    assert minimal.json.loads((tmp_path / "settings.json").read_text())["theme"] == "auto"


def test_a_chosen_theme_ignores_later_system_changes_but_auto_follows(win, monkeypatch):
    monkeypatch.setattr(minimal, "system_mode", lambda: "light")
    win.choose_theme(0)
    win.follow_system()
    assert win.mode == "light"                                        # auto follows the system
    monkeypatch.setattr(minimal, "system_mode", lambda: "dark")
    win.follow_system()
    assert win.mode == "dark"
    win.choose_theme(1)                                               # Light is now fixed
    monkeypatch.setattr(minimal, "system_mode", lambda: "dark")
    win.follow_system()
    assert win.mode == "light"


def test_unknown_saved_theme_falls_back_to_auto(tmp_path, monkeypatch):
    (tmp_path / "s.json").write_text('{"theme": "sepia"}')
    monkeypatch.setattr(minimal, "SETTINGS", tmp_path / "s.json")
    monkeypatch.setattr(minimal.ytdl, "update_engine", lambda: (False, "ok"))
    window = minimal.App()
    try:
        assert window.theme == "auto" and window.theme_seg.index == 0
    finally:
        window.destroy()


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


def test_default_save_folder_is_downloads_ytdl(tmp_path, monkeypatch):
    monkeypatch.setattr(minimal, "SETTINGS", tmp_path / "s.json")
    monkeypatch.setattr(minimal.ytdl, "update_engine", lambda: (False, "ok"))
    window = minimal.App()
    try:
        assert window.is_default_folder()
        assert minimal.shown_path(window.folder).replace("\\", "/").endswith("Downloads/ytdl")
        assert "Saving to" in window.where_label.cget("text") and not window.default_link.winfo_manager()
    finally:
        window.destroy()


def test_choosing_a_folder_is_used_remembered_and_can_be_reset(win, tmp_path, monkeypatch):
    target = tmp_path / "My Videos"
    monkeypatch.setattr(minimal.filedialog, "askdirectory", lambda **k: str(target))
    win.choose_folder()
    win.update()
    assert win.folder == str(target) and not win.is_default_folder()
    assert win.default_link.winfo_manager()                              # a "Default" link appears for custom folders
    assert minimal.json.loads((tmp_path / "settings.json").read_text())["folder"] == str(target)
    win.use_default_folder()
    win.update()
    assert win.is_default_folder() and not win.default_link.winfo_manager()


def test_cancelling_the_folder_dialog_changes_nothing(win, monkeypatch):
    before = win.folder
    monkeypatch.setattr(minimal.filedialog, "askdirectory", lambda **k: "")
    win.choose_folder()
    assert win.folder == before


def test_downloads_land_in_the_chosen_folder(win, media, tmp_path, monkeypatch):
    target = tmp_path / "picked folder"
    monkeypatch.setattr(minimal.filedialog, "askdirectory", lambda **k: str(target))
    win.choose_folder()
    win.field.set(media["one"])
    win.start_download()
    assert pump(win, 60, lambda: statuses(win) == ["done"]), statuses(win)
    saved = Path(next(iter(win.rows.values())).job["files"][0])
    assert saved.parent == target and saved.exists()


def test_long_paths_keep_their_ending(win):
    long_path = "/Users/someone/Documents/a/very/long/path/that/keeps/going/to/Videos"
    assert minimal.short_middle(long_path).endswith("to/Videos") and len(minimal.short_middle(long_path)) <= 34
    assert minimal.shown_path(str(Path.home() / "Downloads" / "ytdl")).replace("\\", "/") == "~/Downloads/ytdl"


def test_paste_becomes_clear_once_a_link_is_in_the_box(win, monkeypatch):
    monkeypatch.setattr(win, "clipboard_get", lambda: "https://youtu.be/jNQXAC9IVRw")
    monkeypatch.setattr(win, "grab_copied_link", lambda: None)         # no automatic filling while we look
    win.field.set("")
    win.update()
    word = lambda: win.field.itemcget("paste", "text")
    assert word() == "Paste" and win.field.itemcget("hint", "state") == "normal"
    win.field.act()                                                    # empty box: it pastes
    win.update()
    assert win.field.get() == "https://youtu.be/jNQXAC9IVRw" and word() == "Clear"
    assert win.field.itemcget("hint", "state") == "hidden"
    win.field.act()                                                    # link in box: it clears
    win.update()
    assert win.field.get() == "" and word() == "Paste" and win.field.itemcget("hint", "state") == "normal"


def test_the_hint_is_never_typed_text(win):
    win.update()
    win.field.entry.focus_force()
    win.update()
    assert win.field.entry.get() == ""                                # nothing to erase, focused or not
    win.field.set("https://youtu.be/x")
    win.field.set("")
    win.update()
    assert win.field.entry.get() == "" and win.field.get() == ""


def test_the_bar_glides_forward_and_never_back(win):
    from app import Bar
    bar = Bar(win, win)
    bar.pack()
    win.update()
    seen = []
    for target in (0.3, 0.6, 0.5, 0.9):          # a report that dips must not pull the bar back
        bar.target = max(bar.target, target)
        for _ in range(5):
            bar.glide()
            seen.append(bar.fraction)
    assert seen == sorted(seen) and 0.5 < seen[-1] <= 0.9
