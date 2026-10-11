set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,socket,subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R000')
status=json.loads((d/'status_batch27.json').read_text())
assert status['state']=='complete_measurements_pending_review'
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as sock:
    assert sock.connect_ex(('127.0.0.1',8095)) != 0
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip()
assert all(int(x)<=100 for x in gpu.splitlines()),gpu
p=pathlib.Path(f'/proc/{status["batch_pid"]}/stat')
assert not p.exists() or p.read_text().split(') ',1)[1][0]=='Z'
for name in ('t00_summarize.py','initial_measurement_close.py'):
    source=pathlib.Path('/data2/FreeToken/runs/plan_batches')/name
    with (d/name).open('xb') as out:
        out.write(source.read_bytes())
PY
/data2/FreeToken/venv/bin/python /data2/_shared/runs/ft_rounds/E2-R000/t00_summarize.py /data2/_shared/runs/ft_rounds/E2-R000 --out /data2/_shared/runs/ft_rounds/E2-R000/t00_summary.json --metadata-out /data2/_shared/runs/ft_rounds/E2-R000/initial_metadata.json
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R000')
s=json.loads((d/'t00_summary.json').read_text())
print(json.dumps({k:s[k] for k in ('round_id','results','historical_comparison','first_shots','telemetry')},ensure_ascii=False))
PY
