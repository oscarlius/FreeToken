set -u
cd /data2/FreeToken/wt/e1r008
/data2/FreeToken/venv/bin/python - <<'PY'
import subprocess
target = subprocess.check_output(['git', 'rev-parse', 'FETCH_HEAD']).strip()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip() == target
paths = subprocess.check_output(['git', 'diff', '--name-only', 'E2-pre', 'HEAD']).decode().splitlines()
subprocess.run(['git', 'add', '--', *paths], check=True)
subprocess.run(['git', 'diff', '--cached', '--exit-code'], check=True)
assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no']).strip()
print('Verified local/server commit and source equality:', target.decode())
PY
check=$?
if test "$check" != 0; then exit "$check"; fi
PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest tests/scheduler tests/kvcache -q > /data2/FreeToken/runs/dev_D01/pytest_final.log 2>&1
result=$?
tail -7 /data2/FreeToken/runs/dev_D01/pytest_final.log
exit "$result"
