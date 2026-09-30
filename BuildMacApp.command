#!/bin/bash
# Builds AutoTyper.app and AutoTyper.dmg. (Double-click on a Mac; the first run takes about 5-10 minutes)
cd "$(dirname "$0")" || exit 1

fail() {
  echo
  echo "[FAILED] $1"
  read -n 1 -s -r -p "Press any key to close this window..." || true
  echo
  exit 1
}

[ "$(uname)" = "Darwin" ] || fail "This script can only run on a Mac."
command -v python3 >/dev/null 2>&1 || fail "Python 3 was not found. Install it from https://www.python.org/downloads/"

echo "1/5 Preparing the build environment"
python3 -m venv build_venv || fail "Could not create the virtual environment."
# shellcheck disable=SC1091
source build_venv/bin/activate
python -m pip install --disable-pip-version-check -q --upgrade pip
python -m pip install --disable-pip-version-check -q \
  pyautogui pyperclip pynput PySide6-Essentials pyinstaller || fail "Package installation failed. Check your internet connection."

echo "2/5 Creating the icon"
rm -rf AutoTyper.iconset
mkdir AutoTyper.iconset
for s in 16 32 64 128 256 512; do
  sips -z $s $s icon.png --out "AutoTyper.iconset/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z $d $d icon.png --out "AutoTyper.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns AutoTyper.iconset -o AutoTyper.icns || fail "Could not create the icon."
rm -rf AutoTyper.iconset

echo "3/5 Building the app"
rm -rf build dist
pyinstaller --noconfirm --clean --windowed \
  --name AutoTyper \
  --icon AutoTyper.icns \
  --osx-bundle-identifier com.autotyper.app \
  --hidden-import pynput.keyboard._darwin \
  --hidden-import pynput.mouse._darwin \
  auto_typer_gui.py || fail "Could not build the app. Check the error messages above."
[ -d dist/AutoTyper.app ] || fail "dist/AutoTyper.app was not created."

echo "4/5 Signing (ad-hoc signature, for use on this Mac)"
codesign --force --deep --sign - dist/AutoTyper.app || echo "Skipping signing."

echo "5/5 Creating the dmg"
rm -rf dmg_stage AutoTyper.dmg
mkdir dmg_stage
cp -R dist/AutoTyper.app dmg_stage/
ln -s /Applications dmg_stage/Applications
hdiutil create -volname "AutoTyper" -srcfolder dmg_stage -ov -format UDZO AutoTyper.dmg >/dev/null \
  || fail "Could not create the dmg."
rm -rf dmg_stage

echo
echo "Done."
echo "  App: $(pwd)/dist/AutoTyper.app"
echo "  dmg: $(pwd)/AutoTyper.dmg"
echo
echo "Open AutoTyper.dmg and drag AutoTyper into Applications to install it."
open -R AutoTyper.dmg
read -n 1 -s -r -p "Press any key to close this window..." || true
echo
