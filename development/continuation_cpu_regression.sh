set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/continuation_cpu_71f93be
cd "$target/repo"
test ! -e "$target/regression.log"
set +e
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 PYTHONPATH=python FT_D0_TIMELINE_SCRIPT=/data2/FreeToken/scripts/d0_timeline_summary.py /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short tests/scheduler tests/kvcache tests/moe/test_d0_fields.py tests/moe/test_d0_decode.py tests/moe/test_d0_timeline_summary.py tests/server/test_dev_logits.py tests/scripts/test_logits_probe.py scripts/tests/test_state_envelope.py > "$target/regression.log" 2>&1
code=$?
set -e
tail -n 30 "$target/regression.log"
test "$code" -le 1
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib, re
root = pathlib.Path('/data2/FreeToken/runs/dev_D03/continuation_cpu_71f93be')
text = (root / 'regression.log').read_text()
failed = re.findall(r'^FAILED (\S+)', text, re.M)
baseline = {'tests/scheduler/test_abort_inflight_prefill.py::test_prefix_commit_sentinel_guard',
            'tests/scheduler/test_abort_inflight_prefill.py::test_post_terminal_overlap_step_is_dropped'}
assert set(failed) <= baseline and len(failed) <= 2, failed
assert re.search(r'\d+ passed', text)
assert hashlib.sha256((root / 'repo/python/freetoken/scheduler/prefill.py').read_bytes()).hexdigest() == '71f93be121edd17235654cfb2cc731c81ac8600396283fee892eb6345d6f12ce'
assert hashlib.sha256((root / 'repo/tests/scheduler/test_scheduler_chunked_prefill.py').read_bytes()).hexdigest() == '5190f4936a4208f80dfe163fa91c239195a6429aa92e7f492aaf09666aca1c91'
print('CONTINUATION_CPU_REGRESSION_NO_NEW_FAILURES', hashlib.sha256((root / 'regression.log').read_bytes()).hexdigest())
PY
