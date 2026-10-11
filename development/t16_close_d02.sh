set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime,json,pathlib,socket,subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D02')
status=json.loads((d/'status_batch25.json').read_text())
assert status['state']=='complete'
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as s:
    assert s.connect_ex(('127.0.0.1',8095)) != 0
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip()
assert all(int(x)<1000 for x in gpu.splitlines()),gpu
review={'rid':'E2-pre-gate-D02','batch':25,'verdict':'PASS','reviewer':'/root/d00_audit (01 independent verifier)',
        'time':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%F %T CST'),
        'checks':['same cold-id, full text and nonempty business sequence in all four arms',
                  'full text SHA256 ec7698e814f239f295126b644e60ab5992cb7a9cf3cc2ab1d037d9f8d0eacdf7',
                  'parsed arguments differ only in generated PID identity',
                  'all prefill events 13; parent D0 rows 12, new rows 13; 12 common integer byte rows equal',
                  'new final row request/chunk/reason/finite ordered timestamps align; flushed while service alive',
                  'D0-off has no D0 files or logs; CUDA graph batch size 2 throughout, timeline disabled',
                  'batch and service exited, lock absent, port8095 free, GPU 4 MiB at independent review'],
        'remaining':['T05 business testing waits for D06','timings are recorded, not performance acceptance']}
with (d/'review_batch25.json').open('x') as f:
    json.dump(review,f,ensure_ascii=False,indent=2)
PY
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/close_t16_initial.py E2-pre-gate-D02 --batch 25 --review /data2/_shared/runs/ft_rounds/E2-pre-gate-D02/review_batch25.json
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D02')
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
for line in (d/'MANIFEST.sha256').read_text().splitlines():
    sha,name=line.split('  ',1)
    assert hashlib.sha256((d/name).read_bytes()).hexdigest()==sha,name
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
print('D02 CLOSURE VERIFY PASS')
PY
