"""
app_ctk.py
----------
customtkinter GUI backend.
Used on: Windows, macOS, and Linux under X11.

Customisation reference:
  Colour theme  ->  ctk.set_default_color_theme()  options: "blue" "dark-blue" "green"
  Light/dark    ->  ctk.set_appearance_mode()       options: "dark" "light" "system"
  Window size   ->  WINDOW_WIDTH / WINDOW_HEIGHT constants below
  Fonts/colours ->  FONT_* and COLOR_* constants below
"""

import threading
from threading import Timer
from datetime import datetime

import customtkinter as ctk

from brain import get_vibe_params
from config import is_configured, load_config, save_config
from spotify_client import SpotifyClient

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_TITLE     = "Spotify AI DJ"
WINDOW_WIDTH  = 540
WINDOW_HEIGHT = 620

FONT_TITLE  = ("Helvetica", 26, "bold")
FONT_MEDIUM = ("Helvetica", 15, "bold")
FONT_BODY   = ("Helvetica", 13)
FONT_SMALL  = ("Helvetica", 11)
FONT_LOG    = ("Courier", 12)

COLOR_ERROR   = "#FF6B6B"
COLOR_SUCCESS = "#4CAF82"
COLOR_MUTED   = "gray"


class SpotifyAIDJApp(ctk.CTk):
    """
    Root application window for the customtkinter backend.

    Two screens are managed by swapping widget trees:
      - Setup screen  : first-run, collects Gemini API key
      - Player screen : main interface
    """

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)

        self._config    = load_config()
        self._spotify   = SpotifyClient()
        self._is_playing = False  # Blocks duplicate requests while one is running

        if is_configured():
            self._show_player_screen()
        else:
            self._show_setup_screen()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_window(self) -> None:
        """Remove all widgets from the window so a new screen can be drawn."""
        for widget in self.winfo_children():
            widget.destroy()

    # ------------------------------------------------------------------
    # Setup screen
    # ------------------------------------------------------------------

    def _show_setup_screen(self) -> None:
        """First-run screen. Collects and saves the user's Gemini API key."""
        self._clear_window()

        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(expand=True, fill="both", padx=48, pady=48)

        ctk.CTkLabel(outer, text=APP_TITLE, font=FONT_TITLE).pack(pady=(0, 6))
        ctk.CTkLabel(
            outer,
            text="Tell it what to play. AI does the rest.",
            font=FONT_BODY,
            text_color=COLOR_MUTED,
        ).pack(pady=(0, 32))

        ctk.CTkLabel(outer, text="One-time setup", font=FONT_MEDIUM).pack(anchor="w")
        ctk.CTkLabel(
            outer,
            text=(
                "This app uses Google Gemini AI to understand your requests.\n"
                "Get a free API key at: aistudio.google.com  (about 60 seconds)"
            ),
            font=FONT_SMALL,
            text_color=COLOR_MUTED,
            justify="left",
            wraplength=WINDOW_WIDTH - 96,
        ).pack(anchor="w", pady=(6, 18))

        ctk.CTkLabel(outer, text="Gemini API Key", font=FONT_BODY).pack(anchor="w")
        self._setup_key_entry = ctk.CTkEntry(
            outer,
            placeholder_text="Paste your key here",
            height=42,
            show="*",
            font=FONT_BODY,
        )
        self._setup_key_entry.pack(fill="x", pady=(4, 4))
        self._setup_key_entry.bind("<Return>", lambda _: self._handle_setup_submit())

        self._show_key_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            outer,
            text="Show key",
            variable=self._show_key_var,
            command=self._toggle_key_visibility,
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(2, 16))

        self._setup_error_label = ctk.CTkLabel(
            outer, text="", text_color=COLOR_ERROR, font=FONT_SMALL
        )
        self._setup_error_label.pack(pady=(0, 4))

        ctk.CTkButton(
            outer,
            text="Continue",
            height=44,
            font=("Helvetica", 14, "bold"),
            command=self._handle_setup_submit,
        ).pack(fill="x")

        ctk.CTkLabel(
            outer,
            text=(
                "Your Spotify credentials are built into the app.\n"
                "You will be redirected to log in to Spotify on first play."
            ),
            font=("Helvetica", 10),
            text_color=COLOR_MUTED,
            justify="center",
        ).pack(pady=(20, 0))

    def _toggle_key_visibility(self) -> None:
        self._setup_key_entry.configure(show="" if self._show_key_var.get() else "*")

    def _handle_setup_submit(self) -> None:
        key = self._setup_key_entry.get().strip()
        if not key:
            self._setup_error_label.configure(text="Please enter your Gemini API key.")
            return
        if len(key) < 20:
            self._setup_error_label.configure(
                text="That doesn't look like a valid key. Check and try again."
            )
            return
        self._config["gemini_api_key"] = key
        save_config(self._config)
        self._show_player_screen()

    # ------------------------------------------------------------------
    # Player screen
    # ------------------------------------------------------------------

    def _show_player_screen(self) -> None:
        """Main player UI shown after setup is complete."""
        self._clear_window()

        # Top bar
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(20, 0))
        ctk.CTkLabel(top_bar, text=APP_TITLE, font=("Helvetica", 20, "bold")).pack(side="left")
        ctk.CTkButton(
            top_bar,
            text="Settings",
            width=80,
            height=30,
            font=FONT_SMALL,
            fg_color="transparent",
            border_width=1,
            command=self._open_settings_dialog,
        ).pack(side="right")

        # Request input
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.pack(fill="x", padx=20, pady=(24, 0))

        ctk.CTkLabel(
            input_frame, text="What do you want to hear?", font=FONT_BODY
        ).pack(anchor="w", pady=(0, 6))

        self._request_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="e.g. 'dark techno' or 'late night lo-fi'",
            height=44,
            font=FONT_BODY,
        )
        self._request_entry.pack(fill="x")
        self._request_entry.bind("<Return>", lambda _: self._handle_play())

        btn_row = ctk.CTkFrame(input_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))

        self._play_button = ctk.CTkButton(
            btn_row,
            text="Play",
            height=44,
            font=("Helvetica", 14, "bold"),
            command=self._handle_play,
        )
        self._play_button.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._continue_button = ctk.CTkButton(
            btn_row,
            text="Continue",
            height=44,
            width=120,
            font=("Helvetica", 14, "bold"),
            fg_color="transparent",
            border_width=1,
            command=self._handle_continue,
        )
        self._continue_button.pack(side="left")

        # Player bar
        player_frame = ctk.CTkFrame(self, corner_radius=10)
        player_frame.pack(fill="x", padx=20, pady=(16, 0))

        # Track info
        self._track_label = ctk.CTkLabel(
            player_frame,
            text="Not playing",
            font=("Helvetica", 12),
            text_color="gray",
            anchor="w",
            wraplength=WINDOW_WIDTH - 180,
        )
        self._track_label.pack(side="left", padx=(12, 0), pady=10, fill="x", expand=True)

        # Controls (right side)
        controls = ctk.CTkFrame(player_frame, fg_color="transparent")
        controls.pack(side="right", padx=8, pady=6)

        self._prev_button = ctk.CTkButton(
            controls, text="⏮", width=36, height=32,
            font=("Helvetica", 14),
            fg_color="transparent", border_width=1,
            command=self._handle_previous,
        )
        self._prev_button.pack(side="left", padx=2)

        self._next_button = ctk.CTkButton(
            controls, text="⏭", width=36, height=32,
            font=("Helvetica", 14),
            fg_color="transparent", border_width=1,
            command=self._handle_skip,
        )
        self._next_button.pack(side="left", padx=2)

        self._like_button = ctk.CTkButton(
            controls, text="♡", width=36, height=32,
            font=("Helvetica", 14),
            fg_color="transparent", border_width=1,
            command=self._handle_like,
        )
        self._like_button.pack(side="left", padx=2)

        # Activity log
        log_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, padx=20, pady=(16, 20))

        ctk.CTkLabel(log_frame, text="Activity", font=("Helvetica", 13, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        self._log_box = ctk.CTkTextbox(
            log_frame, font=FONT_LOG, state="disabled", wrap="word"
        )
        self._log_box.pack(fill="both", expand=True)

        self._log("Ready. Enter a request and press Play.")

        def _preauth():
            try:
                self._spotify._get_client()
            except Exception as e:
                print(f"[auth] pre-auth failed: {e}")
            self._start_player_poll()

        self.after(800, _preauth)

    # ------------------------------------------------------------------
    # Playback logic
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Player bar controls
    # ------------------------------------------------------------------

    def _handle_like(self) -> None:
        def _work():
            ok, msg = self._spotify.like_current_track()
            self._log(msg)
            self.after(0, self._refresh_player_bar)
        threading.Thread(target=_work, daemon=True).start()

    def _handle_skip(self) -> None:
        def _work():
            ok, msg = self._spotify.skip_track()
            if ok:
                # Brief pause then refresh so Spotify has time to change tracks
                import time; time.sleep(0.6)
                self.after(0, self._refresh_player_bar)
            else:
                self._log(msg)
        threading.Thread(target=_work, daemon=True).start()

    def _handle_previous(self) -> None:
        def _work():
            ok, msg = self._spotify.previous_track()
            if ok:
                import time; time.sleep(0.6)
                self.after(0, self._refresh_player_bar)
            else:
                self._log(msg)
        threading.Thread(target=_work, daemon=True).start()

    def _refresh_player_bar(self) -> None:
        """Poll Spotify for the current track and update the player bar."""
        if not hasattr(self, "_track_label"):
            return
        def _work():
            track = self._spotify.get_current_track()
            self.after(0, lambda: self._update_player_bar(track))
        threading.Thread(target=_work, daemon=True).start()

    def _update_player_bar(self, track: dict | None) -> None:
        if not hasattr(self, "_track_label"):
            return
        if track:
            self._track_label.configure(
                text=f"{track['name']}  —  {track['artist']}",
                text_color="white",
            )
            self._like_button.configure(text="♥" if track["is_liked"] else "♡")
        else:
            self._track_label.configure(text="Not playing", text_color="gray")
            self._like_button.configure(text="♡")

    def _start_player_poll(self) -> None:
        """Poll current track every 5 seconds to keep the bar in sync."""
        self._refresh_player_bar()
        try:
            self._poll_timer = self.after(5000, self._start_player_poll)
        except Exception:
            pass  # Window destroyed

    def _handle_play(self) -> None:
        """Triggered by the Play button or Enter key."""
        if self._is_playing:
            return
        request = self._request_entry.get().strip()
        if not request:
            self._log("Enter a request first.")
            return
        self._spotify.last_request = request
        self._set_busy(True)
        threading.Thread(target=self._play_worker, args=(request, False), daemon=True).start()

    def _handle_continue(self) -> None:
        """Extend the current session with fresh tracks in the same vibe."""
        if self._is_playing:
            return
        if not self._spotify.last_request:
            self._log("Nothing playing yet — use Play first.")
            return
        self._set_busy(True)
        threading.Thread(target=self._play_worker, args=(self._spotify.last_request, True), daemon=True).start()

    def _play_worker(self, request: str, is_continue: bool = False) -> None:
        """
        Runs in a background thread.
        Calls the AI then Spotify, then schedules UI updates on the main thread.
        """
        if is_continue:
            self._log(f'Continuing: "{request}"')
        else:
            self._log(f'Request: "{request}"')

        # Step 1 - AI generates search queries
        try:
            config = load_config()
            api_key = config.get("gemini_api_key", "")
            if is_continue:
                from brain import get_continue_params
                directives = get_continue_params(
                    request,
                    self._spotify.last_queries,
                    api_key,
                )
            else:
                directives = get_vibe_params(request, api_key)
            self._log(f"AI: {directives.reasoning}")
            self._log(f"Running {len(directives.queries)} searches, targeting {directives.queue_size} tracks...")
        except Exception as e:
            self.after(0, lambda: self._finish_worker(f"AI error: {e}", success=False))
            return

        # Step 2 - Search Spotify and start playback
        try:
            result = self._spotify.search_and_play(directives)
        except Exception as e:
            self.after(0, lambda: self._finish_worker(f"Spotify error: {e}", success=False))
            return

        if result.success:
            extra = f" — {result.track_count} tracks from {result.queries_run} searches" if result.track_count > 1 else ""
            self.after(
                0,
                lambda: self._finish_worker(
                    f"Now playing: {result.first_track}{extra}", success=True
                ),
            )
        else:
            self.after(0, lambda: self._finish_worker(result.message, success=False))

    def _finish_worker(self, message: str, success: bool) -> None:
        """Called on the main thread once the background worker completes."""
        self._log(message, success=success)
        self._set_busy(False)
        if success:
            # Refresh player bar after a short delay to let Spotify catch up
            self.after(1200, self._refresh_player_bar)

    def _set_busy(self, busy: bool) -> None:
        """Disable or re-enable input controls during a request."""
        self._is_playing = busy
        state = "disabled" if busy else "normal"
        self._play_button.configure(
            state=state, text="Working..." if busy else "Play"
        )
        self._continue_button.configure(state=state)
        self._request_entry.configure(state=state)

    # ------------------------------------------------------------------
    # Settings dialog
    # ------------------------------------------------------------------

    def _open_settings_dialog(self) -> None:
        """Modal window for updating the Gemini API key."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("420x260")
        dialog.resizable(False, False)
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=32, pady=32)

        ctk.CTkLabel(frame, text="Settings", font=("Helvetica", 18, "bold")).pack(
            anchor="w", pady=(0, 16)
        )
        ctk.CTkLabel(frame, text="Gemini API Key", font=FONT_BODY).pack(anchor="w")

        key_entry = ctk.CTkEntry(frame, height=40, show="*", font=FONT_BODY)
        key_entry.insert(0, self._config.get("gemini_api_key", ""))
        key_entry.pack(fill="x", pady=(4, 16))

        error_label = ctk.CTkLabel(frame, text="", text_color=COLOR_ERROR, font=FONT_SMALL)
        error_label.pack()

        def save() -> None:
            new_key = key_entry.get().strip()
            if not new_key:
                error_label.configure(text="Key cannot be empty.")
                return
            self._config["gemini_api_key"] = new_key
            save_config(self._config)
            self._log("Gemini API key updated.")
            dialog.destroy()

        ctk.CTkButton(
            frame, text="Save", height=40, font=FONT_BODY, command=save
        ).pack(fill="x", pady=(4, 8))
        ctk.CTkButton(
            frame,
            text="Cancel",
            height=40,
            font=FONT_BODY,
            fg_color="transparent",
            border_width=1,
            command=dialog.destroy,
        ).pack(fill="x")

    # ------------------------------------------------------------------
    # Log helper
    # ------------------------------------------------------------------

    def _log(self, message: str, success: bool = None) -> None:
        """
        Append a timestamped message to the activity log.
        Thread-safe: schedules the write on the main thread via self.after().
        """
        def _append() -> None:
            if not hasattr(self, "_log_box"):
                return
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._log_box.configure(state="normal")
            self._log_box.insert("end", f"[{timestamp}] {message}\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")

        try:
            self.after(0, _append)
        except RuntimeError:
            pass  # Window was destroyed before the callback ran - safe to ignore