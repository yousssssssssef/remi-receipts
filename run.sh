#!/bin/sh
# Start the receipt scanner UI. Creates the Python environment on first run.
set -e
cd "$(dirname "$0")"

if curl -s -o /dev/null http://127.0.0.1:8765/; then
  echo "Already running at http://localhost:8765"
  open "http://localhost:8765"
  exit 0
fi

if [ ! -x .venv/bin/python ]; then
  PY=$(command -v python3.11 || command -v python3.12 || command -v python3.10 || true)
  if [ -z "$PY" ]; then
    echo "Needs Python 3.10-3.12 (e.g. brew install python@3.11)" >&2
    exit 1
  fi
  echo "Setting up Python environment (one time, a few minutes)..."
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

(sleep 4 && open "http://localhost:8765") >/dev/null 2>&1 &
exec .venv/bin/python app.py
