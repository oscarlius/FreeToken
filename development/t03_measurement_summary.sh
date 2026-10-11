set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,socket,subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R008')
status=json.loads((d/'status_batch29.json').read_text())
assert status['rid']==d.name and status['gate']=='T03' and status['batch']==29
assert status['state']=='complete_measurements_pending_review',status
pid=status['batch_pid']
p=pathlib.Path(f'/proc/{pid}/stat')
assert not p.exists() or p.read_text().partition(') ')[2].startswith('Z'),'batch still alive'
assert not pathlib.Path('/data2/_shared/gpu.lock').exists(),'GPU lock still present'
with socket.socket() as s:
    assert s.connect_ex(('127.0.0.1',8095))!=0,'service still alive'
used=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip())
assert used<=8,used
for name in ['t03_summarize.py','initial_measurement_close.py']:
    with (d/name).open('xb') as f:
        f.write((pathlib.Path('/data2/FreeToken/runs/plan_batches')/name).read_bytes())
subprocess.run(['/data2/FreeToken/venv/bin/python',str(d/'t03_summarize.py'),'--round',str(d),'--batch','29',
                '--summary-out',str(d/'t03_summary.json'),'--metadata-out',str(d/'measurements.json')],check=True)
summary=json.loads((d/'t03_summary.json').read_text())
for key in ['results','cold_seg_reasons','cache_regressions','proposed_verdict','snapshot_positive_coverage']:
    print(key,json.dumps(summary[key],ensure_ascii=False))
print('ACTUAL T03 MEASUREMENT SUMMARY READY; formal verdict remains pending review')
PY
