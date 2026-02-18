"""
config.py
---------
Manages persistent user configuration stored as JSON.

Config file:          ~/.spotify-ai-dj/config.json
Spotify token cache:  ~/.spotify-ai-dj/.spotify_cache

The config directory is created automatically on first write.
Deleting it resets the app to first-run state.
"""

import json
from pathlib import Path

CONFIG_DIR         = Path.home() / ".spotify-ai-dj"
CONFIG_FILE        = CONFIG_DIR / "config.json"
SPOTIFY_CACHE_FILE = CONFIG_DIR / ".spotify_cache"

# Keys present here are always available in the loaded config dict,
# even if the file predates a new key being added.
DEFAULT_CONFIG: dict = {
    "gemini_api_key": "",
}


def load_config() -> dict:
    """
    Load config from disk and merge with defaults.
    Returns defaults if the file does not exist or cannot be parsed.
    """
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULT_CONFIG, **data}
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Write config to disk, creating the directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def is_configured() -> bool:
    """Return True only if a non-empty Gemini API key has been saved."""
    return bool(load_config().get("gemini_api_key", "").strip())


def get_spotify_cache_path() -> str:
    """
    Return the path to the Spotify OAuth token cache file as a string.
    The config directory is created if it does not exist.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return str(SPOTIFY_CACHE_FILE)