set -euo pipefail
cd /data2/FreeToken/wt/e1r003st
log=/data2/FreeToken/runs/dev_D03/cpu_regression.log
test ! -e "$log"
set +e
CUDA_VISIBLE_DEVICES='' PYTHONPATH=python FT_D0_TIMELINE_SCRIPT=/data2/FreeToken/scripts/d0_timeline_summary.py /data2/FreeToken/venv/bin/python -m pytest tests/scheduler tests/kvcache tests/moe/test_d0_fields.py tests/moe/test_d0_decode.py tests/moe/test_d0_timeline_summary.py tests/server/test_dev_logits.py tests/scripts/test_logits_probe.py scripts/tests/test_state_envelope.py -q > "$log" 2>&1
code=$?
set -e
tail -n 38 "$log"
echo "pytest_exit=$code"
test "$code" -eq 1
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib,re
text=pathlib.Path('/data2/FreeToken/runs/dev_D03/cpu_regression.log').read_text()
failures=re.findall(r'^FAILED (\S+)',text,re.M)
expected={'tests/scheduler/test_abort_inflight_prefill.py::test_prefix_commit_sentinel_guard',
          'tests/scheduler/test_abort_inflight_prefill.py::test_post_terminal_overlap_step_is_dropped'}
assert set(failures)==expected and len(failures)==2,failures
print('D03 G1 REGRESSION PASS: exactly the two recorded baseline failures, no new failures')
PY
