"""
preferences.py
--------------
Learns and stores the user's music taste over time.

Two systems that work together:

OPTION 1 — Preference Store (works with any AI)
  A JSON file at ~/.spotify-ai-dj/preferences.json that records:
    - liked_artists:   {artist_name: like_count}
    - skipped_artists: {artist_name: skip_count}
    - liked_tracks:    [{"id": ..., "name": ..., "artist": ..., "description": ...}]
    - skipped_tracks:  [{"id": ..., "name": ..., "artist": ...}]
    - request_history: [{"request": ..., "success": bool, "timestamp": ...}]
  
  This data is injected into every AI prompt so the model knows your taste.

OPTION 2 — Embedding Taste Profile (local mode only)
  Uses sentence-transformers to embed track descriptions into 384-dimensional
  vectors and maintains a "taste centroid" — the average of all liked tracks.
  
  New candidate tracks are scored by cosine similarity to the centroid.
  High similarity = likely to be liked = gets boosted in queue ranking.
  
  The model (all-MiniLM-L6-v2, ~90MB) downloads once to ~/.cache/huggingface.
  The centroid itself is just 1 vector saved in preferences.json.

Both systems update automatically as you use the app:
  - Like button pressed → positive signal
  - Track skipped within SKIP_THRESHOLD seconds → negative signal
  - Play button pressed → request logged

SKIP_THRESHOLD: how many seconds before we consider a track "not skipped"
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

PREF_FILE       = Path.home() / ".spotify-ai-dj" / "preferences.json"
SKIP_THRESHOLD  = 20   # seconds — skip within this window = dislike signal
MAX_HISTORY     = 500  # rolling window for liked/skipped tracks
MAX_REQUESTS    = 100  # rolling window for request history

# Embedding model — small, fast, CPU-friendly
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Preference store (Option 1)
# ---------------------------------------------------------------------------

def _empty_prefs() -> dict:
    return {
        "liked_artists":   {},   # {artist: count}
        "skipped_artists": {},   # {artist: count}
        "liked_tracks":    [],   # list of track dicts
        "skipped_tracks":  [],   # list of track dicts
        "request_history": [],   # list of request dicts
        "taste_centroid":  None, # list of floats (embedding vector) or None
        "version":         1,
    }



def is_learning_enabled() -> bool:
    """Check config to see if preference learning is enabled."""
    try:
        from config import load_config
        return load_config().get("learning_enabled", True)
    except Exception:
        return True


def load_preferences() -> dict:
    """Load preferences from disk. Returns empty prefs if file doesn't exist."""
    if not PREF_FILE.exists():
        return _empty_prefs()
    try:
        text = PREF_FILE.read_text(encoding="utf-8").strip()
        if not text:
            return _empty_prefs()
        data = json.loads(text)
        # Merge with empty to ensure all keys exist (handles old versions)
        merged = _empty_prefs()
        merged.update(data)
        return merged
    except Exception as e:
        print(f"[prefs] Could not load preferences: {e}")
        return _empty_prefs()


def save_preferences(prefs: dict) -> None:
    """Write preferences to disk."""
    PREF_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(PREF_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[prefs] Could not save preferences: {e}")


def record_like(track: dict) -> None:
    """Record a liked track. Updates artist counts and track list."""
    if not is_learning_enabled():
        return
    prefs = load_preferences()

    artist = track.get("artist", "Unknown")
    prefs["liked_artists"][artist] = prefs["liked_artists"].get(artist, 0) + 1

    entry = {
        "id":          track.get("id", ""),
        "name":        track.get("name", ""),
        "artist":      artist,
        "description": f"{track.get('name', '')} by {artist}",
        "timestamp":   datetime.now().isoformat(),
    }

    # Avoid duplicates
    existing_ids = {t.get("id") for t in prefs["liked_tracks"]}
    if entry["id"] not in existing_ids:
        prefs["liked_tracks"].append(entry)
        prefs["liked_tracks"] = prefs["liked_tracks"][-MAX_HISTORY:]

    save_preferences(prefs)

    # Update embedding centroid in background
    _update_centroid_async(entry["description"], positive=True)


def record_skip(track: dict) -> None:
    """Record a skipped track. Updates artist counts and track list."""
    if not is_learning_enabled():
        return
    prefs = load_preferences()

    artist = track.get("artist", "Unknown")
    prefs["skipped_artists"][artist] = prefs["skipped_artists"].get(artist, 0) + 1

    entry = {
        "id":        track.get("id", ""),
        "name":      track.get("name", ""),
        "artist":    artist,
        "timestamp": datetime.now().isoformat(),
    }

    existing_ids = {t.get("id") for t in prefs["skipped_tracks"]}
    if entry["id"] not in existing_ids:
        prefs["skipped_tracks"].append(entry)
        prefs["skipped_tracks"] = prefs["skipped_tracks"][-MAX_HISTORY:]

    save_preferences(prefs)


def record_request(request: str, success: bool) -> None:
    """Record a play request and whether it found tracks."""
    if not is_learning_enabled():
        return
    prefs = load_preferences()
    prefs["request_history"].append({
        "request":   request,
        "success":   success,
        "timestamp": datetime.now().isoformat(),
    })
    prefs["request_history"] = prefs["request_history"][-MAX_REQUESTS:]
    save_preferences(prefs)


def build_preference_context(prefs: dict, max_artists: int = 10) -> str:
    """
    Build a natural-language summary of user preferences for injection
    into AI prompts. Returns empty string if no preferences recorded yet.
    """
    parts = []

    # Top liked artists (sorted by count)
    liked = sorted(prefs["liked_artists"].items(), key=lambda x: x[1], reverse=True)
    if liked:
        top = [a for a, _ in liked[:max_artists]]
        parts.append(f"Artists they have liked before: {', '.join(top)}")

    # Skipped artists — at most top 5, only if count >= 2 (avoid single-skip noise)
    skipped = sorted(
        [(a, c) for a, c in prefs["skipped_artists"].items() if c >= 2],
        key=lambda x: x[1], reverse=True
    )
    if skipped:
        top_skip = [a for a, _ in skipped[:5]]
        parts.append(f"Artists they tend to skip: {', '.join(top_skip)}")

    if not parts:
        return ""

    return (
        "\n[LISTENER HISTORY — for context only]\n"
        + "\n".join(f"  {p}" for p in parts)
        + "\n  IMPORTANT: The user's request above always takes priority over this history."
        + "\n  Only use this history if the request is vague or genre-neutral."
        + "\n  If the request specifies a genre or mood, follow it exactly — even if it"
        + "\n  differs from their usual taste. People intentionally listen to new things.\n"
    )


# ---------------------------------------------------------------------------
# Embedding taste profile (Option 2 — local mode)
# ---------------------------------------------------------------------------

_embedder       = None   # lazy-loaded sentence-transformers model
_embedder_lock  = __import__("threading").Lock()


def _get_embedder():
    """
    Lazy-load the sentence-transformers model.
    Downloads ~90MB on first call, then cached in ~/.cache/huggingface.
    Returns None if the package isn't installed.
    Thread-safe: lock prevents multiple threads loading simultaneously.
    """
    global _embedder
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        # Re-check inside lock in case another thread loaded it while we waited
        if _embedder is not None:
            return _embedder
        try:
            import os, sys
            from sentence_transformers import SentenceTransformer

            print(f"[prefs] Loading embedding model {EMBEDDING_MODEL}...")

            # Suppress noisy HuggingFace output:
            #   - HF_HUB_DISABLE_PROGRESS_BARS: hides the weight loading bar
            #   - TOKENIZERS_PARALLELISM: suppresses tokenizer fork warning
            #   - Redirect stderr briefly to hide BertModel LOAD REPORT
            os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

            # Redirect both stdout and stderr to suppress BertModel LOAD REPORT,
            # weight loading bars, and HF Hub warnings
            old_stdout, old_stderr = sys.stdout, sys.stderr
            devnull = open(os.devnull, "w")
            sys.stdout = sys.stderr = devnull
            try:
                _embedder = SentenceTransformer(EMBEDDING_MODEL)
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                devnull.close()

            print(f"[prefs] Embedding model ready")
            return _embedder
        except ImportError:
            print("[prefs] sentence-transformers not installed — embedding scoring disabled")
            print("[prefs] Install with: pip install sentence-transformers")
            return None


def _embed(text: str) -> Optional[list[float]]:
    """Embed a text string into a vector. Returns None if unavailable."""
    model = _get_embedder()
    if model is None:
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception as e:
        print(f"[prefs] Embedding error: {e}")
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two pre-normalized vectors."""
    # Vectors are already L2-normalized by sentence-transformers,
    # so cosine similarity is just the dot product.
    return sum(x * y for x, y in zip(a, b))


def _update_centroid(description: str, positive: bool, prefs: dict) -> dict:
    """
    Update the taste centroid with a new data point.

    The centroid is a running average of liked track embeddings.
    Liked tracks push it toward the new vector.
    Skipped tracks push it slightly away (negative learning rate).

    We use exponential moving average so recent history matters more:
      new_centroid = 0.9 * old_centroid + 0.1 * new_vector  (like)
      new_centroid = 0.9 * old_centroid - 0.05 * new_vector (skip)
    """
    vec = _embed(description)
    if vec is None:
        return prefs

    centroid = prefs.get("taste_centroid")
    alpha    = 0.1 if positive else -0.05

    if centroid is None:
        prefs["taste_centroid"] = vec
    else:
        prefs["taste_centroid"] = [
            0.9 * c + alpha * v
            for c, v in zip(centroid, vec)
        ]
    return prefs


def _update_centroid_async(description: str, positive: bool) -> None:
    """Update centroid in a background thread so it doesn't block the UI."""
    if not is_learning_enabled():
        return
    import threading
    def _work():
        prefs = load_preferences()
        prefs = _update_centroid(description, positive, prefs)
        save_preferences(prefs)
    threading.Thread(target=_work, daemon=True).start()


def score_tracks(tracks: list[dict], prefs: dict) -> list[dict]:
    """
    Score and rerank tracks by similarity to the taste centroid.

    Each track gets a "preference_score" field (0.0 to 1.0).
    Tracks by known-skipped artists get penalized.
    If no centroid exists yet, returns tracks unchanged.

    This is called after search, before building the final queue.
    """
    if not is_learning_enabled():
        return tracks   # Learning disabled — return unsorted
    centroid = prefs.get("taste_centroid")
    if not centroid:
        return tracks   # No taste profile yet — return as-is

    skipped_artists = set(prefs.get("skipped_artists", {}).keys())

    for track in tracks:
        artist = ""
        if track.get("artists"):
            artist = track["artists"][0].get("name", "")
        name   = track.get("name", "")
        desc   = f"{name} by {artist}"

        # Base score from embedding similarity
        vec = _embed(desc)
        if vec:
            sim   = _cosine_similarity(centroid, vec)
            score = (sim + 1) / 2   # normalize from [-1,1] to [0,1]
        else:
            score = 0.5   # neutral if embedding unavailable

        # Penalize skipped artists
        if artist in skipped_artists:
            score *= 0.3

        track["_preference_score"] = score

    # Sort by score descending, preserving original order for equal scores
    tracks.sort(key=lambda t: t.get("_preference_score", 0.5), reverse=True)
    return tracks


# ---------------------------------------------------------------------------
# Skip detector
# ---------------------------------------------------------------------------

class SkipDetector:
    """
    Detects when the user skips a track by polling the currently playing track.

    How it works:
      1. When a new track starts playing, record (track_id, start_time)
      2. Poll every 3 seconds
      3. If the track changes AND it's been less than SKIP_THRESHOLD seconds
         → record_skip() on the previous track
      4. If the track changes AND it's been more than SKIP_THRESHOLD seconds
         → the track was listened to (neutral signal, no action)

    The detector runs in a background thread started by the GUI after playback
    begins, and stopped when the app closes.
    """

    def __init__(self, spotify_client):
        self._client        = spotify_client
        self._current_id    = None
        self._current_track = None
        self._start_time    = None
        self._running       = False
        self._thread        = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        import threading
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def notify_track_started(self, track: dict) -> None:
        """
        Call this when playback starts so the detector knows the baseline.
        Avoids false positives on the very first track.
        """
        self._current_id    = track.get("id")
        self._current_track = track
        self._start_time    = time.time()

    def _loop(self) -> None:
        while self._running:
            try:
                self._check()
            except Exception as e:
                print(f"[skip_detector] Error: {e}")
            time.sleep(3)

    def _check(self) -> None:
        track = self._client.get_current_track()
        if track is None:
            return

        new_id = track.get("id")

        if self._current_id is None:
            # First observation — just record the baseline
            self._current_id    = new_id
            self._current_track = track
            self._start_time    = time.time()
            return

        if new_id != self._current_id:
            # Track changed — was it a skip?
            elapsed = time.time() - (self._start_time or 0)
            if elapsed < SKIP_THRESHOLD and self._current_track:
                print(f"[skip_detector] Skip detected: {self._current_track.get('name')} ({elapsed:.0f}s)")
                record_skip(self._current_track)

            # Update baseline to the new track
            self._current_id    = new_id
            self._current_track = track
            self._start_time    = time.time()