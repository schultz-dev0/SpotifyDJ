@echo off
setlocal EnableDelayedExpansion
title Spotify AI DJ - Installer

echo.
echo  ============================================
echo   Spotify AI DJ - Installer
echo  ============================================
echo.

:: ----------------------------------------------------------------
:: Step 1 - Check if Python 3.10+ is installed
:: ----------------------------------------------------------------
echo  Checking for Python...

set PYTHON_CMD=
where python >nul 2>&1 && (
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
    for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
        if %%a GEQ 3 if %%b GEQ 10 set PYTHON_CMD=python
    )
)

if "!PYTHON_CMD!"=="" (
    where python3 >nul 2>&1 && (
        for /f "tokens=2 delims= " %%v in ('python3 --version 2^>^&1') do set PYVER=%%v
        for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
            if %%a GEQ 3 if %%b GEQ 10 set PYTHON_CMD=python3
        )
    )
)

if "!PYTHON_CMD!"=="" (
    echo  Python 3.10 or newer was not found.
    echo  Opening the Python download page in your browser...
    echo.
    echo  IMPORTANT: On the installer, tick "Add Python to PATH"
    echo  before clicking Install Now.
    echo.
    start https://www.python.org/downloads/
    echo  After Python is installed, close this window and
    echo  double-click install.bat again.
    echo.
    pause
    exit /b 1
)

echo  Found Python: !PYVER!

:: ----------------------------------------------------------------
:: Step 2 - Install Python dependencies
:: ----------------------------------------------------------------
echo.
echo  Installing dependencies (this may take a minute)...
echo.

!PYTHON_CMD! -m pip install --upgrade pip --quiet
!PYTHON_CMD! -m pip install -r requirements.txt --quiet

if errorlevel 1 (
    echo.
    echo  Something went wrong installing dependencies.
    echo  Try running this file again, or open a command prompt
    echo  in this folder and run:
    echo    python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo  Dependencies installed successfully.

:: ----------------------------------------------------------------
:: Step 3 - Credential wizard
:: Skipped if .env already contains Spotify credentials.
:: ----------------------------------------------------------------

:: Check if .env already has both Spotify keys
set HAS_KEYS=0
if exist "%~dp0.env" (
    findstr /C:"SPOTIPY_CLIENT_ID=" "%~dp0.env" >nul 2>&1 && (
        findstr /C:"SPOTIPY_CLIENT_SECRET=" "%~dp0.env" >nul 2>&1 && set HAS_KEYS=1
    )
)

if "!HAS_KEYS!"=="1" (
    echo  Credentials already configured (.env found^). Skipping setup.
    echo  To update your credentials, delete .env and re-run this installer.
    goto :SKIP_WIZARD
)

echo.
echo  ============================================
echo   API Key Setup
echo  ============================================
echo.
echo  This app needs two sets of credentials:
echo.
echo  1. Spotify (to control playback)
echo     https://developer.spotify.com/dashboard
echo     - Click 'Create app'
echo     - Set Redirect URI to: http://127.0.0.1:8888/callback
echo     - Copy your Client ID and Client Secret
echo.
echo  2. Google Gemini (for AI music requests - free tier is fine)
echo     https://aistudio.google.com/app/apikey
echo.

:: Spotify Client ID - loop until non-empty
:ASK_CLIENT_ID
set S_ID=
set /p S_ID="  Spotify Client ID:     "
if "!S_ID!"=="" (
    echo  Please enter your Spotify Client ID.
    goto :ASK_CLIENT_ID
)

:: Spotify Client Secret - loop until non-empty
:ASK_CLIENT_SECRET
set S_SEC=
set /p S_SEC="  Spotify Client Secret: "
if "!S_SEC!"=="" (
    echo  Please enter your Spotify Client Secret.
    goto :ASK_CLIENT_SECRET
)

:: Gemini key - optional
echo.
echo  Gemini API Key is optional now - you can also enter it
echo  when you first open the app. Press Enter to skip.
set G_KEY=
set /p G_KEY="  Gemini API Key:        "

:: Write .env file
(
    echo SPOTIPY_CLIENT_ID=!S_ID!
    echo SPOTIPY_CLIENT_SECRET=!S_SEC!
    echo SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
    echo GEMINI_API_KEY=!G_KEY!
) > "%~dp0.env"

echo.
echo  Credentials saved to .env

if "!G_KEY!"=="" (
    echo  No Gemini key entered. You will be prompted for it on first launch.
)

:SKIP_WIZARD

:: ----------------------------------------------------------------
:: Step 4 - Create a desktop shortcut
:: ----------------------------------------------------------------
echo.
echo  Creating desktop shortcut...

set SCRIPT_DIR=%~dp0
set SHORTCUT=%USERPROFILE%\Desktop\Spotify AI DJ.lnk
set ARGS="%SCRIPT_DIR%main.py"

:: Find the full path of python
for /f "delims=" %%i in ('where !PYTHON_CMD! 2^>nul') do set PYTHON_FULL=%%i

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$sc = $ws.CreateShortcut('%SHORTCUT%');" ^
    "$sc.TargetPath = '%PYTHON_FULL%';" ^
    "$sc.Arguments = '%ARGS%';" ^
    "$sc.WorkingDirectory = '%SCRIPT_DIR%';" ^
    "$sc.WindowStyle = 1;" ^
    "$sc.Save()"

if exist "%SHORTCUT%" (
    echo  Shortcut created on your Desktop.
) else (
    echo  Could not create shortcut - use launch.bat to start the app.
)

:: ----------------------------------------------------------------
:: Step 5 - Create launch.bat as a backup launcher
:: ----------------------------------------------------------------
echo !PYTHON_CMD! "%SCRIPT_DIR%main.py" > "%SCRIPT_DIR%launch.bat"
echo  launch.bat created in the app folder.

:: ----------------------------------------------------------------
:: Done
:: ----------------------------------------------------------------
echo.
echo  ============================================
echo   All done! Setup is complete.
echo  ============================================
echo.
echo  You can now:
echo    - Double-click "Spotify AI DJ" on your Desktop, or
echo    - Double-click launch.bat in this folder.
echo.
echo  The first time you press Play, your browser will open
echo  to log in to Spotify. That only happens once.
echo.
pause