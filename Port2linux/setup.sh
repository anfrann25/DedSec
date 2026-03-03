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

echo
echo "OK: venv ready."
echo "Run: source .venv/bin/activate"
echo "Then: python linux_menu.py"