"""
main.py
-------
Entry point for Spotify AI DJ.

Routing:
  No arguments          ->  GUI mode   (opens the graphical window)
  "any text request"    ->  CLI mode   (plays immediately, no GUI)
  --set-key KEY         ->  Save Gemini API key from terminal
  --help / -h           ->  Print usage

Examples:
  python main.py                        # open GUI
  python main.py "dark techno"          # play immediately
  python main.py --set-key AIza...      # save API key
  dj "late night lo-fi"                 # same as above via symlink
"""

import sys


def main() -> None:
    args = sys.argv[1:]

    # No arguments - launch the GUI
    if not args:
        from app import run
        run()
        return

    # --help / -h
    if args[0] in ("--help", "-h"):
        from cli import print_help
        print_help()
        return

    # --set-key KEY  (save Gemini API key from terminal without opening GUI)
    if args[0] == "--set-key":
        if len(args) < 2:
            print("Usage:  python main.py --set-key YOUR_KEY_HERE")
            sys.exit(1)
        from cli import run_set_key
        sys.exit(run_set_key(args[1]))

    # Any other argument is treated as a music request for CLI mode
    request = " ".join(args)
    from cli import run_cli
    sys.exit(run_cli(request))


if __name__ == "__main__":
    main()