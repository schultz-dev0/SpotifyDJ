"""
spotify_client.py
-----------------
Handles Spotify OAuth authentication and playback control.

Credentials are loaded from a .env file in the same directory as this script.
The .env file is created automatically by the installer (install.sh / install.bat
/ install_mac.sh). If you are setting up manually, create a .env file with:

  SPOTIPY_CLIENT_ID=your_client_id_here
  SPOTIPY_CLIENT_SECRET=your_client_secret_here
  SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback

Get your credentials at: https://developer.spotify.com/dashboard
Set the Redirect URI in your app settings to: http://127.0.0.1:8888/callback
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from config import get_spotify_cache_path

# ------------------------------------------------------------------
# Load credentials from .env file
# ------------------------------------------------------------------
def _load_env_file() -> None:
    """
    Parse the .env file next to this script and inject values into
    os.environ. Uses python-dotenv if available, otherwise falls back
    to a simple manual parser so the app works even if dotenv is missing.
    """
    # Resolve .env relative to this file, not the working directory
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, override=False)
        return
    except ImportError:
        pass

    # Fallback: minimal .env parser (handles KEY=value and KEY="value")
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)   # setdefault: don't clobber shell env


_load_env_file()

# Read credentials from environment (set by .env loader above, the shell,
# or the Spotify SDK's own env-var support).
SPOTIFY_CLIENT_ID     = os.environ.get("SPOTIPY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI  = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

# ------------------------------------------------------------------
# Friendly startup check - fail early with a clear message
# ------------------------------------------------------------------
def _check_spotify_credentials() -> None:
    """
    Print a clear error and exit if Spotify credentials are missing.
    Called once at import time so every entry point (GUI, CLI) gets the message.
    """
    if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
        return

    missing = []
    if not SPOTIFY_CLIENT_ID:
        missing.append("  SPOTIPY_CLIENT_ID")
    if not SPOTIFY_CLIENT_SECRET:
        missing.append("  SPOTIPY_CLIENT_SECRET")

    print(
        "\n[error] Spotify credentials are not configured.\n"
        "Missing from .env:\n"
        + "\n".join(missing) + "\n\n"
        "To fix this:\n"
        "  1. Go to https://developer.spotify.com/dashboard and create an app.\n"
        "  2. Set the Redirect URI to:  http://127.0.0.1:8888/callback\n"
        "  3. Copy your Client ID and Client Secret.\n"
        "  4. Create a file called  .env  in the app folder with:\n\n"
        "       SPOTIPY_CLIENT_ID=your_id_here\n"
        "       SPOTIPY_CLIENT_SECRET=your_secret_here\n"
        "       SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback\n\n"
        "  Or re-run the installer:  bash install.sh  (Linux)\n"
        "                            bash install_mac.sh  (macOS)\n"
        "                            install.bat  (Windows)\n",
        file=sys.stderr,
    )
    sys.exit(1)


_check_spotify_credentials()
# ------------------------------------------------------------------

# OAuth scopes required by this app
SPOTIFY_SCOPE = " ".join([
    "user-modify-playback-state",
    "user-read-playback-state",
    "user-read-private",
])


@dataclass
class PlayResult:
    """Returned by SpotifyClient.search_and_play() to describe the outcome."""
    success: bool
    message: str
    first_track: str = field(default="")   # "Track Name - Artist"
    track_count: int = field(default=0)


class SpotifyClient:
    """
    Thin wrapper around spotipy for authentication and playback.

    The OAuth flow runs lazily on the first call to search_and_play().
    The resulting token is cached to disk, so the browser login only
    happens once per machine.
    """

    def __init__(self):
        self._sp: Optional[spotipy.Spotify] = None

    def _get_client(self) -> spotipy.Spotify:
        """Return an authenticated Spotify client, creating one if needed."""
        if self._sp is None:
            auth = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope=SPOTIFY_SCOPE,
                open_browser=True,
                cache_handler=spotipy.cache_handler.CacheFileHandler(
                    cache_path=get_spotify_cache_path()
                ),
            )
            self._sp = spotipy.Spotify(auth_manager=auth)
        return self._sp

    def _find_device_id(self) -> Optional[str]:
        """
        Return the ID of an active Spotify device.
        Falls back to the first available device if none is currently active.
        Returns None if no devices are found at all.
        """
        devices = self._get_client().devices().get("devices", [])
        active  = next((d for d in devices if d["is_active"]), None)
        if active:
            return active["id"]
        if devices:
            return devices[0]["id"]
        return None

    def search_and_play(self, query: str) -> PlayResult:
        """
        Search Spotify for `query` and immediately start playback.
        Returns a PlayResult describing what happened.
        """
        # Authenticate
        try:
            sp = self._get_client()
        except Exception as e:
            return PlayResult(success=False, message=f"Authentication failed: {e}")

        # Locate a playback device
        device_id = self._find_device_id()
        if not device_id:
            return PlayResult(
                success=False,
                message="No Spotify device found. Open Spotify on any device first.",
            )

        # Search for tracks
        try:
            results = sp.search(q=query, limit=10, type="track", market="from_token")
            tracks  = results["tracks"]["items"]
        except Exception as e:
            return PlayResult(success=False, message=f"Search error: {e}")

        if not tracks:
            return PlayResult(success=False, message=f'No tracks found for: "{query}"')

        # Start playback
        uris   = [t["uri"] for t in tracks]
        first  = tracks[0]
        artist = first["artists"][0]["name"] if first["artists"] else "Unknown Artist"
        label  = f"{first['name']} - {artist}"

        try:
            sp.start_playback(device_id=device_id, uris=uris)
        except Exception as e:
            return PlayResult(success=False, message=f"Playback error: {e}")

        return PlayResult(
            success=True,
            message="Playback started.",
            first_track=label,
            track_count=len(tracks),
        )