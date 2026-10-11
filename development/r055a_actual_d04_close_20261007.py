"""Close actual R055a/batch77 only after cold-state and pause independent review."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
ROUND = Path('/data2/_shared/runs/ft_rounds/E2-R055a-gate-D06')
BATCH = 77
CHILD_PID = 1030535
CANDIDATE = 'effb9969706922ddad9e59b96377e46469ebe97f'
PARENT = '0aa23431e5b800797543bdecbf35a01045131d7d'
ARMS = {f'{name}_b77' for name in (
    'PARENT0', 'PARENT1', 'NEW', 'CHUNK_PARENT0', 'CHUNK_PARENT1', 'CHUNK_NEW')}
TOOLS = {
    'round_json_append.py': '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff',
    'round_close.py': 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5',
    'round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def load(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(value if isinstance(value, bytes) else
                     (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    require(not Path(f'/proc/{CHILD_PID}').exists(), 'R055a controller is still running')
    require(not Path('/data2/_shared/gpu.lock').exists(), 'GPU lock remains')
    require(not any((ROUND / name).exists() for name in
                    ('round.json', 'round_history', 'MANIFEST.sha256', 'failed_harness.json')),
            'round already closed or actual batch failed')
    require(not any(path.is_symlink() for path in (ROUND, *ROUND.rglob('*'))), 'symlink evidence')
    require(args.review.is_file() and not args.review.is_symlink() and
            not args.review.stat().st_mode & 0o222, 'independent R receipt must be frozen')
    require(re.fullmatch('[0-9a-f]{64}', args.review_sha256) and
            sha(args.review) == args.review_sha256, 'R receipt SHA differs')
    ir = load(args.review)
    gate_path, pause_path = ROUND / 'gate_batch77.json', ROUND / 'pause_gate.json'
    gate, pause = load(gate_path), load(pause_path)
    status = load(ROUND / 'status_batch77.json')
    require(status.get('state') == 'complete_measurements_pending_review' and
            status.get('batch_pid') == CHILD_PID, 'six cold arms did not finish')
    require(gate.get('proposed_verdict') == 'kept' and gate.get('gate') == 'D06' and
            gate.get('parent_commit') == PARENT and gate.get('new_commit') == CANDIDATE and
            set(gate.get('arms', [])) == ARMS, 'actual six-arm gate matrix differs')
    require(pause.get('schema') == 'ft_r055_pause_on/v1' and
            pause.get('rid') == ROUND.name and pause.get('batch') == BATCH and
            pause.get('candidate_commit') == CANDIDATE, 'pause smoke did not finish')
    expected = {'schema': 'ft_r055a_independent_raw_review/v1', 'round_id': ROUND.name,
                'batch': BATCH, 'candidate_commit': CANDIDATE, 'parent_commit': PARENT,
                'verdict': 'PASS', 'gate_sha256': sha(gate_path),
                'pause_gate_sha256': sha(pause_path)}
    require(all(ir.get(key) == value for key, value in expected.items()) and
            set(ir.get('completed_arms', [])) == ARMS and
            isinstance(ir.get('checks'), dict) and ir['checks'] and
            all(value is True for value in ir['checks'].values()),
            'independent R has missing or failed raw-state/pause checks')
    receipt_path = ROOT / 'runs/dev_R055/launch_E2-R055a-gate-D06_batch77.json'
    receipt = load(receipt_path)
    require(receipt.get('state') == 'launched' and receipt.get('rid') == ROUND.name and
            receipt.get('batch') == BATCH and receipt.get('candidate_commit') == CANDIDATE and
            receipt.get('child', {}).get('execution_id') == '1030535:141527703',
            'actual owned launch binding differs')
    log_path = Path(receipt['batch_log'])
    stops = re.findall(r'STOP PASS owned_pid=(\d+) gpu=\d+', log_path.read_text())
    pause_owned = load(ROUND / 'PAUSE_ON/owned_process.json')
    require(len(stops) == 6 and len(set(stops)) == 6 and
            all(not (Path('/proc') / pid).exists() for pid in stops) and
            type(pause_owned.get('pid')) is int and
            not Path(f"/proc/{pause_owned['pid']}").exists(), 'owned services remain')
    require(sha(receipt['wrapper']) == receipt['wrapper_sha256'] ==
            'ab5ba217aeab0c231fd793c7d88e311e3598615d9f1398273b26cf9b5a822376',
            'actual batch77 wrapper differs')
    arms = {name: {'files': {leaf: sha(ROUND / name / leaf) for leaf in
                            ('SERVE_CMD.txt', 'ENV.txt', 'serve.log', 'serve_args.txt')}}
            for name in sorted(ARMS | {'PAUSE_ON'})}
    for name, digest in TOOLS.items():
        require(sha(ROOT / 'scripts' / name) == digest, 'D04 tool changed: ' + name)
    proof_path = ROOT / 'runs/dev_D06/r055_eff_code_path_basis_r_overlap_v2/review.json'
    require(sha(proof_path) == '23219c992c587dc35ed8f956542a908835be3fd850ba6758c8f61b0aea8ce5a7'
            and not proof_path.stat().st_mode & 0o222, 'default code-path proof differs')
    if not args.close:
        print(json.dumps({'state': 'closure_prevalidated', 'round_id': ROUND.name, 'batch': BATCH}))
        return
    used = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used',
                                    '--format=csv,noheader,nounits'], text=True)
    require(used.strip() and all(int(row) < 1000 for row in used.splitlines()), 'GPU is not idle')
    original = {path.relative_to(ROUND).as_posix(): sha(path)
                for path in ROUND.rglob('*') if path.is_file()}
    write(ROUND / 'review_batch77.json', args.review.read_bytes())
    for name, path in (
        ('launch_receipt.json', receipt_path),
        ('startup_review.json', ROOT / 'runs/dev_R055/reviews/E2-R055a-gate-D06_startup_review_v3.json'),
        ('file_dry_run_receipt.json', ROUND.parent / '.dryrun_R055a_E2-R055a-gate-D06/dry_run_receipt.json'),
        ('default_code_path_basis.json', proof_path),
    ):
        if name != 'launch_receipt.json':
            require(not path.stat().st_mode & 0o222, 'startup proof is writable: ' + name)
        write(ROUND / name, path.read_bytes())
    write(ROUND / 'close_source/r055a_actual_d04_close_20261007.py', Path(__file__).read_bytes())
    for name in TOOLS:
        write(ROUND / name, (ROOT / 'scripts' / name).read_bytes())
    write(ROUND / 'round.json', {
        'schema': 'ft_round/v2', 'round_id': ROUND.name, 'epoch': 2, 'card': 'T16',
        'parent': 'E2-R050-gate-D15', 'base': {'commit': PARENT},
        'experimental': {'candidate_commit': CANDIDATE}, 'serve': {'arms': arms},
        'design': {'batch': BATCH, 'cold_pause_endpoint': False, 'pause_smoke_endpoint': True,
                   'ordinary_prefill': True, 'references_per_mode': 2},
        'results': ir, 'proposed_verdict': 'kept', 'verdict': 'pending_review',
        'verdict_history': [], 'retractions': [], 'independent_review_sha256': sha(args.review),
        'batch_logs': [{'path': str(log_path), 'sha256': sha(log_path)}],
        'acceptance_limits': ['effb996 is a measurement-tree patch only; production remains 0aa23431.',
                              'T17, R041 and R040 retained evidence were not rerun.',
                              'TTFT/throughput of instrumented state capture are not performance claims.'],
        'diagnostics': {'original_raw_files': original,
                        'launch_receipt_sha256': sha(receipt_path),
                        'default_code_path_basis_sha256': sha(proof_path)},
    })
    subprocess.run([sys.executable, str(ROUND / 'round_close.py'), ROUND.name,
                    '--round-root', str(ROUND.parent)], check=True)
    subprocess.run([sys.executable, str(ROUND / 'round_json_append.py'), str(ROUND),
                    'verdict', '--new', 'kept', '--reason',
                    'Independent R recomputed two reference arms and candidate in both cold modes, '
                    'four state roles, input/token/full-text bits, and real pause completion/cancel recovery: PASS.',
                    '--evidence', 'gate_batch77.json', 'pause_gate.json', 'review_batch77.json',
                    'startup_review.json', 'file_dry_run_receipt.json', 'default_code_path_basis.json',
                    '--by', 'root authorized D04 closure'], check=True)
    subprocess.run([sys.executable, str(ROUND / 'round_json_append.py'), str(ROUND), 'check'], check=True)
    require(all(sha(ROUND / name) == digest for name, digest in original.items()), 'original raw bytes changed')
    for line in (ROUND / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ./', 1)
        require(sha(ROUND / name) == digest, 'manifest differs: ' + name)
    require(all(not path.stat().st_mode & 0o222 for path in (ROUND, *ROUND.rglob('*'))),
            'sealed round remains writable')
    binding = {'rid': ROUND.name, 'batch': BATCH, 'parent_commit': PARENT,
               'candidate_commit': CANDIDATE, 'round_sha256': sha(ROUND / 'round.json'),
               'manifest_sha256': sha(ROUND / 'MANIFEST.sha256'), 'gate_sha256': sha(gate_path),
               'pause_gate_sha256': sha(pause_path), 'review_sha256': sha(ROUND / 'review_batch77.json'),
               'verdict': 'kept', 'original_raw_hashes_unchanged': True, 'readonly_tree_verified': True}
    target = ROOT / 'runs/plan_batches/closed_round_pins' / (ROUND.name + '.json')
    write(target, binding)
    target.chmod(0o444)
    print(json.dumps({'closure_binding': str(target), **binding}))


if __name__ == '__main__':
    main()
