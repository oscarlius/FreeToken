set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,socket,subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R003')
s=json.loads((d/'status_batch31.json').read_text())
assert (s['rid'],s['gate'],s['batch'])==(d.name,'T07',31)
assert s['state']=='complete_measurements_pending_review',s
p=pathlib.Path(f"/proc/{s['batch_pid']}/stat")
assert not p.exists() or p.read_text().partition(') ')[2].startswith('Z'),'owned batch still alive'
assert not pathlib.Path('/data2/_shared/gpu.lock').exists(),'GPU lock still present'
with socket.socket() as sock:
    assert sock.connect_ex(('127.0.0.1',8095))!=0,'service still alive'
assert int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip())<=8
for name in ['production_measurement_summarize.py','initial_measurement_close.py']:
    with (d/name).open('xb') as f:
        f.write((pathlib.Path('/data2/FreeToken/runs/plan_batches')/name).read_bytes())
subprocess.run(['/data2/FreeToken/venv/bin/python',str(d/'production_measurement_summarize.py'),'--card','T07','--round',str(d),
                '--out',str(d/'measurements.json')],check=True)
summary=json.loads((d/'measurements.json').read_text())
print('results',json.dumps(summary['results'],ensure_ascii=False))
print('verdict',summary['verdict'])
print('ACTUAL T07 SUMMARY READY; RAW TEXT DIFFERENCES RETAINED AS OBSERVATIONS')
PY
