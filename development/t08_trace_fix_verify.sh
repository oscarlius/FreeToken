set -euo pipefail
cd /data2/FreeToken/runs/plan_batches
/data2/FreeToken/venv/bin/python t08_runner.py --self-test
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib
import t08_runner as runner
p=pathlib.Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json')
d=runner.trace_round_digests(p)
assert len(d)==12
print('ACTUAL REVERSE SOURCE INDEX PASS',len(d),d[0],d[11])
print('MD5 t08_runner.py',hashlib.md5(pathlib.Path('t08_runner.py').read_bytes()).hexdigest())
PY
