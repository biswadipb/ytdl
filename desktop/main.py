"""Entry point: opens the window, or runs the CLI when arguments are given."""
import os
import sys

if __name__ == "__main__":
    # Windowed builds have no console, so printing would crash without these.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if len(sys.argv) > 1:
        import ytdl
        sys.exit(ytdl.cli(sys.argv[1:]))
    import gui
    gui.main()
