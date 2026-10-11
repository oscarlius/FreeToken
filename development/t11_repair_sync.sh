set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, os, pathlib, subprocess
base=pathlib.Path('/data2/FreeToken/runs/plan_batches')
stage=base/'t11_report_fix_20261004'
expected={'e2_launch.py':'a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf',
          'state_test_runner.py':'bf783f25435ab2b30e9bba4c19deedd882552f146d802a829d02aa99ce8177ea',
          'state_measurement_summarize.py':'d1c0c8bb82ab45d9a3f4339ceb592da660d6486aae600a37a22cce491de311af'}
for name,digest in expected.items(): assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==digest,name
env=dict(os.environ,PYTHONPATH=str(base),CUDA_VISIBLE_DEVICES='')
for name in expected:
 subprocess.run(['/data2/FreeToken/venv/bin/python',str(stage/name),'--self-test'],env=env,check=True)
assert hashlib.sha256((base/'state_test_runner.py').read_bytes()).hexdigest()=='cdf90db2a0345e40ebcdc4ea1a9ee2996437d5423149c499d6aff1aa182fc34a'
assert hashlib.md5((base/'state_measurement_summarize.py').read_bytes()).hexdigest()=='4cc3e8c951649009e5f6837165088ac9'
assert hashlib.sha256((base/'e2_launch.py').read_bytes()).hexdigest()=='e34ace4911a061bbbb76c82baae43661b4dca1dead7b9edff37ae4900daf78fc'
for name,digest in expected.items():
 target=base/name
 with (stage/(name+'.before')).open('xb') as f: f.write(target.read_bytes())
 pending=base/(name+'.t11-pending')
 with pending.open('xb') as f: f.write((stage/name).read_bytes())
 os.replace(pending,target)
 assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
 print('T11_CPU_VERIFIED_PUBLISHED',name,digest)
print('T11 repair ready for assigned E2-R011; no GPU launch or comparison/T16 change')
PY
