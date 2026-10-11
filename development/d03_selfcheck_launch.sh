set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,socket,subprocess,sys
root=pathlib.Path('/data2/FreeToken')
dev=root/'runs/dev_D03'
commit='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
script=dev/'d03_gpu_selfcheck.py'
raw=dev/'historical_raw_ids_c30ae0d.json'
assert hashlib.md5(script.read_bytes()).hexdigest()=='127d0f6108f6a387ae031be5df228c2a'
assert hashlib.sha256(raw.read_bytes()).hexdigest()=='6a08e2e855acacab103eeb4ea0d07972f3e477506020783ec930dbca744fa1e2'
assert subprocess.check_output(['git','-C',str(root/'wt/e1r003st'),'rev-parse','HEAD'],text=True).strip()==commit
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as sock: assert sock.connect_ex(('127.0.0.1',8095)) != 0
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True)
assert all(int(line)<1000 for line in gpu.splitlines())
output=dev/'gpu_selfcheck_c30ae0d'
assert not output.exists()
launch=dev/'gpu_selfcheck_launch_c30ae0d.json'
assert not launch.exists()
log=dev/'gpu_selfcheck_c30ae0d.log'
argv=[sys.executable,'-u',str(script),'--run','--raw-ids',str(raw),'--tail-k','64']
with log.open('xb') as sink:
 process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=sink,stderr=subprocess.STDOUT,start_new_session=True,cwd=root)
record={'pid':process.pid,'pgid':process.pid,'candidate_commit':commit,'argv':argv,'log':str(log),'output':str(output),
 'runner_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'raw_manifest_sha256':hashlib.sha256(raw.read_bytes()).hexdigest()}
with launch.open('x') as f: json.dump(record,f,indent=2);f.write('\n')
print('D03_GPU_SELFCHECK_LAUNCHED',json.dumps(record),flush=True)
PY
