"""Seal actual R055a/batch77 OOM failure in place, retaining six cold arms."""
import argparse
from pathlib import Path
import subprocess
import sys

import r055a_actual_d04_close_20261007 as base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    r, root, require, sha = base.ROUND, base.ROOT, base.require, base.sha
    require(sha(Path(base.__file__)) == 'ec0a78874f0c50f9aefec11e61740f1f2cab3716083a7979620a4145c12886d8',
            'actual closure source changed')
    require(not Path('/proc/1030535').exists() and not Path('/data2/_shared/gpu.lock').exists(),
            'batch/controller lock still active')
    require(not any((r / name).exists() for name in ('round.json', 'round_history', 'MANIFEST.sha256')),
            'round already sealed')
    require(not any(p.is_symlink() for p in (r, *r.rglob('*'))), 'symlink raw evidence')
    require(args.review.is_file() and not args.review.is_symlink() and
            not args.review.stat().st_mode & 0o222 and sha(args.review) == args.review_sha256,
            'independent failed review not frozen/bound')
    review = base.load(args.review)
    failure = base.load(r / 'failed_harness.json')
    gate = base.load(r / 'gate_batch77.json')
    require(failure.get('schema') == 'ft_r055_failed_harness/v1' and failure.get('rid') == r.name and
            failure.get('batch') == 77 and failure.get('owned_cleanup_failed') is False,
            'actual terminal failure identity/cleanup differs')
    require(set(gate.get('arms', [])) == base.ARMS and gate.get('new_commit') == base.CANDIDATE and
            gate.get('parent_commit') == base.PARENT, 'six completed cold arms differ')
    expected = {'schema': 'ft_r055a_failed_raw_review/v1', 'round_id': r.name, 'batch': 77,
                'candidate_commit': base.CANDIDATE, 'parent_commit': base.PARENT,
                'verdict': 'failed_harness', 'gate_sha256': sha(r / 'gate_batch77.json'),
                'failed_harness_sha256': sha(r / 'failed_harness.json'),
                'pause_log_sha256': sha(r / 'PAUSE_ON/serve.log'), 'pause_chain_complete': False,
                'controller_gone': True, 'owned_group_gone': True, 'lock_released': True}
    require(all(review.get(k) == v for k, v in expected.items()) and
            set(review.get('completed_arms', [])) == base.ARMS and
            isinstance(review.get('cold_checks'), dict) and review['cold_checks'] and
            all(v is True for v in review['cold_checks'].values()), 'independent partial/failure binding differs')
    require(not (r / 'pause_gate.json').exists() and
            'torch.OutOfMemoryError' in (r / 'PAUSE_ON/serve.log').read_text(errors='replace'),
            'first OOM failure evidence missing')
    cleanup = base.load(r / 'owned_failure_cleanup_complete.json')
    require(cleanup.get('owned_group_gone') is True and cleanup.get('gpu_lock_manually_modified') is False and
            cleanup.get('service_pid') == 1133393 and cleanup.get('start_ticks') == 141715678 and
            not Path('/proc/1133393').exists(), 'owned failed-service cleanup incomplete')
    receipt_path = root / 'runs/dev_R055/launch_E2-R055a-gate-D06_batch77.json'
    receipt = base.load(receipt_path)
    require(receipt.get('child', {}).get('execution_id') == '1030535:141527703' and
            receipt.get('batch') == 77 and receipt.get('rid') == r.name and
            sha(receipt['wrapper']) == receipt['wrapper_sha256'] ==
            'ab5ba217aeab0c231fd793c7d88e311e3598615d9f1398273b26cf9b5a822376',
            'actual launch wrapper/identity differs')
    arms = {name: {'files': {leaf: sha(r / name / leaf) for leaf in
                            ('SERVE_CMD.txt', 'ENV.txt', 'serve.log', 'serve_args.txt')}}
            for name in sorted(base.ARMS | {'PAUSE_ON'})}
    for name, digest in base.TOOLS.items():
        require(sha(root / 'scripts' / name) == digest, 'D04 tool changed: ' + name)
    if not args.close:
        print('R055a failed_harness closure prevalidated')
        return
    used = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used',
                                    '--format=csv,noheader,nounits'], text=True)
    require(used.strip() and all(int(row) < 1000 for row in used.splitlines()), 'GPU is not idle')
    original = {p.relative_to(r).as_posix(): sha(p) for p in r.rglob('*') if p.is_file()}
    base.write(r / 'review_batch77.json', args.review.read_bytes())
    base.write(r / 'launch_receipt.json', receipt_path.read_bytes())
    for name, path in (
        ('startup_review.json', root / 'runs/dev_R055/reviews/E2-R055a-gate-D06_startup_review_v3.json'),
        ('file_dry_run_receipt.json', r.parent / '.dryrun_R055a_E2-R055a-gate-D06/dry_run_receipt.json'),
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
        'parent': 'E2-R050-gate-D15', 'base': {'commit': base.PARENT},
        'experimental': {'candidate_commit': base.CANDIDATE}, 'serve': {'arms': arms},
        'design': {'batch': 77, 'cold_completed_arms': 6, 'pause_complete': False},
        'results': review, 'proposed_verdict': 'failed_harness', 'verdict': 'pending_review',
        'verdict_history': [], 'retractions': [], 'independent_review_sha256': sha(args.review),
        'batch_logs': [{'path': str(log), 'sha256': sha(log)}],
        'acceptance_limits': ['Six reviewed cold arms retained; the complete D06 gate is not kept.',
                              'Pause/cancel/recovery is incomplete after actual service OOM.',
                              'Production remains 0aa23431; no later GPU round may start without user decision.'],
        'diagnostics': {'original_raw_files': original, 'first_failure': 'PAUSE_ON GDN conv prefill CUDA OOM',
                        'launch_receipt_sha256': sha(receipt_path)},
    })
    subprocess.run([sys.executable, str(r / 'round_close.py'), r.name,
                    '--round-root', str(r.parent)], check=True)
    subprocess.run([sys.executable, str(r / 'round_json_append.py'), str(r), 'verdict', '--new',
                    'failed_harness', '--reason',
                    'Six cold arms independently pass; PAUSE_ON 32K prefill failed with CUDA OOM '
                    '(628 MiB request / 625.69 MiB free). Pause/cancel/recovery incomplete; user disposition required.',
                    '--evidence', 'failed_harness.json', 'gate_batch77.json', 'review_batch77.json',
                    'PAUSE_ON/serve.log', 'owned_failure_cleanup_complete.json',
                    '--by', 'root authorized failed D04 closure'], check=True)
    subprocess.run([sys.executable, str(r / 'round_json_append.py'), str(r), 'check'], check=True)
    require(all(sha(r / name) == digest for name, digest in original.items()), 'original raw bytes changed')
    for line in (r / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ./', 1)
        require(sha(r / name) == digest, 'manifest differs: ' + name)
    require(all(not p.stat().st_mode & 0o222 for p in (r, *r.rglob('*'))), 'closed tree remains writable')
    binding = {'rid': r.name, 'batch': 77, 'candidate_commit': base.CANDIDATE,
               'round_sha256': sha(r / 'round.json'), 'manifest_sha256': sha(r / 'MANIFEST.sha256'),
               'gate_sha256': sha(r / 'gate_batch77.json'), 'review_sha256': sha(r / 'review_batch77.json'),
               'verdict': 'failed_harness', 'original_raw_hashes_unchanged': True, 'readonly_tree_verified': True}
    target = root / 'runs/plan_batches/closed_round_pins' / (r.name + '.json')
    base.write(target, binding)
    target.chmod(0o444)
    print(__import__('json').dumps({'closure_binding': str(target), **binding}))


if __name__ == '__main__':
    main()
