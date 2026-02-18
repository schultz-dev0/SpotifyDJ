#!/usr/bin/env bash
# Quick launcher for Spotify AI DJ
# GUI mode:  bash launch.sh
# CLI mode:  bash launch.sh "dark techno"
cd "/home/schultz/projects/SpotifyDJ2.0"
exec python3 main.py "$@"
