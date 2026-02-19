"""
config.py
---------
Manages persistent user configuration.

Gemini API key  -> ~/.spotify-ai-dj/config.json  (user-level, not in repo)
Local LLM config -> .env in the project folder    (gitignored)

The .env approach for LLM config means the same file works for both
direct editing and GUI configuration, and is never committed to git.
"""

import json
from pathlib import Path

CONFIG_DIR         = Path.home() / ".spotify-ai-dj"
CONFIG_FILE        = CONFIG_DIR / "config.json"
SPOTIFY_CACHE_FILE = CONFIG_DIR / ".spotify_cache"
ENV_FILE           = Path(__file__).parent / ".env"

DEFAULT_CONFIG: dict = {
    "gemini_api_key": "",
    "local_ai_only":  False,   # when True, skip Gemini and use local LLM only
}


def load_config() -> dict:
    """Load config from disk, merged with defaults."""
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
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return str(SPOTIFY_CACHE_FILE)


# ---------------------------------------------------------------------------
# .env helpers — read and write Local LLM settings
# ---------------------------------------------------------------------------

ENV_LLM_KEYS = ["LOCAL_LLM_BASE_URL", "LOCAL_LLM_API_KEY", "LOCAL_LLM_MODEL"]


def load_env_llm_config() -> dict:
    """
    Read Local LLM settings from the project .env file.
    Returns a dict with keys: base_url, api_key, model.
    """
    result = {"base_url": "", "api_key": "", "model": "llama3.2:latest"}
    if not ENV_FILE.exists():
        return result

    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        if key.strip() == "LOCAL_LLM_BASE_URL":
            result["base_url"] = val
        elif key.strip() == "LOCAL_LLM_API_KEY":
            result["api_key"] = val
        elif key.strip() == "LOCAL_LLM_MODEL":
            result["model"] = val

    return result


def save_env_llm_config(base_url: str, api_key: str, model: str) -> None:
    """
    Write Local LLM settings into the project .env file.
    Preserves all existing lines (Spotify credentials etc.),
    updating or appending the three LOCAL_LLM_* keys.
    """
    # Read existing lines
    existing_lines: list[str] = []
    if ENV_FILE.exists():
        existing_lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    # Build a map of which lines to replace
    new_values = {
        "LOCAL_LLM_BASE_URL": base_url,
        "LOCAL_LLM_API_KEY":  api_key,
        "LOCAL_LLM_MODEL":    model,
    }
    written = set()
    output  = []

    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in new_values:
                output.append(f"{key}={new_values[key]}")
                written.add(key)
                continue
        output.append(line)

    # Append any keys that weren't already in the file
    if not written.issuperset(new_values.keys()):
        if output and output[-1].strip():
            output.append("")  # blank line separator
        output.append("# Local LLM (optional — leave blank to use Gemini only)")
        for key, val in new_values.items():
            if key not in written:
                output.append(f"{key}={val}")

    ENV_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")