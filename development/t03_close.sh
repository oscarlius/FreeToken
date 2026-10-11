set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,json,pathlib
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R008')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(d/'t03_summary.json')=='2f043855ba427817528f84f8472c0e0a65023d8e7a2cf14090d5d50a2fc4d919'
s=json.loads((d/'t03_summary.json').read_text())
assert s['snapshot_positive_coverage'] is False and not s['cache_regressions']
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%F %T CST')
review={'rid':d.name,'batch':29,'verdict':'PASS',
        'reviewer':'/root/d00_audit (01 independent verifier)','recorded_by':'/root','time':now,
        'checks':['archived summarizer recomputation equals both saved summary and metadata',
                  'exact admission full23f2e2c/tag plus D00/T00 closed evidence',
                  'six ABABAB arms; parsed argument differences restricted to PID and prefill_anchor_cut',
                  'compiled extensions identical across six arms',
                  'original trace 12 unique 16hex; 12 replay files bind actual source list-index and digests',
                  'D0/Prefill/request markers/reasons/continuation cached_tokens agree with raw records',
                  'each side has three cold and twelve hot observations, no discarded observations',
                  'owned batch and six service PIDs have exited; subsequent GPU owner is T04'],
        'values':{'cold_A_minus_B_s':2.628798321355134,'hot_A_minus_B_s':0.008475379436276853,
                  'cache_regressions':0,'snapshot_A':[0,0,0],'snapshot_B':[0,0,0]},
        'gaps':['No nonzero successful snapshot coverage; zero counts are an observation only'],
        'summary_sha256':sha(d/'t03_summary.json')}
with (d/'review_batch29.json').open('x') as f:
    json.dump(review,f,ensure_ascii=False,indent=2)
PY
/data2/FreeToken/venv/bin/python /data2/_shared/runs/ft_rounds/E2-R008/initial_measurement_close.py E2-R008 --batch 29 --metadata /data2/_shared/runs/ft_rounds/E2-R008/measurements.json --review /data2/_shared/runs/ft_rounds/E2-R008/review_batch29.json
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,sys
sys.path.insert(0,'/data2/FreeToken/runs/plan_batches')
from e2_runtime import verify_manifest
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R008')
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
verify_manifest(d)
for name in ['MANIFEST.sha256','round.json','review_batch29.json','t03_summary.json']:
    print(name,hashlib.sha256((d/name).read_bytes()).hexdigest())
print('T03 CLOSURE VERIFY PASS; formal verdict pending D04 append; nonzero snapshot coverage absent')
PY
