"""
app.py
------
Backend router. Detects the display environment at runtime and launches
the appropriate GUI backend.

Routing logic:
  Linux + WAYLAND_DISPLAY set  ->  GTK4 backend  (app_gtk.py)
  Everything else              ->  customtkinter backend  (app_ctk.py)

All business logic (brain.py, spotify_client.py, config.py) is shared
between both backends and is never imported here.
"""

import os
import sys


def _is_wayland() -> bool:
    """Return True when running inside a Wayland session on Linux."""
    return sys.platform.startswith("linux") and bool(os.environ.get("WAYLAND_DISPLAY"))


def run() -> None:
    """
    Select and launch the correct GUI backend.
    Prints a helpful message and exits if a required library is missing.
    """
    if _is_wayland():
        # Verify PyGObject is installed before attempting to load the GTK backend.
        try:
            import gi  # noqa: F401
        except ImportError:
            print(
                "[error] GTK4 backend requires PyGObject.\n"
                "Run the installer again, or install manually:\n"
                "  Debian/Ubuntu:  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0\n"
                "  Arch:           sudo pacman -S python-gobject gtk4\n"
                "  Fedora:         sudo dnf install python3-gobject gtk4\n"
            )
            sys.exit(1)

        from app_gtk import run as gtk_run
        gtk_run()
    else:
        from app_ctk import SpotifyAIDJApp
        SpotifyAIDJApp().mainloop()