set -eu
cd /data2/FreeToken/wt/e1r008
test "$(git symbolic-ref --short HEAD)" = exp/e1r008-anchorcut
test "$(git rev-parse --short=7 HEAD)" = 3db7b50
test -z "$(git diff --cached --name-only)"
git fetch /data2/FreeToken/runs/dev_D01/d01-delivery.bundle exp/e1r008-anchorcut
PYTHONPATH=python /data2/FreeToken/venv/bin/python - <<'PY'
import pathlib
import subprocess

def git(*args):
    return subprocess.check_output(['git', *args])

target = git('rev-parse', 'FETCH_HEAD').decode().strip()
base = git('rev-parse', 'HEAD').decode().strip()
paths = git('diff', '--name-only', base, target).decode().splitlines()
for path in paths:
    expected = git('show', f'{target}:{path}')
    actual = pathlib.Path(path).read_bytes().replace(b'\r\n', b'\n')
    if actual != expected.replace(b'\r\n', b'\n'):
        raise SystemExit(f'uploaded source differs from local commit: {path}')
git('-c', 'core.autocrlf=input', 'add', '--', *paths)
assert git('write-tree').strip() == git('rev-parse', target + '^{tree}').strip()
git('update-ref', 'refs/heads/exp/e1r008-anchorcut', target, base)
for path in paths:
    pathlib.Path(path).write_bytes(git('show', f'{target}:{path}'))
assert not git('status', '--porcelain', '--untracked-files=no').strip()
print('Verified local/server source and commit equality:', target)
PY
PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest tests/scheduler tests/kvcache -q > /data2/FreeToken/runs/dev_D01/pytest_final.log 2>&1
