#!/usr/bin/env bash
set -euo pipefail

# 1) FoA making python env
echo "Creating python enviroment"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

echo "Installing libraries.."
# 2) Minimal deps (μόνο για benign subset - θα το μεγαλώσουμε καθώς βρίσκουμε ανάγκες)
python -m pip install blessed requests psutil pillow

# --- 4. Execution Logic ---
# Path is relative to the current directory (which is assumed to be 'DedSec').
SCRIPT_PATH="./Scripts/Settings.py"

echo "4. Attempting to run $SCRIPT_PATH..."
# First attempt to run the script
if [ -f "$SCRIPT_PATH" ]; then
    python "$SCRIPT_PATH"
    EXEC_STATUS=$?
else
    echo "ERROR: Script file not found at $SCRIPT_PATH. Cannot execute."
    EXEC_STATUS=1 # Set status to error if file is missing
fi
