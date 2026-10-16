"""Drives the window itself: queue, parallel downloads, retry, theme, picker. Skipped without a display."""
import time
import tkinter as tk

import pytest

import gui


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "SETTINGS", str(tmp_path / "settings.json"))
    try:
        window = gui.App()
    except tk.TclError:
        pytest.skip("no display available")
    window.folder.set(str(tmp_path / "out"))
    yield window
    window.destroy()


def pump(app, seconds, until):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.05)
        if until():
            return True
    return False


def statuses(app):
    return [app.tree.set(i, "status") for i in app.tree.get_children()]


def test_window_builds_and_switches_theme(app):
    for choice, expect in (("Dark", "dark"), ("Light", "light")):
        app.theme_choice.set(choice)
        app.on_theme_change()
        app.update()
        assert app.mode == expect
    assert app.cget("bg") == gui.PALETTES["light"]["bg"]


def test_queue_runs_two_downloads_at_once_and_records_history(app, media_url, media_url_2):
    app.parallel.set("2")
    app.speed.set("500 KB/s")  # slow enough that both are visibly running together
    app.on_limits_change()
    app.fmt_box.set("mp3 (audio)")
    app.urls.insert("end", media_url + "\n" + media_url_2)
    app.add_to_queue()
    assert len(app.tree.get_children()) == 2
    peak = 0

    def done():
        nonlocal peak
        peak = max(peak, statuses(app).count("Downloading"))
        return statuses(app) == ["Done", "Done"]

    assert pump(app, 60, done), statuses(app)
    assert peak == 2, "the two downloads should have run at the same time"
    assert len(app.history.get_children()) == 2


def test_failed_item_can_be_retried(app, tmp_path):
    app.retries.set("0")
    app.on_limits_change()
    app.urls.insert("end", "http://127.0.0.1:9/missing.mp4")
    app.add_to_queue()
    iid = app.tree.get_children()[0]
    assert pump(app, 30, lambda: app.tree.set(iid, "status") == "Failed")
    app.tree.selection_set(iid)
    app.retry_selected()
    assert app.tree.set(iid, "status") == "Queued"
    assert pump(app, 30, lambda: app.tree.set(iid, "status") == "Failed")


def test_queued_item_can_be_cancelled(app, media_url, media_url_2):
    app.parallel.set("1")
    app.speed.set("500 KB/s")
    app.on_limits_change()
    app.urls.insert("end", media_url + "\n" + media_url_2)
    app.add_to_queue()
    first, second = app.tree.get_children()
    app.tree.selection_set(second)
    app.cancel_selected()
    assert pump(app, 60, lambda: app.tree.set(second, "status") == "Cancelled")


def test_playlist_picker_lists_choices_and_queues_only_ticked_ones(app):
    entries = [{"title": f"Video {i}", "url": f"http://127.0.0.1:9/{i}.mp4", "duration": 60} for i in range(3)]
    app.urls.insert("end", "http://example.test/list")
    app.show_picker("http://example.test/list", entries)
    assert app.picker_list.size() == 3
    app.picker_list.select_clear(0, "end")
    app.picker_list.select_set(1)
    app.retries.set("0")
    app.on_limits_change()
    app.add_to_queue()
    rows = app.tree.get_children()
    assert len(rows) == 1 and app.tree.item(rows[0], "text") == "Video 1"


def test_subscription_check_queues_new_uploads_in_the_window(app, media_url, media_url_2, monkeypatch):
    import subscriptions
    state = {"entries": [{"id": "old", "url": media_url, "title": "Old", "upcoming": False}]}
    monkeypatch.setattr(subscriptions, "list_entries", lambda *a, **k: ("Chan", list(state["entries"])))
    options = dict(output=app.folder.get(), fmt="mp3", quality="best", naming="title-id", folders="flat",
                   sub_lang=None, sub_embed=False, extras=False)
    subscriptions.follow("https://www.youtube.com/@chan", options)
    app.refresh_subscriptions()
    assert app.subs_tree.item(app.subs_tree.get_children()[0], "text") == "Chan"
    state["entries"].insert(0, {"id": "fresh", "url": media_url_2, "title": "Fresh", "upcoming": False})
    app.check_subscriptions(force=True)
    assert pump(app, 30, lambda: len(app.tree.get_children()) == 1)
    assert pump(app, 60, lambda: statuses(app) == ["Done"])
    (iid,) = app.tree.get_children()
    assert app.items[iid]["url"] == media_url_2   # the new upload, not the video that was already there


def test_closing_the_window_quits_when_there_is_no_tray(app):
    app.tray = None
    closed = []
    app.destroy = lambda: closed.append(True)
    app.on_close()
    assert closed == [True]


def test_closing_the_window_hides_it_when_the_tray_is_running(app, monkeypatch):
    class FakeTray:
        stopped = False
        updates = []
        def update(self, text): self.updates.append(text)
        def stop(self): self.stopped = True
    app.tray = FakeTray()
    app.settings["tray_told"] = True           # skip the one-time explanation dialog
    hidden = []
    app.withdraw = lambda: hidden.append(True)
    app.on_close()
    assert hidden == [True] and not app.tray.stopped
    app.update_tray()
    assert app.tray.updates[-1] == "ytdl is idle"


def test_tray_menu_actions_reach_the_window(app, monkeypatch):
    shown = []
    monkeypatch.setattr(app, "show_window", lambda: shown.append(True))
    app.events.put(("tray", "show"))
    pump(app, 2, lambda: bool(shown))
    assert shown == [True]


def test_ticked_checkboxes_are_filled_with_the_accent_colour_in_both_themes(app):
    """Regression: in light mode a ticked box looked empty because the tick was white on white."""
    from tkinter import ttk
    for mode in ("light", "dark"):
        app.set_mode(mode)
        mapping = dict((state, color) for state, color in ttk.Style(app).map("TCheckbutton", "indicatorbackground"))
        assert mapping.get("selected") == gui.PALETTES[mode]["accent"]


def test_the_sites_label_wraps_instead_of_running_off_the_window(app):
    labels = [w for w in gui.find_widgets(app.urls_frame, gui.ttk.Label) if "Paste links" in str(w.cget("text"))]
    assert labels and int(labels[0].cget("wraplength")) > 0
