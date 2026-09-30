#!/usr/bin/env bash
# Build a clickable Linux or Mac app. Windows uses build_executable.bat.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "Run ./run.sh once so uv and Python are installed, then run this again."
  exit 1
fi

uv run --with pyinstaller pyinstaller --noconfirm --clean receipt_extractor.spec

APP_DIR="$(pwd)/dist/ReceiptExtractor"
BIN="$APP_DIR/ReceiptExtractor"
chmod +x "$BIN"

DESKTOP_FILE="$(pwd)/Receipt Extractor.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Receipt Extractor
Comment=Turn PalmPay receipts into a CSV
Exec=$BIN
Path=$APP_DIR
Terminal=false
Categories=Office;
StartupNotify=true
EOF
chmod +x "$DESKTOP_FILE"
cp "$DESKTOP_FILE" "$APP_DIR/Receipt Extractor.desktop"

if [ -d "$HOME/Desktop" ]; then
  cp "$DESKTOP_FILE" "$HOME/Desktop/Receipt Extractor.desktop"
  chmod +x "$HOME/Desktop/Receipt Extractor.desktop"
fi

echo
echo "Ready. Double-click: $DESKTOP_FILE"
echo "Or the app folder: $BIN"
