#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
if [[ ! -f .env ]]; then
  python setup.py
fi
if [[ ! -d .venv ]]; then
  python -m venv .venv
fi
.venv/bin/python -m pip install -q -r requirements.txt
exec .venv/bin/python bot.py
