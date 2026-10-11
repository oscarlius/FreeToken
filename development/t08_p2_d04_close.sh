set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,importlib.util,json,os,pathlib,subprocess,sys
root=pathlib.Path('/data2/FreeToken')
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R009-p64k')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(d/'initial_metadata.json')=='291d27477ebbbc4cc37f351353b651cca58a4c2998c15066bd6a888797c901ca'
assert sha(d/'P2/measurements.json')=='9894e8dc35e7dd30b8497b19e6d7db915d9085a83ffc7ea3240a6249a0c25f10'
assert sha(d/'parent_p1_binding.json')=='555610700d9af40ab1443ead0e9155a7ee1577b784549ca4d581313304301418'
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
review={'rid':d.name,'batch':37,'verdict':'PASS','reviewer':'/root/d00_audit (independent read-only verifier)',
 'recorded_by':'/root','time':now.strftime('%F %T CST'),
 'checks':['actual production summarizer recomputation equals metadata exactly',
 'taskset1,3-47 and parsed73728 window/4096 chunk/layer-major/checkpoint/cache report/slots0; no D0',
 'first separate; two cold64 probes have built65400/prompt65412 and two cold32 built32052/prompt32064',
 'all128-completion raw probes have zero cached tokens and actual source-cold IDs',
 'parent P1 is sealed and its exact five bound file hashes all match',
 'archived P2 and nine probe/input hashes match; poststop preserves owned-process/port/GPU/lock proof'],
 'values':{'cold64_ttft_s':[13.024,13.089],'cold32_ttft_s':[6.426,6.45]},
 'gaps':['D06 two-decode remains pending'],
 'metadata_sha256':sha(d/'initial_metadata.json'),'measurement_sha256':sha(d/'P2/measurements.json')}
with (d/'review_batch37.json').open('x') as f: json.dump(review,f,indent=2)
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
doc=module.validate(d,d.name,37,d/'initial_metadata.json',d/'review_batch37.json',now)
with (d/'round.json').open('xb') as f: f.write(module.json_bytes(doc))
subprocess.run(['bash',str(d/'round_close.sh'),d.name],env=dict(os.environ,FT_ROUND_PYTHON=sys.executable),check=True)
subprocess.run([sys.executable,str(d/'round_json_append.py'),str(d),'check'],check=True)
sys.path.insert(0,str(root/'runs/plan_batches'))
from e2_runtime import verify_manifest
verify_manifest(d)
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
for name in ['MANIFEST.sha256','round.json','review_batch37.json','d04_tool_versions.json']: print('T08_P2_CLOSED_SHA256',name,sha(d/name))
print('T08 P2 independently reviewed and D04 closed; formal verdict remains pending_review')
PY
