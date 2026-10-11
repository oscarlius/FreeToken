#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
exec "${FT_ROUND_PYTHON:-/data2/FreeToken/venv/bin/python}" "$script_dir/round_close.py" "$@"
