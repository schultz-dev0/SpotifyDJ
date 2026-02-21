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
from preferences import load_preferences, record_like, record_skip, record_request, score_tracks, SkipDetector

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
        self.skip_detector: SkipDetector = SkipDetector(self)
        self._log_fn = print   # GUI can override: self._spotify._log_fn = self._log

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


    def ensure_spotify_open(self) -> bool:
        """
        If no Spotify device is found, attempt to launch Spotify and wait
        for it to appear. Returns True if a device is available afterwards.

        Tries platform-appropriate launch commands. Waits up to 15 seconds
        for Spotify to register with the API before giving up.
        """
        if self._find_device_id():
            return True   # already open

        import subprocess, sys, time

        print("[spotify] No device found — attempting to launch Spotify...")

        # Platform launch commands, tried in order
        launch_commands = []
        if sys.platform.startswith("linux"):
            launch_commands = [
                ["spotify"],                         # native install / PATH
                ["flatpak", "run", "com.spotify.Client"],  # Flatpak (most common on modern distros)
                ["snap", "run", "spotify"],          # Snap
            ]
        elif sys.platform == "darwin":
            launch_commands = [
                ["open", "-a", "Spotify"],
            ]
        elif sys.platform == "win32":
            import os
            spotify_exe = os.path.expandvars(
                r"%APPDATA%\Spotify\Spotify.exe"
            )
            launch_commands = [[spotify_exe]]

        launched = False
        for cmd in launch_commands:
            try:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                launched = True
                print(f"[spotify] Launched via: {' '.join(cmd)}")
                break
            except (FileNotFoundError, OSError):
                continue

        if not launched:
            print("[spotify] Could not find Spotify executable — install Spotify or open it manually")
            return False

        # Poll for up to 15 seconds for a device to appear
        for i in range(15):
            time.sleep(1)
            if self._find_device_id():
                print(f"[spotify] Device ready after {i+1}s")
                return True

        print("[spotify] Spotify launched but no device registered within 15s")
        return False

    def ensure_local_llm_warm(self) -> None:
        """
        If a local LLM is configured, wake it up with a minimal prompt so the
        model is loaded into memory before the user's first real request.

        Ollama lazy-loads models on first use which causes a 5-30 second stall.
        Sending a tiny warmup prompt at app start hides that latency entirely.
        Runs in a background thread so it never blocks the UI.
        """
        import threading

        def _warm():
            try:
                from brain import LOCAL_LLM_BASE_URL, LOCAL_LLM_API_KEY, LOCAL_LLM_MODEL
                if not LOCAL_LLM_BASE_URL:
                    return   # no local LLM configured

                import openai
                print(f"[llm] Warming up {LOCAL_LLM_MODEL}...")
                client = openai.OpenAI(
                    base_url=LOCAL_LLM_BASE_URL.rstrip("/") + "/v1",
                    api_key=LOCAL_LLM_API_KEY or "ollama",
                )
                client.chat.completions.create(
                    model=LOCAL_LLM_MODEL,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                )
                print(f"[llm] {LOCAL_LLM_MODEL} is warm")
            except Exception as e:
                print(f"[llm] Warmup failed (non-fatal): {e}")

        threading.Thread(target=_warm, daemon=True).start()

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


    def _search_albums(self, query: str) -> list[dict]:
        """
        Search for albums matching a query string.
        Returns a list of album dicts with id, name, artists.
        Used for OST/soundtrack mode.
        """
        try:
            token = self._get_token()
            resp  = requests.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": query, "type": "album", "limit": "5"},
                timeout=10,
            )
            if not resp.ok:
                print(f"[spotify] album search failed for '{query}': {resp.status_code}")
                return []
            items = resp.json().get("albums", {}).get("items", [])
            print(f"[spotify] album search '{query}' -> {len(items)} albums")
            return items
        except Exception as e:
            print(f"[spotify] album search error for '{query}': {e}")
            return []

    def _fetch_album_tracks(self, album_id: str) -> list[dict]:
        """
        Fetch all tracks from an album by its Spotify album ID.
        Returns tracks in the same format as _search_page() so the
        rest of the pipeline handles them identically.
        """
        try:
            token  = self._get_token()
            tracks = []
            url    = f"https://api.spotify.com/v1/albums/{album_id}/tracks"
            while url:
                resp = requests.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"limit": "50"},
                    timeout=10,
                )
                if not resp.ok:
                    break
                data  = resp.json()
                items = data.get("items", [])
                for item in items:
                    # Normalise to the same shape as track-search results
                    item["album"] = {"id": album_id}
                tracks.extend(items)
                url = data.get("next")
            return tracks
        except Exception as e:
            print(f"[spotify] album track fetch error: {e}")
            return []

    def _build_album_pool(self, queries: list[str], target: int) -> list[dict]:
        """
        OST/soundtrack mode search pipeline.

        For each query:
          1. Search Spotify for albums matching the query
          2. Take the top result (most relevant album)
          3. Fetch every track from that album

        Deduplicates by URI across all albums, then shuffles.
        Much more precise than track search for soundtracks because album
        search uses richer metadata (genre, label, description) to
        disambiguate "Destiny Original Soundtrack" from songs called Destiny.
        """
        all_tracks: list[dict] = []
        seen_album_ids: set[str] = set()
        seen_uris:      set[str] = set()

        for query in queries:
            albums = self._search_albums(query)
            if not albums:
                # Fall back to track search for this query (e.g. composer name)
                for track in self._run_single_search(query):
                    uri = track.get("uri", "")
                    if uri and uri not in seen_uris:
                        seen_uris.add(uri)
                        all_tracks.append(track)
                continue

            # Take top album result, skip if already fetched
            album    = albums[0]
            album_id = album.get("id", "")
            if not album_id or album_id in seen_album_ids:
                continue

            seen_album_ids.add(album_id)
            album_name = album.get("name", "")
            print(f"[spotify] OST album: '{album_name}' ({album_id})")

            tracks = self._fetch_album_tracks(album_id)
            for track in tracks:
                uri = track.get("uri", "")
                if uri and uri not in seen_uris:
                    seen_uris.add(uri)
                    all_tracks.append(track)

        print(f"[spotify] OST pool: {len(all_tracks)} tracks from {len(seen_album_ids)} albums")
        random.shuffle(all_tracks)
        return all_tracks[:target]

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

        # Score and rerank by taste profile (Option 2)
        # Falls back to shuffle if no centroid exists yet
        prefs = load_preferences()
        if prefs.get("taste_centroid"):
            unique = score_tracks(unique, prefs)
        else:
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
                record_like(track)   # update preference profile
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
            if self.ensure_spotify_open():
                device_id = self._find_device_id()
        if not device_id:
            return PlayResult(
                success=False,
                message="No Spotify device found. Tried to launch Spotify but no device appeared.",
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

        # Find a playback device — launch Spotify if not running
        device_id = self._find_device_id()
        if not device_id:
            self._log_fn("[spotify] No device — attempting to launch Spotify...")
            if self.ensure_spotify_open():
                device_id = self._find_device_id()
        if not device_id:
            return PlayResult(
                success=False,
                message="No Spotify device found. Tried to launch Spotify but no device appeared.",
            )

        # Unpack directives
        if hasattr(directives, "queries"):
            queries     = directives.queries
            queue_size  = max(1, min(100, directives.queue_size))
            search_mode = getattr(directives, "search_mode", "track")
        else:
            queries     = [str(directives)]
            queue_size  = 50
            search_mode = "track"

        if not queries:
            return PlayResult(success=False, message="No search queries were generated.")

        # Build the track pool — route to album pipeline for OST requests
        if search_mode == "album":
            print(f"[spotify] OST mode — searching albums")
            tracks = self._build_album_pool(queries, target=queue_size * 2)
        else:
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

        record_request(
            getattr(directives, "_raw_request", ""),
            success=True,
        )
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