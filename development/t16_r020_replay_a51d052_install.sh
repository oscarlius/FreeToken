set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess,sys
base=pathlib.Path('/data2/FreeToken/runs/dev_D06')
source=base/'t16_r020_replay_a51d052.py'
digest='a51d052c06cfd0988ef3b61a9b4462ee30467d8620317c9f3d864947912e5073'
assert not source.is_symlink() and hashlib.sha256(source.read_bytes()).hexdigest()==digest
stage=base/'t16_r020_replay_a51d052'
assert not stage.exists(),'existing exact stage retained'
stage.mkdir()
runner=stage/'t16_r020_replay.py'
with runner.open('xb') as f:f.write(source.read_bytes())
argv=[sys.executable,str(runner),'--audit']
result=subprocess.run(argv,text=True,capture_output=True,timeout=60)
with (stage/'cpu_replay.log').open('x') as f:f.write(result.stdout+result.stderr)
if result.returncode:
 print((stage/'cpu_replay.log').read_text())
 raise SystemExit(result.returncode)
actual=json.loads(result.stdout)
assert actual['matched_gate_outcomes'] is True
with (stage/'actual_replay.json').open('x') as f:json.dump(actual,f,indent=2);f.write('\n')
proof={'source_stage':str(stage),'source_sha256':digest,'gpu_started':False,'returncode':result.returncode,'argv':argv,'log_sha256':hashlib.sha256((stage/'cpu_replay.log').read_bytes()).hexdigest(),'actual_replay_sha256':hashlib.sha256((stage/'actual_replay.json').read_bytes()).hexdigest(),'gate_sha256':actual['gate_sha256'],'candidate_binding_sha256':actual['candidate_binding_sha256'],'matched_gate_outcomes':True}
with (stage/'cpu_validation.json').open('x') as f:json.dump(proof,f,indent=2);f.write('\n')
for p in sorted(stage.rglob('*'),reverse=True):p.chmod(p.stat().st_mode&~0o222)
stage.chmod(stage.stat().st_mode&~0o222)
print(json.dumps(proof))
PY
