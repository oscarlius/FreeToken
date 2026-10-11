"""Refine the audited prompt baseline to the actual decode attention length."""
import argparse
import hashlib
import json
from pathlib import Path

from reconstruct_context import audit

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
result = audit(args.root)
result['definition'] = 'Per routed decode token: bound full prompt + prior routed decode tokens + current input token (1); request-token-weighted median, in thousands.'
result['position_basis'] = '8256553 engine.py prefill complete_one advances device_len; core.py complete_one adds 1; first decode attends prompt+1.'
result['baseline_audit_sha256'] = hashlib.sha256(Path(__file__).with_name('reconstruct_context.py').read_bytes()).hexdigest()
for group in result['groups'].values():
    for prefix in ('full_trace', 'calibration_prefix'):
        group[prefix + '_median_tokens'] += 1
        group[prefix + '_L_ktok'] = group[prefix + '_median_tokens'] / 1000
with args.out.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2)
print(json.dumps({name: value['full_trace_L_ktok'] for name, value in result['groups'].items()}))
