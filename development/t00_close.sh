set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,json,pathlib
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R000')
s=json.loads((d/'t00_summary.json').read_text())
assert len(s['historical_comparison'])==5
assert all(v['status']=='pass' and v['relative_absolute_delta']<=.07 for v in s['historical_comparison'].values())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%F %T CST')
review={'rid':'E2-R000','batch':27,'verdict':'PASS','reviewer':'/root/d00_audit (01 independent verifier)',
        'recorded_by':'/root','time':now,
        'checks':['eight arms terminal complete in exact order; archived summarizer recomputation equals saved summary',
                  'all raw cold/stdout/source hashes, input diagnostics and cached=0 valid',
                  'parsed raw arguments match declared 4096/73728/slots0/anchor-cut defaults; OFF only checkpoint false and PID',
                  'D0 only one arm; full Prefill3/JSONL3, alive proof, ready separated and ordered cold range RID1/2 match prompt tokens',
                  'all six tax processes contain one cold and four hot pairs with no discarded observations',
                  'all five historical primary comparisons within strict7pct and six source hashes verified',
                  'seed, five original tool hashes and eight-arm compiled extensions identical',
                  'owned batch/service processes gone, lock absent, port8095 free, GPU4MiB'],
        'observation':'OFF_p1 multi hot[0]=4.138834618963301 retained; means and medians use only hot indices1..4',
        'summary_sha256':sha(d/'t00_summary.json')}
with (d/'review_batch27.json').open('x') as f:
    json.dump(review,f,ensure_ascii=False,indent=2)
accepted={'schema':'ft_baseline_acceptance/v1','rid':'E2-R000','batch':27,'verdict':'kept',
          'reviewer':'/root (leader decision following independent01 PASS)', 'accepted_at':now,
          'commit':s['admission']['commit'],'code_version':s['admission']['code_version'],
          'summary_sha256':sha(d/'t00_summary.json'),'review_sha256':sha(d/'review_batch27.json'),
          'criteria':{'historical_absolute_relative_limit':.07,'comparisons':s['historical_comparison']},
          'checkpoint_observation':{'cold_multi_ON_minus_OFF_mean_s':2.822454971338933,
                                    'hot_multi_ON_minus_OFF_mean_s':-.10052773911350732,
                                    'hot_multi_ON_minus_OFF_median_s':-.001848963089287281,
                                    'OFF_p1_hot_outlier_retained':True},
          'scope':'E2 baseline admission; formal round verdict remains pending D04 append; no general throughput claim'}
with (d/'baseline_acceptance.json').open('x') as f:
    json.dump(accepted,f,ensure_ascii=False,indent=2)
PY
/data2/FreeToken/venv/bin/python /data2/_shared/runs/ft_rounds/E2-R000/initial_measurement_close.py E2-R000 --batch 27 --metadata /data2/_shared/runs/ft_rounds/E2-R000/initial_metadata.json --review /data2/_shared/runs/ft_rounds/E2-R000/review_batch27.json
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,sys
sys.path.insert(0,'/data2/FreeToken/runs/plan_batches')
from e2_runtime import admission,verify_manifest
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R000')
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
verify_manifest(d)
print('T00 CLOSURE VERIFY PASS; E2 ADMISSION',admission())
PY
