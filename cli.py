"""
cli.py
------
Headless CLI mode for Spotify AI DJ.

Invoked automatically by main.py when arguments are passed:
  dj "play some dark techno"
  python main.py "relaxing lo-fi"

Prints coloured status output to the terminal and exits when done.
No GUI is launched. Safe to run over SSH or in scripts.
"""
# The only reason I even implimented this was because SOMETIMES I don't wanna open a gui to do something, SOMETIMES a brother just wants to run something via command line. I hope others can relate to this hashtag struggle...

import sys

from brain import get_vibe_params
from config import is_configured, load_config
from spotify_client import SpotifyClient

# ------------------------------------------------------------------
# Colour helpers (auto-disabled when output is not a terminal,
# e.g. when piped into a script or log file)
# ------------------------------------------------------------------
if sys.stdout.isatty():
    _RESET  = "\033[0m"
    _BOLD   = "\033[1m"
    _GREEN  = "\033[32m"
    _YELLOW = "\033[33m"
    _RED    = "\033[31m"
    _CYAN   = "\033[36m"
else:
    _RESET = _BOLD = _GREEN = _YELLOW = _RED = _CYAN = ""


def _info(msg: str)    -> None: print(f"{_CYAN}{_BOLD}[*]{_RESET} {msg}")
def _success(msg: str) -> None: print(f"{_GREEN}{_BOLD}[+]{_RESET} {msg}")
def _warn(msg: str)    -> None: print(f"{_YELLOW}{_BOLD}[!]{_RESET} {msg}")
def _error(msg: str)   -> None: print(f"{_RED}{_BOLD}[x]{_RESET} {msg}")


def run_cli(request: str) -> int:
    """
    Execute a single music request from the terminal.

    Args:
        request: Natural language music request, e.g. "dark techno"

    Returns:
        Exit code - 0 for success, 1 for any error.
    """
    # Guard: require setup before running headlessly.
    if not is_configured():
        _error("No Gemini API key found.")
        _warn(
            "Run the app in GUI mode first to complete setup:\n"
            "    python main.py\n"
            "Or set your key directly:\n"
            "    python main.py --set-key YOUR_KEY_HERE"
        )
        return 1

    config = load_config()

    # Step 1 - AI generates a Spotify search query
    _info(f'Request: "{request}"')
    try:
        directives = get_vibe_params(request, config.get("gemini_api_key", ""))
        _info(f"AI reasoning:  {directives.reasoning}")
        _info(f"Search query:  {directives.search_query}")
    except Exception as e:
        _error(f"AI error: {e}")
        return 1

    # Step 2 - Search Spotify and start playback
    try:
        client = SpotifyClient()
        result = client.search_and_play(directives.search_query)
    except Exception as e:
        _error(f"Spotify error: {e}")
        return 1

    if result.success:
        extra = f" (+{result.track_count - 1} more)" if result.track_count > 1 else ""
        _success(f"Now playing: {_BOLD}{result.first_track}{_RESET}{extra}")
        return 0
    else:
        _error(result.message)
        return 1


def run_set_key(key: str) -> int:
    """
    Save a Gemini API key from the command line without opening the GUI.
    Called when the user runs:  python main.py --set-key AIza...
    """
    from config import save_config
    key = key.strip()
    if len(key) < 20:
        _error("That doesn't look like a valid key.")
        return 1
    config = load_config()
    config["gemini_api_key"] = key
    save_config(config)
    _success("Gemini API key saved.")
    _info("You can now use the CLI:  dj \"your request\"")
    return 0


def print_help() -> None:
    """Print CLI usage information."""
    print(f"""
{_BOLD}Spotify AI DJ{_RESET}

{_BOLD}GUI mode{_RESET} (no arguments):
  python main.py
  dj

{_BOLD}CLI mode{_RESET} (play immediately from terminal):
  dj "dark techno"
  dj "relaxing lo-fi for studying"
  python main.py "90s hip hop"

{_BOLD}First-time setup from terminal{_RESET} (skips the GUI setup screen):
  python main.py --set-key YOUR_GEMINI_API_KEY
  dj --set-key YOUR_GEMINI_API_KEY

{_BOLD}Options{_RESET}:
  --set-key KEY   Save a Gemini API key without opening the GUI
  --help, -h      Show this message
""")