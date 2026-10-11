#!/bin/bash
# 展台静态服务（8100）。与 8099 监控完全独立，不共用进程与文件。
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-8100}"
cd "$DIR" || exit 1
exec /data2/FreeToken/venv/bin/python -m http.server "$PORT" --bind 0.0.0.0