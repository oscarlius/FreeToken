set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/t10_stage2_r013_from_r017_37e10f2
cd "$target"
test ! -e regression.log
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
root = pathlib.Path.cwd()
pins = {
'development/t10_r013_from_r017.py': '37e10f2100977e2e2ab22017f051dbf786748bfcd4a6d15dc85ef8eb59698a25',
'development/d03_t10_r013_launch.py': 'b94ec8c0d2931ab14daad0bf71c31d249701cd8a0e2c8cf3003cb4bcbe214893',
'development/d03_phase2_prepare_r017.py': 'a52e39e95cf002aa3909b860ff084ff7c85f3d91261d1c75baa9e74a38671581',
'development/tests/test_t10_r013_from_r017.py': 'ba4d6b57f467f9d7b3e4daff9731f02dc84b99174e5c6d0c61dc1050c72e58de',
'development/tests/test_t10_r013_launch.py': '65ebeb12e2e9c2456f1692ae60034fcc3f04a137d4106ae49e7928585b365efa',
}
for name, digest in pins.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
PY
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider development/tests/test_t10_r013_from_r017.py development/tests/test_t10_r013_launch.py > regression.log 2>&1
tail -n 8 regression.log
sha256sum regression.log
chmod -R a-w "$target"
CUDA_VISIBLE_DEVICES=0 PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, pathlib
from types import ModuleType
p = pathlib.Path('development/d03_t10_r013_launch.py')
source=p.read_bytes()
assert hashlib.sha256(source).hexdigest() == 'b94ec8c0d2931ab14daad0bf71c31d249701cd8a0e2c8cf3003cb4bcbe214893'
m=ModuleType('r013_preflight'); m.__file__=str(p.resolve())
exec(compile(source,str(p),'exec'),m.__dict__)
lifecycle, atomic=m.verify_sources()
prerequisite=lifecycle.prerequisite()
batch=atomic.next_batch(m.ROUNDS)
runner,forks=m.preflight(batch)
assert len(forks)==11
print('R013_ACTUAL_SEALED_PARENT_PREFLIGHT',json.dumps({'batch_preview':batch,'forks':len(forks),'parent_round_sha256':m.sha(m.ROUNDS/'E2-R017/round.json'),'parent_manifest_sha256':m.sha(m.ROUNDS/'E2-R017/MANIFEST.sha256'),'gpu_started':False,'batch_reserved':False}))
PY
