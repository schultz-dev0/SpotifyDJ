#!/usr/bin/env bash
# Quick launcher for Spotify AI DJ
# Accepts optional arguments for CLI mode:
#   bash launch.sh                   -> open GUI
#   bash launch.sh "dark techno"     -> play immediately
cd "/home/schultz/projects/SpotifyDJ2.0"
exec python3 main.py "$@"
