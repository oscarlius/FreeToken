set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, pathlib, subprocess, sys
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R006')
patch=pathlib.Path('/data2/FreeToken/runs/dev_D04/t10_cache_report_append_20261004.json')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(patch)=='8e49b63780831ddedfe6005d0466f2c97b31f0175c4ca6a59d0886e87c2d9fea'
assert sha(d/'MANIFEST.sha256')=='9c70ea49c1daf40f5851f246fa8b6e44927a3d00a1962a8a51b74ab36613619b'
assert sha(d/'round.json')=='810fe298194c4b4de32eb9d2b131b3377c95b64299827f6f7b4cdf4e06c26b44'
old=(d/'round.json').read_bytes()
data=json.loads(patch.read_text())['cache_report_analysis']
assert data['round_id']==d.name and data['card']=='T10'
assert sha(d/'admission.json')==data['admission_sha256']
for name,arm in data['arms'].items():
 paths={'serve_log':'serve.log','serve_args':'serve_args.txt',
        'reversecold_replay':'reversecold.json','forwardwarm_replay':'forwardwarm.json'}
 for key,rel in paths.items(): assert sha(d/name/rel)==arm['sha256'][key]
 assert arm['enable_cache_report_disabled'] is True
 assert len(arm['reversecold_12'])==len(arm['forwardwarm_12'])==12
 assert all(row['server_cached_tokens']==0 for row in arm['reversecold_12'])
 assert all(row['server_cached_tokens']>0 for row in arm['forwardwarm_12'])
py='/data2/FreeToken/venv/bin/python'
writer='/data2/FreeToken/scripts/round_json_append.py'
subprocess.run([py,writer,str(d),'add','--json',str(patch)],check=True)
subprocess.run([py,writer,str(d),'check'],check=True)
new=json.loads((d/'round.json').read_text())
assert new.pop('cache_report_analysis')==data
assert new==json.loads(old)
assert (d/'round_history/round.v001.json').read_bytes()==old
assert (d/'round_history/round.v002.json').read_bytes()==(d/'round.json').read_bytes()
assert sha(d/'MANIFEST.sha256')=='9c70ea49c1daf40f5851f246fa8b6e44927a3d00a1962a8a51b74ab36613619b'
assert all(not p.stat().st_mode&0o222 for p in [d,*d.rglob('*')])
sys.path.insert(0,'/data2/FreeToken/runs/plan_batches')
from e2_runtime import verify_manifest
verify_manifest(d)
for p in [d/'round.json',d/'round_history/round.v001.json',d/'round_history/round.v002.json',d/'round_history/SHA256SUMS']:
 print('D04_REAL_APPEND_SHA256',p.relative_to(d),sha(p))
print('T10 raw server cache diagnosis appended; original measurements, verdict and manifest unchanged')
PY
