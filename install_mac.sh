#!/usr/bin/env bash
# install_mac.sh - Spotify AI DJ installer for macOS
#
# Requires: macOS 11 (Big Sur) or newer
# Run with: bash install_mac.sh

# claude made this too, I do not use macOS!
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
if [ "$(uname)" != "Darwin" ]; then
    error "This script is for macOS only. Use install.sh on Linux."
fi

MACOS_VERSION=$(sw_vers -productVersion)
info "Detected macOS $MACOS_VERSION"

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

    # Homebrew installs to different paths on Apple Silicon vs Intel.
    # Add it to PATH for the rest of this script session.
    if [ -f "/opt/homebrew/bin/brew" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -f "/usr/local/bin/brew" ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi

    command -v brew &>/dev/null || error "Homebrew install failed. Please install it manually from https://brew.sh then run this script again."
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

    # Homebrew python is installed as versioned binary
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

    [ -z "$PYTHON_CMD" ] && error "Python install failed. Please install Python 3.10+ manually from https://python.org"
    success "Python installed: $($PYTHON_CMD --version)"
fi

# ------------------------------------------------------------------
# Step 4 - Install python-tk (needed by customtkinter on macOS)
# ------------------------------------------------------------------
info "Installing Tcl/Tk for GUI support..."

# Homebrew's python-tk package matches the installed Python version.
# Extract major.minor from the python command to get the right formula.
PY_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')
PY_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.major)')

TK_FORMULA="python-tk@${PY_MAJOR}.${PY_MINOR}"

if brew list "$TK_FORMULA" &>/dev/null 2>&1; then
    success "Tcl/Tk already installed."
else
    brew install "$TK_FORMULA" || warn "Could not install $TK_FORMULA - the app may still work if tk is already present."
fi

# ------------------------------------------------------------------
# Step 5 - Install Python dependencies via pip
# ------------------------------------------------------------------
info "Installing Python dependencies..."

# Homebrew-managed Pythons on macOS do not enforce PEP 668,
# so --break-system-packages is not needed here, but we check
# anyway for safety in case the user has a non-Homebrew Python.
PIP_FLAGS=""
if $PYTHON_CMD -m pip install --help 2>&1 | grep -q "break-system-packages"; then
    PIP_FLAGS="--break-system-packages"
fi

$PYTHON_CMD -m pip install --upgrade pip --quiet $PIP_FLAGS
$PYTHON_CMD -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet $PIP_FLAGS

success "Python dependencies installed."

# ------------------------------------------------------------------
# Step 6 - Create a launch script
# ------------------------------------------------------------------
LAUNCH_SCRIPT="$SCRIPT_DIR/launch.sh"
cat > "$LAUNCH_SCRIPT" <<EOF
#!/usr/bin/env bash
# Quick launcher for Spotify AI DJ
cd "$SCRIPT_DIR"
exec $PYTHON_CMD main.py "\$@"
EOF
chmod +x "$LAUNCH_SCRIPT"

success "launch.sh created in the app folder."

# ------------------------------------------------------------------
# Step 7 - Optionally create an Automator app bundle for the Dock
# ------------------------------------------------------------------
info "Creating a launchable app for your Applications folder..."

APP_BUNDLE="$HOME/Applications/Spotify AI DJ.app"
APP_SCRIPT_DIR="$APP_BUNDLE/Contents/MacOS"

mkdir -p "$APP_SCRIPT_DIR"

# Write the executable stub that macOS will call when the app is opened
cat > "$APP_SCRIPT_DIR/SpotifyAIDJ" <<EOF
#!/usr/bin/env bash
# macOS app bundle stub
# Ensures Homebrew is on PATH before launching (needed on Apple Silicon)
if [ -f "/opt/homebrew/bin/brew" ]; then
    eval "\$(/opt/homebrew/bin/brew shellenv)"
fi
cd "$SCRIPT_DIR"
exec $PYTHON_CMD main.py
EOF
chmod +x "$APP_SCRIPT_DIR/SpotifyAIDJ"

# Minimal Info.plist so macOS recognises it as an application
cat > "$APP_BUNDLE/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Spotify AI DJ</string>
    <key>CFBundleIdentifier</key>
    <string>com.spotifyaidj.app</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>SpotifyAIDJ</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

success "App created at: $APP_BUNDLE"
info  "You can drag it from ~/Applications into your Dock."

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo -e "${C_BOLD} ============================================${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}  All done! Setup is complete.${C_RESET}"
echo -e "${C_BOLD} ============================================${C_RESET}"
echo ""
echo -e " You can now launch the app in two ways:"
echo -e "   ${C_BOLD}1.${C_RESET} Open ${C_CYAN}~/Applications/Spotify AI DJ.app${C_RESET}"
echo -e "   ${C_BOLD}2.${C_RESET} Run ${C_CYAN}bash launch.sh${C_RESET} in this folder"
echo ""
echo -e " ${C_YELLOW}First run:${C_RESET} The app will ask for your Gemini API key."
echo -e " Get one free at: ${C_CYAN}https://aistudio.google.com${C_RESET}"
echo ""
echo -e " ${C_YELLOW}First play:${C_RESET} Your browser will open and ask you to"
echo -e " log in to Spotify. That only happens once."
echo ""