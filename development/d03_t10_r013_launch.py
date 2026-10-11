#!/usr/bin/env python3
"""Launch T10 stage two from the sealed R017 engine-token parent."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
DEV = ROOT / 'runs/dev_D03'
RID = 'E2-R013'
PARENT_RID = 'E2-R017'
CANDIDATE = 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
PARENT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
RUNNER = Path(__file__).with_name('t10_r013_from_r017.py')
PREPARER = Path(__file__).with_name('d03_phase2_prepare_r017.py')
LIFECYCLE = DEV / 'd03_phase2_launch.py'
PROBE = Path(__file__).with_name('logits_probe.py')
ATOMIC = ROOT / 'runs/plan_batches/e2_launch.py'
LIFECYCLE_SHA = '6c403cc8ea2c8719c22c8a6be86de23ad266d138d31e5af63fcb02dcb2a588fe'
ATOMIC_SHA = 'a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf'

# Root supplies these after reviewing the exact staged payload.  Until then a
# --run invocation is inert and cannot reserve a batch or start a service.
FROZEN_BUNDLE: dict[str, str] | None = {
    't10_r013_from_r017.py': 'd231fe011f57babb5c9d8d82bb3e175d95b5ee287e355004219eee9ccf92f49f',
    'd03_phase2_prepare_r017.py': 'a52e39e95cf002aa3909b860ff084ff7c85f3d91261d1c75baa9e74a38671581',
    'logits_probe.py': '7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pinned(path: Path, expected: str, name: str) -> ModuleType:
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != expected:
        raise ValueError(f'frozen source changed: {path.name}')
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ''
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def verify_sources() -> tuple[ModuleType, ModuleType]:
    if FROZEN_BUNDLE is None:
        raise RuntimeError('TODO: root must freeze FROZEN_BUNDLE before --run')
    required = {
        't10_r013_from_r017.py': RUNNER,
        'd03_phase2_prepare_r017.py': PREPARER,
        'logits_probe.py': PROBE,
    }
    if set(FROZEN_BUNDLE) != set(required):
        raise ValueError('frozen R013 bundle has the wrong source set')
    for name, path in required.items():
        if not path.is_file() or sha(path) != FROZEN_BUNDLE[name]:
            raise ValueError(f'frozen R013 source changed: {name}')
    for path, expected in ((LIFECYCLE, LIFECYCLE_SHA), (ATOMIC, ATOMIC_SHA)):
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f'frozen launch dependency changed: {path.name}')
    if any(path.is_symlink() or path.stat().st_mode & 0o222 for path in (RUNNER, PREPARER, PROBE, RUNNER.parent)):
        raise ValueError('R013 runner bundle must be frozen read-only')
    return (
        load_pinned(LIFECYCLE, LIFECYCLE_SHA, 'r013_lifecycle'),
        load_pinned(ATOMIC, ATOMIC_SHA, 'r013_atomic'),
    )


def arguments(batch: int) -> list[str]:
    parent = ROUNDS / PARENT_RID
    return [
        '--batch', str(batch), '--candidate-commit', CANDIDATE,
        '--phase1-manifest', str(parent / 'phase1_manifest.json'),
        '--phase1-round-json', str(parent / 'round.json'),
    ]


def preflight(batch: int) -> tuple[ModuleType, list[dict]]:
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '0':
        raise ValueError('CUDA_VISIBLE_DEVICES must be exactly 0')
    if (ROUNDS / RID).exists() or (DEV / f'launch_{RID}.json').exists():
        raise FileExistsError('R013 round or launch receipt already exists')
    if FROZEN_BUNDLE is None:
        raise RuntimeError('TODO: root must freeze FROZEN_BUNDLE before --run')
    runner = load_pinned(RUNNER, FROZEN_BUNDLE['t10_r013_from_r017.py'], 'r013_runner')
    argv = arguments(batch)
    ns = argparse.Namespace(
        batch=batch,
        candidate_commit=CANDIDATE,
        phase1_manifest=Path(argv[argv.index('--phase1-manifest') + 1]),
        phase1_round_json=Path(argv[argv.index('--phase1-round-json') + 1]),
    )
    run = runner.Run(ns)
    root, manifest, _proof = run.sealed_phase1()
    if root != (ROUNDS / PARENT_RID).resolve() or manifest.get('rid') != PARENT_RID:
        raise ValueError('sealed parent identity mismatch')
    forks = run.recompute_forks(root, manifest)
    runner.self_test()
    if forks:
        run.gate()
    return runner, forks


def _write_exclusive(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def publish_receipt(path: Path, identity: tuple[int, int], value: dict) -> None:
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    try:
        _write_exclusive(temporary, value)
        current = path.stat()
        if path.is_symlink() or (current.st_dev, current.st_ino) != identity:
            raise ValueError('exclusive launch receipt identity changed')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def launch() -> dict:
    if sys.platform != 'linux':
        raise ValueError('R013 launch requires Linux')
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '0':
        raise ValueError('CUDA_VISIBLE_DEVICES must be exactly 0')
    lifecycle, atomic = verify_sources()
    prerequisite = lifecycle.prerequisite()
    batch = atomic.next_batch(ROUNDS)
    runner, forks = preflight(batch)
    if not forks:
        proof = {
            'rid': RID,
            'parent_rid': PARENT_RID,
            'state': 'not_applicable_no_actual_fork',
            'phase1_manifest_sha256': sha(ROUNDS / PARENT_RID / 'phase1_manifest.json'),
            'runner_sha256': sha(RUNNER),
            'gpu_started': False,
        }
        _write_exclusive(DEV / 't10_r013_no_fork.json', proof)
        return proof
    if atomic.next_batch(ROUNDS) != batch:
        raise ValueError('batch ledger changed during preflight')
    receipt_path = DEV / f'launch_{RID}.json'
    phase_root = ROUNDS / PARENT_RID
    phase_manifest = phase_root / 'phase1_manifest.json'
    phase_round = phase_root / 'round.json'
    reserved = {
        'rid': RID, 'parent_rid': PARENT_RID, 'card': 'T10-P2', 'batch': batch,
        'state': 'reserved', 'runner_sha256': sha(RUNNER),
        'runner': str(RUNNER),
        'phase1_manifest': str(phase_manifest),
        'phase1_manifest_sha256': sha(phase_manifest),
        'phase1_round_json': str(phase_round),
        'phase1_round_json_sha256': sha(phase_round),
        'cuda_visible_devices': os.environ['CUDA_VISIBLE_DEVICES'],
    }
    _write_exclusive(receipt_path, reserved)
    stat = receipt_path.stat()
    try:
        process, wrapper, log = atomic.reserve_and_launch(
            batch, RID, [str(ROOT / 'venv/bin/python'), '-u', str(RUNNER), '--run', *arguments(batch)]
        )
    except BaseException as exc:
        publish_receipt(receipt_path, (stat.st_dev, stat.st_ino), {**reserved, 'state': 'launch_failed', 'error': repr(exc)})
        raise
    receipt = {
        **reserved, 'state': 'launched', 'batch_pid': process.pid, 'pgid': process.pid,
        'launcher_sha256': sha(Path(__file__)), 'wrapper': str(wrapper),
        'wrapper_sha256': sha(wrapper), 'batch_log': str(log), 'parent_commit': PARENT,
        'candidate_commit': CANDIDATE, 'atomic_launcher_sha256': ATOMIC_SHA,
        'prerequisite_round': str(prerequisite),
        'prerequisite_round_sha256': sha(prerequisite / 'round.json'),
    }
    publish_receipt(receipt_path, (stat.st_dev, stat.st_ino), receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run or sys.platform != 'linux':
        parser.error('--run on Linux required')
    print(json.dumps(launch(), ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
