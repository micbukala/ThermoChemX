#!/bin/bash

clear

# ==========================================
# APP CONFIGURATION
APP_NAME="ThermoChemX"
SHORTCUT_NAME="ChemX"
RUN_FILE="Run_ChemX.command"
ICON_FILE="src/thermochemx/assets/gui/chemx_icon.icns"
# ==========================================

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$HOME/Desktop"

# ---------------------------------------------------------------
# CUSTOM ICON
# Uses AppleScriptObjC via osascript — part of stock macOS, no
# PyObjC / Xcode CLT required (unlike '/usr/bin/python3 -c "import
# AppKit"', which fails silently on machines without PyObjC).
# ---------------------------------------------------------------
set_icon() {
    # $1 = target file to receive the icon
    osascript >/dev/null 2>&1 <<OSA
use framework "AppKit"
set img to current application's NSImage's alloc()'s initWithContentsOfFile:"$APP_DIR/$ICON_FILE"
if img is not missing value then
    current application's NSWorkspace's sharedWorkspace()'s setIcon:img forFile:"$1" options:0
end if
OSA
}

if [ -f "$APP_DIR/$ICON_FILE" ]; then
    set_icon "$APP_DIR/$RUN_FILE"
else
    echo "[!] Icon file not found: $APP_DIR/$ICON_FILE (shortcut will use default icon)"
fi

# CREATE DESKTOP SHORTCUT (if it doesn't exist)
if [ ! -f "$DESKTOP_DIR/$SHORTCUT_NAME" ]; then
    echo "[*] Creating Desktop Shortcut..."
    osascript -e "tell application \"Finder\"" \
              -e "set myAlias to make alias file to POSIX file \"$APP_DIR/$RUN_FILE\" at (path to desktop folder)" \
              -e "set name of myAlias to \"$SHORTCUT_NAME\"" \
              -e "end tell" > /dev/null
    echo "[+] Shortcut \"$SHORTCUT_NAME\" created on Desktop!"
    echo ""
fi

# Stamp the icon directly onto the alias every run (cheap, and it
# repairs shortcuts created by earlier versions before the icon fix).
if [ -f "$DESKTOP_DIR/$SHORTCUT_NAME" ] && [ -f "$APP_DIR/$ICON_FILE" ]; then
    set_icon "$DESKTOP_DIR/$SHORTCUT_NAME"
fi

echo "==========================================================="
echo "      Starting $APP_NAME..."
echo "==========================================================="
echo ""

cd "$APP_DIR"

# --- Fast path: skip Python detection if venv already exists ---
if [ -x "venv/bin/python3" ]; then
    echo "[1/3] Virtual environment found."
    source venv/bin/activate
    echo "[3/3] Checking dependencies..."
    python3 -m pip install -q -r requirements.txt
    if [ $? -ne 0 ]; then
        echo ""
        echo "[WARNING] Some packages failed to install."
        echo "          Rerun without -q to see details:"
        echo "            python3 -m pip install -r requirements.txt"
        echo ""
    fi
    echo ""
    echo "==========================================================="
    echo "App is running... (Do not close this window)"
    echo "==========================================================="
    echo ""
    python3 app.py
    echo ""
    echo "==========================================================="
    read -p "Press [Enter] key to exit..."
    exit 0
fi

# ---------------------------------------------------------------
# PYTHON DETECTION (needed only to create the venv)
# ---------------------------------------------------------------

find_python() {
    local candidates=(
        "python3"
        "/opt/homebrew/bin/python3"
        "/usr/local/bin/python3"
        "$HOME/miniconda3/bin/python3"
        "$HOME/anaconda3/bin/python3"
        "$HOME/miniforge3/bin/python3"
        "/opt/miniconda3/bin/python3"
        "/usr/bin/python3"
    )
    for cmd in "${candidates[@]}"; do
        # Resolve 'python3' in PATH first
        if [[ "$cmd" == "python3" ]]; then
            cmd="$(command -v python3 2>/dev/null)" || continue
        fi
        [ -x "$cmd" ] || continue
        # Validate: must be >= 3.10
        "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null && {
            echo "$cmd"
            return 0
        }
    done
    return 1
}

PYTHON_CMD="$(find_python)"

if [ -z "$PYTHON_CMD" ]; then
    echo ""
    echo "[ERROR] Python 3.10 or newer was not found on your system."
    echo ""
    echo "Please install Python from one of these sources:"
    echo "  - https://www.python.org/downloads/"
    echo "  - brew install python   (Homebrew)"
    echo "  - https://docs.conda.io/en/latest/miniconda.html"
    echo ""
    read -r -p "Press Enter to close..."
    exit 1
fi

echo "[+] Python found: $PYTHON_CMD"
echo ""

# ---------------------------------------------------------------

if [ ! -d "venv" ]; then
    echo "[1/3] Creating virtual environment... This might take a minute."
    "$PYTHON_CMD" -m venv venv
    if [ $? -ne 0 ]; then
        echo ""
        echo "[ERROR] Failed to create virtual environment."
        echo ""
        read -r -p "Press Enter to close..."
        exit 1
    fi
else
    echo "[1/3] Virtual environment found."
fi

echo "[2/3] Activating virtual environment..."
source venv/bin/activate

echo "[3/3] Checking dependencies..."
python3 -m pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo ""
    echo "[WARNING] Some packages failed to install."
    echo "          Rerun without -q to see details:"
    echo "            python3 -m pip install -r requirements.txt"
    echo ""
fi

# Fix SSL certificates (python.org builds on macOS ship without system certs)
CERT_SCRIPT="/Applications/Python $(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')/Install Certificates.command"
if [ -f "$CERT_SCRIPT" ]; then
    echo "[+] Installing SSL certificates (python.org)..."
    bash "$CERT_SCRIPT" > /dev/null 2>&1
fi

echo ""
echo "==========================================================="
echo "App is running... (Do not close this window)"
echo "==========================================================="
echo ""

python3 app.py

echo ""
echo "==========================================================="
read -p "Press [Enter] key to exit..."
