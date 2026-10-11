set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/phase2_close_24e8656
test ! -e "$target"
test ! -e /data2/FreeToken/runs/dev_D03/d03_phase2_prepare.py
mkdir -p "$target/development/tests" "$target/scripts"
cp /data2/FreeToken/scripts/round_json_append.py "$target/scripts/"
cp /data2/FreeToken/scripts/round_close.py "$target/scripts/"
cp /data2/FreeToken/scripts/round_close.sh "$target/scripts/"
