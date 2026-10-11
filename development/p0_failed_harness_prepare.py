#!/usr/bin/env python3
"""Read-only failed-harness evidence inventory for legacy E2 rounds."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROUND_IDS = ('E2-R001', 'E2-R004', 'E2-R005', 'E2-R012', 'E2-R014', 'E2-R015', 'E2-R016')
REVIEWED_D04_WRITER_SHA256 = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
D04_REQUIRED_ROOT = ('round.json', 'round_history', 'MANIFEST.sha256')
SERVICE_REQUIRED = ('SERVE_CMD.txt', 'serve.log', 'serve_args.txt', 'ENV.txt')
EVIDENCE_NAMES = {
    'batch.sh', 'admission.json', 'RUN_MANIFEST.sha256', 'error.json',
    't04_phase2_error.json', 'status_batch28.json', 'status_batch32.json',
    'status_batch33.json', 'status_batch39.json', 'status_batch41.json',
    'status_batch42.json', 'status_batch43.json', 'owned_process.json',
}
PID_PATTERN = re.compile(r'\b(?:PID|PGID|pid|pgid)\s*[:=]\s*([0-9]+)')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path: Path, root: Path) -> dict[str, Any]:
    return {
        'path': path.relative_to(root).as_posix(),
        'size_bytes': path.stat().st_size,
        'sha256': sha256(path),
    }


def selected_files(round_dir: Path) -> list[Path]:
    selected: set[Path] = set()
    for path in round_dir.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        name = path.name
        if (name in EVIDENCE_NAMES or name in SERVICE_REQUIRED or name.endswith('.py')
                or name.endswith('.log') or name.endswith('_hashes.json')
                or name in {'compiled_extensions.json', 'raw_binding_manifest.json',
                            'terminal_tokens.json', 'tool_hashes.json'}):
            selected.add(path)
    return sorted(selected)


def first_lines(path: Path, limit: int = 8) -> list[str]:
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    lines = []
    for line in text.splitlines():
        if any(token in line for token in ('PID', 'PGID', 'pid', 'pgid', 'Parsed arguments:',
                                            'CUDA_VISIBLE_DEVICES', 'commit', 'worktree',
                                            'freetoken.__file__', 'ERROR', 'Error', 'error')):
            lines.append(line[:500])
        if len(lines) >= limit:
            break
    return lines


def batch_logs(rounds_root: Path, round_id: str) -> list[Path]:
    return sorted(path for path in rounds_root.glob('batch*.log')
                  if round_id in path.read_text(encoding='utf-8', errors='replace'))


def source_candidates(batch_source_root: Path, round_id: str) -> list[Path]:
    if not batch_source_root.is_dir():
        return []
    return sorted(path for path in batch_source_root.rglob('*')
                  if path.is_file() and round_id.lower() in path.name.lower())


def runtime_identity(directory: Path) -> dict[str, Any]:
    env_path = directory / 'ENV.txt'
    cmd_path = directory / 'SERVE_CMD.txt'
    args_path = directory / 'serve_args.txt'
    identity: dict[str, Any] = {
        'freetoken_path': None, 'worktree': None, 'commit': None,
        'service_pid': None, 'service_pgid': None, 'service_session': None,
        'command_pythonpath': None,
    }
    if env_path.is_file():
        lines = env_path.read_text(encoding='utf-8', errors='replace').splitlines()
        for line in lines:
            if '/python/freetoken/__init__.py' in line:
                identity['freetoken_path'] = line.split()[0]
                identity['worktree'] = identity['freetoken_path'].removesuffix('/python/freetoken/__init__.py')
            match = re.search(r'\b([0-9a-f]{40})\b', line)
            if match:
                identity['commit'] = match.group(1)
                break
    if cmd_path.is_file():
        match = re.search(r'PYTHONPATH=([^\s]+)', cmd_path.read_text(encoding='utf-8', errors='replace'))
        if match:
            identity['command_pythonpath'] = match.group(1)
    owned_path = directory / 'owned_process.json'
    if owned_path.is_file():
        try:
            owned = json.loads(owned_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            owned = {}
        for source, target in (('pid', 'service_pid'), ('pgid', 'service_pgid'), ('session', 'service_session')):
            if type(owned.get(source)) is int and owned[source] > 0:
                identity[target] = owned[source]
    if identity['service_pid'] is None and args_path.is_file():
        match = re.search(r"_unique_suffix='\.pid=([0-9]+)'", args_path.read_text(encoding='utf-8', errors='replace'))
        if match:
            identity['service_pid'] = int(match.group(1))
    return identity


def service_inventory(round_dir: Path) -> list[dict[str, Any]]:
    arms: list[dict[str, Any]] = []
    for directory in sorted({path.parent for path in round_dir.rglob('SERVE_CMD.txt')}):
        files = {name: directory / name for name in SERVICE_REQUIRED}
        entry: dict[str, Any] = {
            'arm_path': directory.relative_to(round_dir).as_posix(),
            'required_files': {name: record(path, round_dir) if path.is_file() else None
                               for name, path in files.items()},
            'missing_required_files': [name for name, path in files.items() if not path.is_file()],
        }
        owned = directory / 'owned_process.json'
        entry['owned_process'] = record(owned, round_dir) if owned.is_file() else None
        entry['runtime_identity'] = runtime_identity(directory)
        evidence: list[str] = []
        for path in (files['ENV.txt'], files['serve.log'], files['SERVE_CMD.txt'], files['serve_args.txt'], owned):
            if path.is_file():
                evidence.extend(first_lines(path))
        entry['launch_evidence_lines'] = evidence[:16]
        arms.append(entry)
    return arms


def inspect_round(rounds_root: Path, source_root: Path, round_id: str) -> dict[str, Any]:
    round_dir = rounds_root / round_id
    if not round_dir.is_dir() or round_dir.is_symlink():
        return {'round_id': round_id, 'directory_exists': False,
                'closure_status': 'gap: canonical failure directory is absent'}
    all_files = selected_files(round_dir)
    required_missing = [name for name in D04_REQUIRED_ROOT if not (round_dir / name).exists()]
    batch = batch_logs(rounds_root, round_id)
    source = source_candidates(source_root, round_id)
    failures = [path for path in all_files if path.name in {'error.json', 't04_phase2_error.json'}]
    return {
        'round_id': round_id,
        'canonical_round_dir': str(round_dir),
        'directory_exists': True,
        'd04_required_root_missing': required_missing,
        'd04_append_eligible': not required_missing,
        'closure_status': ('proposal_only: missing canonical D04 first-snapshot inputs'
                           if required_missing else 'unexpectedly D04-append eligible; manual review required'),
        'original_evidence_files': [record(path, round_dir) for path in all_files],
        'failure_evidence': [record(path, round_dir) for path in failures],
        'batch_logs': [record(path, rounds_root) for path in batch],
        'batch_source_candidates': [
            {'path': str(path), 'size_bytes': path.stat().st_size, 'sha256': sha256(path)}
            for path in source
        ],
        'service_start_evidence': service_inventory(round_dir),
        'recovery_source': {
            'metadata_basis': 'new failed-harness metadata must cite only the listed original evidence files and batch sources',
            'missing_d04_service_files': 'each service arm lists missing_required_files; absent evidence must remain a gap, not serve:none',
        },
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        '# Failed-harness closure preparation (proposal only)', '',
        'This is a read-only inventory. It does not mutate a server round, manufacture a `serve:none` declaration, or issue a D04 append.', '',
        f"Canonical root: `{data['rounds_root']}`. Reviewed local D04 writer prerequisite: `{data['reviewed_d04_writer_sha256']}`; observed writer input: `{data['observed_d04_writer_sha256']}` (match: `{data['d04_writer_matches_reviewed']}`).", '',
        '| round | D04 root files missing | service arms found | batch logs | closure proposal |',
        '|---|---|---:|---:|---|',
    ]
    for item in data['rounds']:
        missing = ', '.join(item.get('d04_required_root_missing', [])) or 'none'
        lines.append(f"| {item['round_id']} | {missing} | {len(item.get('service_start_evidence', []))} | {len(item.get('batch_logs', []))} | {item['closure_status']} |")
    for item in data['rounds']:
        lines.extend(['', f"## {item['round_id']}", ''])
        lines.append('Original evidence (path, SHA-256) is listed in the JSON companion; no file is copied or changed.')
        if item.get('failure_evidence'):
            lines.append('Failure evidence: ' + ', '.join(f"`{x['path']}` ({x['sha256']})" for x in item['failure_evidence']) + '.')
        else:
            lines.append('Failure evidence: no named error JSON was found; interpret retained logs only after independent review.')
        if item.get('batch_logs'):
            lines.append('Batch log: ' + ', '.join(f"`{x['path']}` ({x['sha256']})" for x in item['batch_logs']) + '.')
        else:
            lines.append('Batch log: no root `batch*.log` containing this round ID was found by this read-only scan.')
        if item.get('batch_source_candidates'):
            lines.append('Batch-source candidates: ' + ', '.join(f"`{x['path']}` ({x['sha256']})" for x in item['batch_source_candidates']) + '.')
        else:
            lines.append('Batch-source candidates: none found by round-ID filename search; recover only from a cited batch log or retained `batch.sh`.')
        for arm in item.get('service_start_evidence', []):
            missing = arm['missing_required_files']
            identity = arm['runtime_identity']
            lines.append(
                f"Service arm `{arm['arm_path']}`: PID `{identity['service_pid']}`, "
                f"worktree `{identity['worktree']}`, commit `{identity['commit']}`; "
                f"missing D04 service files: {', '.join(missing) if missing else 'none'}."
            )
        lines.append('Required closure action: create separate metadata from this evidence, preserve every original artifact, then validate the new object in an isolated D04 fixture before any leader-owned canonical action.')
    lines.extend(['', '## Boundary', '', 'A service may be described only where the retained command/log/arguments/environment evidence is present. Missing evidence remains a gap; this proposal does not infer service state or causal failure from absence.', ''])
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds-root', type=Path, required=True)
    parser.add_argument('--batch-source-root', type=Path, required=True)
    parser.add_argument('--d04-writer', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reviewed-d04-writer-sha256', default=REVIEWED_D04_WRITER_SHA256)
    parser.add_argument('--markdown-out', type=Path)
    args = parser.parse_args()
    if not args.d04_writer.is_file():
        raise SystemExit(f'missing D04 writer: {args.d04_writer}')
    data = {
        'schema': 'p0_failed_harness_closure_proposal/v1',
        'mode': 'read_only_inventory_no_remote_mutation',
        'rounds_root': str(args.rounds_root),
        'reviewed_d04_writer_sha256': args.reviewed_d04_writer_sha256,
        'observed_d04_writer_sha256': sha256(args.d04_writer),
        'd04_writer_matches_reviewed': sha256(args.d04_writer) == args.reviewed_d04_writer_sha256,
        'rounds': [inspect_round(args.rounds_root, args.batch_source_root, round_id) for round_id in ROUND_IDS],
    }
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.markdown_out:
        args.markdown_out.write_text(render_markdown(data), encoding='utf-8')

if __name__ == '__main__':
    main()
