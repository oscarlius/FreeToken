"""Read current frozen recovery sources without invoking service operations."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "ops", HERE.parent / "r067c_retry2_production_control_20261009/ssh_ops.py"
)
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
try:
    ops.run(client, r'''
import json, pathlib
root = pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
log = (root/'native_build.log').read_text(errors='replace')
print('Native build tail:', log[-700:])
print('Built modules:', [p.name for p in (root/'candidate_63858fa/python/freetoken/kernel').glob('*.so')])
prod = pathlib.Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-02')
approval = json.loads((prod/'deployment_approval.json').read_text())
frozen = pathlib.Path(approval['frozen_ops']['path'])
print('Frozen ops files:', sorted(p.name for p in frozen.iterdir() if p.is_file()))
for name in ('run_smoke.py', 'start_release.py', 'stop_release.py'):
    path = frozen/name
    if path.exists(): print(name, path.read_text()[:15000])
packages = pathlib.Path('/data2/FreeToken/development/ophak_release_e3_20261012')
print('Available e3 packages:', [p.name for p in packages.iterdir() if p.is_dir()])
''')
finally:
    client.close()
