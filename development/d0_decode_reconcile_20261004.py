"""Recompute the historical costs and verify unchanged input manifests; no new inference."""
import hashlib
import json
from pathlib import Path
import shlex
import statistics
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
output={}
for rid in ['E2-R003','E2-R022-gate-D14']:
 directory=root/rid
 result=subprocess.run(['sha256sum','-c','MANIFEST.sha256'],cwd=directory,capture_output=True)
 if result.returncode:raise ValueError('immutable input manifest mismatch: '+rid)
 output[rid]={'manifest_sha256':hashlib.sha256((directory/'MANIFEST.sha256').read_bytes()).hexdigest(),
              'round_sha256':hashlib.sha256((directory/'round.json').read_bytes()).hexdigest(),
              'manifest_entries':len((directory/'MANIFEST.sha256').read_text().splitlines()),
              'manifest_verified':True}
print(json.dumps(output))
'''

if __name__ == '__main__':
    evidence_path = HERE / 'd0_decode_inputs_20261004.json'
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    original = evidence['E2-R003']['arms']
    comparisons = {}
    for target in (8000, 16000, 32052, 48000):
        groups = {}
        for prefix in ('A_d0on_', 'B_d0off_'):
            selected = [row for arm, data in original.items() if arm.startswith(prefix)
                        for name, row in data['formal_samples'].items() if name.startswith('c_' + str(target) + '_')]
            if len(selected) != 6:
                raise ValueError('six actual formal samples per length/arm required')
            for row in selected:
                r = row['record']
                if r['cached_tokens'] != 0 or r['completion_tokens'] != 128 or r['built_tokens'] != target:
                    raise ValueError('actual raw sample protocol differs')
            groups[prefix] = {'samples': selected, 'decode_mean': statistics.mean(row['record']['decode_tps'] for row in selected),
                              'ttft_mean': statistics.mean(row['record']['ttft_s'] for row in selected)}
        a, b = groups['A_d0on_'], groups['B_d0off_']
        comparisons[str(target)] = {'samples_per_group': 6, 'd0_decode_mean': a['decode_mean'], 'prod_decode_mean': b['decode_mean'],
                                    'relative_decode': (a['decode_mean'] - b['decode_mean']) / b['decode_mean'],
                                    'ttft_difference_s': a['ttft_mean'] - b['ttft_mean']}
    gate = evidence['E2-R022-gate-D14']['arms']
    gates = {}
    for a, b in [('PARENT_b50', 'PARENT_P_b50'), ('NEW_b50', 'NEW_P_b50')]:
        x, y = gate[a]['det.json']['record'], gate[b]['det.json']['record']
        gates[a] = {'d0_decode_tps': x['decode_tps'], 'prod_decode_tps': y['decode_tps'],
                    'relative_decode': (x['decode_tps'] - y['decode_tps']) / y['decode_tps'],
                    'ttft_difference_s': x['ttft_s'] - y['ttft_s'], 'samples_per_group': 1}
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-c', shlex.quote(PROGRAM)], capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    result = {'schema': 'ft_d0_read_only_reconciliation/v1', 'gpu_started': False,
              'input_evidence_sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
              'immutable_inputs': json.loads(process.stdout), 'T07': comparisons, 'R022_gate_only': gates,
              'causal_attribution': 'not_established; workload, sample protocol and recorded SM clocks differ',
              'performance_admission': 'R022 D0 gate rates excluded; no reclassification of original rounds'}
    target = HERE / 'd0_decode_reconciliation_20261004.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
