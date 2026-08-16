#!/bin/bash
# Build Instagram Splitter.app with bundled ffmpeg/ffprobe.
set -euo pipefail
cd "$(dirname "$0")"

# Prefer the python that is running this script's ecosystem; fall back to python3.
if [[ -n "${PYTHON:-}" ]]; then
  :
elif /usr/local/bin/python3.12 -c "import tkinter" >/dev/null 2>&1; then
  PYTHON=/usr/local/bin/python3.12
else
  PYTHON=python3
fi

echo "Using $PYTHON ($($PYTHON --version))"

"$PYTHON" -m pip install --user -q "pyinstaller>=6.0"

mkdir -p bin
if [[ ! -x bin/ffmpeg || ! -x bin/ffprobe ]]; then
  echo "Downloading static ffmpeg/ffprobe (x86_64)..."
  curl -fsSL "https://evermeet.cx/ffmpeg/getrelease/zip" -o /tmp/ffmpeg-ig.zip
  curl -fsSL "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip" -o /tmp/ffprobe-ig.zip
  unzip -o /tmp/ffmpeg-ig.zip -d bin
  unzip -o /tmp/ffprobe-ig.zip -d bin
  chmod +x bin/ffmpeg bin/ffprobe
fi
file bin/ffmpeg bin/ffprobe
bin/ffmpeg -version | head -1

APP_NAME="Instagram Splitter"
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier com.local.instagramsplitter \
  --add-binary "bin/ffmpeg:." \
  --add-binary "bin/ffprobe:." \
  --hidden-import tkinter \
  --hidden-import tkinter.filedialog \
  --hidden-import tkinter.messagebox \
  --hidden-import tkinter.ttk \
  split_instagram.py

APP="dist/${APP_NAME}.app"
codesign --force --deep --sign - "$APP"
echo "Built $PWD/$APP"
ls -lh "$APP"
