"""One-shot D04 closure of actual R050/batch76; requires independent final R receipt."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
ROUND = Path('/data2/_shared/runs/ft_rounds/E2-R050-gate-D15')
CANDIDATE = '988c9e183c8dca4415fd9b5d02318b26664da619'
PARENT = 'effb9969706922ddad9e59b96377e46469ebe97f'
ARMS = {'PARENT_b76', 'NEW_b76', 'PARENT_P_b76', 'NEW_P_b76'}
TOOLS = {'round_json_append.py': '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff',
         'round_close.py': 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5',
         'round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    require(not Path('/proc/920015').exists(), 'batch76 controller remains')
    require(not Path('/data2/_shared/gpu.lock').exists(), 'GPU batch still owns lock')
    require(not any((ROUND / name).exists() for name in ('round.json', 'round_history', 'MANIFEST.sha256')), 'D04 metadata already exists')
    require(not any(path.is_symlink() for path in (ROUND, *ROUND.rglob('*'))), 'symlink evidence')
    require(args.review.is_file() and not args.review.is_symlink() and not args.review.stat().st_mode & 0o222, 'R final receipt is not read-only')
    require(re.fullmatch('[0-9a-f]{64}', args.review_sha256) and sha(args.review) == args.review_sha256, 'R receipt SHA differs')
    ir = load(args.review)
    gate_path, status_path = ROUND / 'gate_batch76.json', ROUND / 'status_batch76.json'
    gate, status = load(gate_path), load(status_path)
    require(status.get('state') == 'complete_measurements_pending_review' and status.get('batch_pid') == 920015, 'batch76 has no successful terminal status')
    require(gate.get('proposed_verdict') == 'kept' and gate.get('gate') == 'D15' and gate.get('parent_commit') == PARENT and gate.get('new_commit') == CANDIDATE and set(gate.get('arms', [])) == ARMS, 'actual gate matrix differs')
    require(ir.get('schema') == 'ft_r050_independent_raw_review/v1' and ir.get('verdict') == 'PASS' and ir.get('round_id') == ROUND.name and ir.get('batch') == 76 and ir.get('candidate_commit') == CANDIDATE and ir.get('parent_commit') == PARENT and ir.get('gate_sha256') == sha(gate_path), 'final independent R binding differs')
    receipt_path = ROOT / 'runs/dev_T16/launch_E2-R050-gate-D15_batch76.json'
    receipt = load(receipt_path)
    require(receipt.get('state') == 'launched' and receipt.get('rid') == ROUND.name and receipt.get('batch') == 76 and receipt.get('candidate_commit') == CANDIDATE and receipt.get('child', {}).get('execution_id') == '920015:141319876', 'actual launch binding differs')
    log_path = Path(receipt['batch_log'])
    stops = re.findall(r'STOP PASS owned_pid=(\d+) gpu=\d+', log_path.read_text())
    require(len(stops) == 4 and all(not (Path('/proc') / pid).exists() for pid in stops), 'four owned services did not terminate')
    require(sha(receipt['wrapper']) == receipt['wrapper_sha256'] == '9692b7fedc6f7d720af98ab881c9c703300dbf818a86edd87e8b70503a0699fb', 'actual wrapper differs')
    arms = {name: {'files': {leaf: sha(ROUND / name / leaf) for leaf in ('SERVE_CMD.txt', 'ENV.txt', 'serve.log', 'serve_args.txt')}} for name in sorted(ARMS)}
    for name, digest in TOOLS.items():
        require(sha(ROOT / 'scripts' / name) == digest, 'D04 tool changed: ' + name)
    if not args.close:
        print(json.dumps({'state': 'closure_prevalidated', 'round_id': ROUND.name, 'batch': 76}))
        return
    memory = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True)
    require(memory.strip() and all(int(row) < 1000 for row in memory.splitlines()), 'GPU is not idle')
    original = {path.relative_to(ROUND).as_posix(): sha(path) for path in ROUND.rglob('*') if path.is_file()}
    write(ROUND / 'review_batch76.json', args.review.read_bytes())
    write(ROUND / 'launch_receipt.json', receipt_path.read_bytes())
    for name, path in (
        ('startup_review.json', ROOT / 'runs/dev_T16/reviews/E2-R050-gate-D15_startup_review_v5.json'),
        ('file_dry_run_receipt.json', ROOT / 'runs/dev_T16/reviews/E2-R050-gate-D15_file_dry_run_v1.json')):
        require(path.is_file() and not path.stat().st_mode & 0o222, 'startup proof is not frozen: ' + name)
        write(ROUND / name, path.read_bytes())
    write(ROUND / 'close_source/r050_actual_d04_close_20261007.py', Path(__file__).read_bytes())
    for name in TOOLS:
        write(ROUND / name, (ROOT / 'scripts' / name).read_bytes())
    write(ROUND / 'round.json', {
        'schema': 'ft_round/v2', 'round_id': ROUND.name, 'epoch': 2, 'card': 'T16',
        'parent': 'E2-R041-gate-D17', 'base': {'commit': PARENT}, 'experimental': {'candidate_commit': CANDIDATE},
        'serve': {'arms': arms}, 'design': {'batch': 76, 'pause_endpoint': False, 'ordinary_prefill': False},
        'results': ir, 'proposed_verdict': 'kept', 'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
        'independent_review_sha256': sha(args.review), 'batch_logs': [{'path': str(log_path), 'sha256': sha(log_path)}],
        'acceptance_limits': ['D15 four-arm T16 cold gate only; production baseline remains 0aa23431.', 'TTFT and throughput are recorded, not acceptance thresholds.'],
        'diagnostics': {'original_raw_files': original, 'launch_receipt_sha256': sha(receipt_path)}})
    subprocess.run([sys.executable, str(ROUND / 'round_close.py'), ROUND.name, '--round-root', str(ROUND.parent)], check=True)
    subprocess.run([sys.executable, str(ROUND / 'round_json_append.py'), str(ROUND), 'verdict', '--new', 'kept',
                    '--reason', 'Independent R recomputed four-arm T16 cold full text, business sequence, D0 per-segment transfer and launch/input bindings: PASS.',
                    '--evidence', 'gate_batch76.json', 'review_batch76.json', 'launch_receipt.json', 'startup_review.json', 'file_dry_run_receipt.json',
                    '--by', 'root authorized D04 closure'], check=True)
    subprocess.run([sys.executable, str(ROUND / 'round_json_append.py'), str(ROUND), 'check'], check=True)
    require(all(sha(ROUND / name) == digest for name, digest in original.items()), 'original raw bytes changed')
    for line in (ROUND / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ./', 1)
        require(sha(ROUND / name) == digest, 'manifest payload differs: ' + name)
    require(all(not path.stat().st_mode & 0o222 for path in (ROUND, *ROUND.rglob('*'))), 'sealed round remains writable')
    binding = {'rid': ROUND.name, 'batch': 76, 'parent_commit': PARENT, 'candidate_commit': CANDIDATE,
               'round_sha256': sha(ROUND / 'round.json'), 'manifest_sha256': sha(ROUND / 'MANIFEST.sha256'),
               'gate_sha256': sha(gate_path), 'review_sha256': sha(ROUND / 'review_batch76.json'),
               'verdict': 'kept', 'original_raw_hashes_unchanged': True, 'readonly_tree_verified': True}
    target = ROOT / 'runs/plan_batches/closed_round_pins' / (ROUND.name + '.json')
    write(target, binding)
    target.chmod(0o444)
    print(json.dumps({'closure_binding': str(target), **binding}))


if __name__ == '__main__':
    main()
