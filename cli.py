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


# Persists between CLI calls within the same process (i.e. not between
# separate dj invocations — use the GUI for multi-session continue).
_cli_spotify_client: SpotifyClient | None = None


def _get_cli_client() -> SpotifyClient:
    global _cli_spotify_client
    if _cli_spotify_client is None:
        _cli_spotify_client = SpotifyClient()
    return _cli_spotify_client


def run_cli(request: str, is_continue: bool = False) -> int:
    """
    Execute a music request from the terminal.

    Args:
        request:     Natural language music request, e.g. "dark techno"
        is_continue: If True, generate fresh queries that avoid previous ones

    Returns:
        Exit code - 0 for success, 1 for any error.
    """
    if not is_configured():
        _error("No Gemini API key found.")
        _warn(
            "Run the app in GUI mode first to complete setup:\n"
            "    python main.py\n"
            "Or set your key directly:\n"
            "    python main.py --set-key YOUR_KEY_HERE"
        )
        return 1

    config  = load_config()
    api_key = config.get("gemini_api_key", "")
    client  = _get_cli_client()

    # Step 1 - AI generates search queries
    if is_continue:
        if not client.last_request:
            _error("Nothing playing yet — run a normal request first.")
            return 1
        _info(f'Continuing: "{client.last_request}"')
        try:
            from brain import get_continue_params
            directives = get_continue_params(client.last_request, client.last_queries, api_key)
        except Exception as e:
            _error(f"AI error: {e}")
            return 1
    else:
        _info(f'Request: "{request}"')
        client.last_request = request
        try:
            directives = get_vibe_params(request, api_key)
        except Exception as e:
            _error(f"AI error: {e}")
            return 1

    _info(f"AI: {directives.reasoning}")
    _info(f"Queries ({len(directives.queries)}): {directives.queries}")
    _info(f"Target queue: {directives.queue_size} tracks")

    # Step 2 - Search Spotify and start playback
    try:
        result = client.search_and_play(directives)
    except Exception as e:
        _error(f"Spotify error: {e}")
        return 1

    if result.success:
        _success(f"Now playing: {_BOLD}{result.first_track}{_RESET}")
        _info(f"{result.track_count} tracks queued from {result.queries_run} searches")
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

{_BOLD}Continue playing (fresh tracks, same vibe){_RESET}:
  dj --continue

{_BOLD}First-time setup from terminal{_RESET} (skips the GUI setup screen):
  python main.py --set-key YOUR_GEMINI_API_KEY
  dj --set-key YOUR_GEMINI_API_KEY

{_BOLD}Options{_RESET}:
  --set-key KEY   Save a Gemini API key without opening the GUI
  --help, -h      Show this message
""")