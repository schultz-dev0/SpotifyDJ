#!/usr/bin/env bash
# install_mac.sh - Spotify AI DJ installer for macOS
#
# Requires: macOS 11 (Big Sur) or newer
# Run with: bash install_mac.sh

set -e

# ------------------------------------------------------------------
# Colours
# ------------------------------------------------------------------
if [ -t 1 ]; then
  C_RESET="\033[0m"
  C_BOLD="\033[1m"
  C_GREEN="\033[32m"
  C_YELLOW="\033[33m"
  C_RED="\033[31m"
  C_CYAN="\033[36m"
else
  C_RESET="" C_BOLD="" C_GREEN="" C_YELLOW="" C_RED="" C_CYAN=""
fi

info()    { echo -e "${C_CYAN}${C_BOLD}[*]${C_RESET} $*"; }
success() { echo -e "${C_GREEN}${C_BOLD}[+]${C_RESET} $*"; }
warn()    { echo -e "${C_YELLOW}${C_BOLD}[!]${C_RESET} $*"; }
error()   { echo -e "${C_RED}${C_BOLD}[x]${C_RESET} $*"; exit 1; }

# ------------------------------------------------------------------
# Banner
# ------------------------------------------------------------------
echo ""
echo -e "${C_BOLD} ============================================${C_RESET}"
echo -e "${C_BOLD}  Spotify AI DJ - macOS Installer${C_RESET}"
echo -e "${C_BOLD} ============================================${C_RESET}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ------------------------------------------------------------------
# Step 1 - Confirm macOS
# ------------------------------------------------------------------
[ "$(uname)" != "Darwin" ] && error "This script is for macOS only. Use install.sh on Linux."
info "Detected macOS $(sw_vers -productVersion)"

# ------------------------------------------------------------------
# Step 2 - Install Homebrew if missing
# ------------------------------------------------------------------
info "Checking for Homebrew..."

if ! command -v brew &>/dev/null; then
  warn "Homebrew not found. Installing it now..."
  echo ""
  warn "This will ask for your Mac password. That is normal and required."
  echo ""
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  if   [ -f "/opt/homebrew/bin/brew" ]; then eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -f "/usr/local/bin/brew"    ]; then eval "$(/usr/local/bin/brew shellenv)"
  fi

  command -v brew &>/dev/null || error "Homebrew install failed. Visit https://brew.sh then re-run this script."
  success "Homebrew installed."
else
  success "Homebrew found: $(brew --version | head -1)"
fi

# ------------------------------------------------------------------
# Step 3 - Install Python 3.10+ via Homebrew
# ------------------------------------------------------------------
info "Checking Python version..."

PYTHON_CMD=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    major=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null)
    minor=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)
    if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
      PYTHON_CMD="$cmd"
      success "Found $($cmd --version)"
      break
    fi
  fi
done

if [ -z "$PYTHON_CMD" ]; then
  warn "Python 3.10+ not found. Installing via Homebrew..."
  brew install python@3.12

  for cmd in python3.12 python3 python; do
    if command -v "$cmd" &>/dev/null; then
      major=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null)
      minor=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)
      if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
        PYTHON_CMD="$cmd"
        break
      fi
    fi
  done

  [ -z "$PYTHON_CMD" ] && error "Python install failed. Please install Python 3.10+ from https://python.org"
  success "Python installed: $($PYTHON_CMD --version)"
fi

# ------------------------------------------------------------------
# Step 4 - Install python-tk
# ------------------------------------------------------------------
info "Installing Tcl/Tk for GUI support..."

PY_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')
TK_FORMULA="python-tk@${PY_MAJOR}.${PY_MINOR}"

if brew list "$TK_FORMULA" &>/dev/null 2>&1; then
  success "Tcl/Tk already installed."
else
  brew install "$TK_FORMULA" \
    || warn "Could not install $TK_FORMULA - the app may still work if tk is already present."
fi

# ------------------------------------------------------------------
# Step 5 - Install Python dependencies
# ------------------------------------------------------------------
info "Installing Python dependencies..."

PIP_FLAGS=""
$PYTHON_CMD -m pip install --help 2>&1 | grep -q "break-system-packages" \
  && PIP_FLAGS="--break-system-packages"

$PYTHON_CMD -m pip install --upgrade pip --quiet $PIP_FLAGS
$PYTHON_CMD -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet $PIP_FLAGS

success "Python dependencies installed."

# ------------------------------------------------------------------
# Step 6 - Credential wizard
# Uses AppleScript dialogs for a native Mac feel.
# Falls back to terminal prompts if osascript is unavailable.
# Skipped if .env already has valid Spotify keys.
# ------------------------------------------------------------------
_env_has_spotify_keys() {
  [ -f "$SCRIPT_DIR/.env" ] \
    && grep -q "^SPOTIPY_CLIENT_ID=.\+" "$SCRIPT_DIR/.env" 2>/dev/null \
    && grep -q "^SPOTIPY_CLIENT_SECRET=.\+" "$SCRIPT_DIR/.env" 2>/dev/null
}

_ask_applescript() {
  # Args: prompt, is_secret (true/false)
  local prompt="$1"
  local hidden="$2"
  local result

  if [ "$hidden" = "true" ]; then
    result=$(osascript \
      -e "set dlg to display dialog \"$prompt\" default answer \"\" with hidden answer" \
      -e "text returned of dlg" 2>/dev/null) || true
  else
    result=$(osascript \
      -e "set dlg to display dialog \"$prompt\" default answer \"\"" \
      -e "text returned of dlg" 2>/dev/null) || true
  fi

  echo "$result"
}

if _env_has_spotify_keys; then
  success "Credentials already configured (.env found). Skipping wizard."
  info    "To update your credentials, delete .env and re-run this installer."
else
  echo ""
  echo -e "${C_BOLD} ============================================${C_RESET}"
  echo -e "${C_BOLD}  API Key Setup${C_RESET}"
  echo -e "${C_BOLD} ============================================${C_RESET}"
  echo ""
  echo -e " This app needs two sets of credentials:"
  echo ""
  echo -e " ${C_BOLD}1. Spotify${C_RESET}  ->  ${C_CYAN}https://developer.spotify.com/dashboard${C_RESET}"
  echo -e "    Create an app, set Redirect URI to:"
  echo -e "    ${C_BOLD}http://127.0.0.1:8888/callback${C_RESET}"
  echo ""
  echo -e " ${C_BOLD}2. Gemini${C_RESET}   ->  ${C_CYAN}https://aistudio.google.com/app/apikey${C_RESET}"
  echo -e "    Free tier is fine."
  echo ""

  # Try AppleScript dialogs first (nicer on Mac), fall back to terminal
  USE_APPLESCRIPT=false
  command -v osascript &>/dev/null && USE_APPLESCRIPT=true

  if [ "$USE_APPLESCRIPT" = true ]; then
    info "Opening setup dialogs (look for pop-up windows)..."

    S_ID=""
    while [ -z "$S_ID" ]; do
      S_ID=$(_ask_applescript "Spotify Client ID\n\nGet this from developer.spotify.com/dashboard" false)
      S_ID="${S_ID// /}"
    done

    S_SEC=""
    while [ -z "$S_SEC" ]; do
      S_SEC=$(_ask_applescript "Spotify Client Secret\n\nGet this from developer.spotify.com/dashboard" true)
      S_SEC="${S_SEC// /}"
    done

    G_KEY=$(_ask_applescript "Gemini API Key (optional - can be entered in the app later)\n\nGet this from aistudio.google.com/app/apikey" true)
    G_KEY="${G_KEY// /}"

  else
    # Plain terminal prompts
    while true; do
      read -rp "  Spotify Client ID:     " S_ID
      S_ID="${S_ID// /}"
      [ -n "$S_ID" ] && break
      echo -e "  ${C_RED}Please enter your Spotify Client ID.${C_RESET}"
    done

    while true; do
      read -rp "  Spotify Client Secret: " S_SEC
      S_SEC="${S_SEC// /}"
      [ -n "$S_SEC" ] && break
      echo -e "  ${C_RED}Please enter your Spotify Client Secret.${C_RESET}"
    done

    echo -e "  ${C_YELLOW}Gemini key (optional - you can also set it in the app):${C_RESET}"
    read -rp "  Gemini API Key:        " G_KEY
    G_KEY="${G_KEY// /}"
  fi

  cat > "$SCRIPT_DIR/.env" << EOF
SPOTIPY_CLIENT_ID=$S_ID
SPOTIPY_CLIENT_SECRET=$S_SEC
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
GEMINI_API_KEY=$G_KEY
EOF

  success "Credentials saved to .env"
  [ -z "$G_KEY" ] && warn "No Gemini key entered. You will be prompted for it on first launch."
fi

# ------------------------------------------------------------------
# Step 7 - Create launch.sh
# ------------------------------------------------------------------
LAUNCH_SCRIPT="$SCRIPT_DIR/launch.sh"
cat > "$LAUNCH_SCRIPT" << EOF
#!/usr/bin/env bash
# Quick launcher for Spotify AI DJ
# GUI mode:  bash launch.sh
# CLI mode:  bash launch.sh "dark techno"
cd "$SCRIPT_DIR"
exec $PYTHON_CMD main.py "\$@"
EOF
chmod +x "$LAUNCH_SCRIPT"
success "launch.sh created in the app folder."

# ------------------------------------------------------------------
# Step 8 - Create ~/Applications/Spotify AI DJ.app
# ------------------------------------------------------------------
info "Creating app bundle for your Applications folder..."

APP_BUNDLE="$HOME/Applications/Spotify AI DJ.app"
APP_SCRIPT_DIR="$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_SCRIPT_DIR"

cat > "$APP_SCRIPT_DIR/SpotifyAIDJ" << EOF
#!/usr/bin/env bash
# macOS app bundle stub
if [ -f "/opt/homebrew/bin/brew" ]; then
  eval "\$(/opt/homebrew/bin/brew shellenv)"
fi
cd "$SCRIPT_DIR"
exec $PYTHON_CMD main.py
EOF
chmod +x "$APP_SCRIPT_DIR/SpotifyAIDJ"

cat > "$APP_BUNDLE/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>      <string>Spotify AI DJ</string>
    <key>CFBundleIdentifier</key> <string>com.spotifyaidj.app</string>
    <key>CFBundleVersion</key>   <string>1.0</string>
    <key>CFBundleExecutable</key> <string>SpotifyAIDJ</string>
    <key>CFBundlePackageType</key> <string>APPL</string>
    <key>LSMinimumSystemVersion</key> <string>11.0</string>
    <key>NSHighResolutionCapable</key> <true/>
</dict>
</plist>
EOF

success "App created at: $APP_BUNDLE"
info    "Drag it from ~/Applications into your Dock to pin it."

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo -e "${C_BOLD} ============================================${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}  All done! Setup is complete.${C_RESET}"
echo -e "${C_BOLD} ============================================${C_RESET}"
echo ""
echo -e " You can now launch the app:"
echo -e "   ${C_BOLD}1.${C_RESET} Open ${C_CYAN}~/Applications/Spotify AI DJ.app${C_RESET}"
echo -e "   ${C_BOLD}2.${C_RESET} Run  ${C_CYAN}bash launch.sh${C_RESET} in this folder"
echo ""
echo -e " ${C_YELLOW}First play:${C_RESET} Your browser will open for Spotify login."
echo -e " This only happens once - the token is cached after that."
echo ""