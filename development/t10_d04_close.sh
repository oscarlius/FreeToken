set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import datetime, hashlib, importlib.util, json, os, pathlib, subprocess, sys
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R006')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(d/'measurements.json')=='7102ba5b36fcd5f63a22ba346b6e81b819de29d406beb2526f1e4f95fe6265dc'
assert sha(d/'initial_metadata.json')=='42991faa83f00d8c63e3c78f189284984b360491414139c6fb9dfb986cca67ef'
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
review={'rid':d.name,'batch':34,'verdict':'PASS','reviewer':'/root/d00_audit (01 independent verifier)',
 'recorded_by':'/root','time':now.strftime('%F %T CST'),
 'checks':['archived pure summarizer reproduces measurements and metadata bytes',
 'full E2-base23f2e2c identity and exact original trace joins',
 'three commands/extensions equal; parsed arguments differ only literal owned PID',
 'all 72 full-text comparisons independently read; each process has cold and warm 12-round 200-token replay',
 'all original compare JSON/logs and actual returncodes retained',
 'all owned batch/service PIDs gone; recorded poststop port/GPU/lock proof verified'],
 'values':{'cross_cold_equal':36,'cross_cold_total':36,'cold_warm_different':33,'cold_warm_total':36},
 'gaps':['all cached_tokens=0; original compare cache-hit gates rc=1, not cache-hit PASS',
 'first differing output token remains a text-tokenizer proxy; logits diagnosis is a separate phase'],
 'measurement_sha256':sha(d/'measurements.json'),'metadata_sha256':sha(d/'initial_metadata.json')}
with (d/'review_batch34.json').open('x') as f: json.dump(review,f,ensure_ascii=False,indent=2)
candidate=pathlib.Path('/data2/FreeToken/runs/dev_D04/candidate/scripts')
expected={'round_json_append.py':'a4bd8b095bf718076f4d4b7f9ed8d6f5a96263b80e455ae2324d4f3c67601c91',
 'round_close.py':'e6fa3bc840c5c6e7c5fa43d4091bb5011932e6f856c2e0111ecdbe590f730c08',
 'round_close.sh':'6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9'}
versions={}
for name,digest in expected.items():
 assert sha(candidate/name)==digest,name
 with (d/name).open('xb') as f: f.write((candidate/name).read_bytes())
 versions[name]={'sha256':digest,'md5':hashlib.md5((d/name).read_bytes()).hexdigest()}
with (d/'d04_tool_versions.json').open('x') as f: json.dump(versions,f,indent=2)
spec=importlib.util.spec_from_file_location('initial_closure_validation',d/'initial_measurement_close.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
doc=module.validate(d,d.name,34,d/'initial_metadata.json',d/'review_batch34.json',now)
with (d/'round.json').open('xb') as f: f.write(module.json_bytes(doc))
py='/data2/FreeToken/venv/bin/python'
subprocess.run(['bash',str(d/'round_close.sh'),d.name],env=dict(os.environ,FT_ROUND_PYTHON=py),check=True)
subprocess.run([py,str(d/'round_json_append.py'),str(d),'check'],check=True)
sys.path.insert(0,'/data2/FreeToken/runs/plan_batches')
from e2_runtime import verify_manifest
verify_manifest(d)
assert (d/'round.json').read_bytes()==(d/'round_history/round.v001.json').read_bytes()
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
assert json.loads((d/'round.json').read_text())['verdict']=='pending_review'
for name in ['MANIFEST.sha256','round.json','review_batch34.json','measurements.json','d04_tool_versions.json']:
 print(name,sha(d/name))
print('D04_REAL_CLOSURE_TOOL_MD5',json.dumps(versions))
print('T10 D04 REAL CLOSURE VERIFIED; diagnostic failures preserved, formal verdict still pending')
PY
