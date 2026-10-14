"""Read benchmark hardware and existing checkpoint provenance without loading weights."""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ops',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
client=ops.connect()
try:
    ops.run(client,r'''
import datetime, json, pathlib, re, subprocess
root=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
model=pathlib.Path('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay')
config=json.loads((model/'config.json').read_text())
data={'at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
      'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],text=True),
      'cpu':subprocess.check_output(['lscpu','-J'],text=True),
      'os':pathlib.Path('/etc/os-release').read_text(),
      'model_path':str(model.resolve()),
      'model_identity':{k:config.get(k) for k in ('_name_or_path','model_type','architectures','quantization_config')},
      'model_root_files':sorted(p.name for p in model.iterdir() if p.is_file())[:80]}
references=[]
for path in (model/'README.md',model.resolve().parent/'README.md'):
    if path.is_file():
        for line in path.read_text(errors='replace').splitlines():
            if any(term in line.lower() for term in ('base_model:','model_name:','huggingface.co/','modelscope.cn/')):
                references.append(line[:400])
data['model_card_references']=references[:20]
with (root/'BENCHMARK_METADATA.json').open('x') as f:json.dump(data,f,indent=2)
print(json.dumps({k:v for k,v in data.items() if k not in ('cpu','os')},indent=2))
''')
    sftp=client.open_sftp();sftp.get('/data2/FreeToken/development/upstream_layer_major_pr_20261014/BENCHMARK_METADATA.json',str(HERE/'BENCHMARK_METADATA.json'));sftp.close()
finally:client.close()
