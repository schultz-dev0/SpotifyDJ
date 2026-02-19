"""
spotify_client.py
-----------------
Handles Spotify OAuth authentication and playback control.

Runs multiple AI-generated search queries sequentially, deduplicates
results by track URI, shuffles for variety, and queues up to queue_size tracks.

Credentials are loaded from a .env file in the same directory as this script.
Create one manually if needed:

  SPOTIPY_CLIENT_ID=your_client_id_here
  SPOTIPY_CLIENT_SECRET=your_client_secret_here
  SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback

Get credentials at: https://developer.spotify.com/dashboard
Set Redirect URI to: http://127.0.0.1:8888/callback
"""

import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import json
import re
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from config import get_spotify_cache_path

# ------------------------------------------------------------------
# Load credentials from .env file
# ------------------------------------------------------------------
def _load_env_file() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, override=False)
        return
    except ImportError:
        pass
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

SPOTIFY_CLIENT_ID     = os.environ.get("SPOTIPY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI  = os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

# Tracks fetched per individual search query.
# Spotify reduced the search limit to 10 in their February 2026 API changes.
RESULTS_PER_QUERY = 10   # Spotify's current maximum per request
SEARCH_PAGES = 5           # Pages fetched per query -> 50 tracks per query max


def _check_spotify_credentials() -> None:
    if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
        return
    missing = []
    if not SPOTIFY_CLIENT_ID:     missing.append("  SPOTIPY_CLIENT_ID")
    if not SPOTIFY_CLIENT_SECRET: missing.append("  SPOTIPY_CLIENT_SECRET")
    print(
        "\n[error] Spotify credentials are not configured.\n"
        "Missing from .env:\n" + "\n".join(missing) + "\n\n"
        "Fix: go to https://developer.spotify.com/dashboard, create an app,\n"
        "set Redirect URI to http://127.0.0.1:8888/callback, then add the\n"
        "Client ID and Secret to a .env file in the app folder.\n"
        "Or re-run the installer to be guided through setup.\n",
        file=sys.stderr,
    )
    sys.exit(1)


_check_spotify_credentials()

SPOTIFY_SCOPE = " ".join([
    "user-modify-playback-state",
    "user-read-playback-state",
    "user-read-currently-playing",
    "user-library-modify",
    # user-library-read excluded: contains endpoint returns 403 for new apps
    "user-read-private",
    "playlist-read-private",
    "playlist-read-collaborative",
])


@dataclass
class PlayResult:
    """Returned by SpotifyClient.search_and_play() to describe the outcome."""
    success:     bool
    message:     str
    first_track: str = field(default="")
    track_count: int = field(default=0)
    queries_run: int = field(default=0)


class SpotifyClient:
    """
    Wrapper around spotipy for authentication and playback.
    OAuth runs lazily on the first call and is cached to disk.
    """

    def __init__(self):
        self._sp: Optional[spotipy.Spotify] = None
        # Session state - persists between plays for continue functionality
        self.last_request:  str       = ""
        self.last_queries:  list[str] = []
        self.played_uris:   set[str]  = set()
        self._liked_ids:    set[str]  = set()   # local like state (API endpoint restricted)

    def _get_client(self) -> spotipy.Spotify:
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
        devices = self._get_client().devices().get("devices", [])
        active  = next((d for d in devices if d["is_active"]), None)
        if active:
            return active["id"]
        if devices:
            return devices[0]["id"]
        return None

    def _get_token(self) -> str:
        """
        Get a valid access token, refreshing if expired.

        Strategy: tell spotipy's auth manager to validate/refresh the token
        (which updates the cache file if needed), then read the token string
        directly from the cache. We use the cache rather than spotipy's own
        search wrappers because those add extra parameters that cause 400s.
        """
        auth = self._get_client().auth_manager
        # This triggers a refresh if the token is expired or about to expire
        token_info = auth.get_cached_token()
        if auth.is_token_expired(token_info):
            token_info = auth.refresh_access_token(token_info["refresh_token"])
        return token_info["access_token"]

    def _search_page(self, query: str, token: str, offset: int) -> list[dict]:
        """Fetch one page of search results."""
        try:
            resp = requests.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "q":      query,
                    "type":   "track",
                    "limit":  str(RESULTS_PER_QUERY),
                    "offset": str(offset),
                },
                timeout=10,
            )
            if not resp.ok:
                print(f"[spotify] HTTP {resp.status_code} for '{query}' offset={offset}: {resp.text[:200]}")
                return []
            return resp.json().get("tracks", {}).get("items", [])
        except Exception as e:
            print(f"[spotify] search error for '{query}' offset={offset}: {e}")
            return []

    def _run_single_search(self, query: str) -> list[dict]:
        """
        Fetch multiple pages for a single query to work around Spotify's
        limit of 10 results per request. Fetches SEARCH_PAGES pages,
        giving up to RESULTS_PER_QUERY * SEARCH_PAGES tracks per query.
        """
        try:
            token  = self._get_token()
            tracks = []
            for page in range(SEARCH_PAGES):
                offset = page * RESULTS_PER_QUERY
                page_tracks = self._search_page(query, token, offset)
                tracks.extend(page_tracks)
                # Stop early if Spotify returned fewer results than the limit
                # (means we've hit the end of the result set)
                if len(page_tracks) < RESULTS_PER_QUERY:
                    break
            print(f"[spotify] '{query}' -> {len(tracks)} tracks")
            return tracks
        except Exception as e:
            print(f"[spotify] search failed for '{query}': {e}")
            return []

    def _build_track_pool(self, queries: list[str], target: int) -> list[dict]:
        """
        Run all queries sequentially, deduplicate by URI, and shuffle.

        Sequential is simpler and reliable. With 8-10 queries at ~0.3s each
        this takes 2-3 seconds total — fast enough and no threading complexity.

        Shuffling before truncation gives a varied mix across all queries
        rather than all results from query 1 then all from query 2.
        """
        all_tracks: list[dict] = []

        for query in queries:
            all_tracks.extend(self._run_single_search(query))

        # Deduplicate by URI, preserving first encounter
        seen:   set[str]   = set()
        unique: list[dict] = []
        for track in all_tracks:
            uri = track.get("uri", "")
            if uri and uri not in seen:
                seen.add(uri)
                unique.append(track)

        print(f"[spotify] {len(unique)} unique tracks from {len(queries)} queries")

        # Shuffle for variety then trim to target size
        random.shuffle(unique)
        return unique[:target]

    def get_current_track(self) -> Optional[dict]:
        """
        Return info about the currently playing track, or None.
        Dict keys: id, name, artist, uri, is_liked

        is_liked is tracked locally since Spotify restricts the
        saved-tracks-contains endpoint for new apps (returns 403).
        """
        try:
            current = self._get_client().currently_playing()
            if not current or not current.get("is_playing"):
                return None
            item = current.get("item")
            if not item:
                return None
            track_id = item["id"]
            return {
                "id":       track_id,
                "uri":      item["uri"],
                "name":     item["name"],
                "artist":   item["artists"][0]["name"] if item.get("artists") else "Unknown",
                "is_liked": track_id in self._liked_ids,
            }
        except Exception as e:
            print(f"[spotify] get_current_track error: {e}")
            return None

    def like_current_track(self) -> tuple[bool, str]:
        """
        Toggle like on the currently playing track. Returns (success, message).
        Liked state is tracked locally since the Spotify contains endpoint
        is restricted for new apps.
        """
        track = self.get_current_track()
        if not track:
            return False, "Nothing is currently playing."
        try:
            sp = self._get_client()
            if track["is_liked"]:
                sp.current_user_saved_tracks_delete([track["id"]])
                self._liked_ids.discard(track["id"])
                return True, f"Unliked: {track['name']} - {track['artist']}"
            else:
                sp.current_user_saved_tracks_add([track["id"]])
                self._liked_ids.add(track["id"])
                return True, f"Liked: {track['name']} - {track['artist']}"
        except Exception as e:
            return False, f"Could not update like: {e}"

    def skip_track(self) -> tuple[bool, str]:
        """Skip to the next track."""
        try:
            device_id = self._find_device_id()
            self._get_client().next_track(device_id=device_id)
            return True, "Skipped to next track."
        except Exception as e:
            return False, f"Skip error: {e}"

    def previous_track(self) -> tuple[bool, str]:
        """Go back to the previous track."""
        try:
            device_id = self._find_device_id()
            self._get_client().previous_track(device_id=device_id)
            return True, "Went to previous track."
        except Exception as e:
            return False, f"Previous error: {e}"

    def get_playlist_tracks(self, playlist_url: str) -> list[dict]:
        """
        Fetch all tracks from a Spotify playlist URL or URI.
        Uses raw HTTP (not spotipy wrapper) to avoid market=None / fields=None
        being sent as explicit params which Spotify rejects with 403.
        Handles pagination automatically for large playlists.
        """
        import re
        match = re.search(r"playlist[/:]([A-Za-z0-9]+)", playlist_url)
        if not match:
            raise ValueError(f"Could not extract playlist ID from: {playlist_url!r}")

        playlist_id = match.group(1)
        token  = self._get_token()
        tracks = []
        url    = f"https://api.spotify.com/v1/playlists/{playlist_id}/items"

        while url:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"limit": 100, "fields": "next,items(track(id,uri,name,artists))"},
                timeout=15,
            )
            if not resp.ok:
                raise Exception(f"http status: {resp.status_code} - {resp.text[:200]}")
            data  = resp.json()
            items = data.get("items", [])
            for item in items:
                track = item.get("track")
                if track and track.get("uri") and track.get("id"):
                    tracks.append(track)
            url = data.get("next")  # None when no more pages

        print(f"[spotify] Fetched {len(tracks)} tracks from playlist {playlist_id}")
        return tracks

    def search_and_play_mixed(
        self,
        playlist_tracks: list[dict],
        directives,
        mix_ratio: float = 0.5,
    ) -> PlayResult:
        """
        Mix playlist tracks with AI-searched tracks and start playback.
        mix_ratio: fraction of queue from the playlist (0.5 = 50/50).
        Tracks are interleaved so playlist and discovered songs alternate.
        """
        import random

        queue_size = max(1, min(200, getattr(directives, "queue_size", 50)))
        n_playlist = int(queue_size * mix_ratio)
        n_search   = queue_size - n_playlist

        # Shuffle and sample from the playlist
        playlist_sample = list(playlist_tracks)
        random.shuffle(playlist_sample)
        playlist_sample = playlist_sample[:n_playlist]

        # Build search pool, excluding tracks already in the playlist
        playlist_uris = {t.get("uri") for t in playlist_tracks}
        search_pool   = self._build_track_pool(directives.queries, target=n_search * 3)
        search_pool   = [t for t in search_pool if t.get("uri") not in playlist_uris]
        search_pool   = search_pool[:n_search]

        # Interleave: playlist, search, playlist, search...
        mixed = []
        pi, si = 0, 0
        while pi < len(playlist_sample) or si < len(search_pool):
            if pi < len(playlist_sample):
                mixed.append(playlist_sample[pi]); pi += 1
            if si < len(search_pool):
                mixed.append(search_pool[si]); si += 1

        if not mixed:
            return PlayResult(success=False, message="No tracks found to queue.")

        device_id = self._find_device_id()
        if not device_id:
            return PlayResult(
                success=False,
                message="No Spotify device found. Open Spotify on any device first.",
            )

        uris   = [t["uri"] for t in mixed]
        first  = mixed[0]
        artist = first["artists"][0]["name"] if first.get("artists") else "Unknown"
        label  = f"{first['name']} - {artist}"

        try:
            self._get_client().start_playback(device_id=device_id, uris=uris)
        except Exception as e:
            return PlayResult(success=False, message=f"Playback error: {e}")

        if hasattr(directives, "queries"):
            self.last_queries = directives.queries
        for t in mixed:
            uri = t.get("uri")
            if uri:
                self.played_uris.add(uri)

        return PlayResult(
            success=True,
            message="Playback started.",
            first_track=label,
            track_count=len(mixed),
            queries_run=len(getattr(directives, "queries", [])),
        )

    def search_and_play(self, directives) -> PlayResult:
        """
        Build a queue from AI-generated directives and start playback.
        Accepts a DJDirectives object (from brain.py) or a plain string.
        """
        # Authenticate
        try:
            self._get_client()
        except Exception as e:
            return PlayResult(success=False, message=f"Authentication failed: {e}")

        # Find a playback device
        device_id = self._find_device_id()
        if not device_id:
            return PlayResult(
                success=False,
                message="No Spotify device found. Open Spotify on any device first.",
            )

        # Unpack directives
        if hasattr(directives, "queries"):
            queries    = directives.queries
            queue_size = max(1, min(100, directives.queue_size))
        else:
            queries    = [str(directives)]
            queue_size = 50

        if not queries:
            return PlayResult(success=False, message="No search queries were generated.")

        # Build the track pool, then filter out anything already played
        tracks = self._build_track_pool(queries, target=queue_size * 2)  # fetch extra to absorb filtering
        tracks = [t for t in tracks if t.get("uri") not in self.played_uris]
        tracks = tracks[:queue_size]

        if not tracks:
            return PlayResult(
                success=False,
                message=f"No tracks found. Tried {len(queries)} queries: {queries}",
            )

        # Start playback
        uris   = [t["uri"] for t in tracks]
        first  = tracks[0]
        artist = first["artists"][0]["name"] if first.get("artists") else "Unknown"
        label  = f"{first['name']} - {artist}"

        try:
            self._get_client().start_playback(device_id=device_id, uris=uris)
        except Exception as e:
            return PlayResult(success=False, message=f"Playback error: {e}")

        # Store session state for continue functionality
        if hasattr(directives, "queries"):
            self.last_queries = directives.queries
        for t in tracks:
            uri = t.get("uri")
            if uri:
                self.played_uris.add(uri)

        return PlayResult(
            success=True,
            message="Playback started.",
            first_track=label,
            track_count=len(tracks),
            queries_run=len(queries),
        ) 

# if i get one more http 400 i will actually fucking crash out dude 20:20 feb 18
# oh the issue was I was making the API call wrong... whoops, works fine now, still collects only 10 raw tracks per request 20:26
# this will probably be frowned upon by I used claude to add a bunch of GUI specific stuff and media playback. Code might now look different here than everyone else. Oh well

# tracking playback is ehhh work in progress, since it's not available via spotify I need to do it locally. Noted, do not ask AI to do a thing you can do yourself

# I have added a feature which SHOULD work that will allow you to paste a link and ask for "similar music" it accepts playlists and artists