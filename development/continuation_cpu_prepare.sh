set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib, subprocess
source = pathlib.Path('/data2/FreeToken/wt/e1r003st')
target = pathlib.Path('/data2/FreeToken/runs/dev_D03/continuation_cpu_71f93be')
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
assert not target.exists()
target.mkdir()
subprocess.run(['git', '-C', str(source), 'worktree', 'add', '--detach', str(target / 'repo'),
                'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'], check=True)
for extension in (source / 'python/freetoken').rglob('*.so'):
    path = target / 'repo/python/freetoken' / extension.relative_to(source / 'python/freetoken')
    assert not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(extension.resolve())
print('ISOLATED_CONTINUATION_CPU_SURFACE_CREATED; active c30 source unchanged')
PY
