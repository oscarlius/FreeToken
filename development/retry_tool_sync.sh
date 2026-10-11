set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, os, pathlib, subprocess
base=pathlib.Path('/data2/FreeToken/runs/plan_batches')
stage=base/'retry_ready_20261004'
expected={
 'e2_launch.py':'e34ace4911a061bbbb76c82baae43661b4dca1dead7b9edff37ae4900daf78fc',
 'production_measurement_summarize.py':'bf8bb45348822c4b69b02a2927f4087507ba0ff4c995bcd8a0a0984aae04ac8f',
 't08_runner.py':'d6c01ce3f4e908ac47c4268ebd22b090b825bb872cea3929cbecf261cb11f751',
 't09_runner.py':'865b9d02f9902598a62bb7030eaba7119c552455a6f5acf486069a545734e676',
}
for name,sha in expected.items():
 assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==sha,name
env=dict(os.environ,PYTHONPATH=str(base),CUDA_VISIBLE_DEVICES='')
for name in expected:
 subprocess.run(['/data2/FreeToken/venv/bin/python',str(stage/name),'--self-test'],env=env,check=True)
# Archive originals; publish only the four tested sources. T16 and original
# comparison tools stay untouched while T10/T11 use their frozen baseline.
for name,sha in expected.items():
 target=base/name
 backup=stage/(name+'.before')
 with backup.open('xb') as f:
  f.write(target.read_bytes())
 pending=base/(name+'.retry-pending')
 with pending.open('xb') as f:
  f.write((stage/name).read_bytes())
 os.replace(pending,target)
 assert hashlib.sha256(target.read_bytes()).hexdigest()==sha
 print('PUBLISHED_CPU_VERIFIED',name,sha,flush=True)
print('RETRY TOOL SYNC PASS; no GPU launch, baseline/T16/comparison files unchanged')
PY
