import functools
import http.server
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ytdl  # noqa: E402


@pytest.fixture(scope="session")
def ffmpeg():
    path = ytdl.find_ffmpeg()
    if not path:
        pytest.skip("ffmpeg not available")
    return path


@pytest.fixture(scope="session")
def media_server(tmp_path_factory, ffmpeg):
    """A 6-second test video (picture and tone) served from this machine, so tests need no internet."""
    root = tmp_path_factory.mktemp("site")
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=duration=6:size=320x180:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "15", "-c:a", "aac", "-movflags", "+faststart", str(root / "sample.mp4")],
        check=True)
    (root / "other.mp4").write_bytes((root / "sample.mp4").read_bytes())  # a second, differently named video
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def media_url(media_server):
    return media_server + "/sample.mp4"


@pytest.fixture(scope="session")
def media_url_2(media_server):
    return media_server + "/other.mp4"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def probe(ffmpeg, path):
    """ffmpeg's description of a file: stream types, codecs, duration, tags."""
    return subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr


def duration(ffmpeg, path):
    import re
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe(ffmpeg, path))
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


@pytest.fixture(autouse=True)
def isolated_subscriptions(tmp_path, monkeypatch):
    """Tests never read or write the real ~/.ytdl or touch the real OS scheduler."""
    import subscriptions
    monkeypatch.setattr(subscriptions, "HOME_DIR", tmp_path / "ytdl-home")
    monkeypatch.setattr(subscriptions, "STORE", tmp_path / "ytdl-home" / "subscriptions.json")
    monkeypatch.setattr(subscriptions, "LOCK", tmp_path / "ytdl-home" / "subscriptions.lock")
    monkeypatch.setattr(subscriptions, "schedule_installed", lambda: False)
