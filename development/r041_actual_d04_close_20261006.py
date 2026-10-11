"""Canonical D04 closure for the actual R041 cold/four-warm candidate gate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
ROUND = Path('/data2/_shared/runs/ft_rounds/E2-R041-gate-D17')
CANDIDATE = '0aa23431e5b800797543bdecbf35a01045131d7d'
CONTROL = 'a9dca443cd07e1f60d1533e0a678935a09d21636'
PARENT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
SAMPLE4 = {'prefix-8192-tail-65', 'prefix-12416-tail-4097',
           'prefix-12736-tail-8193', 'prefix-18944-tail-4097'}
TOOLS = {'round_json_append.py': '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff',
         'round_close.py': 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5',
         'round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    # Check actual controller termination before reading a completed result or
    # querying GPU state. A status file alone cannot establish termination.
    require(not Path('/proc/3105554').exists(), 'actual R041 controller is still present')
    require(not Path('/data2/_shared/gpu.lock').exists(), 'another GPU owner remains')
    require(not any((ROUND / name).exists() for name in ('round.json', 'round_history', 'MANIFEST.sha256')),
            'round already has D04 metadata; do not repeat this one-shot writer')
    require(not any(path.is_symlink() for path in (ROUND, *ROUND.rglob('*'))), 'symlink evidence')
    review = args.review
    require(review.is_file() and not review.is_symlink() and not review.stat().st_mode & 0o222,
            'independent review must be a sealed regular file')
    require(re.fullmatch('[0-9a-f]{64}', args.review_sha256) is not None
            and sha(review) == args.review_sha256, 'caller-pinned independent review differs')
    ir = load(review)
    raw = load(ROUND / 'result.json')
    status = load(ROUND / 'status_batch68.json')
    receipt_path = ROOT / 'runs/dev_D17/launch_E2-R041-gate-D17.json'
    require(sha(receipt_path) == '607bd365dfd3d98e5babd515c5c382fbeab63b63b34bdde2723ef128d2a02e6d',
            'actual launch receipt changed')
    receipt = load(receipt_path)
    require(receipt['batch_pid'] == 3105554 and receipt['batch_start_ticks'] == 137322467,
            'actual controller birth differs')
    require(status.get('state') == 'complete_measurements_pending_review'
            and status.get('batch_pid') == 3105554, 'R041 has no complete terminal status')
    require(raw.get('schema') == 'ft_d17_r041/v1' and raw.get('candidate_commit') == CANDIDATE
            and raw.get('control_commit') == CONTROL and raw.get('rid') == ROUND.name
            and raw.get('verdict') == 'measurements_pass_pending_independent_review'
            and raw.get('cold', {}).get('passed') is True and set(raw.get('cases', {})) == SAMPLE4,
            'actual R041 measurement matrix differs')
    require(ir.get('schema') == 'ft_d17_r041_independent_audit/v1'
            and ir.get('verdict') == 'kept_pending_independent_review'
            and ir.get('rid') == ROUND.name and ir.get('batch') == 68
            and ir.get('candidate_commit') == CANDIDATE and ir.get('control_commit') == CONTROL
            and ir.get('result_sha256') == sha(ROUND / 'result.json')
            and set(ir.get('cases', {})) == SAMPLE4, 'independent R041 raw recomputation differs')
    log_path = Path(receipt['batch_log'])
    stops = re.findall(r'STOP PASS owned_pid=(\d+) gpu=\d+', log_path.read_text())
    arms = {path.name: {'files': {name: sha(path / name) for name in
            ('SERVE_CMD.txt', 'ENV.txt', 'serve.log', 'serve_args.txt', 'compiled_extensions.json')}}
            for path in ROUND.iterdir() if path.is_dir() and (path / 'SERVE_CMD.txt').is_file()}
    require(len(arms) == len(stops) == 10 and all(not (Path('/proc') / pid).exists() for pid in stops),
            'actual ten owned services have not terminated')
    for name, digest in TOOLS.items():
        require(sha(ROOT / 'scripts' / name) == digest, 'canonical D04 tool changed: ' + name)
    if not args.close:
        print(json.dumps({'state': 'closure_prevalidated', 'model_admitted': False}))
        return
    memory = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True)
    require(memory.strip() and all(int(row) < 1000 for row in memory.splitlines()), 'GPU is not idle')
    original = {path.relative_to(ROUND).as_posix(): sha(path) for path in ROUND.rglob('*') if path.is_file()}
    write(ROUND / 'review_batch68.json', review.read_bytes())
    write(ROUND / 'close_source/r041_actual_d04_close_20261006.py', Path(__file__).read_bytes())
    for name in TOOLS:
        write(ROUND / name, (ROOT / 'scripts' / name).read_bytes())
    metadata = {'schema': 'ft_round/v2', 'round_id': ROUND.name, 'epoch': 2, 'card': 'T16',
                'parent': 'E2-R038', 'base': {'commit': PARENT}, 'experimental': {'candidate_commit': CANDIDATE},
                'serve': {'arms': arms}, 'design': {'batch': 68, 'warm_control_commit': CONTROL, 'warm_cases': sorted(SAMPLE4)},
                'results': ir, 'proposed_verdict': 'kept', 'verdict': 'pending_review', 'verdict_history': [],
                'retractions': [], 'independent_review_sha256': sha(review),
                'batch_logs': [{'path': str(log_path), 'sha256': sha(log_path)}],
                'acceptance_limits': ['D17 cold default and four warm continuation pairs only; T20 remains pending.'],
                'diagnostics': {'original_raw_files': original, 'launch_receipt_sha256': sha(receipt_path)}}
    write(ROUND / 'round.json', encoded(metadata))
    subprocess.run([sys.executable, str(ROUND / 'round_close.py'), ROUND.name, '--round-root', str(ROUND.parent)], check=True)
    subprocess.run([sys.executable, str(ROUND / 'round_json_append.py'), str(ROUND), 'verdict', '--new', 'kept',
                    '--reason', 'PLAN section 8.3: independent raw cold comparison and four D14/D17 warm pairs bitwise PASS.',
                    '--evidence', 'result.json', 'gate_batch68.json', 'review_batch68.json', 'launch_receipt.json',
                    '--by', 'root authorized D04 closure'], check=True)
    subprocess.run([sys.executable, str(ROUND / 'round_json_append.py'), str(ROUND), 'check'], check=True)
    require(all(sha(ROUND / name) == digest for name, digest in original.items()), 'original raw bytes changed')
    for line in (ROUND / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ./', 1)
        require(sha(ROUND / name) == digest, 'manifest payload differs: ' + name)
    require(all(not path.stat().st_mode & 0o222 for path in (ROUND, *ROUND.rglob('*'))), 'round remains writable')
    binding = {'round': ROUND.name, 'batch': 68, 'parent_commit': PARENT, 'candidate_commit': CANDIDATE,
               'round_sha256': sha(ROUND / 'round.json'), 'gate_sha256': sha(ROUND / 'gate_batch68.json'),
               'review_sha256': sha(ROUND / 'review_batch68.json'), 'manifest_sha256': sha(ROUND / 'MANIFEST.sha256'),
               'verdict': 'kept', 'original_raw_files_verified': len(original), 'readonly_tree_verified': True,
               'manifest_payload_hashes_verified': True, 'original_raw_hashes_unchanged': True}
    target = ROOT / 'runs/dev_D17/r041_d04_closure_20261006/closure_binding.json'
    write(target, encoded(binding))
    target.chmod(0o444)
    target.parent.chmod(0o555)
    print(json.dumps({'closure_binding': str(target), 'closure_sha256': sha(target), **binding}))


if __name__ == '__main__':
    main()
