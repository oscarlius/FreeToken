set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,importlib.util,json,os,pathlib,subprocess,sys
root=pathlib.Path('/data2/FreeToken')
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R009')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(d/'initial_metadata.json')=='4ad143778af3390d9fde799b480e0ecb8c696e7e25eb76c43ee1ee4b31dd4416'
assert sha(d/'P1/measurements.json')=='bf97e0bafcf4868b440c1f8de63fc738e8636fff0169248d59139e481a7e2f9b'
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
review={'rid':d.name,'batch':36,'verdict':'PASS','reviewer':'/root/d01_switch (independent read-only verifier)',
 'recorded_by':'/root','time':now.strftime('%F %T CST'),
 'checks':['in-memory actual production summarizer equals initial metadata exactly',
 'actual taskset affinity1,3-47 and parsed49152 window/4096 chunk/layer-major/special checkpoint; no D0',
 'same s5A input contract and full text/events match historical deterministic evidence',
 'all three12-row replays are source-bound, live non-dry, non-error; first request retained separately',
 'quality raw60 unique boolean rows and evaluator source hash match recorded measurements',
 'soak raw counts103/103 success, duration1815.46s, errors0',
 'all eight tool/source hashes rechecked; owned batch/service gone, port free, lock absent, GPU4MiB'],
 'values':{'quality_pass':38,'quality_fail':22,'soak_success':103,'soak_errors':0,'soak_duration_s':1815.46},
 'gaps':['D06 two-decode remains pending; quality score is measured, not all-pass'],
 'metadata_sha256':sha(d/'initial_metadata.json'),'measurement_sha256':sha(d/'P1/measurements.json')}
with (d/'review_batch36.json').open('x',encoding='utf-8') as f: json.dump(review,f,ensure_ascii=False,indent=2)
validation=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R006/initial_measurement_close.py')
assert hashlib.md5(validation.read_bytes()).hexdigest()=='bc5caf05e40b17a267a5aebe19ffe0ff'
with (d/'initial_measurement_close.py').open('xb') as f: f.write(validation.read_bytes())
versions={}
for name,digest in {'round_json_append.py':'88178a9a3c83dec204e90e6dcf8c4db9','round_close.py':'415aa82b34c8fd82d09bfe8a8ce67eed','round_close.sh':'430693122ef66bb5a293fb421ff0f7fc'}.items():
 source=root/'scripts'/name
 assert hashlib.md5(source.read_bytes()).hexdigest()==digest
 with (d/name).open('xb') as f: f.write(source.read_bytes())
 versions[name]={'md5':digest,'sha256':sha(source)}
with (d/'d04_tool_versions.json').open('x') as f: json.dump(versions,f,indent=2)
spec=importlib.util.spec_from_file_location('initial_validation',d/'initial_measurement_close.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
doc=module.validate(d,d.name,36,d/'initial_metadata.json',d/'review_batch36.json',now)
with (d/'round.json').open('xb') as f: f.write(module.json_bytes(doc))
subprocess.run(['bash',str(d/'round_close.sh'),d.name],env=dict(os.environ,FT_ROUND_PYTHON=sys.executable),check=True)
subprocess.run([sys.executable,str(d/'round_json_append.py'),str(d),'check'],check=True)
sys.path.insert(0,str(root/'runs/plan_batches'))
from e2_runtime import verify_manifest
verify_manifest(d)
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
for name in ['MANIFEST.sha256','round.json','review_batch36.json','d04_tool_versions.json']: print('T08_P1_CLOSED_SHA256',name,sha(d/name))
print('T08 P1 independently reviewed and D04 closed; formal verdict remains pending_review')
PY
