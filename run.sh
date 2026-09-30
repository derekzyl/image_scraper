#!/usr/bin/env bash
# First run downloads uv and Python if they are missing, then opens the app.
set -euo pipefail
cd "$(dirname "$0")"

UV_DIR="${UV_INSTALL_DIR:-$HOME/.local/bin}"
export PATH="$UV_DIR:$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Downloading it now."
  echo "uv will also download Python, so a separate Python install is not required."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$UV_DIR" sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$UV_DIR" sh
  else
    echo "This computer needs curl or wget to download uv."
    echo "On Ubuntu or Debian: sudo apt install curl"
    exit 1
  fi
  export PATH="$UV_DIR:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was downloaded but could not be found in $UV_DIR."
  echo "Close this terminal, open a new one, and run ./run.sh again."
  exit 1
fi

PY_VERSION="3.13"
if [ -f .python-version ]; then
  PY_VERSION="$(tr -d '[:space:]' < .python-version)"
fi

echo "Checking Python ${PY_VERSION} and the app libraries..."
uv python install "$PY_VERSION"
uv sync
exec uv run python main.py
