#!/bin/bash
# Runs the GUI directly without building the app. Double-click to use.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed."
  echo "Install it from https://www.python.org/downloads/ and run this again."
  read -n 1 -s -r -p "Press any key to close..." || true
  echo
  exit 1
fi

python3 auto_typer_gui.py
status=$?
if [ $status -ne 0 ]; then
  echo
  read -n 1 -s -r -p "An error occurred. Press any key to close this window..." || true
  echo
fi
