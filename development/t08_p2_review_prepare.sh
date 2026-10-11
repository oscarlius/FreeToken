set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,socket,subprocess,sys
root=pathlib.Path('/data2/FreeToken')
rounds=pathlib.Path('/data2/_shared/runs/ft_rounds')
d=rounds/'E2-R009-p64k'
status=json.loads((d/'status_batch37.json').read_text())
assert status['state']=='complete_measurements_pending_review' and status['batch_pid']==2185365
for pid in [2185365,2185786]: assert not pathlib.Path(f'/proc/{pid}').exists(),pid
with socket.socket() as sock: assert sock.connect_ex(('127.0.0.1',8095)) != 0
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip()
assert all(int(line.split(',')[0])<1000 for line in gpu.splitlines())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
tool=root/'runs/plan_batches/production_measurement_summarize.py'
assert sha(tool)=='bf8bb45348822c4b69b02a2927f4087507ba0ff4c995bcd8a0a0984aae04ac8f'
with (d/'poststop_review_prepare.json').open('x') as out:
 json.dump({'batch_pid':2185365,'service_pid':2185786,'both_exited':True,'port_8095_free':True,'lock_absent':True,'gpu':gpu},out,indent=2)
subprocess.run([sys.executable,str(tool),'--card','T08','--round',str(d),'--phase','P2','--parent-round',str(rounds/'E2-R009'),'--out',str(d/'initial_metadata.json')],check=True)
for name in ['admission.json','measurement_summary.json','initial_metadata.json','P2/measurements.json','poststop_review_prepare.json','parent_p1_binding.json']:
 print('SHA256',name,sha(d/name))
print('T08_P2_NUMBERS',json.dumps(json.loads((d/'initial_metadata.json').read_text())['results']))
PY
