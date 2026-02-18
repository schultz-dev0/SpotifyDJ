"""
config.py
---------
Manages persistent user configuration stored as JSON.

Config file:          ~/.spotify-ai-dj/config.json
Spotify token cache:  ~/.spotify-ai-dj/.spotify_cache

The config directory is created automatically on first write.
Deleting it resets the app to first-run state.

Gemini API key priority (highest to lowest):
  1. Saved in config.json  (entered via the GUI setup screen or --set-key)
  2. GEMINI_API_KEY in the .env file  (set by the installer wizard)
  3. GEMINI_API_KEY environment variable  (set manually in the shell)
"""

import json
import os
from pathlib import Path

CONFIG_DIR         = Path.home() / ".spotify-ai-dj"
CONFIG_FILE        = CONFIG_DIR / "config.json"
SPOTIFY_CACHE_FILE = CONFIG_DIR / ".spotify_cache"

# Keys present here are always available in the loaded config dict,
# even if the file predates a new key being added.
DEFAULT_CONFIG: dict = {
    "gemini_api_key": "",
}


def _read_gemini_key_from_env() -> str:
    """
    Read the Gemini API key from the .env file or the shell environment.
    Called as a fallback when the key is not stored in config.json.
    """
    # Try .env file first (same directory as this script)
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        value = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if value:
                            return value
        except OSError:
            pass

    # Fall back to shell environment variable
    return os.environ.get("GEMINI_API_KEY", "")


def load_config() -> dict:
    """
    Load config from disk and merge with defaults.
    If the stored Gemini key is empty, falls back to the value in
    the .env file or the GEMINI_API_KEY environment variable.
    Returns defaults if the file does not exist or cannot be parsed.
    """
    if not CONFIG_FILE.exists():
        config = DEFAULT_CONFIG.copy()
    else:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            config = {**DEFAULT_CONFIG, **data}
        except (json.JSONDecodeError, IOError):
            config = DEFAULT_CONFIG.copy()

    # If the GUI hasn't been used yet to save a key, fall back to .env
    if not config.get("gemini_api_key", "").strip():
        env_key = _read_gemini_key_from_env()
        if env_key:
            config["gemini_api_key"] = env_key

    return config


def save_config(config: dict) -> None:
    """Write config to disk, creating the directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def is_configured() -> bool:
    """
    Return True only if a non-empty Gemini API key is available
    (from config.json, the .env file, or the environment).
    """
    return bool(load_config().get("gemini_api_key", "").strip())


def get_spotify_cache_path() -> str:
    """
    Return the path to the Spotify OAuth token cache file as a string.
    The config directory is created if it does not exist.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return str(SPOTIFY_CACHE_FILE)