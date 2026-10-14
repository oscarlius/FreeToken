"""Read production recovery metadata and freeze public synthetic CPU inputs."""
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
import hashlib, json, pathlib, subprocess
root = pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
launch = json.loads((root/'native_build_launch.json').read_text())
proc = pathlib.Path(f"/proc/{launch['pid']}/stat")
print('Native build process:', proc.read_text().split()[2] if proc.exists() else 'absent')
log = (root/'native_build.log').read_bytes()
print('Native build log SHA256:', hashlib.sha256(log).hexdigest())
print(log.decode(errors='replace')[-4500:])
prod = pathlib.Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-02')
for name in ('owner.json', 'deployment_approval.json', 'smoke_invocation.json', 'smoke_campaign.json'):
    value = json.loads((prod/name).read_text())
    print(name, json.dumps(value, ensure_ascii=False)[:9000])
model = pathlib.Path('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay')
cfg = json.loads((model/'config.json').read_text())
print('Model config identity:', {key: cfg.get(key) for key in ('_name_or_path','model_type','architectures','expert_quant')})
print('Tokenizer files:', [p.name for p in model.iterdir() if 'token' in p.name])
''')
finally:
    client.close()
