set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,json,pathlib
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R002')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(d/'t04_summary_v2.json')=='b42e2c9c1f6ce1cd1641c5a2c9cdc4fc564dda438f4aa7f9d7998fea2eddc939'
assert sha(d/'measurements_v2.json')=='a2c9775bf5c3baddc8fceeea972316cf69b5ec761dc0e277389d85c725547c82'
s=json.loads((d/'t04_summary_v2.json').read_text())
assert s['diagnostics']['comparability_gate']['observed']==12
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%F %T CST')
review={'rid':d.name,'batch':30,'verdict':'PASS','reviewer':'/root/d00_audit (01 independent verifier)',
        'recorded_by':'/root','time':now,
        'checks':['v2 archived summarizer recomputation matches saved summary and metadata apart from generation time',
                  'actual full23f2e2c/E2-base tag/trace SHA and source ENV bind three completed arms',
                  'three replay files strictly match source list-index and 12 unique 16hex digests',
                  '8192 parsed args differ only max_extend_tokens and PID; LM only prefill_layer_major and PID',
                  'compiled extension SHAs identical',
                  'historical B vs R4096 12 of12 bitwise equal; legal-reorder comparisons preserve rc1 differences',
                  'pair8192 has12 comparable lengths, no aggregate supplementation of minimum6',
                  'owned batch1529121 and service PIDs1529382/1551995/1571183 have exited'],
        'summary_sha256':sha(d/'t04_summary_v2.json'),
        'gaps':['original aggregate36 gate defect retained; v2 pair12 supersedes it',
                'no tolerance admission from phase1 maxabs; relative-L2/logits await D03'],
        'observation':{'LM_12416_ngram_dtype':'int32','LM_12416_ngram_maxabs':108521,
                       'LM_18944_ngram_dtype':'int32','LM_18944_ngram_maxabs':4073}}
with (d/'review_batch30.json').open('x') as f:
    json.dump(review,f,ensure_ascii=False,indent=2)
PY
/data2/FreeToken/venv/bin/python /data2/_shared/runs/ft_rounds/E2-R002/initial_measurement_close.py E2-R002 --batch 30 --metadata /data2/_shared/runs/ft_rounds/E2-R002/measurements_v2.json --review /data2/_shared/runs/ft_rounds/E2-R002/review_batch30.json
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
print('T04 PHASE1 CLOSURE VERIFY PASS; no tolerance admission')
PY
