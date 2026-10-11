set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/continuation_cpu_71f93be
cd "$target/repo"
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib, subprocess
base = pathlib.Path('/data2/FreeToken/runs/dev_D03/continuation_cpu_71f93be')
expected = {
 'prefill_after.py': '71f93be121edd17235654cfb2cc731c81ac8600396283fee892eb6345d6f12ce',
 'repo/tests/scheduler/test_scheduler_chunked_prefill.py': '5190f4936a4208f80dfe163fa91c239195a6429aa92e7f492aaf09666aca1c91',
}
for name, digest in expected.items():
    assert hashlib.sha256((base / name).read_bytes()).hexdigest() == digest, name
original = subprocess.check_output(['git', 'show', 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5:python/freetoken/scheduler/prefill.py'])
assert pathlib.Path('python/freetoken/scheduler/prefill.py').read_bytes() == original
assert not (base / 'red.log').exists() and not (base / 'green.log').exists()
PY
set +e
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short tests/scheduler/test_scheduler_chunked_prefill.py -k continuation_diagnostic > "$target/red.log" 2>&1
red_code=$?
set -e
tail -n 35 "$target/red.log"
test "$red_code" = 1
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib, re
base = pathlib.Path('/data2/FreeToken/runs/dev_D03/continuation_cpu_71f93be')
text = (base / 'red.log').read_text()
failed = re.findall(r'^FAILED (\S+)', text, re.M)
assert len(failed) == 2 and all('continuation_diagnostic' in item for item in failed), failed
assert '_dev_restore_proof' in text and 'ERROR collecting' not in text
path = base / 'repo/python/freetoken/scheduler/prefill.py'
path.write_bytes((base / 'prefill_after.py').read_bytes())
print('REGRESSION_REPRODUCED_ON_UNMODIFIED_C30; applying reviewed six-line diagnostic delta to isolated CPU surface')
PY
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short tests/scheduler/test_scheduler_chunked_prefill.py tests/scheduler/test_prefill_anchor_cut_switch.py tests/kvcache/test_state_dump_at.py tests/server/test_dev_logits.py > "$target/green.log" 2>&1
tail -n 15 "$target/green.log"
sha256sum "$target/red.log" "$target/green.log"
