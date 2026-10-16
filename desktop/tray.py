"""Menu-bar (Mac) or system-tray (Windows, Linux) icon so ytdl can keep working with its window closed.

It runs beside the window's own event loop (pystray's "detached" mode). Everything it triggers is put on
the window's event queue, so the window stays the only thing that touches its widgets.
"""
import os
import sys


def label():
    return "menu bar" if sys.platform == "darwin" else "system tray"


class Tray:
    def __init__(self, events, icon_path):
        self.events = events
        self.icon_path = icon_path
        self.status = "ytdl is idle"
        self.icon = None

    def start(self):
        """Show the icon. Returns False (and does nothing) if this system can't."""
        if os.environ.get("YTDL_NO_TRAY"):
            return False
        try:
            import pystray
            from PIL import Image
            image = Image.open(self.icon_path).convert("RGBA").resize((64, 64))
            menu = pystray.Menu(
                pystray.MenuItem(lambda item: self.status, None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open ytdl", lambda *_: self.events.put(("tray", "show")), default=True),
                pystray.MenuItem("Check subscriptions now", lambda *_: self.events.put(("tray", "check"))),
                pystray.MenuItem("Quit ytdl", lambda *_: self.events.put(("tray", "quit"))),
            )
            self.icon = pystray.Icon("ytdl", image, "ytdl", menu)
            self.icon.run_detached()
            return True
        except Exception:  # no tray support (e.g. a Linux desktop without one): carry on without it
            self.icon = None
            return False

    def update(self, text):
        if self.icon is None or text == self.status:
            return
        self.status = text
        try:
            self.icon.title = text
            self.icon.update_menu()
        except Exception:
            pass

    def stop(self):
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
