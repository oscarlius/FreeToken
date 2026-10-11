#!/usr/bin/env python3
"""Freeze and execute the CPU-only T04 f506/Y129 verification package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import time

CORE_PINS = {
    't04_f506_y129_runner.py': '311a0becb129bc25e3ada81281107ff892d4286b274c8e3a1cffe10ca9b4950b',
    't04_capture_controlled.py': '14b1eb09a9a49ba4c46176ca3edc5d52b927a07f4c476ae55c1d144c979c50fb',
    'tests/test_t04_f506_y129.py': '4d7e3fd703f864af9328dca110bbf744eb5eb526f137074f6093e7af8ef80705',
    'tests/test_t04_capture_controlled.py': '040fe9376cbfffd8e8c07ba02b6df00b5d374d15b7a24c50ee7103d642a7cda2',
    't04_f506_y129_README.md': 'e3fb3198cca7d1a8f80c28ce79fa428c85a83e4d95d2dfec85333be7ae569eb5',
}
FROZEN_PINS = {
    'd03_gpu_selfcheck_f506.py': '96db3ca98bf40a629342586061b5d0acd21d1fb4e1c47fb8bef0e9b8ea56715b',
    'd03_gpu_selfcheck.py': '4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453',
    'e2d03/scripts/logits_probe.py': '7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7',
}
PINS = {**CORE_PINS, **FROZEN_PINS}



def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(root: Path, pins: dict[str, str] = PINS) -> dict[str, object]:
    actual = {name: digest(root / name) for name in pins}
    if actual != pins:
        raise RuntimeError(f'whitelist source pin mismatch: {actual}')
    return {'schema': 't04_y129_cpu_source/v1', 'pins': actual, 'gpu_started': False}


def build(args: argparse.Namespace) -> None:
    root = args.source.resolve()
    source_value = manifest(root, CORE_PINS)
    stage = args.archive.parent / 't04_y129_311a0bec_payload'
    if stage.exists():
        raise FileExistsError(f'local package staging already exists: {stage}')
    stage.mkdir()
    try:
        for name in CORE_PINS | {'d03_gpu_selfcheck_f506.py': '', 'd03_gpu_selfcheck.py': ''}:
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root / name).read_bytes())
        probe = subprocess.check_output(['git', '-C', str(root / 'e2d03-continuation'), 'cat-file', 'blob', 'HEAD:scripts/logits_probe.py'])
        target = stage / 'e2d03/scripts/logits_probe.py'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(probe)
        value = manifest(stage)
        (stage / 'SOURCE_MANIFEST.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
        with tarfile.open(args.archive, 'x:gz') as archive:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(stage).as_posix(), recursive=False)
    finally:
        for path in sorted(stage.rglob('*'), reverse=True):
            if path.is_file(): path.unlink()
            elif path.is_dir(): path.rmdir()
        stage.rmdir()
    args.manifest.write_text(json.dumps({**value, 'archive_sha256': digest(args.archive), 'core_source': source_value}, indent=2) + '\n', encoding='utf-8')


def extract_checked(archive_path: Path, stage: Path) -> None:
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        wanted = set(PINS) | {'SOURCE_MANIFEST.json'}
        if names != wanted or any(member.isdir() or member.issym() or PurePosixPath(member.name).is_absolute() or '..' in PurePosixPath(member.name).parts for member in members):
            raise RuntimeError('archive members differ from CPU whitelist')
        archive.extractall(stage, members=members, filter='data')
    value = manifest(stage)
    saved = json.loads((stage / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    if saved.get('pins') != value['pins']:
        raise RuntimeError('extracted source manifest differs from source bytes')


def run_logged(command: list[str], cwd: Path, log: Path) -> dict[str, object]:
    started = time.time()
    with log.open('x', encoding='utf-8') as handle:
        completed = subprocess.run(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, env={**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4', 'PYTHONDONTWRITEBYTECODE': '1'}, check=False)
    return {'command': command, 'returncode': completed.returncode, 'seconds': time.time() - started, 'log_sha256': digest(log)}


def remote(args: argparse.Namespace) -> int:
    stage = args.stage.resolve()
    if stage.exists():
        raise FileExistsError(f'remote staging must be exclusive: {stage}')
    stage.mkdir(parents=True)
    report: dict[str, object] = {'schema': 't04_y129_cpu_report/v1', 'stage': str(stage), 'gpu_started': False}
    try:
        extract_checked(args.archive, stage)
        report['source'] = manifest(stage)
        py = args.python
        report['pytest'] = run_logged([py, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests/test_t04_f506_y129.py', 'tests/test_t04_capture_controlled.py'], stage, stage / 'pytest.log')
        report['self_test'] = run_logged([py, 't04_f506_y129_runner.py', '--self-test'], stage, stage / 'selftest.log')
        report['success'] = report['pytest']['returncode'] == 0 and report['self_test']['returncode'] == 0
        return 0 if report['success'] else 1
    except BaseException as exc:
        report['success'] = False
        report['error'] = repr(exc)
        return 1
    finally:
        report_path = stage / 'CPU_REPORT.json'
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        for path in stage.rglob('*'):
            if path.is_file(): path.chmod(0o444)
        stage.chmod(0o555)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--build', action='store_true')
    mode.add_argument('--remote-stage', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--python', default='/data2/FreeToken/venv/bin/python')
    args = parser.parse_args()
    if args.build:
        if args.source is None or args.manifest is None: parser.error('--build requires --source and --manifest')
        build(args); return 0
    if args.stage is None: parser.error('--remote-stage requires --stage')
    return remote(args)

if __name__ == '__main__':
    raise SystemExit(main())
