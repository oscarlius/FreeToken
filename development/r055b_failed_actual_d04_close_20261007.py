"""Seal actual R055b/batch79 HTTP-504 harness failure in place."""
import argparse
from pathlib import Path
import subprocess
import sys

import r055b_actual_d04_close_20261007 as base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    r, root, require, sha = base.ROUND, base.ROOT, base.require, base.sha
    require(sha(Path(base.__file__)) == 'd0a74e82d0dfd877e38368886f3d252eb9924c88eca0c6bc13b9011ffad12beb',
            'actual closure dependency changed')
    require(not Path('/proc/1489092').exists() and not Path('/data2/_shared/gpu.lock').exists(),
            'owned batch or GPU lock remains')
    require(not any((r / name).exists() for name in ('round.json', 'round_history', 'MANIFEST.sha256')),
            'round already sealed')
    require(not any(p.is_symlink() for p in (r, *r.rglob('*'))), 'symlink raw evidence')
    require(args.review.is_file() and not args.review.is_symlink() and
            not args.review.stat().st_mode & 0o222 and sha(args.review) == args.review_sha256,
            'failed review not frozen or bound')
    review = base.load(args.review)
    failure = base.load(r / 'failed_harness.json')
    require(failure.get('schema') == 'ft_r055_failed_harness/v1' and failure.get('rid') == r.name and
            failure.get('batch') == 79 and failure.get('owned_cleanup_failed') is False and
            failure.get('error') == "<HTTPError 504: 'Gateway Timeout'>", 'actual first failure differs')
    expected = {'schema': 'ft_r055b_failed_independent_raw_review/v1', 'round_id': r.name,
                'batch': 79, 'candidate_commit': base.CANDIDATE, 'parent_commit': base.PARENT,
                'verdict': 'failed_harness', 'failed_harness_sha256': sha(r / 'failed_harness.json'),
                'pause_log_sha256': sha(r / 'PAUSE_ON/serve.log'), 'pause_chain_complete': False,
                'controller_gone': True, 'owned_group_gone': True, 'lock_released': True}
    require(all(review.get(key) == value for key, value in expected.items()),
            'independent failure binding differs')
    require(review.get('cuda_memory_summary', {}).get('complete') is False,
            'incomplete CUDA evidence must stay incomplete')
    require(not (r / 'pause_gate.json').exists() and not (r / 'gate_batch79.json').exists() and
            not (r / 'PAUSE_ON/pause_cancel.json').exists() and
            not (r / 'PAUSE_ON/after_cancel.json').exists(), 'failed chain unexpectedly has later results')
    owned = base.load(r / 'PAUSE_ON/owned_process.json')
    require(owned.get('pid') == 1489104 and owned.get('birth', {}).get('start_ticks') == 142358090 and
            not Path('/proc/1489104').exists() and not Path('/proc/1489323').exists(),
            'owned service or GPU worker remains')
    receipt_path = root / 'runs/dev_R055/launch_E2-R055b-gate-D06_batch79.json'
    receipt = base.load(receipt_path)
    require(receipt.get('rid') == r.name and receipt.get('batch') == 79 and
            receipt.get('child', {}).get('execution_id') == base.EXECUTION_ID and
            sha(receipt['wrapper']) == receipt['wrapper_sha256'] ==
            '39757c295f0471c064f5553800d11e6cefa2ac4de52d28a8fcd2d6261412f469',
            'actual launch identity differs')
    arms = {'PAUSE_ON': {'files': {leaf: sha(r / 'PAUSE_ON' / leaf) for leaf in
                                  ('SERVE_CMD.txt', 'ENV.txt', 'serve.log', 'serve_args.txt')}}}
    for name, digest in base.TOOLS.items():
        require(sha(root / 'scripts' / name) == digest, 'D04 tool changed: ' + name)
    if not args.close:
        print('R055b failed_harness closure prevalidated')
        return
    used = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used',
                                    '--format=csv,noheader,nounits'], text=True)
    require(used.strip() and all(int(row) < 1000 for row in used.splitlines()), 'GPU is not idle')
    original = {p.relative_to(r).as_posix(): sha(p) for p in r.rglob('*') if p.is_file()}
    base.write(r / 'review_batch79.json', args.review.read_bytes())
    base.write(r / 'launch_receipt.json', receipt_path.read_bytes())
    for name, path in (
        ('startup_review.json', root / 'runs/dev_R055/reviews/E2-R055b-gate-D06_startup_review_v3.json'),
        ('file_dry_run_receipt.json', r.parent / '.dryrun_R055b_E2-R055b-gate-D06/dry_run_receipt.json'),
        ('default_code_path_basis.json', root / 'runs/dev_D06/r055_eff_code_path_basis_r_overlap_v2/review.json'),
    ):
        require(not path.stat().st_mode & 0o222, 'startup proof is writable: ' + name)
        base.write(r / name, path.read_bytes())
    for source in (Path(__file__), Path(base.__file__)):
        base.write(r / 'close_source' / source.name, source.read_bytes())
    for name in base.TOOLS:
        base.write(r / name, (root / 'scripts' / name).read_bytes())
    log = Path(receipt['batch_log'])
    base.write(r / 'round.json', {
        'schema': 'ft_round/v2', 'round_id': r.name, 'epoch': 2, 'card': 'T16',
        'parent': 'E2-R055a-gate-D06', 'base': {'commit': base.PARENT},
        'experimental': {'candidate_commit': base.CANDIDATE}, 'serve': {'arms': arms},
        'design': {'batch': 79, 'cold_arms_replayed': False, 'pause_complete': False, 'route_trace': False},
        'results': review, 'proposed_verdict': 'failed_harness', 'verdict': 'pending_review',
        'verdict_history': [], 'retractions': [], 'independent_review_sha256': sha(args.review),
        'batch_logs': [{'path': str(log), 'sha256': sha(log)}],
        'acceptance_limits': ['R055a six accepted cold arms remain retained; old failed verdict unchanged.',
                              'Pause/cancel/recovery incomplete; second pause HTTP504 escaped client parsing.',
                              'Request-before CUDA sample is missing; partial margin cannot admit T06.',
                              'Production remains 0aa23431; next GPU batch requires user disposition.'],
        'diagnostics': {'original_raw_files': original,
                        'first_failure': 'second POST /dev/pause HTTP504 raised in urllib before parsing',
                        'raw_status_is_stale': True, 'launch_receipt_sha256': sha(receipt_path)},
    })
    subprocess.run([sys.executable, str(r / 'round_close.py'), r.name,
                    '--round-root', str(r.parent)], check=True)
    subprocess.run([sys.executable, str(r / 'round_json_append.py'), str(r), 'verdict', '--new',
                    'failed_harness', '--reason',
                    'Second pause/cancel HTTP504 was not parsed by the harness; recovery was not executed. '
                    'CUDA request-before sample is missing. Independent partial evidence retained; user decision required.',
                    '--evidence', 'failed_harness.json', 'review_batch79.json', 'PAUSE_ON/serve.log',
                    '--by', 'root authorized failed D04 closure'], check=True)
    subprocess.run([sys.executable, str(r / 'round_json_append.py'), str(r), 'check'], check=True)
    require(all(sha(r / name) == digest for name, digest in original.items()), 'original raw bytes changed')
    for line in (r / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ./', 1)
        require(sha(r / name) == digest, 'manifest differs: ' + name)
    require(all(not p.stat().st_mode & 0o222 for p in (r, *r.rglob('*'))), 'closed tree remains writable')
    binding = {'rid': r.name, 'batch': 79, 'candidate_commit': base.CANDIDATE,
               'round_sha256': sha(r / 'round.json'), 'manifest_sha256': sha(r / 'MANIFEST.sha256'),
               'review_sha256': sha(r / 'review_batch79.json'), 'verdict': 'failed_harness',
               'original_raw_hashes_unchanged': True, 'readonly_tree_verified': True}
    target = root / 'runs/plan_batches/closed_round_pins' / (r.name + '.json')
    base.write(target, binding)
    target.chmod(0o444)
    print(__import__('json').dumps({'closure_binding': str(target), **binding}))


if __name__ == '__main__':
    main()
