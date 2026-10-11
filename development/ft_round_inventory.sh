set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,re
r=pathlib.Path('/data2/_shared/runs/ft_rounds')
print(json.dumps({'e2_rounds':sorted(p.name for p in r.iterdir() if re.fullmatch(r'E2-R\d{3}.*',p.name)),
                  'max_batch':max(int(m.group(1)) for p in r.iterdir() if (m:=re.fullmatch(r'batch(\d+)\.log',p.name))),
                  'short_probe_md5':hashlib.md5(pathlib.Path('/data2/FreeToken/scripts/ft_perf_decomp.py').read_bytes()).hexdigest()}))
PY
