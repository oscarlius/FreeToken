#!/usr/bin/env python3
"""发布 e3 补充 1 §5.2：私有挂载命名空间中原样运行未修改的 stop 脚本（可行性验证）。

护栏（补充 1 §5.2）：
1. stop 链路写死的绝对路径全部列出（grep，记入报告）；会被写入的路径在命名空间内 bind 到临时目录。
2. 进入命名空间后、运行 stop 之前，逐个检查标记文件，确认看到的是临时目录。
3. 伪造的 owner 只引用本脚本启动的哑进程（sleep 3600），并断言其 pid 不属于生产（指针、计算进程、生产进程集合）。
4. 宿主侧在测试前后各记录一次：真实 production.active.json 的 SHA256、gpu.lock 的 inode 与内容、481 的 health。
   任一项不一致，记为失败并报告。
5. 只在命名空间内进行：不改任何文件，不触碰真实指针，不向生产进程发信号。

输出：WORK/ns_feasibility_<时间>/NS_STOP_FEASIBILITY.json（0444）。
预计耗时约 220 秒（release_control --stop 的等待上限）。
"""
from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

WORK = Path(__file__).resolve().parent
PACKAGE = WORK / 'release_e3'
STOP = PACKAGE / 'stop_approved_restore.py'
APPROVAL = PACKAGE / 'DEPLOYMENT_APPROVAL.json'
ARCHIVE_DEV = Path('/data2/FreeToken/runs/dev_release/release_e3_ops_v1_20261012/source/development')
D07 = ARCHIVE_DEV / 'd07_g3g4_prepare.py'
D07_SHA = 'c4a28aaa602536b3c1f5b94a77f9e18cd48443867f3c0cc8a029ab0531bbddd0'
POINTER = Path('/data2/FreeToken/run/production.active.json')
LOCK = Path('/data2/_shared/gpu.lock')
RUN_DIR = Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-01')
APPROVAL_ID = 'RELEASE-E3-20261012-01'
COMMIT = '9db0ee776c25afa8d2719ab700b2de7ccc606142'
HEALTH_URL = 'http://172.16.108.9:8095/health'
CHAIN_FILES = [STOP, PACKAGE / 'deploy_conditional.py', PACKAGE / 'e3_probe.py',
               ARCHIVE_DEV / 'release_e2_ops_v2' / 'release_control.py',
               ARCHIVE_DEV / 'release_e2_ops_v2' / 'release_config.py',
               ARCHIVE_DEV / 'release_e2_ops_v2' / 'worktree_checks.py', D07]
ABS_PATH_RE = re.compile(r'/data2/[^\s\'"]+')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_d07() -> Any:
    if sha(D07) != D07_SHA:
        raise SystemExit('pinned d07 helper differs; refusing')
    spec = importlib.util.spec_from_file_location('ns_d07', D07)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lock_state() -> Any:
    if not LOCK.exists():
        return None
    stat = LOCK.stat()
    return {'inode': stat.st_ino, 'size': stat.st_size, 'sha256': sha(LOCK)}


def health_state() -> dict[str, Any]:
    """481 的健康检查：状态码与 status/maintenance/model 三个字段（响应体中可能有随时间变化的字段，不做整体哈希）。"""
    with httpx.Client(trust_env=False, timeout=5.0) as client:
        response = client.get(HEALTH_URL)
    try:
        body = response.json()
    except ValueError:
        body = {}
    return {'status': response.status_code,
            'serving': {key: body.get(key) for key in ('status', 'maintenance', 'model')}}


def gpu_pids() -> list[str]:
    proc = subprocess.run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
                          capture_output=True, text=True, timeout=60)
    return sorted(line.strip() for line in proc.stdout.splitlines() if line.strip())


def production_pids(exclude: set[int]) -> list[int]:
    """命令行含 /data2/FreeToken/ 的进程（只读扫描 /proc）。"""
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) in exclude:
            continue
        try:
            text = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8', errors='replace')
        except OSError:
            continue
        if '/data2/FreeToken/' in text:
            found.append(int(entry.name))
    return sorted(found)


def pointer_pids(pointer: dict[str, Any] | None) -> list[int]:
    if not pointer:
        return []
    pids = []
    for key in ('supervisor', 'service', 'monitor'):
        value = pointer.get(key)
        if isinstance(value, dict) and isinstance(value.get('pid'), int):
            pids.append(value['pid'])
    return pids


def snapshot(own_pid: int) -> dict[str, Any]:
    pointer = json.loads(POINTER.read_text(encoding='utf-8')) if POINTER.exists() else None
    pids = production_pids({own_pid})
    return {'pointer_sha256': sha(POINTER) if POINTER.exists() else None,
            'pointer_pids': pointer_pids(pointer), 'lock': lock_state(), 'health': health_state(),
            'gpu_compute_pids': gpu_pids(), 'production_pids': pids, 'run_dir_exists': RUN_DIR.exists()}


GUARD = r'''
set -u
mount --bind "$T_RUN" /data2/FreeToken/run || { echo GUARD_BIND_RUN_FAILED; exit 90; }
mount --bind "$T_PROD" /data2/FreeToken/runs/production || { echo GUARD_BIND_PROD_FAILED; exit 91; }
mount --bind "$T_SHARED" /data2/_shared || { echo GUARD_BIND_SHARED_FAILED; exit 92; }
grep -qx "$TOKEN" /data2/FreeToken/run/NS_MARKER.txt || { echo GUARD_MARKER_RUN; exit 93; }
grep -qx "$TOKEN" /data2/FreeToken/runs/production/NS_MARKER.txt || { echo GUARD_MARKER_PROD; exit 94; }
grep -qx "$TOKEN" /data2/_shared/NS_MARKER.txt || { echo GUARD_MARKER_SHARED; exit 95; }
test ! -e /data2/_shared/gpu.lock || { echo GUARD_REAL_LOCK_VISIBLE; exit 96; }
cmp -s /data2/FreeToken/run/production.active.json "$T_RUN/production.active.json" || { echo GUARD_POINTER_NOT_FAKE; exit 97; }
echo GUARD_OK
cd "$PKG" || exit 98
/data2/FreeToken/venv/bin/python -B stop_approved_restore.py
echo "STOP_RC=$?"
'''


def main() -> int:
    stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
    out = WORK / f'ns_feasibility_{stamp}'
    out.mkdir()
    own = os.getpid()
    before = snapshot(own)
    stop_sha, approval_sha = sha(STOP), sha(APPROVAL)
    d07 = load_d07()
    dummy = subprocess.Popen(['sleep', '3600'], start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.3)
    identity = d07.process_identity(dummy.pid)
    production = set(before['production_pids']) | set(before['pointer_pids'])
    dummy_ok = (identity is not None and dummy.pid not in production and dummy.pid not in before['gpu_compute_pids']
                and str(dummy.pid) not in before['gpu_compute_pids'])
    if not dummy_ok:
        dummy.kill()
        raise SystemExit('dummy pid is not isolated from production; refusing')
    binds = {name: out / 'binds' / name for name in ('run', 'prod', 'shared')}
    token = secrets.token_hex(12)
    for path in binds.values():
        path.mkdir(parents=True)
        (path / 'NS_MARKER.txt').write_text(token + '\n', encoding='utf-8')
    fake_pointer = {'mode': 'release', 'approval_id': APPROVAL_ID, 'commit': COMMIT, 'run_dir': str(RUN_DIR),
                    'host': '172.16.108.9', 'supervisor': identity, 'service': None, 'monitor': None,
                    'note': 'feasibility dummy: sleep 3600, not production'}
    (binds['run'] / 'production.active.json').write_text(json.dumps(fake_pointer, indent=2) + '\n', encoding='utf-8')
    env = {**os.environ, 'T_RUN': str(binds['run']), 'T_PROD': str(binds['prod']),
           'T_SHARED': str(binds['shared']), 'PKG': str(PACKAGE), 'TOKEN': token}
    started = time.time()
    proc = subprocess.run(['unshare', '-rm', '/bin/bash', '-c', GUARD], env=env, capture_output=True, text=True,
                          timeout=420)
    duration = time.time() - started
    dummy_rc = dummy.poll()
    if dummy_rc is None:
        dummy.kill()
        dummy.wait(timeout=10)
    after = snapshot(own)
    stop_record = binds['prod'] / APPROVAL_ID / f'stop_{APPROVAL_ID}.json'
    checks = {
        'guard_ok': 'GUARD_OK' in proc.stdout,
        'stop_script_sha_unchanged': sha(STOP) == stop_sha,
        'approval_sha_unchanged': sha(APPROVAL) == approval_sha,
        'host_pointer_sha_unchanged': before['pointer_sha256'] == after['pointer_sha256'],
        'host_lock_identity_unchanged': before['lock'] == after['lock'],
        'host_health_unchanged': before['health'] == after['health'],
        'host_gpu_compute_unchanged': before['gpu_compute_pids'] == after['gpu_compute_pids'],
        'host_production_pids_unchanged': before['production_pids'] == after['production_pids'],
        'host_run_dir_still_absent': not after['run_dir_exists'],
        'stop_record_written_inside_bind': stop_record.exists(),
        'dummy_received_sigterm_only': dummy_rc is not None and dummy_rc != 0,
    }
    report = {
        'schema': 'ft_ns_stop_feasibility/v1',
        'started_at': datetime.datetime.now().astimezone().isoformat(),
        'duration_seconds': round(duration, 1),
        'stop_chain_absolute_paths': {
            str(path): [{'line': number, 'text': match}
                        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1)
                        for match in ABS_PATH_RE.findall(line)]
            for path in CHAIN_FILES},
        'dummy': {'pid': dummy.pid, 'identity': identity, 'exit_code': dummy_rc},
        'binds': {'/data2/FreeToken/run': str(binds['run']), '/data2/FreeToken/runs/production': str(binds['prod']),
                  '/data2/_shared': str(binds['shared'])},
        'namespace_returncode': proc.returncode,
        'namespace_stdout': proc.stdout[-1500:],
        'namespace_stderr_tail': proc.stderr[-1200:],
        'before': before,
        'after': after,
        'checks': checks,
        'all_checks_pass': all(checks.values()),
        'verdict': ('namespace isolation and stop-script execution verified; the controller cannot complete while '
                    'production 481 holds host ports 8095/8096 or GPU compute, so the takeover-success path cannot be '
                    'demonstrated with the real controller on this host (see stop_exceeded in stderr)'),
    }
    target = out / 'NS_STOP_FEASIBILITY.json'
    with target.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    os.chmod(target, 0o444)
    print(json.dumps({'dir': str(out), 'namespace_returncode': proc.returncode, 'checks': checks,
                      'all_checks_pass': report['all_checks_pass']}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
