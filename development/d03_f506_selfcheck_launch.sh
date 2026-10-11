set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, json, os, pathlib, socket, subprocess, sys, tempfile
root = pathlib.Path('/data2/FreeToken')
dev = root / 'runs/dev_D03'
stage = dev / 'selfcheck_f506_96db3ca'
raw = dev / 'historical_raw_ids_f5067bb_v2.json'
script = stage / 'd03_gpu_selfcheck_f506.py'
expected = {
    script: '96db3ca98bf40a629342586061b5d0acd21d1fb4e1c47fb8bef0e9b8ea56715b',
    stage / 'd03_gpu_selfcheck.py': '4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453',
    stage / 'cpu_validation.log': 'f121084bf972d50012f827489bc6bfa042caf33e7f64af71d77c3be9f36e8491',
    raw: '0d59fa0777bdfb3e521b84723c426a895418942a7eff9fa0367d8b3078444926',
}
for path, digest in expected.items():
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('frozen input changed: ' + str(path))
cpu = json.loads((stage / 'cpu_validation.json').read_text())
if any(step['returncode'] for step in cpu['steps']):
    raise ValueError('Linux CPU validation failed')
for wt, commit in [('e1r003st', 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'),
                   ('e2d03-continuation', 'f5067bbe05da51d5f78185213435a8be095a684a')]:
    path = root / 'wt' / wt
    if subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip() != commit:
        raise ValueError('worktree commit changed')
    if subprocess.check_output(['git','-C',str(path),'status','--porcelain','--untracked-files=no'],text=True).strip():
        raise ValueError('tracked source is dirty')
if pathlib.Path('/data2/_shared/gpu.lock').exists():
    raise ValueError('GPU lock occupied')
with socket.socket() as sock:
    if sock.connect_ex(('127.0.0.1',8095)) == 0:
        raise ValueError('validation service port occupied')
memory = subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True)
if not memory.strip() or any(int(line) >= 1000 for line in memory.splitlines()):
    raise ValueError('GPU remains occupied')
output = dev / 'gpu_selfcheck_f5067bb'
receipt = dev / 'gpu_selfcheck_launch_f5067bb.json'
log = dev / 'gpu_selfcheck_f5067bb.log'
if output.exists() or receipt.exists() or log.exists():
    raise FileExistsError('existing development artifacts retained')
argv = [sys.executable,'-u',str(script),'--run','--raw-manifest',str(raw),'--tail-k','64']
record = {'schema':'ft_development_selfcheck_launch/v1','state':'reserved',
          'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'candidate_commit':'f5067bbe05da51d5f78185213435a8be095a684a',
          'parent_commit':'c30ae0d7003c3bbbf56867ce74da797332fa7ed5',
          'runner_sha256':expected[script],'raw_manifest_sha256':expected[raw],
          'argv':argv,'output':str(output),'log':str(log)}
with receipt.open('x') as stream:
    json.dump(record,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
with log.open('xb') as sink:
    process = subprocess.Popen(argv,cwd=root,stdin=subprocess.DEVNULL,stdout=sink,
                               stderr=subprocess.STDOUT,start_new_session=True)
record.update(state='launched',pid=process.pid,pgid=process.pid)
# Exclusive reservation survives any launch/persistence failure for inspection.
fd, temporary = tempfile.mkstemp(prefix=receipt.name+'.',dir=dev)
with os.fdopen(fd,'w') as stream:
    json.dump(record,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
os.replace(temporary,receipt)
print(json.dumps(record),flush=True)
PY
