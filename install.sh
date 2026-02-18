#!/usr/bin/env bash
# install.sh - Spotify AI DJ installer for Linux
#
# Supports: Debian/Ubuntu, Arch/Manjaro, Fedora/RHEL, openSUSE, Gentoo
# Run with: bash install.sh

set -e

# ------------------------------------------------------------------
# Colours for output
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
echo -e "${C_BOLD}  Spotify AI DJ - Linux Installer${C_RESET}"
echo -e "${C_BOLD} ============================================${C_RESET}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ------------------------------------------------------------------
# Step 1 - Detect package manager
# ------------------------------------------------------------------
info "Detecting package manager..."

PKG_MANAGER=""
DISTRO_NAME=""

if   command -v apt-get &>/dev/null; then PKG_MANAGER="apt";    DISTRO_NAME="Debian/Ubuntu"
elif command -v pacman  &>/dev/null; then PKG_MANAGER="pacman"; DISTRO_NAME="Arch Linux"
elif command -v dnf     &>/dev/null; then PKG_MANAGER="dnf";    DISTRO_NAME="Fedora/RHEL"
elif command -v zypper  &>/dev/null; then PKG_MANAGER="zypper"; DISTRO_NAME="openSUSE"
elif command -v emerge  &>/dev/null; then PKG_MANAGER="emerge"; DISTRO_NAME="Gentoo"
else
  warn "Could not detect a supported package manager."
  warn "Please install Python 3.10+, python3-tk, and run:"
  warn "  pip install -r requirements.txt"
  PKG_MANAGER="unknown"
fi

[ "$PKG_MANAGER" != "unknown" ] && success "Found: $DISTRO_NAME ($PKG_MANAGER)"

# ------------------------------------------------------------------
# Step 2 - Detect display server
# ------------------------------------------------------------------
info "Detecting display server..."

WAYLAND=false
if [ -n "$WAYLAND_DISPLAY" ]; then
  WAYLAND=true
  success "Wayland session detected - GTK4 backend will be used."
else
  success "X11 session detected - customtkinter backend will be used."
fi

# ------------------------------------------------------------------
# Step 3 - Check / install Python 3.10+
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
  warn "Python 3.10+ not found. Installing..."
  case "$PKG_MANAGER" in
    apt)    sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip ;;
    pacman) sudo pacman -Sy --noconfirm python python-pip ;;
    dnf)    sudo dnf install -y python3 python3-pip ;;
    zypper) sudo zypper install -y python3 python3-pip ;;
    emerge) sudo emerge dev-lang/python ;;
    *)      error "Cannot install Python automatically. Please install Python 3.10+ manually." ;;
  esac

  for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
      major=$("$cmd" -c 'import sys; print(sys.version_info.major)' 2>/dev/null)
      minor=$("$cmd" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)
      if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
        PYTHON_CMD="$cmd"
        break
      fi
    fi
  done
  [ -z "$PYTHON_CMD" ] && error "Python install failed. Please install Python 3.10+ manually."
  success "Python installed."
fi

# ------------------------------------------------------------------
# Step 4 - Install tkinter
# ------------------------------------------------------------------
info "Installing tkinter..."
case "$PKG_MANAGER" in
  apt)    sudo apt-get install -y python3-tk ;;
  pacman) sudo pacman -Sy --noconfirm tk ;;
  dnf)    sudo dnf install -y python3-tkinter ;;
  zypper) sudo zypper install -y python3-tk ;;
  emerge) sudo emerge dev-python/tkinter ;;
  unknown) warn "Skipping tkinter install - please install it manually." ;;
esac

# ------------------------------------------------------------------
# Step 5 - Install GTK4 + PyGObject if on Wayland
# ------------------------------------------------------------------
if [ "$WAYLAND" = true ]; then
  info "Installing GTK4 libraries for Wayland support..."
  case "$PKG_MANAGER" in
    apt)
      sudo apt-get install -y \
        python3-gi python3-gi-cairo gir1.2-gtk-4.0 libgtk-4-dev
      ;;
    pacman) sudo pacman -Sy --noconfirm python-gobject gtk4 ;;
    dnf)    sudo dnf install -y python3-gobject gtk4 ;;
    zypper) sudo zypper install -y python3-gobject typelib-1_0-Gtk-4_0 ;;
    emerge) sudo emerge dev-python/pygobject gui-libs/gtk ;;
    unknown) warn "Skipping GTK4 install - please install PyGObject and GTK4 manually." ;;
  esac
  success "GTK4 libraries installed."
else
  info "Skipping GTK4 install (not needed on X11)."
fi

# ------------------------------------------------------------------
# Step 6 - Install Python dependencies via pip
# ------------------------------------------------------------------
info "Installing Python dependencies..."

PIP_FLAGS=""
if $PYTHON_CMD -m pip install --help 2>&1 | grep -q "break-system-packages"; then
  PIP_FLAGS="--break-system-packages"
fi

$PYTHON_CMD -m pip install --upgrade pip --quiet $PIP_FLAGS
$PYTHON_CMD -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet $PIP_FLAGS

success "Python dependencies installed."

# ------------------------------------------------------------------
# Step 7 - Credential wizard
# Creates .env in the app folder. Skipped if .env already exists and
# contains both Spotify keys (allows re-running the installer safely).
# ------------------------------------------------------------------
_env_has_spotify_keys() {
  [ -f "$SCRIPT_DIR/.env" ] \
    && grep -q "^SPOTIPY_CLIENT_ID=.\+" "$SCRIPT_DIR/.env" 2>/dev/null \
    && grep -q "^SPOTIPY_CLIENT_SECRET=.\+" "$SCRIPT_DIR/.env" 2>/dev/null
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
  echo -e " ${C_BOLD}1. Spotify${C_RESET} (to control playback)"
  echo -e "    ${C_CYAN}https://developer.spotify.com/dashboard${C_RESET}"
  echo -e "    • Click 'Create app'"
  echo -e "    • Set Redirect URI to:  ${C_BOLD}http://127.0.0.1:8888/callback${C_RESET}"
  echo -e "    • Copy your Client ID and Client Secret"
  echo ""
  echo -e " ${C_BOLD}2. Google Gemini${C_RESET} (for AI music requests - free tier is fine)"
  echo -e "    ${C_CYAN}https://aistudio.google.com/app/apikey${C_RESET}"
  echo ""

  # Spotify Client ID
  while true; do
    read -rp "  Spotify Client ID:     " S_ID
    S_ID="${S_ID// /}"   # strip accidental spaces
    [ -n "$S_ID" ] && break
    echo -e "  ${C_RED}Please enter your Spotify Client ID.${C_RESET}"
  done

  # Spotify Client Secret
  while true; do
    read -rp "  Spotify Client Secret: " S_SEC
    S_SEC="${S_SEC// /}"
    [ -n "$S_SEC" ] && break
    echo -e "  ${C_RED}Please enter your Spotify Client Secret.${C_RESET}"
  done

  # Gemini API Key (optional - can be entered via the GUI later)
  echo ""
  echo -e "  ${C_YELLOW}Gemini key (optional now - you can also set it in the app):${C_RESET}"
  read -rp "  Gemini API Key:        " G_KEY
  G_KEY="${G_KEY// /}"

  cat > "$SCRIPT_DIR/.env" << EOF
SPOTIPY_CLIENT_ID=$S_ID
SPOTIPY_CLIENT_SECRET=$S_SEC
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
GEMINI_API_KEY=$G_KEY
EOF

  success "Credentials saved to .env"

  if [ -z "$G_KEY" ]; then
    warn "No Gemini key entered. You will be prompted for it on first launch."
  fi
fi

# ------------------------------------------------------------------
# Step 8 - Create a .desktop launcher
# ------------------------------------------------------------------
info "Creating application launcher..."

DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/spotify-ai-dj.desktop" << EOF
[Desktop Entry]
Name=Spotify AI DJ
Comment=Tell it what to play. AI does the rest.
Exec=$PYTHON_CMD $SCRIPT_DIR/main.py
Terminal=false
Type=Application
Categories=AudioVideo;Music;
StartupWMClass=com.spotifyaidj.app
EOF

chmod +x "$DESKTOP_DIR/spotify-ai-dj.desktop"
command -v update-desktop-database &>/dev/null \
  && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

success "App launcher created (check your application menu)."

# ------------------------------------------------------------------
# Step 9 - Create launch.sh
# ------------------------------------------------------------------
cat > "$SCRIPT_DIR/launch.sh" << EOF
#!/usr/bin/env bash
# Quick launcher for Spotify AI DJ
# GUI mode:  bash launch.sh
# CLI mode:  bash launch.sh "dark techno"
cd "$SCRIPT_DIR"
exec $PYTHON_CMD main.py "\$@"
EOF
chmod +x "$SCRIPT_DIR/launch.sh"

success "launch.sh created in the app folder."

# ------------------------------------------------------------------
# Step 10 - Install the 'dj' command
# ------------------------------------------------------------------
info "Installing 'dj' command..."

DJ_WRAPPER="/usr/local/bin/dj"
sudo tee "$DJ_WRAPPER" > /dev/null << EOF
#!/usr/bin/env bash
# dj - Spotify AI DJ command
cd "$SCRIPT_DIR"
exec $PYTHON_CMD main.py "\$@"
EOF
sudo chmod +x "$DJ_WRAPPER"

success "'dj' command installed. Use it from any terminal."

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo -e "${C_BOLD} ============================================${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}  All done! Setup is complete.${C_RESET}"
echo -e "${C_BOLD} ============================================${C_RESET}"
echo ""
echo -e " ${C_BOLD}Launch the GUI:${C_RESET}"
echo -e "   ${C_CYAN}dj${C_RESET}  or search 'Spotify AI DJ' in your app menu"
echo ""
echo -e " ${C_BOLD}Play directly from the terminal:${C_RESET}"
echo -e "   ${C_CYAN}dj \"dark techno\"${C_RESET}"
echo -e "   ${C_CYAN}dj \"relaxing lo-fi for studying\"${C_RESET}"
echo ""
echo -e " ${C_YELLOW}First play:${C_RESET} Your browser will open for Spotify login."
echo -e " This only happens once - the token is cached after that."
echo ""