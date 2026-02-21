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

import re
import threading
from datetime import datetime
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango

from brain import get_vibe_params, get_playlist_vibe_params
from config import is_configured, load_config, save_config, load_env_llm_config, save_env_llm_config
from preferences import load_preferences
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
    .player-bar {{
        background-color: {c['surface']};
        border-radius: 10px;
        padding: 10px 16px;
    }}
    .player-control {{
        background-color: transparent;
        color: {c['text']};
        border: 1px solid {c['overlay']};
        border-radius: 8px;
        padding: 4px 0;
        font-size: 16px;
        min-width: 40px;
    }}
    .player-control:hover {{ background-color: {c['surface']}; }}
    switch {{
        background-color: {c['overlay']};
        border-radius: 14px;
    }}
    switch:checked {{
        background-color: {c['primary']};
    }}
    switch slider {{
        background-color: {c['text']};
        border-radius: 12px;
        min-width: 20px;
        min-height: 20px;
    }}
    .log-view {{
        background-color: {c['bg_alt']};
        color: {c['subtext']};
        border-radius: 10px;
        padding: 12px 14px;
        font-family: monospace;
        font-size: 12px;
    }}
    separator {{
        background-color: {c['overlay']};
        min-height: 1px;
        opacity: 0.5;
    }}
    scale {{
        min-width: 80px;
    }}
    scale trough {{
        background-color: {c['overlay']};
        border-radius: 4px;
        min-height: 4px;
    }}
    scale highlight {{
        background-color: {c['primary']};
        border-radius: 4px;
    }}
    scale slider {{
        background-color: {c['text']};
        border-radius: 50%;
        min-width: 14px;
        min-height: 14px;
    }}
    .status-dot-active {{
        color: {c['primary']};
        font-size: 10px;
    }}
    .status-dot-idle {{
        color: {c['muted']};
        font-size: 10px;
    }}
    .input-label {{
        font-size: 11px;
        font-weight: bold;
        color: {c['subtext']};
        letter-spacing: 1px;
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
        outer.set_margin_start(28)
        outer.set_margin_end(28)
        outer.set_margin_top(24)
        outer.set_margin_bottom(24)

        # Top bar
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        top_bar.set_margin_bottom(20)

        title_label = Gtk.Label(label=APP_TITLE)
        title_label.add_css_class("title-large")
        title_label.set_hexpand(True)
        title_label.set_halign(Gtk.Align.START)
        top_bar.append(title_label)

        settings_btn = Gtk.Button(label="Settings")
        settings_btn.add_css_class("secondary")
        settings_btn.connect("clicked", lambda _: self._open_settings_dialog())
        top_bar.append(settings_btn)
        outer.append(top_bar)

        # Request input
        input_label = Gtk.Label(label="WHAT DO YOU WANT TO HEAR?")
        input_label.set_halign(Gtk.Align.START)
        input_label.add_css_class("input-label")
        input_label.set_margin_bottom(6)
        outer.append(input_label)

        self._request_entry = Gtk.Entry()
        self._request_entry.set_placeholder_text("e.g. 'dark techno' or 'late night lo-fi'")
        self._request_entry.set_margin_bottom(10)
        self._request_entry.connect("activate", lambda _: self._handle_play())
        outer.append(self._request_entry)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_margin_bottom(20)

        self._play_button = Gtk.Button(label="Play")
        self._play_button.add_css_class("primary")
        self._play_button.set_hexpand(True)
        self._play_button.connect("clicked", lambda _: self._handle_play())
        btn_row.append(self._play_button)

        self._continue_button = Gtk.Button(label="Continue")
        self._continue_button.add_css_class("secondary")
        self._continue_button.connect("clicked", lambda _: self._handle_continue())
        btn_row.append(self._continue_button)

        outer.append(btn_row)

        # Separator
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep1.set_margin_bottom(16)
        outer.append(sep1)

        # Player bar
        player_frame = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        player_frame.add_css_class("player-bar")
        player_frame.set_margin_bottom(16)

        track_info = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        track_info.set_hexpand(True)

        self._learning_dot = Gtk.Label(label="●")
        self._learning_dot.set_valign(Gtk.Align.CENTER)
        track_info.append(self._learning_dot)

        self._track_label = Gtk.Label(label="Not playing")
        self._track_label.add_css_class("label-muted")
        self._track_label.set_halign(Gtk.Align.START)
        self._track_label.set_hexpand(True)
        self._track_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._track_label.set_max_width_chars(38)
        track_info.append(self._track_label)
        player_frame.append(track_info)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self._prev_button = Gtk.Button(label="⏮")
        self._prev_button.add_css_class("player-control")
        self._prev_button.connect("clicked", lambda _: self._handle_previous())
        controls.append(self._prev_button)

        self._next_button = Gtk.Button(label="⏭")
        self._next_button.add_css_class("player-control")
        self._next_button.connect("clicked", lambda _: self._handle_skip())
        controls.append(self._next_button)

        self._like_button = Gtk.Button(label="♡")
        self._like_button.add_css_class("player-control")
        self._like_button.connect("clicked", lambda _: self._handle_like())
        controls.append(self._like_button)

        # Volume slider
        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        vol_box.set_margin_start(8)

        vol_icon = Gtk.Label(label=" ")
        vol_icon.add_css_class("label-muted")
        vol_box.append(vol_icon)

        self._vol_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self._vol_slider.set_value(50)
        self._vol_slider.set_draw_value(False)
        self._vol_slider.set_size_request(80, -1)
        self._vol_slider.set_tooltip_text("Volume")
        self._vol_slider_handler = self._vol_slider.connect("value-changed", self._on_volume_changed)
        vol_box.append(self._vol_slider)

        controls.append(vol_box)
        player_frame.append(controls)
        outer.append(player_frame)

        # Separator
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep2.set_margin_top(4)
        sep2.set_margin_bottom(12)
        outer.append(sep2)

        # Bottom pane: queue list (left) + activity log (right)
        bottom_pane = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bottom_pane.set_vexpand(True)
        outer.append(bottom_pane)

        # -- Queue panel --
        queue_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        queue_col.set_size_request(180, -1)

        queue_label = Gtk.Label(label="UP NEXT")
        queue_label.set_halign(Gtk.Align.START)
        queue_label.add_css_class("input-label")
        queue_label.set_margin_bottom(6)
        queue_col.append(queue_label)

        self._queue_store = Gtk.StringList()
        self._queue_list  = Gtk.ListView()

        factory = Gtk.SignalListItemFactory()
        def _setup(f, item):
            lbl = Gtk.Label()
            lbl.set_halign(Gtk.Align.START)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_max_width_chars(22)
            lbl.add_css_class("label-muted")
            item.set_child(lbl)
        def _bind(f, item):
            item.get_child().set_text(item.get_item().get_string())
        factory.connect("setup", _setup)
        factory.connect("bind",  _bind)

        self._queue_list.set_factory(factory)
        self._queue_list.set_model(Gtk.NoSelection.new(self._queue_store))
        self._queue_list.add_css_class("log-view")

        queue_scroll = Gtk.ScrolledWindow()
        queue_scroll.set_vexpand(True)
        queue_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        queue_scroll.set_child(self._queue_list)
        queue_col.append(queue_scroll)
        bottom_pane.append(queue_col)

        # Vertical separator
        vsep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        bottom_pane.append(vsep)

        # -- Activity log --
        log_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        log_col.set_hexpand(True)

        activity_label = Gtk.Label(label="ACTIVITY")
        activity_label.set_halign(Gtk.Align.START)
        activity_label.add_css_class("input-label")
        activity_label.set_margin_bottom(6)
        log_col.append(activity_label)

        self._log_buffer = Gtk.TextBuffer()

        log_view = Gtk.TextView(buffer=self._log_buffer)
        log_view.set_editable(False)
        log_view.set_cursor_visible(False)
        log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        log_view.add_css_class("log-view")

        self._log_mono_tag = self._log_buffer.create_tag(
            "monospace",
            font_desc=Pango.FontDescription.from_string("monospace 11"),
        )

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(log_view)
        self._log_scroll = scroll
        log_col.append(scroll)
        bottom_pane.append(log_col)

        self._stack.add_named(outer, "player")
        # Set initial learning dot state
        self._learning_dot.add_css_class("status-dot-active")
        self._learning_dot.set_tooltip_text("Preference learning: ON")
        self._log("Ready. Enter a request and press Play.")
        # Pre-authenticate on the main thread so worker threads never need
        # to trigger the OAuth browser flow (which deadlocks in GTK).
        # Do it in an idle callback so the window is visible first.
        def _preauth():
            try:
                self._spotify._get_client()
                # Route spotify_client log messages to the activity log
                self._spotify._log_fn = self._log
                # Warm up the local LLM in the background so first request isn't slow
                self._spotify.ensure_local_llm_warm()
                # Start skip detector globally — catches media key / keybind skips too
                self._spotify.skip_detector.start()
                print("[skip_detector] Global skip monitoring active")
            except Exception as e:
                print(f"[auth] pre-auth failed: {e}")
            self._start_player_poll()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(800, _preauth)

    # ------------------------------------------------------------------
    # Playback logic
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Player bar controls
    # ------------------------------------------------------------------

    def _on_volume_changed(self, slider) -> None:
        """Debounced volume change — only fires Spotify API call when user stops dragging."""
        vol = int(slider.get_value())
        if hasattr(self, "_vol_timer_id"):
            GLib.source_remove(self._vol_timer_id)
        def _apply():
            self._spotify.set_volume(vol)
            return GLib.SOURCE_REMOVE
        self._vol_timer_id = GLib.timeout_add(400, _apply)

    def _handle_like(self) -> None:
        def _work():
            ok, msg = self._spotify.like_current_track()
            self._log(msg)
            GLib.idle_add(self._refresh_player_bar)
        threading.Thread(target=_work, daemon=True).start()

    def _handle_skip(self) -> None:
        def _work():
            ok, msg = self._spotify.skip_track()
            if ok:
                import time; time.sleep(0.6)
                GLib.idle_add(self._refresh_player_bar)
            else:
                self._log(msg)
        threading.Thread(target=_work, daemon=True).start()

    def _handle_previous(self) -> None:
        def _work():
            ok, msg = self._spotify.previous_track()
            if ok:
                import time; time.sleep(0.6)
                GLib.idle_add(self._refresh_player_bar)
            else:
                self._log(msg)
        threading.Thread(target=_work, daemon=True).start()

    def _refresh_player_bar(self) -> bool:
        """Poll Spotify for current track and update the bar. GLib-safe."""
        def _work():
            track = self._spotify.get_current_track()
            GLib.idle_add(self._update_player_bar, track)
        threading.Thread(target=_work, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _update_player_bar(self, track) -> bool:
        if not hasattr(self, "_track_label"):
            return GLib.SOURCE_REMOVE
        if track:
            self._track_label.set_text(f"{track['name']}  —  {track['artist']}")
            self._track_label.remove_css_class("label-muted")
            self._like_button.set_label("♥" if track["is_liked"] else "♡")
            # Sync volume slider without triggering the change handler
            vol = self._spotify.get_volume()
            if vol >= 0:
                self._vol_slider.handler_block(self._vol_slider_handler)
                self._vol_slider.set_value(vol)
                self._vol_slider.handler_unblock(self._vol_slider_handler)
        else:
            self._track_label.set_text("Not playing")
            self._track_label.add_css_class("label-muted")
            self._like_button.set_label("♡")
        # Refresh queue panel
        def _fetch_queue():
            items = self._spotify.get_queue()
            GLib.idle_add(self._update_queue_panel, items)
        threading.Thread(target=_fetch_queue, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _update_queue_panel(self, items: list) -> bool:
        while self._queue_store.get_n_items():
            self._queue_store.remove(0)
        for t in items:
            self._queue_store.append(f"{t['name']}  —  {t['artist']}")
        return GLib.SOURCE_REMOVE

    def _start_player_poll(self) -> None:
        """Poll current track every 5 seconds."""
        self._refresh_player_bar()
        GLib.timeout_add(5000, self._poll_tick)

    def _poll_tick(self) -> bool:
        self._refresh_player_bar()
        return GLib.SOURCE_CONTINUE  # repeat

    def _handle_play(self) -> None:
        if self._is_playing:
            return
        request = self._request_entry.get_text().strip()
        if not request:
            self._log("Enter a request first.")
            return
        self._spotify.last_request = request
        self._set_busy(True)
        threading.Thread(target=self._play_worker, args=(request, False), daemon=True).start()

    def _handle_continue(self) -> None:
        if self._is_playing:
            return
        if not self._spotify.last_request:
            self._log("Nothing playing yet — use Play first.")
            return
        self._set_busy(True)
        threading.Thread(target=self._play_worker, args=(self._spotify.last_request, True), daemon=True).start()

    def _play_worker(self, request: str, is_continue: bool = False) -> None:
        """Background thread: AI query then Spotify playback."""
        if is_continue:
            self._log(f'Continuing: "{request}"')
        else:
            self._log(f'Request: "{request}"')

        try:
            config     = load_config()
            api_key    = config.get("gemini_api_key", "")
            local_only = config.get("local_ai_only", False)

            # Detect playlist URL in request
            import re as _re
            playlist_url = _re.search(
                r"(https?://open\.spotify\.com/playlist/[A-Za-z0-9]+|spotify:playlist:[A-Za-z0-9]+)",
                request
            )

            if is_continue:
                from brain import get_continue_params
                queue_tracks = self._spotify.get_queue()
                if queue_tracks:
                    self._log(f"Queue snapshot: {len(queue_tracks)} tracks — using for smarter continuation")
                directives = get_continue_params(
                    self._spotify.last_request,
                    self._spotify.last_queries,
                    api_key,
                    local_only=local_only,
                    queue_tracks=queue_tracks,
                )
                playlist_tracks = None
            elif playlist_url:
                self._log("Playlist detected — fetching tracks...")
                try:
                    playlist_tracks = self._spotify.get_playlist_tracks(playlist_url.group(0))
                    self._log(f"Fetched {len(playlist_tracks)} tracks from playlist")
                except Exception as e:
                    GLib.idle_add(self._finish_worker, f"Playlist error: {e}", False)
                    return
                # Strip the URL from the prompt so the AI sees only the user's intent
                user_intent = _re.sub(r"https?://\S+|spotify:\S+", "", request).strip()
                directives = get_playlist_vibe_params(
                    playlist_tracks, user_intent, api_key, local_only=local_only
                )
                self._log(f"AI: {directives.reasoning}")
                self._log(f"Running {len(directives.queries)} searches for similar tracks...")
            else:
                playlist_tracks = None
                directives = get_vibe_params(request, api_key, local_only=local_only)
                self._log(f"AI: {directives.reasoning}")
                self._log(f"Running {len(directives.queries)} searches, targeting {directives.queue_size} tracks...")
        except Exception as e:
            GLib.idle_add(self._finish_worker, f"AI error: {e}", False)
            return

        try:
            result = self._spotify.search_and_play(directives)
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
        if success:
            GLib.timeout_add(1200, self._refresh_player_bar)
            # Start skip detector — detects skips within 20s as dislike signals
            self._spotify.skip_detector.start()
        return GLib.SOURCE_REMOVE

    def _set_busy(self, busy: bool) -> None:
        self._is_playing = busy
        self._play_button.set_sensitive(not busy)
        self._play_button.set_label("Working..." if busy else "Play")
        self._continue_button.set_sensitive(not busy)
        self._request_entry.set_sensitive(not busy)

    # ------------------------------------------------------------------
    # Settings dialog
    # ------------------------------------------------------------------

    def _open_settings_dialog(self) -> None:
        llm_cfg = load_env_llm_config()

        dialog = Gtk.Window(title="Settings")
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        dialog.set_default_size(460, 540)
        dialog.set_resizable(False)

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        frame.set_margin_start(32)
        frame.set_margin_end(32)
        frame.set_margin_top(32)
        frame.set_margin_bottom(32)
        dialog.set_child(frame)

        def _section(title: str, margin_top: int = 0) -> None:
            lbl = Gtk.Label(label=title)
            lbl.add_css_class("title-medium")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_margin_top(margin_top)
            lbl.set_margin_bottom(10)
            frame.append(lbl)

        def _field(label: str, value: str, placeholder: str = "") -> Gtk.Entry:
            lbl = Gtk.Label(label=label)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_margin_bottom(3)
            frame.append(lbl)
            entry = Gtk.Entry()
            entry.set_text(value)
            if placeholder:
                entry.set_placeholder_text(placeholder)
            entry.set_margin_bottom(10)
            frame.append(entry)
            return entry

        # ---- Gemini ----
        _section("Gemini API Key")
        gemini_entry = _make_key_entry()
        gemini_entry.set_text(self._config.get("gemini_api_key", ""))
        gemini_entry.set_placeholder_text("AIza...")
        gemini_entry.set_margin_bottom(16)
        frame.append(gemini_entry)

        # ---- Local LLM ----
        _section("Local LLM  (optional)", margin_top=4)

        hint = Gtk.Label(label="Leave blank to use Gemini only. Ollama: http://localhost:11434")
        hint.add_css_class("label-muted")
        hint.set_halign(Gtk.Align.START)
        hint.set_wrap(True)
        hint.set_margin_bottom(10)
        frame.append(hint)

        url_entry   = _field("Base URL",  llm_cfg["base_url"],  "http://localhost:11434")
        key_entry   = _field("API Key",   llm_cfg["api_key"],   "sk-... or leave blank for Ollama")
        model_entry = _field("Model",     llm_cfg["model"],     "llama3.2:latest")

        # ---- Toggles ----
        def _toggle_row(label_text: str, active: bool) -> Gtk.Switch:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_top(6)
            row.set_margin_bottom(6)
            lbl = Gtk.Label(label=label_text)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_hexpand(True)
            sw = Gtk.Switch()
            sw.set_active(active)
            sw.set_valign(Gtk.Align.CENTER)
            row.append(lbl)
            row.append(sw)
            frame.append(row)
            return sw

        toggle_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        toggle_sep.set_margin_top(8)
        toggle_sep.set_margin_bottom(8)
        frame.append(toggle_sep)

        local_only_switch  = _toggle_row(
            "Use local AI only  (skip Gemini entirely)",
            self._config.get("local_ai_only", False)
        )
        learning_switch = _toggle_row(
            "Enable preference learning  (likes, skips, taste profile)",
            self._config.get("learning_enabled", True)
        )

        prefs = load_preferences()
        n_liked    = len(prefs.get("liked_tracks", []))
        n_skipped  = len(prefs.get("skipped_tracks", []))
        has_vector = prefs.get("taste_centroid") is not None
        pref_hint  = Gtk.Label(
            label=f"Profile: {n_liked} liked · {n_skipped} skipped · embedding {'ready' if has_vector else 'building...'}"
        )
        pref_hint.add_css_class("label-muted")
        pref_hint.set_halign(Gtk.Align.START)
        pref_hint.set_margin_bottom(8)
        frame.append(pref_hint)

        # ---- Error / buttons ----
        error_label = Gtk.Label(label="")
        error_label.add_css_class("label-error")
        error_label.set_halign(Gtk.Align.START)
        error_label.set_margin_bottom(10)
        frame.append(error_label)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        frame.append(btn_row)

        def save(_btn) -> None:
            using_local_only = local_only_switch.get_active()
            new_gemini = gemini_entry.get_text().strip()

            # Gemini key only required when not in local-only mode
            if not using_local_only and not new_gemini:
                error_label.set_text("Gemini API key required (or enable local-only mode).")
                return

            self._config["gemini_api_key"]   = new_gemini
            self._config["local_ai_only"]    = using_local_only
            self._config["learning_enabled"] = learning_switch.get_active()
            save_config(self._config)

            save_env_llm_config(
                base_url = url_entry.get_text().strip(),
                api_key  = key_entry.get_text().strip(),
                model    = model_entry.get_text().strip() or "llama3.2:latest",
            )
            mode     = "local-only" if using_local_only else "Gemini + local fallback"
            learning = "on" if learning_switch.get_active() else "off"
            self._log(f"Settings saved. AI mode: {mode} | Learning: {learning}")
            dialog.close()

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("primary")
        save_btn.set_hexpand(True)
        save_btn.connect("clicked", save)
        btn_row.append(save_btn)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("secondary")
        cancel_btn.connect("clicked", lambda _: dialog.close())
        btn_row.append(cancel_btn)

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