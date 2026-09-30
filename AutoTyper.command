#!/bin/bash
# Double-click to run the auto typer.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed."
  echo "Install it from https://www.python.org/downloads/ and run this again."
  read -n 1 -s -r -p "Press any key to close..." || true
  echo
  exit 1
fi

python3 auto_typer_console.py

echo
read -n 1 -s -r -p "The program has ended. Press any key to close this window..." || true
echo
