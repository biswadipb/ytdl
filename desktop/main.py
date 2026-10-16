"""Entry point: opens the window, or runs the CLI when arguments are given."""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        import ytdl
        sys.exit(ytdl.cli(sys.argv[1:]))
    import gui
    gui.main()
