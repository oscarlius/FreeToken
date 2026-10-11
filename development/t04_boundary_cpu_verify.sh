set -euo pipefail
target=/data2/FreeToken/runs/dev_D03/t04_boundary_cpu_1e1a75c
cd "$target"
test ! -e prediction.json
test ! -e regression.log
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, pathlib
pins={
'development/t04_boundary_cpu_gate.py':'1e1a75cc85577fd09af27a8312f9a39a65d3bcf03ec128bd6d76d88fdc294209',
'development/tests/test_t04_boundary_cpu_gate.py':'66f632525992fb8a78bbdde8ef1bf370f9fbfaaf8dcfc6bfe29789de36f8008b',
'development/t04_r015_boundary_inputs.json':'69e77aafa80b49a0f6a6e4898a2ce1e7265a58e4066860df71901762da93474d',
'development/t04_r015_geometry.json':'dddee68b5b3a8e308ac7f2446cce71f381b14a21d1ea83366b033578a2a27549'}
for name,digest in pins.items():
 assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()==digest,name
PY
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python development/t04_boundary_cpu_gate.py --runtime-root development/e2d03-continuation --out prediction.json
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider development/tests/test_t04_boundary_cpu_gate.py > regression.log 2>&1
tail -n 8 regression.log
/data2/FreeToken/venv/bin/python - <<'PY'
import json, pathlib, hashlib
p=pathlib.Path('prediction.json');o=json.loads(p.read_text())
print('T04_ACTUAL_CPU_PREDICTION',json.dumps({'prediction_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'runtime_sha256':o['runtime_sha256'],'scenarios':o['scenarios']},sort_keys=True))
PY
sha256sum regression.log
