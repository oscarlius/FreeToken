set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/close_tools_c30ae0d
cd "$target"
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m pytest -q development/tests/test_d03_t16_close.py | tee regression.log
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python -m py_compile development/d03_t16_close.py
test ! -e /data2/FreeToken/runs/dev_D03/d03_t16_close.py
cp development/d03_t16_close.py /data2/FreeToken/runs/dev_D03/d03_t16_close.py
sha256sum development/d03_t16_close.py development/tests/test_d03_t16_close.py regression.log
