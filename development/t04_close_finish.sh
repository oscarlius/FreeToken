set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R002')
p=pathlib.Path('/data2/FreeToken/runs/plan_batches/initial_measurement_close.py')
assert hashlib.md5(p.read_bytes()).hexdigest()=='bc5caf05e40b17a267a5aebe19ffe0ff'
subprocess.run(['/data2/FreeToken/venv/bin/python',str(p),'--self-test'],check=True)
assert (d/'review_batch30.json').is_file()
assert (d.parent/'batch30.log').is_file() and (d.parent/'batch30.log').stat().st_size==0
with (d/'initial_measurement_close_v2.py').open('xb') as f:
    f.write(p.read_bytes())
PY
/data2/FreeToken/venv/bin/python /data2/_shared/runs/ft_rounds/E2-R002/initial_measurement_close_v2.py E2-R002 --batch 30 --metadata /data2/_shared/runs/ft_rounds/E2-R002/measurements_v2.json --review /data2/_shared/runs/ft_rounds/E2-R002/review_batch30.json
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,sys
sys.path.insert(0,'/data2/FreeToken/runs/plan_batches')
from e2_runtime import verify_manifest
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R002')
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
verify_manifest(d)
for name in ['MANIFEST.sha256','round.json','review_batch30.json','t04_summary_v2.json']:
    print(name,hashlib.sha256((d/name).read_bytes()).hexdigest())
print('T04 PHASE1 CLOSURE VERIFY PASS; original empty batch log retained; no tolerance admission')
PY
