import functools
import http.server
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

os.environ.setdefault("YTDL_NO_TRAY", "1")
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "desktop"))
import ytdl  # noqa: E402


@pytest.fixture(scope="session")
def ffmpeg():
    path = ytdl.find_ffmpeg()
    if not path:
        pytest.skip("ffmpeg not available")
    return path


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="session")
def media(tmp_path_factory, ffmpeg):
    """Two short test videos served from this machine, so tests need no internet."""
    root = tmp_path_factory.mktemp("site")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x180:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-movflags", "+faststart", str(root / "one.mp4")], check=True)
    (root / "two.mp4").write_bytes((root / "one.mp4").read_bytes())
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield {"one": f"http://127.0.0.1:{server.server_port}/one.mp4", "two": f"http://127.0.0.1:{server.server_port}/two.mp4"}
    server.shutdown()
