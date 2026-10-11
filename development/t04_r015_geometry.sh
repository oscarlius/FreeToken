set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json, pathlib
path = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R015/restore/serve.log')
assert not path.is_symlink()
with path.open('rb') as stream:
    text = stream.read(1024 * 1024).decode('utf-8', errors='replace')
matches = [line for line in text.splitlines() if 'Page size' in line or 'page_size' in line and 'overrid' in line]
print(json.dumps({'path': str(path), 'read_limit_bytes': 1024 * 1024, 'geometry_lines': matches[:8]}, ensure_ascii=False))
PY
