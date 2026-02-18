@echo off
setlocal EnableDelayedExpansion
title Spotify AI DJ - Installer

echo.
echo  ============================================
echo   Spotify AI DJ - Installer
echo  ============================================
echo.

:: Claude made this, I do not use windows!

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
    echo  IMPORTANT: On the installer page, make sure to tick
    echo  "Add Python to PATH" before clicking Install Now.
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
    echo  Try running this file again. If it keeps failing,
    echo  open a command prompt in this folder and run:
    echo    python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo  Dependencies installed successfully.

:: ----------------------------------------------------------------
:: Step 3 - Create a desktop shortcut
:: ----------------------------------------------------------------
echo.
echo  Creating desktop shortcut...

set SCRIPT_DIR=%~dp0
set SHORTCUT=%USERPROFILE%\Desktop\Spotify AI DJ.lnk
set TARGET=!PYTHON_CMD!
set ARGS="%SCRIPT_DIR%main.py"

:: Use PowerShell to create the shortcut (works on all modern Windows versions)
powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$sc = $ws.CreateShortcut('%SHORTCUT%');" ^
    "$sc.TargetPath = '$(where !PYTHON_CMD!)';" ^
    "$sc.Arguments = '%ARGS%';" ^
    "$sc.WorkingDirectory = '%SCRIPT_DIR%';" ^
    "$sc.WindowStyle = 1;" ^
    "$sc.Save()"

if exist "%SHORTCUT%" (
    echo  Shortcut created on your Desktop.
) else (
    echo  Could not create shortcut - you can launch the app manually
    echo  by double-clicking launch.bat in this folder.
)

:: ----------------------------------------------------------------
:: Step 4 - Create a simple launch script as backup
:: ----------------------------------------------------------------
echo !PYTHON_CMD! "%SCRIPT_DIR%main.py" > "%SCRIPT_DIR%launch.bat"

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
echo  and ask you to log in to Spotify. That only happens once.
echo.
pause