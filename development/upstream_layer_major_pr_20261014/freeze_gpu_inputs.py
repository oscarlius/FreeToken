"""Freeze synthetic, non-private text inputs with the existing target tokenizer."""
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
import os, pathlib, subprocess
root = pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
env = dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
           TOKENIZERS_PARALLELISM='false', HF_HUB_OFFLINE='1')
code = r"""
import datetime, hashlib, json, pathlib
from transformers import AutoTokenizer
root = pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
model = pathlib.Path('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay')
tokenizer = AutoTokenizer.from_pretrained(str(model), local_files_only=True, trust_remote_code=False)
def encode(text):
    return tokenizer.encode(text, add_special_tokens=False)
def exact(text, size):
    ids = encode(text)
    assert len(ids) >= size
    out = tokenizer.decode(ids[:size], skip_special_tokens=False, clean_up_tokenization_spaces=False)
    assert encode(out) == ids[:size], ('non-roundtripping prefix', size)
    return out
short = exact(('Arithmetic exercises: add two small integers and explain the answer.\n' * 100), 512)
sources = [
 'Astronomy records describe distant stars, spectral lines, orbital periods and careful observations.\n',
 'Botanical notes describe leaves, roots, flowering seasons, soil moisture and seed dispersal.\n',
 'Cartography exercises describe rivers, mountain contours, compass bearings and geographic coordinates.\n',
]
groups = []
for index, paragraph in enumerate(sources):
    full = exact(paragraph * 3500, 32077)
    cold = exact(full, 32012)
    assert full.startswith(cold)
    assert encode(full)[:32012] == encode(cold)
    assert len(encode(full)) - len(encode(cold)) == 65
    groups.append({'label': f'long{index+1}', 'cold': cold, 'continuation': full})
inputs = {'version': 1, 'short512': short, 'long': groups,
          'sampling': {'temperature': 0, 'max_tokens': 128, 'ignore_eos': True}}
payload = (json.dumps(inputs, ensure_ascii=False, indent=2)+'\n').encode()
with (root/'inputs.json').open('xb') as handle: handle.write(payload)
receipt = {'at': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
 'synthetic_only': True, 'inputs_sha256': hashlib.sha256(payload).hexdigest(),
 'tokenizer_sha256': {name: hashlib.sha256((model/name).read_bytes()).hexdigest()
                      for name in ('tokenizer.json','tokenizer_config.json')},
 'token_counts': {'short512': len(encode(short)), 'cold_each': 32012, 'continuation_each': 32077},
 'prefixes_preserved': True, 'no_model_download': True, 'no_gpu': True}
with (root/'INPUTS_MANIFEST.json').open('x') as handle: json.dump(receipt, handle, indent=2)
print(json.dumps(receipt, indent=2))
"""
result = subprocess.run([str(root/'main-venv/bin/python'), '-c', code], env=env,
                        capture_output=True, text=True, timeout=120)
print(result.stdout); print(result.stderr); assert result.returncode == 0, result.returncode
''')
    sftp = client.open_sftp()
    for name in ('inputs.json', 'INPUTS_MANIFEST.json'):
        sftp.get('/data2/FreeToken/development/upstream_layer_major_pr_20261014/' + name,
                 str(HERE/name))
    sftp.close()
finally:
    client.close()
