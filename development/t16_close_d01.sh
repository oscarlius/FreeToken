set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime,json,pathlib
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D01')
review={'rid':'E2-pre-gate-D01','batch':24,'verdict':'PASS','reviewer':'/root/d00_audit (01 verifier)',
        'time':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%F %T CST'),
        'checks':['parsed argument union: exact PID identity and prefill_anchor_cut=True only',
                  'D0 and production full texts identical, SHA256 32ba9d9910f6c57cd45aaaa86e50c7622ed1fae2aee0d0ecd667686bb8502431',
                  'all prefill events 13, old/new D0 rows 12 with identical integer byte counters',
                  'nonempty business sequences byte-equal; D01 request metadata aligns with full events',
                  'all 11 reused parent SHA256 values unchanged',
                  'D0-off has no D0 files or bank/reason logs',
                  'batch/serve exited; port8095 free, lock absent'],
        'remaining':['T03 business test pending','nonzero successful decode snapshot positive control missing'],
        'failure_history':'batch21-23 preserved; four accepted arms are PARENT/NEW_b24/PARENT_P_b24/NEW_P_b24'}
with (d/'review_batch24.json').open('x') as f: json.dump(review,f,ensure_ascii=False,indent=2)
PY
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/close_t16_initial.py E2-pre-gate-D01 --batch 24 --review /data2/_shared/runs/ft_rounds/E2-pre-gate-D01/review_batch24.json
PYTHONPATH=/data2/FreeToken/wt/e1r008/python /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D01')
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
for line in (d/'MANIFEST.sha256').read_text().splitlines():
    sha,name=line.split('  ',1); assert hashlib.sha256((d/name).read_bytes()).hexdigest()==sha,name
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
print('D01 CLOSURE VERIFY PASS')
PY
