#!/usr/bin/env python3
"""Inert, carrier-preserving closure for the completed D15 Window A/B run; never starts or stops a service."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/data2/FreeToken')
RID = 'E2-D15-WINDOW-AB-20261010'
DEST = Path('/data2/_shared/runs/ft_rounds') / RID
PIN = ROOT / 'runs/plan_batches/closed_round_pins' / f'{RID}.json'
ORIGINAL = ROOT / 'runs/d15_window_ab/20261010_221156'
RESUME = ROOT / 'runs/d15_window_ab/20261010_222649_resume'
EXPECTED_REVIEW_SHA256 = '7468d001c90c4a9f6cab16721f6fa67dbdaa4e81be1ba13ed916d04f2c7f687e'
ROUND_CLOSE = ROOT / 'scripts/round_close.py'
ROUND_APPEND = ROOT / 'scripts/round_json_append.py'
ROUND_CLOSE_SHA256 = 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5'
ROUND_APPEND_SHA256 = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
ADMISSION_ORIGINAL = ROOT / 'development/d15_window_ab_20261010/ROOT_GPU_ADMISSION_PATHFIX.json'
ADMISSION_RESUME = ROOT / 'development/d15_window_ab_20261010/ROOT_GPU_ADMISSION_RESUME.json'
LAUNCH_ORIGINAL = ROOT / 'development/d15_window_ab_20261010/ROOT_GPU_LAUNCH_PATHFIX.json'
LAUNCH_RESUME = ROOT / 'development/d15_window_ab_20261010/ROOT_GPU_LAUNCH_RESUME.json'
RECOVERY = ROOT / 'development/d15_window_ab_20261010/ROOT_OWNED_CLEANUP_RECOVERY_221156.json'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f'expected regular file: {path}')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise RuntimeError(f'expected JSON object: {path}')
    return value


def put(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write('\n')


def tree_hashes(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir() or any(item.is_symlink() for item in root.rglob('*')):
        raise RuntimeError(f'raw tree is missing, non-regular, or contains a symlink: {root}')
    return {str(item.relative_to(root)): sha(item) for item in root.rglob('*') if item.is_file()}


def validate(review_path: Path) -> tuple[dict, dict, dict]:
    if review_path.is_symlink() or not review_path.is_file() or review_path.stat().st_mode & 0o222:
        raise RuntimeError('independent review must be a read-only regular file')
    if sha(review_path) != EXPECTED_REVIEW_SHA256:
        raise RuntimeError('independent review SHA differs')
    review = read(review_path)
    if (review.get('schema') != 'd15_window_ab_independent_terminal_review/v1'
            or review.get('formal_verdict') != 'not_met'
            or review.get('recommendation') != 'CLOSE_NOT_MET'
            or review.get('product_acceptance') is not False
            or review.get('production_activated') is not False):
        raise RuntimeError('independent review conclusion differs')
    raw = review.get('raw_artifact_sha256')
    if not isinstance(raw, dict) or raw.get('original') != tree_hashes(ORIGINAL) or raw.get('resume') != tree_hashes(RESUME):
        raise RuntimeError('raw artifact inventory differs from independent review')
    original, resume = read(ORIGINAL/'failure.json'), read(RESUME/'failure.json')
    if original.get('verdict') != 'failed_harness' or resume.get('verdict') != 'not_met':
        raise RuntimeError('raw failure carriers differ')
    budget = review.get('budget_accounting', {})
    if (budget.get('actual_services'), budget.get('generation_dispatched'), budget.get('generation_completed'), budget.get('limit_generation_calls')) != (2, 21, 20, 21):
        raise RuntimeError('review budget accounting differs')
    if review.get('a8_identity', {}).get('all_equal') is not True:
        raise RuntimeError('A8 native identity proof differs')
    slots = review.get('slots', {})
    if slots.get('W98K', {}).get('actual_slots') != 2700 or slots.get('W128K', {}).get('actual_slots') != 2400:
        raise RuntimeError('actual slot evidence differs')
    comparison = review.get('comparison', {})
    if abs(comparison.get('decline_pct', 0) - 4.200859186214345) > 1e-12:
        raise RuntimeError('A/B decline evidence differs')
    cold = review.get('cold', {})
    if '129024' not in str(cold.get('cpu_frontend_recheck', {})) or 'OutOfMemoryError' not in str(cold.get('oom', '')):
        raise RuntimeError('cold OOM evidence differs')
    cleanup = review.get('cleanup', {})
    if not (cleanup.get('resume_group_dead') is True and cleanup.get('resume_ports_free') is True and cleanup.get('resume_gpu_idle_at_cleanup') is True and cleanup.get('resume_stop_errors_preserved') == []):
        raise RuntimeError('historical cleanup evidence differs')
    if sha(RECOVERY) != cleanup.get('original_recovery_sha256') or sha(RESUME/'cleanup_receipt.json') != cleanup.get('resume_cleanup_sha256'):
        raise RuntimeError('cleanup artifact binding differs')
    for tool, digest in ((ROUND_CLOSE, ROUND_CLOSE_SHA256), (ROUND_APPEND, ROUND_APPEND_SHA256)):
        if tool.is_symlink() or sha(tool) != digest:
            raise RuntimeError('formal closure tool pin differs')
    for path, digest in ((ADMISSION_ORIGINAL, review['identity']['admission_sha256']), (LAUNCH_ORIGINAL, review['identity']['launch_sha256'])):
        if path.is_symlink() or sha(path) != digest:
            raise RuntimeError('original admission/launch binding differs')
    return review, original, resume


def write_arm(dest: Path, name: str, source: Path) -> dict:
    arm = dest / name
    arm.mkdir()
    os.link(source/'serve.log', arm/'serve.log')
    # The raw runs retained no per-service argv or environment dump.  Preserve that absence rather than fabricate one.
    (arm/'SERVE_CMD.txt').write_text('No raw per-service command dump was retained. This closure annotation is not a reconstructed command. See raw/%s/owned_process.json and closure_evidence launch receipts.\n' % ('original' if name == 'W98K' else 'resume'), encoding='utf-8')
    (arm/'serve_args.txt').write_text('No raw per-service argv dump was retained; no argv is reconstructed.\n', encoding='utf-8')
    (arm/'ENV.txt').write_text('No raw per-service environment dump was retained; this is not a live environment readback and no environment is reconstructed.\n', encoding='utf-8')
    return {'raw_source': str(source.relative_to(ORIGINAL.parent.parent.parent)), 'owned_process_sha256': sha(source/'owned_process.json'), 'command_environment_status': 'raw per-service argv/env absent; absence explicitly preserved'}


def execute(review_path: Path) -> None:
    if DEST.exists() or PIN.exists() or (ORIGINAL/'round.json').exists() or (RESUME/'round.json').exists():
        raise RuntimeError('destination/pin exists or a raw carrier was modified')
    review, original_failure, resume_failure = validate(review_path)
    if os.stat(ORIGINAL).st_dev != os.stat(DEST.parent).st_dev:
        raise RuntimeError('raw and formal round roots must share a filesystem for hardlink archive')
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ORIGINAL, DEST/'raw'/'original', copy_function=os.link)
    shutil.copytree(RESUME, DEST/'raw'/'resume', copy_function=os.link)
    evidence = DEST/'closure_evidence'; evidence.mkdir()
    for source, name in ((review_path, 'independent_review.json'), (ADMISSION_ORIGINAL, 'admission_original.json'), (ADMISSION_RESUME, 'admission_resume.json'), (LAUNCH_ORIGINAL, 'launch_original.json'), (LAUNCH_RESUME, 'launch_resume.json'), (RECOVERY, 'original_cleanup_recovery.json'), (Path(__file__), 'close_window_ab.py')):
        shutil.copyfile(source, evidence/name)
    (DEST/'batch.sh').write_text('# Archived controller launch declarations; never execute. Values below are copied from sealed launch receipts and are not service argv/env readback.\n' + json.dumps({'original': read(LAUNCH_ORIGINAL).get('argv'), 'resume': read(LAUNCH_RESUME).get('argv')}, indent=2) + '\n', encoding='utf-8')
    arms = {'W98K': write_arm(DEST, 'W98K', ORIGINAL/'W98K'), 'W128K': write_arm(DEST, 'W128K', RESUME/'W128K')}
    put(DEST/'round.json', {
        'schema': 'ft_round/v2', 'round_id': RID, 'card': 'D15-WINDOW-AB', 'experimental': {'candidate_commit': review['identity']['candidate_commit']},
        'verdict': 'pending_review', 'proposed_verdict': 'not_met', 'verdict_history': [], 'retractions': [],
        'original_carriers': {'original_failure_verdict': original_failure['verdict'], 'resume_failure_verdict': resume_failure['verdict'], 'resume_oom_serve_sha256': review['carrier_preservation']['resume_failure']['oom_serve_sha256']},
        'actual_services': 2, 'actual_generation_dispatched': 21, 'actual_generation_completed': 20, 'generation_call_limit': 21,
        'product_acceptance': False, 'production_activated': False, 'gate_acceptance': None,
        'serve': {'arms': arms}, 'independent_review_sha256': sha(review_path),
        'raw_binding': {'original': {'path': 'raw/original', 'files': review['raw_artifact_sha256']['original']}, 'resume': {'path': 'raw/resume', 'files': review['raw_artifact_sha256']['resume']}},
        'measurement_summary': {'a8_all_native_equal': True, 'actual_slots': {'W98K': 2700, 'W128K': 2400}, 'pooled_decode_decline_pct': 4.200859186214345, 'cold': {'prompt_tokens': 129024, 'outcome': 'model CUDA OOM', 'no_ttft_claim': True}},
        'cleanup_scope': 'Historical window cleanup is bound to raw resume cleanup and independent review. Current production GPU/lock state is deliberately not queried or interpreted.',
        'conclusion_scope': 'Carrier-preserving not_met archive: cold request reached model CUDA OOM. This closure does not claim production activation or alter source.'})
    subprocess.run([str(ROOT/'venv/bin/python'), str(ROUND_CLOSE), RID, '--round-root', str(DEST.parent)], check=True)
    subprocess.run([str(ROOT/'venv/bin/python'), str(ROUND_APPEND), str(DEST), 'verdict', '--new', 'not_met', '--reason', 'Independent terminal review binds raw resume CUDA OOM; original failed_harness carrier preserved.', '--evidence', 'closure_evidence/independent_review.json', 'raw/resume/failure.json', 'raw/resume/W128K/serve.log', '--by', 'root'], check=True)
    subprocess.run([str(ROOT/'venv/bin/python'), str(ROUND_APPEND), str(DEST), 'check'], check=True)
    if PIN.exists() or PIN.is_symlink():
        raise RuntimeError('closed-round pin already exists')
    put(PIN, {'rid': RID, 'round_sha256': sha(DEST/'round.json'), 'manifest_sha256': sha(DEST/'MANIFEST.sha256')})
    PIN.chmod(0o444)
    print(json.dumps({'rid': RID, 'verdict': 'not_met', 'round_sha256': sha(DEST/'round.json'), 'manifest_sha256': sha(DEST/'MANIFEST.sha256'), 'pin_sha256': sha(PIN)}, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--independent-review', type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode': 'inert', 'rid': RID, 'requires': 'read-only independent terminal review and exact raw artifact hashes'}))
    elif args.independent_review is None:
        parser.error('--execute requires --independent-review')
    else:
        execute(args.independent_review)
