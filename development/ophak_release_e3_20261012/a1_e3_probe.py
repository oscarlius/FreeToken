"""发布 e3 只读探测与 W3.5 预检（补充 1 §1、§2）。只读：不取锁，不发信号，不改任何生产路径。

live_probe(approval) 返回一份快照；precheck_failures(snapshot) 返回未满足的 W3.5 条件（空列表即通过）；
run_precheck() 最长等 60 秒。不通过时把快照写到 runs/production/<approval_id>.W35_SNAPSHOT.json，
不创建 run 目录（start_approved_release.py 要求 run 目录不存在）。
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

ACTIVE = Path('/data2/FreeToken/run/production.active.json')
QUARANTINE = Path('/data2/FreeToken/run/production.cleanup_failed.json')
GPU_LOCK = Path('/data2/_shared/gpu.lock')
PORTS = (8095, 8096)
MAX_GPU_MIB = 1000
POLL_S = 2.0
POLL_WINDOW_S = 60.0
PRECHECK_RC = 5
SNAPSHOT_SUFFIX = '.W35_SNAPSHOT.json'


def read_pointer() -> Any:
    try:
        return json.loads(ACTIVE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def release_control_processes(approval_id: str) -> list[int]:
    """命令行同时含 release_control.py 与 e3 审批号的进程（只读扫描 /proc）。"""
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry / 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        text = ' '.join(part.decode('utf-8', errors='replace') for part in argv if part)
        if 'release_control.py' in text and approval_id in text:
            found.append(int(entry.name))
    return sorted(found)


def run_nvidia_smi(query: str) -> list[str]:
    proc = subprocess.run(['nvidia-smi', query, '--format=csv,noheader,nounits'],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode:
        raise RuntimeError(f'nvidia-smi failed: {proc.stderr[-200:]}')
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def listening_lines() -> list[str]:
    proc = subprocess.run(['ss', '-H', '-ltn', '( sport = :8095 or sport = :8096 )'],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode:
        raise RuntimeError(f'ss failed: {proc.stderr[-200:]}')
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def live_probe(approval: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(approval['run_dir'])
    pointer_exists = ACTIVE.exists() or ACTIVE.is_symlink()
    return {
        'pointer_exists': pointer_exists,
        'pointer': read_pointer() if pointer_exists else None,
        'owner_json': (run_dir / 'owner.json').exists(),
        'run_dir_exists': run_dir.exists(),
        'lock_exists': GPU_LOCK.exists() or GPU_LOCK.is_symlink(),
        'cleanup_failed_exists': QUARANTINE.exists() or QUARANTINE.is_symlink(),
        'processes': release_control_processes(approval['approval_id']),
        'listeners': listening_lines(),
        'compute_pids': run_nvidia_smi('--query-compute-apps=pid'),
        'gpu_memory_mib': [int(value) for value in run_nvidia_smi('--query-gpu=memory.used')],
        'at': time.time(),
    }


def precheck_failures(snapshot: dict[str, Any]) -> list[str]:
    """W3.5 的全部条件（补充 1 §2）。返回未满足的条件名。"""
    failures = []
    if snapshot['compute_pids']:
        failures.append('compute_processes')
    if any(mib >= MAX_GPU_MIB for mib in snapshot['gpu_memory_mib']):
        failures.append('gpu_memory_at_or_above_1000_MiB')
    if snapshot['listeners']:
        failures.append('listening_8095_or_8096')
    if snapshot['lock_exists']:
        failures.append('gpu_lock_present')
    if snapshot['pointer_exists']:
        failures.append('production_active_present')
    if snapshot['cleanup_failed_exists']:
        failures.append('cleanup_failed_present')
    if snapshot['run_dir_exists']:
        failures.append('e3_run_dir_present')
    return failures


def write_snapshot(approval: dict[str, Any], payload: dict[str, Any]) -> Path:
    path = Path(approval['run_dir']).parent / (approval['approval_id'] + SNAPSHOT_SUFFIX)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write('\n')
    return path


def run_precheck(approval: dict[str, Any], probe: Callable[[dict[str, Any]], dict[str, Any]] = live_probe,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> int:
    """W3.5：通过返回 0；60 秒内仍不通过返回 PRECHECK_RC，并写快照。两种结果都不启动任何服务。"""
    deadline = clock() + POLL_WINDOW_S
    while True:
        snapshot = probe(approval)
        failures = precheck_failures(snapshot)
        if not failures:
            print(json.dumps({'w35': 'passed'}), flush=True)
            return 0
        if clock() >= deadline:
            path = write_snapshot(approval, {'w35': 'failed', 'failures': failures, 'snapshot': snapshot})
            print(json.dumps({'w35': 'failed', 'failures': failures, 'snapshot': str(path)}), flush=True)
            return PRECHECK_RC
        sleep(POLL_S)
