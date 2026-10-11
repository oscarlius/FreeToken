set -euo pipefail
cd /data2/FreeToken/wt/e1r003st
test "$(git rev-parse HEAD)" = c30ae0d7003c3bbbf56867ce74da797332fa7ed5
log=/data2/FreeToken/runs/dev_D03/cpu_regression_c30ae0d.log
test ! -e "$log"
set +e
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 PYTHONPATH=python FT_D0_TIMELINE_SCRIPT=/data2/FreeToken/scripts/d0_timeline_summary.py /data2/FreeToken/venv/bin/python -m pytest tests/scheduler tests/kvcache tests/moe/test_d0_fields.py tests/moe/test_d0_decode.py tests/moe/test_d0_timeline_summary.py tests/server/test_dev_logits.py tests/scripts/test_logits_probe.py scripts/tests/test_state_envelope.py -q > "$log" 2>&1
code=$?
set -e
tail -n 38 "$log"
test "$code" -le 1
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,re
path=pathlib.Path('/data2/FreeToken/runs/dev_D03/cpu_regression_c30ae0d.log')
text=path.read_text()
failures=re.findall(r'^FAILED (\S+)',text,re.M)
baseline={'tests/scheduler/test_abort_inflight_prefill.py::test_prefix_commit_sentinel_guard',
          'tests/scheduler/test_abort_inflight_prefill.py::test_post_terminal_overlap_step_is_dropped'}
assert set(failures)<=baseline and len(failures)<=2,failures
assert re.search(r'\d+ passed',text)
print('D03 G1 current-source regression has no failures beyond the two recorded baseline failures')
print('D03_CURRENT_REGRESSION_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
PY
