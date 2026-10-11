#!/usr/bin/env python3
"""Prepare isolated, append-only failed-harness closure fixtures from legacy rounds.

Without --close this command only emits a preview.  --close never writes to the
source round; it requires a distinct output root and refuses a still-present
recorded service PID.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROUND_IDS = ('E2-R001', 'E2-R004', 'E2-R005', 'E2-R012', 'E2-R014', 'E2-R015', 'E2-R016')
SERVICE_FILES = ('SERVE_CMD.txt', 'serve.log', 'serve_args.txt', 'ENV.txt')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {'path': path.relative_to(root).as_posix(), 'sha256': sha256(path), 'size_bytes': path.stat().st_size}


def service_dirs(source: Path) -> list[Path]:
    return sorted({path.parent for path in source.rglob('SERVE_CMD.txt')})


def status_failure(source: Path) -> dict[str, Any]:
    statuses = sorted(source.glob('status_batch*.json'))
    if len(statuses) != 1:
        raise ValueError(f'{source.name}: expected exactly one status_batch*.json')
    status = json.loads(statuses[0].read_text(encoding='utf-8'))
    if status.get('rid') != source.name or status.get('state') not in {'failed', 'error'} or not isinstance(status.get('error'), str):
        raise ValueError(f'{source.name}: status record is not an explicit terminal failure record')
    return {'path': statuses[0].name, 'sha256': sha256(statuses[0]), 'size_bytes': statuses[0].stat().st_size, 'error_excerpt': status['error'],
            'terminal_state': status['state'], 'batch': status.get('batch'), 'batch_pid': status.get('batch_pid'), 'updated_at': status.get('updated_at')}


def original_pid(arm: Path) -> int | None:
    owned = arm / 'owned_process.json'
    if owned.is_file():
        data = json.loads(owned.read_text(encoding='utf-8'))
        if type(data.get('pid')) is int and data['pid'] > 0:
            return data['pid']
    args = arm / 'serve_args.txt'
    if args.is_file():
        import re
        found = re.search(r"_unique_suffix='\.pid=([0-9]+)'", args.read_text(encoding='utf-8', errors='replace'))
        if found:
            return int(found.group(1))
    return None


def pid_terminated(pid: int | None) -> bool | None:
    if pid is None:
        return None
    if os.name != 'posix':
        return None
    return not Path('/proc') .joinpath(str(pid)).exists()


def availability_record(source: Path, arm: Path) -> dict[str, Any]:
    paths = {name: arm / name for name in ('SERVE_CMD.txt', 'serve.log', 'ENV.txt')}
    if not all(path.is_file() for path in paths.values()):
        raise ValueError(f'{source.name}/{arm.name}: required R012 provenance files are missing')
    return {
        'schema': 'failed_harness_runtime_args_availability/v1',
        'actual_dump_emitted': False,
        'reason': 'legacy harness failed before a retained runtime serve_args dump was emitted',
        'source_files': {name: file_record(path, source) for name, path in paths.items()},
        'parsed_cmd_provenance': 'SERVE_CMD.txt is retained command provenance only; it is not a captured runtime parsed-arguments record.',
        'not_a_runtime_acceptance': True,
    }


def batch_source(source_root: Path, round_id: str) -> Path:
    candidates = sorted(path for path in source_root.rglob('*') if path.is_file() and round_id.lower() in path.name.lower())
    if len(candidates) != 1:
        raise ValueError(f'{round_id}: expected one batch source, found {len(candidates)}')
    return candidates[0]


def preview_one(source: Path, source_root: Path) -> dict[str, Any]:
    failure = status_failure(source)
    batch = batch_source(source_root, source.name)
    arms = []
    for arm in service_dirs(source):
        missing = [name for name in SERVICE_FILES if not (arm / name).is_file()]
        item = {'arm': arm.relative_to(source).as_posix(), 'service_pid': original_pid(arm),
                'pid_terminated_now': pid_terminated(original_pid(arm)), 'missing_required_files': missing,
                'source_files': {name: file_record(arm / name, source) for name in SERVICE_FILES if (arm / name).is_file()}}
        if missing == ['serve_args.txt']:
            item['availability_record'] = availability_record(source, arm)
        arms.append(item)
    return {
        'round_id': source.name, 'source_round': str(source), 'status_failure': failure,
        'batch_source': {'path': str(batch), 'sha256': sha256(batch), 'size_bytes': batch.stat().st_size},
        'arms': arms,
        'legacy_d04_complete_service_evidence': all(not arm['missing_required_files'] for arm in arms),
        'proposal': 'first snapshot pending_review, then failed_harness verdict; preserve originals and record all copied-source hashes',
    }


def metadata(plan: dict[str, Any]) -> dict[str, Any]:
    incomplete = [arm for arm in plan['arms'] if arm['missing_required_files']]
    serve: Any = {'arms': {arm['arm']: {} for arm in plan['arms']}}
    anomalies = [{
        'kind': 'failed_harness', 'reason': plan['status_failure']['error_excerpt'],
        'evidence': [plan['status_failure']['path']],
    }]
    failure_archive: dict[str, Any] = {}
    if incomplete:
        missing_entries = []
        for arm in incomplete:
            evidence = [
                arm['source_files']['SERVE_CMD.txt'], arm['source_files']['serve.log'],
                {'path': plan['status_failure']['path'], 'sha256': plan['status_failure']['sha256'],
                 'size_bytes': plan['status_failure']['size_bytes']},
            ]
            missing_entries.append({
                'arm': arm['arm'],
                'reason': 'legacy harness failed before a retained runtime serve_args dump was emitted',
                'evidence': evidence,
            })
        failure_archive['missing_serve_args'] = missing_entries
        anomalies.append({'kind': 'runtime_args_missing', 'reason': 'No replacement serve_args.txt is created; failure_archive records the retained command, log, and failure evidence.',
                          'evidence': [entry['path'] for entry in missing_entries[0]['evidence']]})
    return {
        'schema': 'ft_round/v2', 'round_id': plan['round_id'], 'serve': serve,
        'closed_at': None, 'batch_logs': [], 'proposed_verdict': 'failed_harness',
        'verdict': 'pending_review', 'verdict_history': [], 'retractions': [], 'anomalies': anomalies,
        'failure_archive': failure_archive,
        'metadata_provenance': {
            'schema': 'failed_harness_metadata_provenance/v1', 'source_round': plan['source_round'],
            'status_failure': plan['status_failure'], 'batch_source': plan['batch_source'], 'arms': plan['arms'],
            'note': 'All listed source files must retain their pre-copy SHA-256; this metadata is a new closure record, not a rewrite of legacy artifacts.',
        },
    }


def copy_checked(source: Path, destination: Path, source_root: Path) -> dict[str, Any]:
    plan = preview_one(source, source_root)
    target = destination / source.name
    if target.exists():
        raise ValueError(f'{target}: already exists; refusing overwrite')
    target.mkdir(parents=True)
    source_paths = [Path(plan['batch_source']['path']), source / plan['status_failure']['path']]
    for arm_plan in plan['arms']:
        source_paths.extend(source / record['path'] for record in arm_plan['source_files'].values())
    source_before = {str(path): sha256(path) for path in source_paths}
    try:
        batch = Path(plan['batch_source']['path'])
        shutil.copyfile(batch, target / 'batch.sh')
        if sha256(batch) != sha256(target / 'batch.sh'):
            raise ValueError(f'{source.name}: batch.sh copy hash mismatch')
        for arm_plan in plan['arms']:
            source_arm = source / arm_plan['arm']
            target_arm = target / arm_plan['arm']; target_arm.mkdir(parents=True)
            for name in SERVICE_FILES:
                original = source_arm / name
                if original.is_file():
                    copied = target_arm / name
                    shutil.copyfile(original, copied)
                    if sha256(original) != sha256(copied):
                        raise ValueError(f'{source.name}/{name}: source changed or copy mismatch')
            if arm_plan['missing_required_files']:
                (target_arm / 'runtime_args_availability.json').write_text(json.dumps(arm_plan['availability_record'], indent=2) + '\n', encoding='utf-8')
        (target / plan['status_failure']['path']).write_bytes((source / plan['status_failure']['path']).read_bytes())
        (target / 'round.json').write_text(json.dumps(metadata(plan), indent=2) + '\n', encoding='utf-8')
        source_after = {str(path): sha256(path) for path in source_paths}
        if source_after != source_before:
            raise ValueError(f"{source.name}: source artifacts changed during isolated copy")
        return {'plan': plan, 'target': target, 'source_sha256_pre_and_post_equal': True,
                'source_artifact_hashes': source_before}
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise


def close_one(prepared: dict[str, Any], close_script: Path, writer: Path) -> dict[str, Any]:
    plan, target = prepared['plan'], prepared['target']
    living = [arm['service_pid'] for arm in plan['arms'] if arm['pid_terminated_now'] is False]
    if living:
        raise ValueError(f"{plan['round_id']}: refuse close while recorded service PID(s) still exist: {living}")
    root = target.parent
    closed = subprocess.run([sys.executable, str(close_script), plan['round_id'], '--round-root', str(root)], text=True, capture_output=True)
    if closed.returncode:
        raise ValueError(f"{plan['round_id']}: D04 close failed: {closed.stderr.strip()}")
    verdict = subprocess.run([sys.executable, str(writer), str(target), 'verdict', '--new', 'failed_harness',
                              '--reason', plan['status_failure']['error_excerpt'], '--evidence', plan['status_failure']['path'],
                              '--by', 'failed-harness-closure-tool'], text=True, capture_output=True)
    if verdict.returncode:
        raise ValueError(f"{plan['round_id']}: D04 verdict failed: {verdict.stderr.strip()}")
    return {'round_id': plan['round_id'], 'closed': True, 'close_stdout': closed.stdout.strip(), 'verdict_stdout': verdict.stdout.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds-root', type=Path, required=True)
    parser.add_argument('--batch-source-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--close', action='store_true')
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--d04-close-script', type=Path, default=Path(__file__).resolve().parents[1] / 'scripts/round_close.py')
    parser.add_argument('--d04-writer', type=Path, default=Path(__file__).resolve().parents[1] / 'scripts/round_json_append.py')
    args = parser.parse_args()
    plans = [preview_one(args.rounds_root / rid, args.batch_source_root) for rid in ROUND_IDS]
    output: dict[str, Any] = {'schema': 'p0_failed_harness_close_preview/v1', 'mode': 'readonly_preview', 'rounds': plans}
    if args.close:
        if args.output_root is None or args.output_root.resolve() == args.rounds_root.resolve():
            raise SystemExit('--close requires a distinct --output-root')
        if args.output_root.exists():
            raise SystemExit('--output-root must not already exist')
        args.output_root.mkdir(parents=True)
        prepared = [copy_checked(args.rounds_root / rid, args.output_root, args.batch_source_root) for rid in ROUND_IDS]
        output['mode'] = 'isolated_fixture_close'
        output['source_copy_verification'] = [{'round_id': item['plan']['round_id'], 'source_sha256_pre_and_post_equal': item['source_sha256_pre_and_post_equal'], 'source_artifact_hashes': item['source_artifact_hashes']} for item in prepared]
        output['close_results'] = [close_one(item, args.d04_close_script, args.d04_writer) for item in prepared]
    args.out.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
