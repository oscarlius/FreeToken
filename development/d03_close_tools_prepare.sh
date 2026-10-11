set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/close_tools_c30ae0d
test ! -e "$target"
test ! -e /data2/FreeToken/runs/dev_D03/d03_t16_close.py
mkdir -p "$target/development/tests" "$target/scripts"
cp /data2/FreeToken/scripts/round_json_append.py "$target/scripts/"
cp /data2/FreeToken/scripts/round_close.py "$target/scripts/"
cp /data2/FreeToken/scripts/round_close.sh "$target/scripts/"
cp /data2/FreeToken/runs/dev_D03/d03_t16_prepare.py "$target/development/"
