set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,json,pathlib
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R003')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
s=json.loads((d/'measurements.json').read_text())
assert s['verdict']=='pending_review' and s['proposed_verdict'] is None
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%F %T CST')
review={'rid':d.name,'batch':31,'verdict':'PASS',
        'reviewer':'/root/d00_audit (01 independent verifier)','recorded_by':'/root','time':now,
        'checks':['archived pure summarizer recomputation matches metadata except created_at',
                  'full immutable23f2e2c E2-base admission with D00/T00 closed bindings',
                  'six ABABAB arms have identical compiled extensions and only D0 environment differs',
                  'each arm retains 8 cold samples and excluded first shot; all source tuples identical',
                  'all formal cold samples cached_tokens=0; D0 while-alive aggregates intact',
                  'four-length TTFT/decode CI and holdout predictions independently recomputed',
                  'original source tools fixed MD5; all eight text diagnostics equal and retained',
                  'owned batch1592640 and six service PIDs gone; subsequent GPU owner is T08 batch32'],
        'values':s['results'],'gaps':[],
        'measurement_sha256':sha(d/'measurements.json')}
with (d/'review_batch31.json').open('x') as f:
    json.dump(review,f,ensure_ascii=False,indent=2)
PY
/data2/FreeToken/venv/bin/python /data2/_shared/runs/ft_rounds/E2-R003/initial_measurement_close.py E2-R003 --batch 31 --metadata /data2/_shared/runs/ft_rounds/E2-R003/measurements.json --review /data2/_shared/runs/ft_rounds/E2-R003/review_batch31.json
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,sys
sys.path.insert(0,'/data2/FreeToken/runs/plan_batches')
from e2_runtime import verify_manifest
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R003')
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
verify_manifest(d)
for name in ['MANIFEST.sha256','round.json','review_batch31.json','measurements.json','measurement_summary.json']:
    print(name,hashlib.sha256((d/name).read_bytes()).hexdigest())
print('T07 CLOSURE VERIFY PASS; formal verdict pending D04 append')
PY
