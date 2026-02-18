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
# Resolve the ABSOLUTE path to Python so the app bundle always works.
# 'command -v' can return a shell function or alias on some setups;
# 'which' is more reliable for getting the real filesystem path.
# ------------------------------------------------------------------
PYTHON_ABS="$(which "$PYTHON_CMD" 2>/dev/null || command -v "$PYTHON_CMD")"

# Follow symlinks all the way to the real binary. This matters because
# Homebrew Python is symlinked and Finder-launched processes need the
# real path to find the correct lib/ directory.
if command -v realpath &>/dev/null; then
  PYTHON_ABS="$(realpath "$PYTHON_ABS")"
elif command -v readlink &>/dev/null; then
  # macOS readlink doesn't support -f, loop manually
  _link="$PYTHON_ABS"
  while [ -L "$_link" ]; do
    _link="$(readlink "$_link")"
    # Handle relative symlinks
    case "$_link" in
      /*) ;;
      *)  _link="$(dirname "$PYTHON_ABS")/$_link" ;;
    esac
    PYTHON_ABS="$_link"
  done
fi

info "Using Python at: $PYTHON_ABS ($($PYTHON_ABS --version))"

# ------------------------------------------------------------------
# Step 4 - Install python-tk
# ------------------------------------------------------------------
info "Installing Tcl/Tk for GUI support..."

PY_MAJOR=$($PYTHON_ABS -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PYTHON_ABS -c 'import sys; print(sys.version_info.minor)')
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
$PYTHON_ABS -m pip install --help 2>&1 | grep -q "break-system-packages" \
  && PIP_FLAGS="--break-system-packages"

$PYTHON_ABS -m pip install --upgrade pip --quiet $PIP_FLAGS
$PYTHON_ABS -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet $PIP_FLAGS

success "Python dependencies installed."

# ------------------------------------------------------------------
# Step 6 - Credential wizard
# ------------------------------------------------------------------
_env_has_spotify_keys() {
  [ -f "$SCRIPT_DIR/.env" ] \
    && grep -q "^SPOTIPY_CLIENT_ID=.\+" "$SCRIPT_DIR/.env" 2>/dev/null \
    && grep -q "^SPOTIPY_CLIENT_SECRET=.\+" "$SCRIPT_DIR/.env" 2>/dev/null
}

_ask_applescript() {
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
# Step 7 - Create launch.sh (terminal launcher / CLI mode)
# ------------------------------------------------------------------
LAUNCH_SCRIPT="$SCRIPT_DIR/launch.sh"
cat > "$LAUNCH_SCRIPT" << EOF
#!/usr/bin/env bash
# Quick launcher for Spotify AI DJ
# GUI mode:  bash launch.sh
# CLI mode:  bash launch.sh "dark techno"
cd "$SCRIPT_DIR"
exec "$PYTHON_ABS" main.py "\$@"
EOF
chmod +x "$LAUNCH_SCRIPT"
success "launch.sh created in the app folder."

# ------------------------------------------------------------------
# Step 8 - Install the 'dj' command
#
# We write the wrapper to /usr/local/bin which exists on both Intel
# and Apple Silicon Macs and is on PATH in all shells by default.
# The wrapper uses PYTHON_ABS (absolute, symlinks resolved) so it
# works identically whether called from a login shell, an SSH session,
# or a script — no reliance on PATH to find python3.
# ------------------------------------------------------------------
info "Installing 'dj' command..."

DJ_WRAPPER="/usr/local/bin/dj"

# /usr/local/bin may not exist on a fresh macOS install
sudo mkdir -p /usr/local/bin

sudo tee "$DJ_WRAPPER" > /dev/null << EOF
#!/bin/bash
# dj - Spotify AI DJ command-line launcher
#
# GUI mode:       dj
# CLI mode:       dj "dark techno"
# Save API key:   dj --set-key YOUR_KEY
# Help:           dj --help

# Source Homebrew so any Homebrew-managed libs are findable
if [ -f "/opt/homebrew/bin/brew" ]; then
  eval "\$(/opt/homebrew/bin/brew shellenv)"
elif [ -f "/usr/local/bin/brew" ]; then
  eval "\$(/usr/local/bin/brew shellenv)"
fi

cd "$SCRIPT_DIR" || {
  echo "[dj] Error: app folder not found at $SCRIPT_DIR"
  echo "     Please re-run install_mac.sh"
  exit 1
}

exec "$PYTHON_ABS" main.py "\$@"
EOF

sudo chmod +x "$DJ_WRAPPER"
success "'dj' command installed at $DJ_WRAPPER"

# ------------------------------------------------------------------
# Step 9 - Build ~/Applications/Spotify AI DJ.app
#
# (was Step 8 before the dj command step was added)
#
# Key design decisions:
#
#   1. We embed PYTHON_ABS (the resolved absolute path to the Python
#      binary, with symlinks followed) directly into the stub script.
#      Finder-launched processes do NOT source ~/.zshrc / ~/.bash_profile
#      so PATH-based lookups like `python3` silently fail.
#
#   2. We source Homebrew's shellenv unconditionally for Apple Silicon
#      (/opt/homebrew) and Intel (/usr/local) so that any Homebrew-
#      managed shared libraries Python depends on are findable.
#
#   3. All stdout and stderr are tee'd to ~/Library/Logs/SpotifyAIDJ.log
#      so if the app crashes on launch, the user has somewhere to look.
#      The log path is printed at the end of this installer.
#
#   4. SCRIPT_DIR is cd'd into before exec'ing Python so that relative
#      imports (from brain import ...) resolve correctly regardless of
#      where macOS decides to set the working directory.
# ------------------------------------------------------------------
info "Creating app bundle..."

APP_BUNDLE="$HOME/Applications/Spotify AI DJ.app"
APP_MACOS_DIR="$APP_BUNDLE/Contents/MacOS"
LOG_FILE="$HOME/Library/Logs/SpotifyAIDJ.log"

# Remove any old bundle first so stale files don't cause confusion
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_MACOS_DIR"

cat > "$APP_MACOS_DIR/SpotifyAIDJ" << EOF
#!/bin/bash
# Spotify AI DJ - macOS app bundle launcher
# If the app won't open, check: $LOG_FILE

LOG="$LOG_FILE"
mkdir -p "\$(dirname "\$LOG")"

{
  echo "--- Launch: \$(date) ---"

  # Bring Homebrew onto PATH for both Apple Silicon and Intel Macs.
  # This is required even though we use an absolute Python path because
  # Python's ctk / tkinter may dlopen Homebrew-managed Tcl/Tk libraries.
  if [ -f "/opt/homebrew/bin/brew" ]; then
    eval "\$(/opt/homebrew/bin/brew shellenv)"
  elif [ -f "/usr/local/bin/brew" ]; then
    eval "\$(/usr/local/bin/brew shellenv)"
  fi

  # Change into the app source directory so relative imports work
  cd "$SCRIPT_DIR" || {
    echo "ERROR: App folder not found at $SCRIPT_DIR"
    echo "Please re-run install_mac.sh"
    osascript -e 'display alert "Spotify AI DJ" message "App folder not found.\nPlease re-run install_mac.sh." as critical'
    exit 1
  }

  # Launch the app, piping all output to the log
  exec "$PYTHON_ABS" main.py

} >> "\$LOG" 2>&1

# If we reach here, exec failed (Python not found at embedded path)
osascript -e 'display alert "Spotify AI DJ" message "Could not start Python.\nPlease re-run install_mac.sh." as critical'
EOF

chmod +x "$APP_MACOS_DIR/SpotifyAIDJ"

# Minimal Info.plist
cat > "$APP_BUNDLE/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>             <string>Spotify AI DJ</string>
    <key>CFBundleIdentifier</key>       <string>com.spotifyaidj.app</string>
    <key>CFBundleVersion</key>          <string>1.0</string>
    <key>CFBundleExecutable</key>       <string>SpotifyAIDJ</string>
    <key>CFBundlePackageType</key>      <string>APPL</string>
    <key>LSMinimumSystemVersion</key>   <string>11.0</string>
    <key>NSHighResolutionCapable</key>  <true/>
    <key>LSUIElement</key>              <false/>
</dict>
</plist>
EOF

success "App bundle created at: $APP_BUNDLE"

# ------------------------------------------------------------------
# Quick smoke-test: run Python with our absolute path to catch bad
# installs before the user tries to double-click the app.
# ------------------------------------------------------------------
info "Verifying Python launch..."
if "$PYTHON_ABS" -c "import tkinter; import customtkinter" 2>/dev/null; then
  success "Python and customtkinter OK."
else
  warn "Could not import tkinter or customtkinter."
  warn "The app may not open. If it doesn't, run:"
  warn "  bash launch.sh"
  warn "to see the error in your terminal."
fi

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo -e "${C_BOLD} ============================================${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}  All done! Setup is complete.${C_RESET}"
echo -e "${C_BOLD} ============================================${C_RESET}"
echo ""
echo -e " Launch the GUI:"
echo -e "   ${C_BOLD}Option A:${C_RESET} Open ${C_CYAN}~/Applications/Spotify AI DJ.app${C_RESET} in Finder"
echo -e "   ${C_BOLD}Option B:${C_RESET} Run  ${C_CYAN}bash launch.sh${C_RESET} in this folder"
echo -e "   ${C_BOLD}Option C:${C_RESET} Run  ${C_CYAN}dj${C_RESET}  (new terminal tab, any directory)"
echo ""
echo -e " ${C_BOLD}CLI mode${C_RESET} - play immediately from any terminal:"
echo -e "   ${C_CYAN}dj \"dark techno\"${C_RESET}"
echo -e "   ${C_CYAN}dj \"relaxing lo-fi for studying\"${C_RESET}"
echo ""
echo -e " ${C_YELLOW}If the app won't open,${C_RESET} check the log for errors:"
echo -e "   ${C_CYAN}cat ~/Library/Logs/SpotifyAIDJ.log${C_RESET}"
echo ""
echo -e " ${C_YELLOW}First play:${C_RESET} Your browser will open for Spotify login."
echo -e " This only happens once - the token is cached after that."
echo ""