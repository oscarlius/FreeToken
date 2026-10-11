set -euo pipefail
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64:${LD_LIBRARY_PATH:-}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1
FT=/data2/FreeToken/venv/bin/ft
PY=/data2/FreeToken/venv/bin/python
SCR=/data2/FreeToken/scripts
SOURCE=/data2/FreeToken/runs/plan_batches/batch22_E2-pre-gate-D01_resume_fixed.sh
test "$(command -v ft)" = "$FT"
test "$(readlink -f "$(command -v ft)")" = "$FT"
"$FT" --help > /dev/null
numactl --cpunodebind=0,1 --interleave=all "$FT" --help > /dev/null
PYTHONPATH=/data2/FreeToken/wt/e1r008/python "$PY" -c 'import freetoken.kernel._pinned_tensor,freetoken.kernel._cpu_moe'
sha256sum "$SCR/cold_eq.py" "$SCR/ft_probe_ckpt_tax.py" "$SCR/serve_args_diff.py"
grep -F 'set -euo pipefail' "$SOURCE" > /dev/null
grep -F 'COLD_ID=E2-pre-gate-D01-det' "$SOURCE" > /dev/null
grep -F "re.fullmatch(r'\\.pid=\\d+'" "$SOURCE" > /dev/null
grep -F 'strict_h2d' "$SOURCE" > /dev/null
test ! -e /data2/_shared/gpu.lock
test -z "$(ss -ltn | grep ':8095 ' || true)"
test "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)" -lt 1000
echo PREFLIGHT-OK
