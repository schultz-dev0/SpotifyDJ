#!/usr/bin/env bash
# install.sh - Spotify AI DJ installer for Linux
#
# Supports: Debian/Ubuntu, Arch/Manjaro, Fedora/RHEL, openSUSE, Gentoo
# Run with: bash install.sh

set -e  # Exit immediately if any command fails

# ------------------------------------------------------------------
# Colours for output (disabled automatically if not a terminal)
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

# ------------------------------------------------------------------
# Locate the directory this script lives in so paths are always
# correct regardless of where the user runs it from.
# ------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ------------------------------------------------------------------
# Step 1 - Detect the package manager
# ------------------------------------------------------------------
info "Detecting package manager..."

PKG_MANAGER=""
DISTRO_NAME=""

if command -v apt-get &>/dev/null; then
    PKG_MANAGER="apt"
    DISTRO_NAME="Debian/Ubuntu"
elif command -v pacman &>/dev/null; then
    PKG_MANAGER="pacman"
    DISTRO_NAME="Arch Linux"
elif command -v dnf &>/dev/null; then
    PKG_MANAGER="dnf"
    DISTRO_NAME="Fedora/RHEL"
elif command -v zypper &>/dev/null; then
    PKG_MANAGER="zypper"
    DISTRO_NAME="openSUSE"
elif command -v emerge &>/dev/null; then
    PKG_MANAGER="emerge"
    DISTRO_NAME="Gentoo"
else
    warn "Could not detect a supported package manager."
    warn "You will need to install the following manually:"
    warn "  - Python 3.10+"
    warn "  - python3-tk  (tkinter)"
    warn "  - python3-gi, python3-gi-cairo, gir1.2-gtk-4.0  (GTK4, Wayland only)"
    warn "Then run:  pip install -r requirements.txt"
    PKG_MANAGER="unknown"
fi

if [ "$PKG_MANAGER" != "unknown" ]; then
    success "Found: $DISTRO_NAME ($PKG_MANAGER)"
fi

# ------------------------------------------------------------------
# Step 2 - Detect display server (Wayland vs X11)
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
# Step 3 - Check Python version
# ------------------------------------------------------------------
info "Checking Python version..."

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)
        major=$("$cmd" -c 'import sys; print(sys.version_info.major)')
        minor=$("$cmd" -c 'import sys; print(sys.version_info.minor)')
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            success "Found $($cmd --version)"
            break
        fi
    fi
done

# ------------------------------------------------------------------
# Step 4 - Install Python if missing
# ------------------------------------------------------------------
if [ -z "$PYTHON_CMD" ]; then
    warn "Python 3.10+ not found. Installing..."

    case "$PKG_MANAGER" in
        apt)
            sudo apt-get update -qq
            sudo apt-get install -y python3 python3-pip
            ;;
        pacman)
            sudo pacman -Sy --noconfirm python python-pip
            ;;
        dnf)
            sudo dnf install -y python3 python3-pip
            ;;
        zypper)
            sudo zypper install -y python3 python3-pip
            ;;
        emerge)
            sudo emerge dev-lang/python
            ;;
        *)
            error "Cannot install Python automatically. Please install Python 3.10+ manually."
            ;;
    esac

    # Re-check after install
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
    success "Python installed successfully."
fi

# ------------------------------------------------------------------
# Step 5 - Install tkinter (needed for X11 / non-Wayland fallback)
# ------------------------------------------------------------------
info "Installing tkinter..."

case "$PKG_MANAGER" in
    apt)
        sudo apt-get install -y python3-tk
        ;;
    pacman)
        sudo pacman -Sy --noconfirm tk
        ;;
    dnf)
        sudo dnf install -y python3-tkinter
        ;;
    zypper)
        sudo zypper install -y python3-tk
        ;;
    emerge)
        sudo emerge dev-python/tkinter
        ;;
    unknown)
        warn "Skipping tkinter install - please install it manually."
        ;;
esac

# ------------------------------------------------------------------
# Step 6 - Install GTK4 + PyGObject if on Wayland
# ------------------------------------------------------------------
if [ "$WAYLAND" = true ]; then
    info "Installing GTK4 libraries for Wayland support..."

    case "$PKG_MANAGER" in
        apt)
            sudo apt-get install -y \
                python3-gi \
                python3-gi-cairo \
                gir1.2-gtk-4.0 \
                libgtk-4-dev
            ;;
        pacman)
            sudo pacman -Sy --noconfirm \
                python-gobject \
                gtk4
            ;;
        dnf)
            sudo dnf install -y \
                python3-gobject \
                gtk4
            ;;
        zypper)
            sudo zypper install -y \
                python3-gobject \
                typelib-1_0-Gtk-4_0
            ;;
        emerge)
            sudo emerge dev-python/pygobject gui-libs/gtk
            ;;
        unknown)
            warn "Skipping GTK4 install - please install PyGObject and GTK4 manually."
            ;;
    esac

    success "GTK4 libraries installed."
else
    info "Skipping GTK4 install (not needed on X11)."
fi

# ------------------------------------------------------------------
# Step 7 - Install Python dependencies via pip
# ------------------------------------------------------------------
info "Installing Python dependencies..."

# Use --break-system-packages on newer systems that enforce PEP 668,
# but only if the flag is actually supported by this pip version.
PIP_FLAGS=""
if $PYTHON_CMD -m pip install --help 2>&1 | grep -q "break-system-packages"; then
    PIP_FLAGS="--break-system-packages"
fi

$PYTHON_CMD -m pip install --upgrade pip --quiet $PIP_FLAGS
$PYTHON_CMD -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet $PIP_FLAGS

success "Python dependencies installed."

# ------------------------------------------------------------------
# Step 8 - Create a .desktop launcher (shows up in app menus)
# ------------------------------------------------------------------
info "Creating application launcher..."

DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

DESKTOP_FILE="$DESKTOP_DIR/spotify-ai-dj.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Spotify AI DJ
Comment=Tell it what to play. AI does the rest.
Exec=$PYTHON_CMD $SCRIPT_DIR/main.py
Terminal=false
Type=Application
Categories=AudioVideo;Music;
StartupWMClass=com.spotifyaidj.app
EOF

chmod +x "$DESKTOP_FILE"

# Also update the desktop database so the entry appears immediately
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

success "App launcher created (check your application menu)."

# ------------------------------------------------------------------
# Step 9 - Create a quick-launch shell script
# ------------------------------------------------------------------
LAUNCH_SCRIPT="$SCRIPT_DIR/launch.sh"
cat > "$LAUNCH_SCRIPT" <<EOF
#!/usr/bin/env bash
# Quick launcher for Spotify AI DJ
# Accepts optional arguments for CLI mode:
#   bash launch.sh                   -> open GUI
#   bash launch.sh "dark techno"     -> play immediately
cd "$SCRIPT_DIR"
exec $PYTHON_CMD main.py "\$@"
EOF
chmod +x "$LAUNCH_SCRIPT"

success "launch.sh created in the app folder."

# ------------------------------------------------------------------
# Step 10 - Install the 'dj' command to /usr/local/bin
# This allows running:  dj "dark techno"  from any terminal
# ------------------------------------------------------------------
info "Installing 'dj' command..."

DJ_WRAPPER="/usr/local/bin/dj"

sudo tee "$DJ_WRAPPER" > /dev/null <<EOF
#!/usr/bin/env bash
# dj - Spotify AI DJ command
# GUI mode:  dj
# CLI mode:  dj "dark techno"
# Set key:   dj --set-key YOUR_API_KEY
cd "$SCRIPT_DIR"
exec $PYTHON_CMD main.py "\$@"
EOF

sudo chmod +x "$DJ_WRAPPER"

success "'dj' command installed. You can now use it from any terminal."

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo -e "${C_BOLD} ============================================${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}  All done! Setup is complete.${C_RESET}"
echo -e "${C_BOLD} ============================================${C_RESET}"
echo ""
echo -e " ${C_BOLD}GUI mode${_RESET} - open the app window:"
echo -e "   ${C_CYAN}dj${C_RESET}  or search 'Spotify AI DJ' in your app menu"
echo ""
echo -e " ${C_BOLD}CLI mode${C_RESET} - play immediately from terminal:"
echo -e "   ${C_CYAN}dj \"dark techno\"${C_RESET}"
echo -e "   ${C_CYAN}dj \"relaxing lo-fi for studying\"${C_RESET}"
echo ""
echo -e " ${C_YELLOW}First run:${C_RESET} The app will ask for your Gemini API key."
echo -e " Get one free at: ${C_CYAN}https://aistudio.google.com${C_RESET}"
echo -e " Or set it now:   ${C_CYAN}dj --set-key YOUR_KEY_HERE${C_RESET}"
echo ""
echo -e " ${C_YELLOW}First play:${C_RESET} Your browser will open and ask you to"
echo -e " log in to Spotify. That only happens once."
echo ""