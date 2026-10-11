set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/t10_stage2_r013_from_r017_d231fe0
cd "$target"
test ! -e regression.log
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
root = pathlib.Path.cwd()
pins = {
'development/logits_probe.py': '7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7',
'development/t10_r013_from_r017.py': 'd231fe011f57babb5c9d8d82bb3e175d95b5ee287e355004219eee9ccf92f49f',
'development/d03_t10_r013_launch.py': '1c0e538b7a5e0b3056879f946a93d6a612feafb33c7f71df80615debf846d60a',
'development/d03_phase2_prepare_r017.py': 'a52e39e95cf002aa3909b860ff084ff7c85f3d91261d1c75baa9e74a38671581',
'development/tests/test_t10_r013_from_r017.py': 'be96833497ec5567a99b5930e42ca4b612c52b25ec1e4f8ffebd95aa0bd257b4',
'development/tests/test_t10_r013_launch.py': '105716478dc63d0d818e790d7278c31b1dce0b2847c33e2913a69ff2e35dd0c5',
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
assert hashlib.sha256(source).hexdigest() == '1c0e538b7a5e0b3056879f946a93d6a612feafb33c7f71df80615debf846d60a'
m=ModuleType('r013_preflight'); m.__file__=str(p.resolve())
exec(compile(source,str(p),'exec'),m.__dict__)
lifecycle, atomic=m.verify_sources()
prerequisite=lifecycle.prerequisite()
batch=atomic.next_batch(m.ROUNDS)
runner,forks=m.preflight(batch)
assert len(forks)==11
print('R013_ACTUAL_SEALED_PARENT_PREFLIGHT',json.dumps({'batch_preview':batch,'forks':len(forks),'parent_round_sha256':m.sha(m.ROUNDS/'E2-R017/round.json'),'parent_manifest_sha256':m.sha(m.ROUNDS/'E2-R017/MANIFEST.sha256'),'gpu_started':False,'batch_reserved':False}))
PY
