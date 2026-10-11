set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, pathlib, re
from transformers import AutoTokenizer
root = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R015')
def small(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError('unbounded input artifact')
    return json.loads(path.read_text())
prefix = small(root / 'prompt_ids.json')
branch = small(root / 'restore/logits/branch_ids.json')
tokenizer = AutoTokenizer.from_pretrained('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay', local_files_only=True)
markers = {marker: tokenizer.encode(marker, add_special_tokens=False) for marker in ('</think>', '<|im_end|>', '<tool_call>')}
args = (root / 'restore/serve_args.txt').read_text()
fields = {key: (match.group(1) if (match := re.search(r'\b' + key + r'=([^,\s)]+)', args)) else None)
          for key in ('page_size', 'prefill_anchor_cut', 'prefill_layer_major', 'special_token_ckpt', 'max_extend_tokens')}
index = root / 'restore/logits/index.jsonl'
if index.stat().st_size > 1024 * 1024 or index.is_symlink():
    raise ValueError('unbounded index')
rows = [json.loads(line) for line in index.read_text().splitlines() if line.strip()]
result = {'prefix_ids': prefix, 'prefix_file_sha256': hashlib.sha256((root / 'prompt_ids.json').read_bytes()).hexdigest(),
          'branch': branch, 'marker_ids': markers, 'parsed_configuration': fields,
          'restore_logits_extra': [row.get('extra') for row in rows if row.get('kind') == 'logits']}
print(json.dumps(result, ensure_ascii=False, allow_nan=False))
PY
