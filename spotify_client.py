"""
spotify_client.py
-----------------
Handles Spotify OAuth authentication and playback control.

DEVELOPER NOTE:
  The credentials below belong to the Spotify app registered at
  https://developer.spotify.com/dashboard

  If you fork this project and distribute it yourself, create your own
  Spotify app and replace these values. In your app settings, add:
    Redirect URI:  http://127.0.0.1:8888/callback

  End users never need to touch this file.
"""

from dataclasses import dataclass, field
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from config import get_spotify_cache_path

# ------------------------------------------------------------------
# Spotify app credentials - replace if you fork this project
# ------------------------------------------------------------------
SPOTIFY_CLIENT_ID     = "5bdc81a576f44cf5a566ef4fc793ed01"
SPOTIFY_CLIENT_SECRET = "9073a2be454348fa854871da20c33c14"
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8888/callback"
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