#!/usr/bin/env python3
"""发布 e3 P1 演练（指令 §2.6，补充 1 之后）。全部在沙箱副本、桩服务与录制 runner 上进行：不取 GPU 锁，不碰 8095，
不停 481，不改真实包与存档，不写真实生产目录。

正向：W0 只读检查（含当前 W3.5 的只读结果）→ W2 Q1（桩）→ W3 finalize（沙箱副本，夹具）→ W4 取锁前（干净探测，
      录制 runner，停在 start_approved_release.py 处）。
反向：(a) 短请求 SHA 不符 → finalize 拒绝；(b) 长请求 [512,7745] → finalize 拒绝；
      (c) argv 漏参数 → 参数门拒绝；(d) PYTHONPATH 指向 release-e2 → 构建门拒绝；
      (e) 冒烟与 Q1 参考值不一致 → 包内路径停 e3 → restore14，不调用 ROLLBACK184（审批的 run 目录指向沙箱）；
      (f) 三态路由（补充 1 §1、§3）：确认不存在 / 第 25 秒接管 / 守护进程存活无 owner / 指针属于他人 /
          指针部分匹配 / 接管后 stop 失败。真实 stop 脚本在封印包的副本中运行，只替换指针路径、run 目录与
          ops 目录；controller 为测试替身（真实 controller 在本机的限制见 NS_STOP_FEASIBILITY.json）。

用法：drill_e3.py --sandbox NAME（目录不得已存在）。输出 NAME/DRILL_E3.json（0444）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import q1_e3 as q1

WORK = Path(__file__).resolve().parent
PACKAGE = WORK / 'release_e3'
ARCHIVE = q1.ARCHIVE
PREREG = Path('/data2/FreeToken/development/release_e3_accounting_20261012/PREREG_RELEASE_E3.json')
PRODUCTION_ACTIVE = Path('/data2/FreeToken/run/production.active.json')
GPU_LOCK = Path('/data2/_shared/gpu.lock')
RUN_13 = Path('/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-13')
RUN_E3 = Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-01')
W35_REAL = Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-01.W35_SNAPSHOT.json')
COORD_LOG = Path('/data2/FreeToken/plan/COORDINATION_LOG.md')
APPROVAL_ID = 'RELEASE-E3-20261012-01'
REF_REL = Path('source/development/release_e3_reference_20261012')
E2_SHORT_SHA = 'fd11a31559daaafb889b8a80f29a412470e0635caae631971a0a31e948a9dfdd'
RELEASE_E2_ROOT = '/data2/FreeToken/wt/release-e2/python'
E3_RELEASE_RE = re.compile(r'^- \S+ 主会话.*发布 e3 放行')
RESTORE14_CALL = 'restore14:deploy_conditional.py'
STOP_CALL = 'stop_approved_restore.py'
EXPECTED_F = {
    'absent_confirmed_twice': {'calls': [RESTORE14_CALL], 'rc': 0, 'now': 2.0, 'stopped': False},
    'owner_appears_at_25s': {'calls': [STOP_CALL, RESTORE14_CALL], 'rc': 0, 'now': 26.0, 'stopped': True},
    'daemon_alive_no_owner': {'calls': [], 'rc': 3, 'now': 60.0, 'ambiguous': True},
    'foreign_pointer': {'calls': [], 'rc': 3, 'now': 0.0, 'ambiguous': True},
    'partial_pointer_match': {'calls': [], 'rc': 3, 'now': 0.0, 'ambiguous': True},
    'stop_fails_after_owner': {'calls': [STOP_CALL], 'rc': 3, 'ambiguous': True, 'stopped': False},
}


class StopBeforeGpu(Exception):
    """录制 runner 在取锁命令处停止；此后的命令会占用 GPU 或改动生产。"""


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def port_free(port: int) -> bool:
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((q1.Q1_HOST, port))
        except OSError:
            return False
    return True


def protected_state() -> dict[str, Any]:
    """真实包、真实存档、生产指针与 GPU 锁的哈希，以及真实生产路径的缺席状态；演练前后必须相同。"""
    files = [PACKAGE / 'DEPLOYMENT_APPROVAL.json', PACKAGE / 'ROOT_FINAL_REVIEW.json',
             PACKAGE / 'SOURCE_MANIFEST.json', ARCHIVE / 'evidence' / 'source_manifest.json',
             PRODUCTION_ACTIVE, GPU_LOCK]
    absent = [ARCHIVE / REF_REL, RUN_E3, W35_REAL]
    return {'sha256': {str(p): sha(p) if p.exists() else None for p in files},
            'absent': {str(p): not p.exists() for p in absent}}


def clean_snapshot() -> dict[str, Any]:
    return {'pointer_exists': False, 'pointer': None, 'owner_json': False, 'run_dir_exists': False,
            'lock_exists': False, 'cleanup_failed_exists': False, 'processes': [], 'listeners': [],
            'compute_pids': [], 'gpu_memory_mib': [0], 'at': 0.0}


def clean_probe(approval: dict[str, Any]) -> dict[str, Any]:
    """W3 之后的主机状态（模拟）：没有监听，没有计算进程，没有锁、指针与 run 目录。"""
    return clean_snapshot()


def make_pristine(sandbox: Path) -> dict[str, Path]:
    base = sandbox / 'pristine'
    shutil.copytree(ARCHIVE, base / 'archive', symlinks=True)
    shutil.copytree(PACKAGE, base / 'package', symlinks=True)
    return {'archive': base / 'archive', 'package': base / 'package'}


def fresh_case(sandbox: Path, pristine: dict[str, Path], name: str) -> dict[str, Path]:
    case = sandbox / 'cases' / name
    shutil.copytree(pristine['archive'], case / 'archive', symlinks=True)
    shutil.copytree(pristine['package'], case / 'package', symlinks=True)
    return {'archive': case / 'archive', 'package': case / 'package'}


def run_finalize(q1_json: Path, case: dict[str, Path]) -> dict[str, Any]:
    proc = subprocess.run([sys.executable, '-B', str(case['package'] / 'finalize_e3.py'), '--q1', str(q1_json),
                           '--archive', str(case['archive']), '--package', str(case['package']),
                           '--prereg', str(PREREG)],
                          capture_output=True, text=True, timeout=600,
                          env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    return {'rc': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}


def write_fixture(source: Path, target: Path) -> None:
    """夹具：把 Q1 输出的短请求 SHA 换成 e2 参考值，仅用于在沙箱中走通 finalize 的正向机制；不是测量。"""
    payload = json.loads(source.read_text(encoding='utf-8'))
    payload['results']['short']['sha256'] = E2_SHORT_SHA
    payload['fixture'] = ('FIXTURE: short sha256 set to the e2 reference value; not a measurement. '
                          'Used only to exercise finalize mechanics in a sandbox.')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def w0_readonly(tb: Any) -> dict[str, Any]:
    """W0 的只读检查（不取锁、不发请求、不碰 8095，不调用会写快照的 run_precheck）。"""
    active = json.loads(PRODUCTION_ACTIVE.read_text(encoding='utf-8')) if PRODUCTION_ACTIVE.exists() else {}
    lock = json.loads(GPU_LOCK.read_text(encoding='utf-8')) if GPU_LOCK.exists() else {}
    observer_lines = (RUN_13 / 'observer_outer_B.log').read_text(encoding='utf-8').splitlines()
    observer_docs = [json.loads(line) for line in observer_lines if line.startswith('{')]
    observer_ok = bool(observer_docs) and observer_docs[-1].get('event') == 'observation_completed' \
        and observer_docs[-1].get('issues') == []
    observers = tb.procs_matching(lambda argv, cwd: any(Path(a).name == 'observe_overnight.py' for a in argv))
    stale = tb.procs_matching(lambda argv, cwd: any(Path(a).name in ('q1_e3.py', 'stub_e3_server.py')
                                                    for a in argv))
    compute = subprocess.run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
                             capture_output=True, text=True, timeout=60).stdout.split()
    coord = COORD_LOG.read_text(encoding='utf-8').splitlines()
    release_lines = [line for line in coord if E3_RELEASE_RE.match(line)]
    checks = {
        'owner_is_restore13': {'pass': active.get('approval_id') == 'RESTORE481-MORNING-20261011-13'
                               and active.get('commit') == '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9',
                               'approval_id': active.get('approval_id'), 'commit': active.get('commit')},
        'gpu_lock_is_restore13': {'pass': lock.get('owner') == 'production:release:RESTORE481-MORNING-20261011-13',
                                  'owner': lock.get('owner')},
        'observer_13_completed_clean': {'pass': observer_ok and not observers, 'observer_processes': observers},
        'port_8123_free': {'pass': port_free(q1.Q1_PORT)},
        'no_q1_or_stub_process': {'pass': not stale, 'pids': stale},
        'no_e3_run_dir': {'pass': not RUN_E3.exists()},
    }
    info = {'release_line_present': bool(release_lines),
            'release_line_evidence': release_lines[-1] if release_lines else None,
            'release_phrase_mentions_in_log': sum('发布 e3 放行' in line for line in coord),
            'nvidia_compute_pids': compute,
            'not_probed': '8095 健康检查不在演练中进行（§2.6）'}
    return {'checks': checks, 'info': info, 'all_pass': all(item['pass'] for item in checks.values())}


def live_w35() -> dict[str, Any]:
    """只读：此刻主机上 W3.5 会看到什么（不调用 run_precheck，因为它会写快照）。"""
    probe = q1.load_module('real_e3_probe', PACKAGE / 'e3_probe.py')
    approval = json.loads((PACKAGE / 'DEPLOYMENT_APPROVAL.json').read_text(encoding='utf-8'))
    snapshot = probe.live_probe(approval)
    return {'failures_now': probe.precheck_failures(snapshot), 'listeners_now': snapshot['listeners'],
            'compute_pids_now': snapshot['compute_pids'], 'gpu_memory_mib_now': snapshot['gpu_memory_mib'],
            'note': 'expected to fail while 481 serves; W3.5 runs after W1 in the window'}


def pre_gpu(package: Path) -> dict[str, Any]:
    """正向 W4：真实入口 execute() 在干净探测下通过 W3.5，并在第一条取锁命令前停止。录制 runner 不执行任何命令。"""
    try:
        dc = q1.load_module('deploy_case_positive', package / 'deploy_conditional.py')
        calls: list[str] = []

        def runner(argv: list[str]) -> SimpleNamespace:
            calls.append(Path(argv[1]).name)
            raise StopBeforeGpu(Path(argv[1]).name)

        clock = Clock()
        stopped_at = None
        try:
            dc.execute(runner, probe=clean_probe, clock=clock, sleep=clock.sleep)
        except StopBeforeGpu as exc:
            stopped_at = str(exc)
        return {'calls': calls, 'stopped_at': stopped_at, 'w35_simulated_clean': True,
                'pass': calls == ['start_approved_release.py'] and stopped_at == 'start_approved_release.py'}
    except Exception as exc:  # noqa: BLE001 - 审批或复审校验失败：记录，不计为通过
        return {'error': repr(exc), 'pass': False}


def positive(sandbox: Path, pristine: dict[str, Path], tb: Any) -> dict[str, Any]:
    out: dict[str, Any] = {'W0_readonly': w0_readonly(tb)}
    out['W0_readonly']['info']['live_w35'] = live_w35()
    q1_run = q1.run_q1(sandbox / 'runs' / 'positive_q1', 'stub')
    out['W2_q1_stub'] = {'classification': q1_run['classification'], 'detail': q1_run['detail'],
                         'pass': q1_run['classification'] == 'passed'}
    if q1_run['classification'] == 'passed':
        fixture = sandbox / 'fixtures' / 'cold_smoke_FIXTURE_e2_short_sha.json'
        write_fixture(sandbox / 'runs' / 'positive_q1' / 'cold_smoke.json', fixture)
        case = fresh_case(sandbox, pristine, 'positive')
        fin = run_finalize(fixture, case)
        out['W3_finalize_fixture'] = {'rc': fin['rc'], 'stdout_head': fin['stdout'][:300],
                                      'stderr_tail': fin['stderr'][-300:],
                                      'pass': fin['rc'] == 0 and '"q1_check": "passed"' in fin['stdout']}
        out['W4_before_gpu_lock'] = pre_gpu(case['package'])
    else:
        out['W3_finalize_fixture'] = {'pass': False, 'note': 'not run: W2 did not pass'}
        out['W4_before_gpu_lock'] = {'pass': False, 'note': 'not run: W2 did not pass'}
    return out


def case_a(sandbox: Path, pristine: dict[str, Path]) -> dict[str, Any]:
    run_dir = sandbox / 'runs' / 'a_short_sha'
    run = q1.run_q1(run_dir, 'stub', short_variant='B')
    if run['classification'] != 'passed':
        return {'q1': run['classification'], 'pass': False, 'note': 'Q1 must produce a payload for this drill'}
    fin = run_finalize(run_dir / 'cold_smoke.json', fresh_case(sandbox, pristine, 'a'))
    return {'q1': run['classification'], 'finalize_rc': fin['rc'], 'stderr_tail': fin['stderr'][-300:],
            'expected': 'finalize rc 2 with 短请求 SHA refusal; route restore14 (未上线)',
            'pass': fin['rc'] == 2 and '短请求 SHA' in fin['stderr']}


def case_b(sandbox: Path, pristine: dict[str, Path]) -> dict[str, Any]:
    run_dir = sandbox / 'runs' / 'b_long_split'
    run = q1.run_q1(run_dir, 'stub', long_segments='512,7745')
    if run['classification'] != 'passed':
        return {'q1': run['classification'], 'pass': False, 'note': 'Q1 must produce a payload for this drill'}
    fin = run_finalize(run_dir / 'cold_smoke.json', fresh_case(sandbox, pristine, 'b'))
    return {'q1': run['classification'], 'finalize_rc': fin['rc'], 'stderr_tail': fin['stderr'][-300:],
            'expected': 'finalize rc 2 with 长请求行结构 refusal; route restore14 (未上线)',
            'pass': fin['rc'] == 2 and '长请求行结构' in fin['stderr']}


def case_c(sandbox: Path) -> dict[str, Any]:
    run_dir = sandbox / 'runs' / 'c_argv_missing_flag'
    run = q1.run_q1(run_dir, 'stub', drop_anchor_flag=True)
    no_requests = not (run_dir / 'short.json').exists() and not (run_dir / 'cold_smoke.json').exists()
    return {'q1': run['classification'], 'detail': run['detail'], 'no_requests_sent': no_requests,
            'pass': run['classification'] == 'param_gate_refused' and no_requests}


def case_d(sandbox: Path) -> dict[str, Any]:
    run_dir = sandbox / 'runs' / 'd_pythonpath_e2'
    run = q1.run_q1(run_dir, 'stub', pythonpath=RELEASE_E2_ROOT)
    no_serve = not (run_dir / 'serve.log').exists()
    return {'q1': run['classification'], 'detail': run['detail'], 'no_service_started': no_serve,
            'pass': run['classification'] == 'build_gate_refused' and no_serve}


def case_e(sandbox: Path, pristine: dict[str, Path]) -> dict[str, Any]:
    """冒烟与 Q1 参考值不一致。正式冒烟需要生产 owner，因此用 test_smoke_live.compare_expected_reference 代替它；
    审批的 run 目录指向沙箱，stop/restore14/observer 只记录不执行。"""
    case = fresh_case(sandbox, pristine, 'e')
    fin = run_finalize(sandbox / 'fixtures' / 'cold_smoke_FIXTURE_e2_short_sha.json', case)
    if fin['rc'] != 0:
        return {'pass': False, 'note': 'reference not written', 'finalize_rc': fin['rc']}
    smoke_case = q1.load_module('smoke_case_e', case['archive'] / 'source' / 'development' /
                                'release_e2_ops_v2' / 'test_smoke_live.py')
    dc = q1.load_module('deploy_case_e', case['package'] / 'deploy_conditional.py')
    approval = json.loads((case['package'] / 'DEPLOYMENT_APPROVAL.json').read_text(encoding='utf-8'))
    (sandbox / 'e_run').mkdir()
    approval['run_dir'] = str(sandbox / 'e_run' / APPROVAL_ID)
    dc.load = lambda: approval
    dc.require_root_final_review = lambda approval_arg: None  # 审批已改为沙箱 run 目录；复审校验在 W4 中已做
    state = {'started': False}

    def probe(approval_arg: dict[str, Any]) -> dict[str, Any]:
        snapshot = clean_snapshot()
        if state['started']:
            snapshot.update(pointer_exists=True, owner_json=True, run_dir_exists=True,
                            pointer={'approval_id': APPROVAL_ID, 'commit': approval['restore_commit'],
                                     'run_dir': approval['run_dir']})
        return snapshot

    candidate = json.loads((sandbox / 'runs' / 'a_short_sha' / 'cold_smoke.json').read_text(encoding='utf-8'))
    calls: list[str] = []

    def runner(argv: list[str]) -> SimpleNamespace:
        name = Path(argv[1]).name
        calls.append(('restore14:' if 'restore14' in str(argv[1]) else '') + name)
        if name == 'start_approved_release.py':
            state['started'] = True
            return SimpleNamespace(returncode=0)
        if name == 'wait_release_and_smoke.py':
            try:
                smoke_case.compare_expected_reference(candidate)
            except AssertionError:
                return SimpleNamespace(returncode=1)  # 冒烟判失败：与 Q1 参考值不一致
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=0)

    clock = Clock()
    rc = dc.execute(runner, probe=probe, clock=clock, sleep=clock.sleep)
    expected = ['start_approved_release.py', 'wait_release_and_smoke.py', STOP_CALL, RESTORE14_CALL]
    no_rollback = not any('rollback' in call.lower() for call in calls)
    return {'calls': calls, 'execute_rc': rc, 'expected_calls': expected, 'no_rollback_call': no_rollback,
            'pass': calls == expected and rc == 0 and no_rollback}


def case_f(sandbox: Path, pristine: dict[str, Path]) -> dict[str, Any]:
    """三态路由（补充 1 §3）：六个场景由封印包的测试模块运行；每个场景在副本中执行真实的 stop 脚本。"""
    case = fresh_case(sandbox, pristine, 'f')
    tests = q1.load_module('case_tests_f', case['package'] / 'test_cpu_orchestration.py')
    results: dict[str, Any] = {}
    for name, expected in EXPECTED_F.items():
        root = sandbox / 'f' / name
        root.mkdir(parents=True)
        record = tests.run_scenario(root, name)
        checks = {'calls': record['calls'] == expected['calls'], 'rc': record['rc'] == expected['rc'],
                  'no_rollback': not any('rollback' in call.lower() for call in record['calls'])}
        for key in ('now', 'ambiguous', 'stopped'):
            if key in expected:
                checks[key] = record[key] == expected[key] if key == 'now' else bool(record[key]) == expected[key]
        results[name] = {**record, 'expected': expected, 'checks': checks, 'pass': all(checks.values())}
    return {'scenarios': results, 'pass': all(item['pass'] for item in results.values()),
            'controller': 'test double inside the sealed package tests; the real controller cannot complete on this host '
                          '(see NS_STOP_FEASIBILITY.json)'}


def namespace_summary() -> dict[str, Any]:
    reports = sorted(WORK.glob('ns_feasibility_*/NS_STOP_FEASIBILITY.json'))
    if not reports:
        return {'present': False}
    report = json.loads(reports[-1].read_text(encoding='utf-8'))
    return {'present': True, 'path': str(reports[-1]), 'all_checks_pass': report['all_checks_pass'],
            'stop_stdout': report['namespace_stdout'][-200:], 'duration_seconds': report['duration_seconds']}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='发布 e3 P1 演练（补充 1 之后）')
    parser.add_argument('--sandbox', required=True)
    args = parser.parse_args(argv)
    sandbox = WORK / args.sandbox
    if sandbox.exists():
        raise SystemExit(f'沙箱已存在，拒绝覆盖：{sandbox}')
    (sandbox / 'runs').mkdir(parents=True)
    tb = q1.load_modules().tb
    before = protected_state()
    pristine = make_pristine(sandbox)
    report: dict[str, Any] = {'schema': 'ft_p1_drill_e3/v2', 'sandbox': str(sandbox), 'started_at': tb.server_now()}
    report['positive'] = positive(sandbox, pristine, tb)
    report['reverse'] = {'a': case_a(sandbox, pristine), 'b': case_b(sandbox, pristine), 'c': case_c(sandbox),
                         'd': case_d(sandbox), 'e': case_e(sandbox, pristine), 'f': case_f(sandbox, pristine)}
    report['real_artifacts_unchanged'] = before == protected_state()
    report['residual_stub_processes'] = tb.procs_matching(
        lambda argv_, cwd: any(Path(a).name == 'stub_e3_server.py' for a in argv_))
    expected = {'W0': report['positive']['W0_readonly']['all_pass'],
                'W2': report['positive']['W2_q1_stub']['pass'],
                'W3': report['positive']['W3_finalize_fixture']['pass'],
                'W4': report['positive']['W4_before_gpu_lock']['pass'],
                'a': report['reverse']['a']['pass'], 'b': report['reverse']['b']['pass'],
                'c': report['reverse']['c']['pass'], 'd': report['reverse']['d']['pass'],
                'e': report['reverse']['e']['pass'], 'f': report['reverse']['f']['pass']}
    report['summary'] = {'expected_pass': expected,
                         'live_w35_now': report['positive']['W0_readonly']['info']['live_w35'],
                         'namespace_feasibility': namespace_summary(),
                         'real_artifacts_unchanged': report['real_artifacts_unchanged'],
                         'residual_stub_processes': report['residual_stub_processes'],
                         'all_expected_pass': all(expected.values()) and report['real_artifacts_unchanged']
                         and not report['residual_stub_processes']}
    tb.write_new(sandbox / 'DRILL_E3.json', report)
    print(json.dumps(report['summary'], ensure_ascii=False, indent=1))
    return 0 if report['summary']['all_expected_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
