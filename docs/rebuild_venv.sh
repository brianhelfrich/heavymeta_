# heavymetal/docs/rebuild_venv.sh
#!/usr/bin/env bash
#
# Rebuild the virtual environment with a new Python version.
# Usage:
#   ./docs/rebuild_venv.sh python3.13
#
# Notes:
#   - Pass the desired python executable (default: `python3`).
#   - Requires a requirements.txt in project root.
#   - Always run from project root.

set -euo pipefail

# Pick python interpreter (default: python3)
PYTHON_BIN="${1:-python3}"

# Paths
VENV_DIR="venv"
REQ_FILE="requirements.txt"

# Step 1: Remove old venv if present
if [ -d "$VENV_DIR" ]; then
  echo "==> Removing old virtual environment at $VENV_DIR"
  rm -rf "$VENV_DIR"
fi

# Step 2: Create new venv
echo "==> Creating new virtual environment with $PYTHON_BIN"
$PYTHON_BIN -m venv "$VENV_DIR"

# Step 3: Activate and upgrade tooling
source "$VENV_DIR/bin/activate"
echo "==> Upgrading pip/setuptools/wheel"
pip install --upgrade pip setuptools wheel

# Step 4: Install dependencies
if [ -f "$REQ_FILE" ]; then
  echo "==> Installing requirements from $REQ_FILE"
  pip install -r "$REQ_FILE"
else
  echo "!! No $REQ_FILE found, skipping package installation."
fi

echo "==> Done! Virtual environment rebuilt at $VENV_DIR"
