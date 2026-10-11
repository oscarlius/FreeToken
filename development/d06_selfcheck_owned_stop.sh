set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,os,pathlib,signal,time
receipt_path=pathlib.Path('/data2/FreeToken/runs/dev_D06/gpu_selfcheck_launch_195aa332.json')
assert hashlib.sha256(receipt_path.read_bytes()).hexdigest()=='e0ceca3447cbf365e2cb4453fd8beec86d634033866b763e9ff5a12de4f70793'
receipt=json.loads(receipt_path.read_text());pid=receipt['pid'];proc=pathlib.Path('/proc')/str(pid)
fields=proc.joinpath('stat').read_text().rpartition(') ')[2].split()
argv=[part.decode() for part in proc.joinpath('cmdline').read_bytes().split(b'\0') if part]
assert fields[0]!='Z' and int(fields[2])==pid and int(fields[3])==pid
assert argv==receipt['argv'] and proc.stat().st_uid==os.geteuid()
identity=(fields[19],proc.stat().st_uid)
check=proc.joinpath('stat').read_text().rpartition(') ')[2].split()
assert (check[19],proc.stat().st_uid)==identity
os.kill(pid,signal.SIGTERM)
deadline=time.monotonic()+45
while proc.exists() and proc.joinpath('stat').read_text().rpartition(') ')[2].split()[0]!='Z':
 if time.monotonic()>deadline:raise TimeoutError('owned selfcheck cleanup still active; lock retained')
 time.sleep(.5)
output=pathlib.Path(receipt['output']);error=json.loads((output/'error.json').read_text())
owned=json.loads((output/'candidate/owned_process.json').read_text())
service=pathlib.Path('/proc')/str(owned['pid'])
assert not service.exists() or service.joinpath('stat').read_text().rpartition(') ')[2].split()[0]=='Z'
proof={'pid':pid,'receipt_sha256':hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
 'reason':'client tokenizer/prompt construction stalled before any generation POST; prioritize P0',
 'scope':'SIGTERM only to verified owned selfcheck leader; runner owns probe and service cleanup',
 'batch_terminal':True,'owned_service_terminal':True,'error':error,
 'lock_present':pathlib.Path('/data2/_shared/gpu.lock').exists()}
target=receipt_path.parent/'gpu_selfcheck_195aa332_owned_stop.json'
with target.open('x') as stream:stream.write(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
PY
