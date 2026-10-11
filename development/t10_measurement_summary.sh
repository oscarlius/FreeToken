set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, json, pathlib, socket, subprocess
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R006')
s=json.loads((d/'status_batch34.json').read_text())
assert (s['rid'],s['card'],s['batch'])==(d.name,'T10',34)
assert s['state']=='complete',s
pid=pathlib.Path(f"/proc/{s['batch_pid']}/stat")
assert not pid.exists() or pid.read_text().partition(') ')[2].startswith('Z')
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as sock:
 assert sock.connect_ex(('127.0.0.1',8095))!=0
used=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip()
assert int(used)<=8,used
proof={'recorded_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%F %T CST'),
       'status':s,'owned_batch_gone':True,'port8095_free':True,'gpu_memory_mib':int(used),'shared_lock_absent':True}
with (d/'poststop_proof.json').open('x') as f: json.dump(proof,f,indent=2)
source=pathlib.Path('/data2/FreeToken/runs/plan_batches')
for name in ['state_measurement_summarize.py','initial_measurement_close.py']:
 with (d/name).open('xb') as f: f.write((source/name).read_bytes())
subprocess.run(['/data2/FreeToken/venv/bin/python',str(d/'state_measurement_summarize.py'),'T10',str(d),
 '--out',str(d/'measurements.json'),'--metadata-out',str(d/'initial_metadata.json'),
 '--tokenizer-path','/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay'],check=True)
for name in ['measurements.json','initial_metadata.json','poststop_proof.json']:
 print(name,hashlib.sha256((d/name).read_bytes()).hexdigest())
summary=json.loads((d/'measurements.json').read_text())
print('T10_SUMMARY_RESULTS',json.dumps(summary.get('results')))
print('T10 SUMMARY PREPARED; no formal verdict or closure yet')
PY
