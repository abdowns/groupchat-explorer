#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  task_python=""
  for candidate in python3.12 python3.11 python3.13; do
    if command -v "$candidate" >/dev/null 2>&1; then task_python="$candidate"; break; fi
  done
  if [ -z "$task_python" ]; then echo "Install Python 3.12 (brew install python@3.12)."; exit 1; fi
  "$task_python" -m venv .venv
  .venv/bin/pip install -e '.[dev]'
fi
if [ ! -d node_modules ]; then npm ci; fi
if ! command -v cargo >/dev/null 2>&1; then echo "Install Rust (brew install rust)."; exit 1; fi
cargo build --release --locked --manifest-path importer/Cargo.toml
npm run build
echo "Open http://127.0.0.1:8765 — your archive stays on this Mac."
exec .venv/bin/python -m gcapp.cli serve
