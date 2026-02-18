# Spotify AI DJ

Why does this exist? Spotify AI DJ sucks, what kinda DJ doesn't take requests?? While working I was having trouble picking out the right music to listen to, and I thought "Man it would be great if I could request a song from an AI that would truly understand what I want, I tried the spotify AI DJ but it really does suck. So I decided to make my own, kinda started out as a super small project, but I liked it so much that I made it into a full app that I can share and get others to use.

Anyways, this one doesn't suck, tell it what you wanna hear and it will play it. Read all of this though ↓
---

## Requirements

- A Spotify account — **playback control requires Spotify Premium**
- A free Gemini API key from [Google AI Studio](https://aistudio.google.com)
  (Takes a few seconds to make, is free!! (a good thing))

---

## Installation

### Windows

1. Download and unzip the project folder
2. Double-click **`install.bat`**
3. If Python is not installed, your browser will open the download page.
   Install Python — make sure to tick **"Add Python to PATH"** — then
   double-click `install.bat` again
4. Launch via the **Spotify AI DJ** shortcut on your Desktop

---

### Linux (all distros — Wayland and X11, it works well in hyprland, cuz I use hyprland)

```bash
git clone https://github.com/schultz-dev0/SpotifyDJ

```

```bash
install.sh
```

The script detects your distro, package manager, and display server
automatically.

Supported distros: Any

On **Wayland** (Hyprland, Sway, GNOME Wayland, etc.) the GTK4 backend is
installed and the app runs as a native Wayland window.

On **X11** the customtkinter backend is used instead.

After install, launch via your application menu or run `bash launch.sh`
from the project folder.

---

### macOS (Big Sur 11+)

```bash
bash install_mac.sh
```

The script installs Homebrew if needed, then Python, tkinter, and all
dependencies. It also creates **`Spotify AI DJ.app`** in `~/Applications`
which you can drag into the Dock.

---

### First launch (all platforms)

On first run, the app will ask for your Gemini API key — paste it in and
press Continue. This is a one-time step.

On first play, your browser will open and ask you to log in to Spotify.
After that the token is saved and you will not be asked again.

---

## Usage

### GUI mode

Launch with no arguments to open the graphical window:

```bash
dj
python main.py
```

Type your request and press **Play** or **Enter**.

---

### CLI mode (Linux / macOS)

Pass your request as an argument — plays immediately, no window opens.
Perfect for terminal workflows, scripts, or keybinds.

```bash
dj "dark techno"
dj "relaxing lo-fi for studying"
dj "90s hip hop"
dj "aggressive drum and bass"
dj "something cinematic and intense"
```

On Windows, use Python directly since the `dj` command is not installed:

```bash
python main.py "dark techno"
```

---

### First-time key setup from terminal

Skip the GUI setup screen entirely by setting your key on the command line:

```bash
dj --set-key YOUR_GEMINI_API_KEY
```

---

### Help

```bash
dj --help
```

---

## Troubleshooting

**"No Spotify device found"**
Open Spotify on your phone, computer, or any device, then try again.
The app can only control a device that already has Spotify running.

**Playback starts but nothing plays / skips immediately**
Spotify Premium is required for remote playback control via the API.
Free accounts can search but cannot be controlled programmatically.

**Gemini quota errors**
The app automatically tries several models in sequence. If all fail it
falls back to basic keyword search so you always get results.

**Linux — GTK4 not found error**
Run `bash install.sh` again. If you installed manually, make sure
`python3-gi` and `gir1.2-gtk-4.0` are installed at the system level
(not via pip).

**macOS — app does not open after double-clicking**
Open Terminal, navigate to the project folder, and run `bash launch.sh`.
If that works, the issue is macOS Gatekeeper blocking unsigned apps.
Go to System Settings > Privacy & Security and allow the app to run.

**Reset the app**
Delete `~/.spotify-ai-dj/` to wipe your saved key and Spotify token.
The setup screen will appear on next launch.

---

## For Developers
(For clarity this section was made with Gemini because I suck at explaining things)

### Project structure

```
SpotifyDJ/
├── main.py             Entry point — routes to GUI or CLI based on arguments
├── app.py              Backend router — detects Wayland vs X11/Windows/macOS
├── app_gtk.py          GTK4 backend (Linux Wayland)
├── app_ctk.py          customtkinter backend (Windows, macOS, Linux X11)
├── cli.py              Headless CLI mode — play without opening a window
├── brain.py            Gemini AI — converts requests to Spotify search queries
├── spotify_client.py   Spotify OAuth and playback control
├── config.py           User config storage (~/.spotify-ai-dj/config.json)
├── requirements.txt    Python dependencies
├── install.bat         Windows installer (double-click)
├── install.sh          Linux installer (all distros, Wayland + X11)
└── install_mac.sh      macOS installer (Big Sur+)
```


### How the backend router works

`app.py` checks `$WAYLAND_DISPLAY` at startup:

```
Linux + WAYLAND_DISPLAY set  ->  app_gtk.py   (native Wayland window)
everything else              ->  app_ctk.py   (customtkinter window)
```

To force a specific backend for testing, edit the `run()` function in
`app.py` and hard-code which backend to load.

### Changing the GTK4 appearance

All colours, fonts, and spacing are defined in the `APP_CSS` constant
near the top of `app_gtk.py`. It uses standard CSS. Edit it freely.

### Changing the customtkinter appearance

Edit the constants at the top of `app_ctk.py`:

```python
ctk.set_appearance_mode("dark")        # "dark" | "light" | "system"
ctk.set_default_color_theme("blue")    # "blue" | "dark-blue" | "green"
```

Font and colour constants (`FONT_*`, `COLOR_*`) are also at the top of
the same file.

### Swapping Spotify credentials

If you fork and redistribute this project, create your own Spotify app
at https://developer.spotify.com/dashboard and set the Redirect URI to
`http://127.0.0.1:8888/callback`. Then update the constants at the top
of `spotify_client.py`:

```python
SPOTIFY_CLIENT_ID     = "your_client_id"
SPOTIFY_CLIENT_SECRET = "your_client_secret"
```

### Changing the AI model list

Edit `CANDIDATE_MODELS` in `brain.py`. Models are tried in order — put
the fastest or most quota-generous ones first.

### Hyprland window rules

The GTK4 backend registers the app with the ID `com.spotifyaidj.app`.
You can target it in `hyprland.conf`:

```
windowrule = float,        class:com.spotifyaidj.app
windowrule = size 540 620, class:com.spotifyaidj.app
windowrule = blur,         class:com.spotifyaidj.app
```

### User config location

| Platform | Path                             |
|----------|----------------------------------|
| Windows  | `C:\Users\<you>\.spotify-ai-dj\` |
| macOS    | `/Users/<you>/.spotify-ai-dj/`   |
| Linux    | `/home/<you>/.spotify-ai-dj/`    |

Contents:

```
config.json      Gemini API key
.spotify_cache   Spotify OAuth token (auto-refreshed)
```

### Packaging into a standalone executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "SpotifyAIDJ" main.py
```

Output is placed in the `dist/` folder. Note that the GTK4 backend
cannot be bundled this way — the PyInstaller build will always use
the customtkinter backend regardless of platform.
