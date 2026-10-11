#!/usr/bin/env python3
"""R044b retry1 executable wrapper over the byte-pinned predecessor.

It changes only retry1 identity wiring, strict ServerArgs normalization, and
telemetry shutdown.  The retained six-service/144-call implementation remains
loaded from the immutable predecessor copy.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
RID = 'E2-R044b-retry2-20261010'
FROZEN = HERE / 'frozen' / 'run_r044b_actual.py'
FROZEN_SHA256 = 'ff58d4c77dcee19f95b60e07b020ca4170cf7d2b5c4980d35b479ff2da46734b'
PARSER = HERE / 'r044b_retry2_parser.py'
TELEMETRY = HERE / 'r044b_retry2_telemetry.py'
OLD = ROOT / 'development/r044_capture_path_retry2_20261010'
READER = OLD / 'd04_original/serve_args_diff.py'
LEAF = Path('/data2/_shared/experiment_harness/evidence.py')
ADMISSION = HERE / 'ROOT_ADMISSION_R044B.json'
REVIEW_DIR = ROOT / 'runs/dev_T10/reviews' / RID
FILE_DRY_SCHEMA = 'ft_r044b_retry2_file_dry/v1'


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_bindings() -> dict[str, str]:
    paths = (Path(__file__).resolve(), FROZEN, PARSER, TELEMETRY, OLD / 'r044_prepare_v6.py', OLD / 'queue_authorization.py', READER, LEAF)
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f'retry1 source unavailable or symlinked: {path}')
    if sha(FROZEN) != FROZEN_SHA256:
        raise RuntimeError('retry1 immutable predecessor source SHA differs')
    return {str(path): sha(path) for path in paths}


def filedry() -> dict[str, Any]:
    return {
        'schema': FILE_DRY_SCHEMA,
        'rid': RID,
        'bindings': source_bindings(),
        'protocol': {'services_exact': 6, 'replay_calls_exact': 144, 'per_service_replays_exact': 24, 'first_not_met_stop': 'B1/B2 after strict identity'},
        'negative_caps': {'total_wall_s': 5400, 'work_window_s': 5250, 'cleanup_reserve_s': 150, 'generation_phase_s': 1500},
        'side_effects': False,
    }


def _copy_verified(source: Path, target: Path) -> dict[str, Any]:
    shutil.copyfile(source, target)
    target.chmod(0o600)
    with target.open('ab') as handle:
        handle.flush(); os.fsync(handle.fileno())
    if sha(source) != sha(target):
        raise RuntimeError(f'retry1 runtime source copy differs: {source.name}')
    return {'source': str(source), 'copy': str(target), 'sha256': sha(target), 'mode': oct(target.stat().st_mode & 0o777)}


def _serve_identity(legacy, arm: Path, layer_major: bool) -> dict[str, Any]:
    parser = _load(PARSER, 'r044b_retry2_parser_runtime')
    value = parser.serve_identity(arm / 'serve.log', arm / 'owned_process.json', layer_major, legacy.ARGS_READER)
    return {'parsed': value['raw_parsed'], 'normalized': value['normalized'], 'serve_log_sha256': value['serve_log_sha256'], 'owned_process': value['owned_process'], 'alias': value['alias']}


def _child_argv(legacy, batch: int, receipt: Path, wt: Path, output_root: Path) -> list[str]:
    return [str(legacy.VENV / 'bin/python'), str(Path(__file__).resolve()), '--run', '--owned-child', '--batch', str(batch), '--launch-receipt', str(receipt), '--worktree', str(wt), '--output-root', str(output_root)]


def _copy_runtime_sources(legacy, frozen, original):
    def copy_runtime_sources(target: Path):
        rows = original(target)
        retry_rows = []
        for source in (Path(__file__).resolve(), FROZEN, PARSER, TELEMETRY, LEAF):
            retry_rows.append(_copy_verified(source, target / source.name))
        frozen.write_new(target / 'retry1_source_manifest.json', {'schema': 'ft_r044b_retry2_runtime_sources/v1', 'rid': RID, 'predecessor_sha256': FROZEN_SHA256, 'retry1_sources': retry_rows})
        return rows + retry_rows
    return copy_runtime_sources


def _pre_popen_marker(frozen, output_root: Path, error: BaseException, start_attempted: bool) -> None:
    run = Path(output_root) / RID
    if start_attempted or not run.is_dir() or (run / 'pre_popen_failed.json').exists():
        return
    frozen.write_new(run / 'pre_popen_failed.json', {'schema': 'ft_r044b_retry2_pre_popen/v1', 'rid': RID, 'classification': 'pre_gpu_failed', 'services_started': 0, 'replay_calls': 0, 'retry_budget_debited': False, 'error': repr(error), 'at': datetime.now().astimezone().isoformat()})


def _owned_child(frozen, legacy, wt: Path, output_root: Path, batch: int, receipt: Path, **kwargs):
    successful_service_processes = 0
    original_popen = legacy.subprocess.Popen
    capture_name = Path(legacy.CAPTURE_STARTUP).name
    def watched_popen(argv, *args, **inner):
        nonlocal successful_service_processes
        is_service = any(Path(str(part)).name == capture_name for part in argv)
        process = original_popen(argv, *args, **inner)
        if is_service:
            successful_service_processes += 1
        return process
    legacy.subprocess.Popen = watched_popen
    try:
        return frozen.execute_owned_child(legacy, wt, output_root, batch, receipt, **kwargs)
    except BaseException as exc:
        _pre_popen_marker(frozen, output_root, exc, successful_service_processes != 0)
        raise
    finally:
        legacy.subprocess.Popen = original_popen

def configure(legacy_loader=None):
    frozen = _load(FROZEN, 'r044b_retry2_frozen')
    telemetry = _load(TELEMETRY, 'r044b_retry2_telemetry_runtime')
    frozen.ROOT = ROOT; frozen.PACKET = HERE; frozen.OLD = OLD; frozen.READER = READER; frozen.LEAF = LEAF; frozen.RID = RID
    frozen.serve_identity = _serve_identity
    frozen.child_argv = _child_argv
    frozen.OwnedTelemetry = telemetry.retry1_telemetry_class(frozen.OwnedTelemetry)
    legacy = (legacy_loader or frozen.load_legacy)()
    legacy = frozen.configure(legacy)
    original_copy = legacy.copy_runtime_sources
    legacy.copy_runtime_sources = _copy_runtime_sources(legacy, frozen, original_copy)
    return frozen, legacy



def require_file_dry_receipt(path: Path, dry: dict[str, Any]) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError('retry1 file-dry receipt is absent, mutable, or symlinked')
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schema') != FILE_DRY_SCHEMA or value.get('rid') != RID or value.get('bindings') != dry['bindings']:
        raise RuntimeError('retry1 file-dry receipt identity/source differs')
    proof = value.get('file_dry', {})
    if proof.get('services_materialized') != 6 or any(proof.get(key) is not False for key in ('service_started', 'requests_sent', 'gpu_lock_taken')):
        raise RuntimeError('retry1 file-dry receipt service coverage/effect differs')
    return {'path': str(path), 'sha256': sha(path)}


def _read_admission(dry: dict[str, Any]) -> dict[str, Any]:
    if ADMISSION.is_symlink() or not ADMISSION.is_file():
        raise RuntimeError('retry1 root admission is absent')
    value = json.loads(ADMISSION.read_text(encoding='utf-8'))
    if value.get('rid') != RID or value.get('bindings') != dry['bindings']:
        raise RuntimeError('retry1 root admission source binding differs')
    receipt = require_file_dry_receipt(Path(value.get('file_dry_receipt', '')), dry)
    if value.get('file_dry_receipt_sha256') != receipt['sha256']:
        raise RuntimeError('retry1 root admission file-dry SHA differs')
    return value


def run(*, owned_child=False, batch=None, launch_receipt=None, worktree=None, output_root=None, legacy_loader=None, clock=None, telemetry_factory=None):
    if os.environ.get('R044B_RETRY1_ROOT_AUTHORIZED') != '1':
        raise RuntimeError('root must set R044B_RETRY1_ROOT_AUTHORIZED=1 for --run')
    dry = filedry(); _read_admission(dry)
    frozen, legacy = configure(legacy_loader)
    wt = Path(worktree) if worktree is not None else legacy.WT
    out = Path(output_root) if output_root is not None else legacy.ROUNDS
    if not owned_child:
        os.environ['R044B_ROOT_AUTHORIZED'] = '1'
        try:
            result = legacy.execute(wt, out, owned_child=False, batch=batch, launch_receipt=launch_receipt)
        finally:
            os.environ.pop('R044B_ROOT_AUTHORIZED', None)
        return frozen.validate_controller_receipt(result)
    if batch is None or launch_receipt is None:
        raise RuntimeError('retry1 owned child requires controller receipt and reserved batch')
    options = {'telemetry_factory': frozen.OwnedTelemetry}
    if clock is not None: options['clock'] = clock
    if telemetry_factory is not None: options['telemetry_factory'] = telemetry_factory
    result = _owned_child(frozen, legacy, wt, out, batch, Path(launch_receipt), **options)
    gate = frozen.evaluate_raw_measurement(result)
    result['r044b_product_gate'] = gate
    frozen.write_new(out / RID / 'r044b_product_gate.json', {'schema': 'ft_r044b_product_gate/v1', 'rid': RID, 'raw_result_sha256': legacy.sha(out / RID / 'result.json'), **gate})
    return result


def file_dry_run(directory: Path, *, legacy_loader=None) -> dict[str, Any]:
    """Materialize all six service plans without Popen, lock, GPU, or HTTP."""
    frozen, legacy = configure(legacy_loader)
    directory = Path(directory)
    if directory.exists() or not directory.name.startswith('.dryrun_R044b_retry1_') or directory.parent != legacy.ROUNDS:
        raise RuntimeError('retry1 file-dry directory must be fresh canonical .dryrun_R044b_retry1_<source-hash>')
    directory.mkdir(mode=0o700)
    copies = legacy.copy_runtime_sources(directory / 'source')
    d = legacy.load_d07(); planned = []
    for mode, layer_major in legacy.MODES.items():
        for arm in legacy.ARMS:
            arm_dir = directory / mode / arm; arm_dir.mkdir(parents=True)
            pair = legacy.port_pair(); frozen.write_new(arm_dir / 'port_pair.json', pair)
            prepared = legacy.start_mode(d, arm_dir, legacy.WT, pair['api'], arm_dir / 'route', layer_major, directory / 'source' / legacy.CAPTURE_STARTUP.name, file_dry=True)
            planned.append({'mode': mode, 'arm': arm, 'service': prepared})
    value = {**filedry(), 'side_effects': False, 'file_dry': {'services_materialized': len(planned), 'service_started': False, 'requests_sent': False, 'gpu_lock_taken': False, 'source_copies': copies, 'services': planned}}
    frozen.write_new(directory / 'dry_run_receipt.json', value)
    (directory / 'dry_run_receipt.json').chmod(0o444)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true'); parser.add_argument('--file-dry-run', type=Path); parser.add_argument('--owned-child', action='store_true'); parser.add_argument('--batch', type=int); parser.add_argument('--launch-receipt', type=Path); parser.add_argument('--worktree', type=Path); parser.add_argument('--output-root', type=Path)
    args = parser.parse_args(argv)
    if args.file_dry_run:
        if args.run or args.owned_child or args.batch is not None or args.launch_receipt is not None: parser.error('--file-dry-run cannot mix launch arguments')
        print(json.dumps(file_dry_run(args.file_dry_run), ensure_ascii=False, indent=2)); return
    if not args.run: print(json.dumps(filedry(), ensure_ascii=False, indent=2)); return
    print(json.dumps(run(owned_child=args.owned_child, batch=args.batch, launch_receipt=args.launch_receipt, worktree=args.worktree, output_root=args.output_root), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()





