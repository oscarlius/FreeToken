"""Close the independently reviewed D03 T16 gate using the published D04 tools."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
RID = 'E2-R002-gate-D03'
DIRECTORY = Path('/data2/_shared/runs/ft_rounds') / RID
PREPARER_SHA = '802e5a80f4e05b5fd863289a0a55009afa1059ab72390e77b1fdfb9823c440da'
TOOLS = {
    'round_json_append.py': '88178a9a3c83dec204e90e6dcf8c4db9',
    'round_close.py': '415aa82b34c8fd82d09bfe8a8ce67eed',
    'round_close.sh': '430693122ef66bb5a293fb421ff0f7fc',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_exclusive(path, data, created):
    with path.open('xb') as stream:
        created.append((path, path.stat().st_dev, path.stat().st_ino))
        stream.write(data)


def rollback(directory, created, original_modes):
    # A successful or partially completed seal is evidence. Never undo it here.
    if any((directory / name).exists() for name in ('round_history', 'MANIFEST.sha256')):
        raise RuntimeError('formal closure artifacts retained; inspect the D04 failure before retrying')
    for path, mode, device, inode in original_modes:
        current = path.stat()
        if (current.st_dev, current.st_ino) != (device, inode):
            raise RuntimeError(f'original artifact identity changed; retained: {path}')
        os.chmod(path, mode)
    for path, device, inode in reversed(created):
        if path.is_symlink() or path.parent != directory:
            raise RuntimeError(f'rollback target escaped exact round: {path}')
        if not path.exists():
            continue
        current = path.stat()
        if (current.st_dev, current.st_ino) != (device, inode):
            raise RuntimeError(f'rollback artifact identity changed; retained: {path}')
        os.chmod(path, stat.S_IMODE(current.st_mode) | stat.S_IWUSR)
        path.unlink()


def close(batch, directory=DIRECTORY, root=ROOT):
    directory = directory.resolve(strict=True)
    if directory.name != RID:
        raise ValueError('exact assigned T16 round directory required')
    if any((directory / name).exists() for name in ['round.json', 'round_history', 'MANIFEST.sha256']):
        raise ValueError('existing formal control artifact retained')
    review = directory / f'review_batch{batch}.json'
    preparer_path = root / 'runs/dev_D03/d03_t16_prepare.py'
    if sha(preparer_path) != PREPARER_SHA:
        raise ValueError('reviewed T16 metadata preparer changed')
    spec = importlib.util.spec_from_file_location('d03_t16_prepare', preparer_path)
    preparer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preparer)
    sources = {}
    for name, expected in TOOLS.items():
        source = root / 'scripts' / name
        data = source.read_bytes()
        if hashlib.md5(data).hexdigest() != expected:
            raise ValueError(f'published D04 tool changed: {name}')
        if (directory / name).exists():
            raise FileExistsError(f'existing tool archive retained: {name}')
        sources[name] = data
    if (directory / 'd04_tool_versions.json').exists():
        raise FileExistsError('existing D04 version archive retained')
    if (directory / 'initial_metadata.json').exists():
        raise FileExistsError('existing initial metadata retained')
    # Complete input validation before any writes, including inputs the frozen
    # preparer validates again. Archive the exact tool bytes checked above.
    preparer.assert_owned_tree(directory)
    gate, _ = preparer.validate_gate(directory, batch)
    preparer.validate_status(directory, batch)
    preparer.validate_review(review, batch)
    for arm in gate['arms']:
        preparer.validate_arm(directory, arm)
    wrapper = preparer.require_file(directory / f'batch{batch}.sh').read_bytes()
    if (directory / 'batch.sh').exists() and (directory / 'batch.sh').read_bytes() != wrapper:
        raise ValueError('existing batch.sh differs from actual batch wrapper')
    batch_log = directory.parent / f'batch{batch}.log'
    preparer.require_file(batch_log)
    if batch_log.is_symlink():
        raise ValueError('batch log must not be a symlink')
    batch_log_sha = sha(batch_log)
    original_modes = [(path, stat.S_IMODE(path.stat().st_mode), path.stat().st_dev, path.stat().st_ino)
                      for path in [directory, *directory.rglob('*')]]
    preparer_outputs = [directory / name for name in ('batch.sh', 'initial_metadata.json')
                        if not (directory / name).exists()]
    created = []
    sealed = False
    # T16 has gate=D03 and no measurement admission.json. Its own completed
    # gate preparer validates that schema before the direct D04 closure.
    try:
        try:
            preparer.prepare(directory, batch, review)
        finally:
            # Track even a partial preparer write, so an I/O exception is retryable.
            for path in preparer_outputs:
                if path.exists():
                    created.append((path, path.stat().st_dev, path.stat().st_ino))
        versions = {}
        for name, data in sources.items():
            write_exclusive(directory / name, data, created)
            versions[name] = {'md5': TOOLS[name], 'sha256': hashlib.sha256(data).hexdigest()}
        write_exclusive(directory / 'd04_tool_versions.json',
                        preparer.json_bytes(versions), created)
        metadata = json.loads((directory / 'initial_metadata.json').read_text())
        finish_metadata(metadata, batch, review, batch_log, batch_log_sha)
        write_exclusive(directory / 'round.json', preparer.json_bytes(metadata), created)
        subprocess.run(['bash', str(directory / 'round_close.sh'), RID,
                        '--round-root', str(directory.parent)],
                       env={**os.environ, 'FT_ROUND_PYTHON': sys.executable}, check=True)
        sealed = True
    except BaseException:
        if not sealed:
            rollback(directory, created, original_modes)
        raise
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'check'], check=True)
    for line in (directory / 'MANIFEST.sha256').read_text().splitlines():
        expected, relative = line.split('  ', 1)
        path = (directory / relative).resolve()
        if directory not in path.parents or sha(path) != expected:
            raise ValueError(f'closed T16 manifest mismatch: {relative}')
    if (directory / 'round.json').read_bytes() != (directory / 'round_history/round.v001.json').read_bytes():
        raise ValueError('initial round differs from its history snapshot')
    if any(path.stat().st_mode & 0o222 for path in [directory, *directory.rglob('*')]):
        raise ValueError('D04 closure left writable artifacts')
    result = {
        'rid': RID, 'batch': batch, 'round_sha256': sha(directory / 'round.json'),
        'manifest_sha256': sha(directory / 'MANIFEST.sha256'), 'formal_verdict': 'pending_review',
    }
    print('D03_T16_D04_CLOSED', json.dumps(result), flush=True)
    return result


def finish_metadata(metadata, batch, review, batch_log, batch_log_sha):
    metadata['parent'] = 'E2-R000'
    metadata['executor'] = '01 test executor with independent native verification'
    metadata['base'].update(branch='e2/base',
                            freetoken_file='/data2/FreeToken/wt/e2base/python/freetoken/__init__.py',
                            upstream_base='d3512b4')
    metadata['experimental'].update(branch='exp/e1r003-statetools',
                                    freetoken_file='/data2/FreeToken/wt/e1r003st/python/freetoken/__init__.py')
    metadata['design']['first_shot_policy'] = 'preserved individually; no aggregate performance verdict'
    metadata['sub_conclusions'] = [{
        'id': 'SC1', 'text': 'D03 default output, prefill sequence and transfer counters match the parent',
        'status': 'pending', 'evidence': [f'gate_batch{batch}.json', review.name],
    }]
    metadata['anomalies'] = []
    metadata['closed_at'] = datetime.now(timezone(timedelta(hours=8))).strftime('%F %T CST')
    metadata['batch_logs'] = [{'path': str(batch_log), 'sha256': batch_log_sha}]
    metadata['manifest'] = 'MANIFEST.sha256'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True, type=int)
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    if not args.close or sys.platform != 'linux':
        parser.error('--close and the Linux test host are required')
    close(args.batch)


if __name__ == '__main__':
    main()
