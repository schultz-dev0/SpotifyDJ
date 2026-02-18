"""
app_gtk.py
----------
GTK4 GUI backend.
Used on: Linux with a Wayland session (WAYLAND_DISPLAY is set).

This backend produces a native Wayland window. Hyprland window rules,
animations, blur, and borders all apply as normal using the app ID:
  windowrulev2 = float, class:com.spotifyaidj.app
  windowrulev2 = blur,  class:com.spotifyaidj.app

Theming:
  Colours are read at startup from matugen's generated file:
    ~/.config/matugen/generated/colors.css
  If that file is missing or unreadable, Catppuccin Mocha is used instead.
  Layout, fonts, and spacing can be adjusted in _build_css() below.

Requires (installed by install.sh automatically):
  sudo pacman -S python-gobject gtk4
"""

# If you are snooping through the source files, I decided to make a ctk and gtk version because a GUI that looks good is a good gui, don't tell anyone but AI wrote the app_ctk file lol. Idk how to do that stuff hashtag vibecode lmao

import re
import threading
from datetime import datetime
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from brain import get_vibe_params
from config import is_configured, load_config, save_config
from spotify_client import SpotifyClient

APP_TITLE = "Spotify AI DJ"
APP_ID    = "com.spotifyaidj.app"

# matugen writes generated GTK colours here after each wallpaper change
MATUGEN_COLORS_FILE = Path.home() / ".config/matugen/generated/colors.css"

# Catppuccin Mocha - used when matugen colours are not available
CATPPUCCIN_FALLBACK = {
    "bg":         "#1e1e2e",  # base
    "bg_alt":     "#181825",  # mantle
    "surface":    "#313244",  # surface0
    "overlay":    "#45475a",  # surface1
    "muted":      "#6c7086",  # overlay0
    "text":       "#cdd6f4",  # text
    "subtext":    "#a6adc8",  # subtext0
    "primary":    "#89b4fa",  # blue
    "primary_fg": "#1e1e2e",  # base (text on filled primary buttons)
    "secondary":  "#b4befe",  # lavender (hover state)
    "error":      "#f38ba8",  # red
}


def _parse_matugen_colors(css_text: str) -> dict:
    """
    Extract colours from matugen's generated CSS file and map them onto
    the app's semantic colour slots.

    Matugen's actual output format uses GTK @define-color with underscored names:
      @define-color primary #ffb599;
      @define-color surface #1a110e;
      @define-color on_surface #f1dfd9;

    Any slot not found in the file falls back to its Catppuccin value so a
    partial file still produces a coherent theme.
    """
    # Parse all  @define-color name #hex;  declarations
    variables: dict = {}
    for match in re.finditer(r"@define-color\s+([\w]+)\s+(#[0-9a-fA-F]{3,8})", css_text):
        variables[match.group(1)] = match.group(2)

    def first(*keys: str):
        """Return the value of the first key that exists in variables."""
        for key in keys:
            if key in variables:
                return variables[key]
        return None

    c = CATPPUCCIN_FALLBACK.copy()

    # Map matugen's Material You names (underscored) to app colour slots.
    # Multiple candidates listed in preference order for each slot.
    c["bg"]         = first("background", "surface", "surface_dim")              or c["bg"]
    c["bg_alt"]     = first("surface_container_lowest", "surface_container_low") or c["bg_alt"]
    c["surface"]    = first("surface_container_high", "surface_container")       or c["surface"]
    c["overlay"]    = first("surface_container_highest", "outline_variant")      or c["overlay"]
    c["muted"]      = first("outline")                                           or c["muted"]
    c["text"]       = first("on_surface", "on_background")                       or c["text"]
    c["subtext"]    = first("on_surface_variant")                                or c["subtext"]
    c["primary"]    = first("primary")                                           or c["primary"]
    c["primary_fg"] = first("on_primary")                                        or c["primary_fg"]
    c["secondary"]  = first("secondary", "tertiary")                             or c["secondary"]
    c["error"]      = first("error")                                             or c["error"]

    return c




def _load_theme_colors() -> dict:
    """
    Load colours from matugen's generated file if it exists.
    Falls back to Catppuccin Mocha silently if not.
    """
    if MATUGEN_COLORS_FILE.exists():
        try:
            text   = MATUGEN_COLORS_FILE.read_text(encoding="utf-8")
            colors = _parse_matugen_colors(text)
            print(f"[theme] Loaded matugen colours from {MATUGEN_COLORS_FILE}")
            return colors
        except Exception as e:
            print(f"[theme] Could not read matugen colours ({e}) — using Catppuccin fallback")

    return CATPPUCCIN_FALLBACK.copy()


def _build_css(c: dict) -> bytes:
    """
    Render the app's CSS using the provided colour dict.
    To adjust layout, fonts, or spacing, edit the template here.
    """
    css = f"""
    window {{
        background-color: {c['bg']};
        color: {c['text']};
    }}
    .title-large {{
        font-size: 26px;
        font-weight: bold;
        color: {c['text']};
    }}
    .title-medium {{
        font-size: 20px;
        font-weight: bold;
        color: {c['text']};
    }}
    .label-muted {{
        color: {c['muted']};
        font-size: 12px;
    }}
    .label-error {{
        color: {c['error']};
        font-size: 12px;
    }}
    entry {{
        background-color: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['overlay']};
        border-radius: 8px;
        padding: 10px 12px;
        font-size: 13px;
        caret-color: {c['primary']};
    }}
    entry:focus {{
        border-color: {c['primary']};
    }}
    button.primary {{
        background-color: {c['primary']};
        color: {c['primary_fg']};
        border: none;
        border-radius: 8px;
        padding: 10px 0;
        font-size: 14px;
        font-weight: bold;
    }}
    button.primary:hover    {{ background-color: {c['secondary']}; }}
    button.primary:disabled {{ background-color: {c['overlay']}; color: {c['muted']}; }}
    button.secondary {{
        background-color: transparent;
        color: {c['text']};
        border: 1px solid {c['overlay']};
        border-radius: 8px;
        padding: 8px 0;
        font-size: 13px;
    }}
    button.secondary:hover {{ background-color: {c['surface']}; }}
    .log-view {{
        background-color: {c['bg_alt']};
        color: {c['subtext']};
        border-radius: 8px;
        padding: 8px;
        font-family: monospace;
        font-size: 12px;
    }}
    """
    return css.encode("utf-8")


# Build CSS once at import time from whatever theme is currently active.
# Restart the app after running matugen to pick up new colours.
APP_CSS = _build_css(_load_theme_colors())


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _make_key_entry(placeholder: str = "") -> Gtk.Entry:
    """
    Create a password-style entry using Gtk.Entry with a visibility toggle.

    Gtk.PasswordEntry has inconsistent API support across GTK4 versions on
    different distros, so we use a plain Entry with visibility off instead.
    """
    entry = Gtk.Entry()
    entry.set_visibility(False)
    entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    if placeholder:
        entry.set_placeholder_text(placeholder)
    entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "view-conceal-symbolic")
    entry.set_icon_activatable(Gtk.EntryIconPosition.SECONDARY, True)
    entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, "Show / hide")

    def _toggle(_entry, _pos):
        visible = not _entry.get_visibility()
        _entry.set_visibility(visible)
        icon = "view-reveal-symbolic" if visible else "view-conceal-symbolic"
        _entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, icon)

    entry.connect("icon-press", _toggle)
    return entry


# ------------------------------------------------------------------
# Main window
# ------------------------------------------------------------------

class SpotifyAIDJWindow(Gtk.ApplicationWindow):
    """
    Main application window for the GTK4 backend.
    Uses a Gtk.Stack to swap between the setup and player screens.
    """

    def __init__(self, application: Gtk.Application):
        super().__init__(application=application, title=APP_TITLE)
        self.set_default_size(540, 620)
        self.set_resizable(False)

        self._config     = load_config()
        self._spotify    = SpotifyClient()
        self._is_playing = False

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)
        self.set_child(self._stack)

        self._build_setup_screen()
        self._build_player_screen()

        if is_configured():
            self._stack.set_visible_child_name("player")
        else:
            self._stack.set_visible_child_name("setup")

    # ------------------------------------------------------------------
    # Setup screen
    # ------------------------------------------------------------------

    def _build_setup_screen(self) -> None:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_start(48)
        outer.set_margin_end(48)
        outer.set_margin_top(48)
        outer.set_margin_bottom(48)
        outer.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label(label=APP_TITLE)
        title.add_css_class("title-large")
        title.set_margin_bottom(6)
        outer.append(title)

        subtitle = Gtk.Label(label="Tell it what to play. AI does the rest.")
        subtitle.add_css_class("label-muted")
        subtitle.set_margin_bottom(32)
        outer.append(subtitle)

        section = Gtk.Label(label="One-time setup")
        section.set_halign(Gtk.Align.START)
        section.add_css_class("title-medium")
        outer.append(section)

        instructions = Gtk.Label(
            label=(
                "This app uses Google Gemini AI to understand your requests.\n"
                "Get a free API key at: aistudio.google.com  (about 60 seconds)"
            )
        )
        instructions.add_css_class("label-muted")
        instructions.set_halign(Gtk.Align.START)
        instructions.set_wrap(True)
        instructions.set_margin_top(6)
        instructions.set_margin_bottom(18)
        outer.append(instructions)

        key_label = Gtk.Label(label="Gemini API Key")
        key_label.set_halign(Gtk.Align.START)
        key_label.set_margin_bottom(4)
        outer.append(key_label)

        self._setup_key_entry = _make_key_entry("Paste your key here")
        self._setup_key_entry.set_margin_bottom(4)
        self._setup_key_entry.connect("activate", lambda _: self._handle_setup_submit())
        outer.append(self._setup_key_entry)

        self._setup_error_label = Gtk.Label(label="")
        self._setup_error_label.add_css_class("label-error")
        self._setup_error_label.set_halign(Gtk.Align.START)
        self._setup_error_label.set_margin_bottom(8)
        outer.append(self._setup_error_label)

        continue_btn = Gtk.Button(label="Continue")
        continue_btn.add_css_class("primary")
        continue_btn.connect("clicked", lambda _: self._handle_setup_submit())
        continue_btn.set_margin_bottom(16)
        outer.append(continue_btn)

        footer = Gtk.Label(
            label=(
                "Your Spotify credentials are built into the app.\n"
                "You will be redirected to log in to Spotify on first play."
            )
        )
        footer.add_css_class("label-muted")
        footer.set_justify(Gtk.Justification.CENTER)
        outer.append(footer)

        self._stack.add_named(outer, "setup")

    def _handle_setup_submit(self) -> None:
        key = self._setup_key_entry.get_text().strip()
        if not key:
            self._setup_error_label.set_text("Please enter your Gemini API key.")
            return
        if len(key) < 20:
            self._setup_error_label.set_text(
                "That doesn't look like a valid key. Check and try again."
            )
            return
        self._config["gemini_api_key"] = key
        save_config(self._config)
        self._stack.set_visible_child_name("player")

    # ------------------------------------------------------------------
    # Player screen
    # ------------------------------------------------------------------

    def _build_player_screen(self) -> None:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_start(20)
        outer.set_margin_end(20)
        outer.set_margin_top(20)
        outer.set_margin_bottom(20)

        # Top bar
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        top_bar.set_margin_bottom(24)

        title_label = Gtk.Label(label=APP_TITLE)
        title_label.add_css_class("title-medium")
        title_label.set_hexpand(True)
        title_label.set_halign(Gtk.Align.START)
        top_bar.append(title_label)

        settings_btn = Gtk.Button(label="Settings")
        settings_btn.add_css_class("secondary")
        settings_btn.connect("clicked", lambda _: self._open_settings_dialog())
        top_bar.append(settings_btn)
        outer.append(top_bar)

        # Request input
        input_label = Gtk.Label(label="What do you want to hear?")
        input_label.set_halign(Gtk.Align.START)
        input_label.set_margin_bottom(6)
        outer.append(input_label)

        self._request_entry = Gtk.Entry()
        self._request_entry.set_placeholder_text("e.g. 'dark techno' or 'late night lo-fi'")
        self._request_entry.set_margin_bottom(10)
        self._request_entry.connect("activate", lambda _: self._handle_play())
        outer.append(self._request_entry)

        self._play_button = Gtk.Button(label="Play")
        self._play_button.add_css_class("primary")
        self._play_button.connect("clicked", lambda _: self._handle_play())
        self._play_button.set_margin_bottom(20)
        outer.append(self._play_button)

        # Activity log
        activity_label = Gtk.Label(label="Activity")
        activity_label.set_halign(Gtk.Align.START)
        activity_label.set_margin_bottom(6)
        outer.append(activity_label)

        self._log_buffer = Gtk.TextBuffer()

        log_view = Gtk.TextView(buffer=self._log_buffer)
        log_view.set_editable(False)
        log_view.set_cursor_visible(False)
        log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        log_view.add_css_class("log-view")

        # Monospace font via buffer tag - modify_font() is GTK3 only
        self._log_mono_tag = self._log_buffer.create_tag(
            "monospace",
            font_desc=Pango.FontDescription.from_string("monospace 11"),
        )

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(log_view)
        self._log_scroll = scroll
        outer.append(scroll)

        self._stack.add_named(outer, "player")
        self._log("Ready. Enter a request and press Play.")

    # ------------------------------------------------------------------
    # Playback logic
    # ------------------------------------------------------------------

    def _handle_play(self) -> None:
        if self._is_playing:
            return
        request = self._request_entry.get_text().strip()
        if not request:
            self._log("Enter a request first.")
            return
        self._set_busy(True)
        threading.Thread(target=self._play_worker, args=(request,), daemon=True).start()

    def _play_worker(self, request: str) -> None:
        """Background thread: AI query then Spotify playback."""
        self._log(f'Request: "{request}"')

        try:
            config     = load_config()
            directives = get_vibe_params(request, config.get("gemini_api_key", ""))
            self._log(f"AI reasoning: {directives.reasoning}")
            self._log(f"Searching Spotify for: {directives.search_query}")
        except Exception as e:
            GLib.idle_add(self._finish_worker, f"AI error: {e}", False)
            return

        try:
            result = self._spotify.search_and_play(directives.search_query)
        except Exception as e:
            GLib.idle_add(self._finish_worker, f"Spotify error: {e}", False)
            return

        if result.success:
            extra = f" (+{result.track_count - 1} more)" if result.track_count > 1 else ""
            GLib.idle_add(self._finish_worker, f"Now playing: {result.first_track}{extra}", True)
        else:
            GLib.idle_add(self._finish_worker, result.message, False)

    def _finish_worker(self, message: str, success: bool) -> bool:
        self._log(message)
        self._set_busy(False)
        return GLib.SOURCE_REMOVE

    def _set_busy(self, busy: bool) -> None:
        self._is_playing = busy
        self._play_button.set_sensitive(not busy)
        self._play_button.set_label("Working..." if busy else "Play")
        self._request_entry.set_sensitive(not busy)

    # ------------------------------------------------------------------
    # Settings dialog
    # ------------------------------------------------------------------

    def _open_settings_dialog(self) -> None:
        dialog = Gtk.Window(title="Settings")
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        dialog.set_default_size(420, 240)
        dialog.set_resizable(False)

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        frame.set_margin_start(32)
        frame.set_margin_end(32)
        frame.set_margin_top(32)
        frame.set_margin_bottom(32)
        dialog.set_child(frame)

        heading = Gtk.Label(label="Settings")
        heading.add_css_class("title-medium")
        heading.set_halign(Gtk.Align.START)
        heading.set_margin_bottom(16)
        frame.append(heading)

        key_label = Gtk.Label(label="Gemini API Key")
        key_label.set_halign(Gtk.Align.START)
        key_label.set_margin_bottom(4)
        frame.append(key_label)

        key_entry = _make_key_entry()
        key_entry.set_text(self._config.get("gemini_api_key", ""))
        key_entry.set_margin_bottom(8)
        frame.append(key_entry)

        error_label = Gtk.Label(label="")
        error_label.add_css_class("label-error")
        error_label.set_halign(Gtk.Align.START)
        error_label.set_margin_bottom(12)
        frame.append(error_label)

        def save(_btn) -> None:
            new_key = key_entry.get_text().strip()
            if not new_key:
                error_label.set_text("Key cannot be empty.")
                return
            self._config["gemini_api_key"] = new_key
            save_config(self._config)
            self._log("Gemini API key updated.")
            dialog.close()

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("primary")
        save_btn.connect("clicked", save)
        save_btn.set_margin_bottom(8)
        frame.append(save_btn)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("secondary")
        cancel_btn.connect("clicked", lambda _: dialog.close())
        frame.append(cancel_btn)

        dialog.present()

    # ------------------------------------------------------------------
    # Log helper
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """Append a timestamped line to the log. Thread-safe via GLib.idle_add."""
        def _append() -> bool:
            timestamp = datetime.now().strftime("%H:%M:%S")
            end_iter  = self._log_buffer.get_end_iter()
            self._log_buffer.insert_with_tags(
                end_iter,
                f"[{timestamp}] {message}\n",
                self._log_mono_tag,
            )
            adj = self._log_scroll.get_vadjustment()
            adj.set_value(adj.get_upper())
            return GLib.SOURCE_REMOVE

        GLib.idle_add(_append)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def run() -> None:
    """Called by app.py when a Wayland session is detected."""
    application = Gtk.Application(application_id=APP_ID)

    def on_activate(app: Gtk.Application) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(APP_CSS)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        SpotifyAIDJWindow(application=app).present()

    application.connect("activate", on_activate)
    application.run(None)