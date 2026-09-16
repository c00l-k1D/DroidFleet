#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
OUTPUT="${OUTPUT:-dist/FarmAgent-linux}"

if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
  echo "Python pip is required in the Linux/WSL distribution."
  echo "Install it with: sudo apt update && sudo apt install -y python3-pip python3-venv"
  exit 2
fi

"$PYTHON" -m pip install pyinstaller psutil pyngrok Pillow PyAutoGUI

ARGS=(
  --noconfirm
  --clean
  --onefile
  --name FarmAgent-linux
)

ADB="${DROIDFLEET_ADB:-}"
if [[ -z "$ADB" ]]; then
  ADB="$(command -v adb || true)"
fi
if [[ -n "$ADB" && -f "$ADB" ]]; then
  mkdir -p "$ROOT/platform-tools"
  cp "$ADB" "$ROOT/platform-tools/adb"
  ARGS+=(--add-binary "$ROOT/platform-tools/adb:platform-tools")
fi

"$PYTHON" -m PyInstaller "${ARGS[@]}" agent/agent.py
if [[ "$OUTPUT" != "dist/FarmAgent-linux" ]]; then
  mv -f dist/FarmAgent-linux "$OUTPUT"
fi
chmod +x "$OUTPUT"
printf 'Built %s\n' "$OUTPUT"
