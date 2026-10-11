set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import datetime,json,pathlib,socket,subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D00')
status=json.loads((d/'status_batch26.json').read_text())
gate=json.loads((d/'gate_batch26.json').read_text())
assert status['state']=='complete' and gate['proposed_verdict']=='kept'
assert len(gate['arms'])==8
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as s:
    assert s.connect_ex(('127.0.0.1',8095)) != 0
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip()
assert all(int(x)<1000 for x in gpu.splitlines()),gpu
review={'rid':'E2-pre-gate-D00','batch':26,'verdict':'PASS',
        'reviewer':'/root/d00_audit (01 independent verifier)',
        'time':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%F %T CST'),
        'checks':['eight arms terminal complete; parent 80943fd, new 23f2e2c',
                  'four pairs: layer/non-layer, D0 on/off; same cold input and complete text for det/short/chunked',
                  'layer all prefill 13/business12, non-layer all23/business22; original legacy D0 one row shorter',
                  'all shared nonnegative integer H2D/D2D byte counts equal; no zip truncation',
                  'new rows contiguous chunks; request metadata and finite ordered timestamps align to all prefill events',
                  'all four live-flush records prove service alive before shutdown',
                  'raw parsed arguments differ only generated PID plus new defaults prefill_anchor_cut=True and mamba_host_slots=0',
                  'four D0-off arms have no D0 artifacts or bank/instrumentation logs; dev environment cleared',
                  'independent resource check: batch and all eight service PIDs gone, lock absent, port8095 free, GPU4MiB'],
        'remaining':['business T03 and later measurement gates are separate',
                     'nonzero successful snapshot positive coverage remains unproved']}
with (d/'review_batch26.json').open('x') as f:
    json.dump(review,f,ensure_ascii=False,indent=2)
PY
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/close_t16_initial.py E2-pre-gate-D00 --batch 26 --review /data2/_shared/runs/ft_rounds/E2-pre-gate-D00/review_batch26.json
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,pathlib,subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D00')
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
for line in (d/'MANIFEST.sha256').read_text().splitlines():
    sha,name=line.split('  ',1)
    assert hashlib.sha256((d/name).read_bytes()).hexdigest()==sha,name
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
root='/data2/FreeToken/wt/e2base'
def git(*args):
    return subprocess.check_output(['git','-C',root,*args],text=True).strip()
assert git('rev-parse','HEAD')=='23f2e2caa3395837c9474735ffc83321f3b9b5a1'
assert git('rev-parse','HEAD^{tree}')=='abf260e436a793ef28827962193de4c94067d004'
assert git('rev-parse','--short','E2-pre^{commit}')=='3db7b50'
assert not git('status','--porcelain','--untracked-files=no')
assert not git('tag','--list','E2-base@23f2e2c')
subprocess.run(['git','-C',root,'tag','-a','E2-base@23f2e2c','-m',
                'D00 integrated E2 base: D01/D02 T16 and batch26 eight-arm D00 gate independently PASS'],check=True)
assert git('describe','--tags','--exact-match')=='E2-base@23f2e2c'
print('D00 CLOSURE VERIFY PASS; E2-base@23f2e2c TAG PASS')
PY
