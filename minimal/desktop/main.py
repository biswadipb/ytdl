"""Entry point for ytdl minimal."""
import os
import sys

if __name__ == "__main__":
    # Windowed builds have no console, so printing would crash without these.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if "--selftest" in sys.argv:   # used by the build to check the packaged app really contains everything
        import app
        import ytdl
        ok = bool(ytdl.find_ffmpeg()) and bool(ytdl.yt_dlp.version.__version__) and hasattr(app, "App")
        sys.exit(0 if ok else 1)
    import app
    app.main()
