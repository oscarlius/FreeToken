#!/usr/bin/env python3
"""发布 e3 观察检查（指令 §4，只读）：12:00、18:00、次日 09:00 各一次。

用法：e3_observe_check.py --label LABEL [--final] [--dry-run]
      e3_observe_check.py --selftest

只读：不取锁、不发信号、不发推理请求、不改生产文件。结果写入 WORK/OBS_CHECK_<LABEL>.json（0444）。

口径（§4，2026-10-12 12:03 之后的主会话裁定）：
- OOM 次数：serve.log 中 "out of memory" 与 "worker_restarting_after_oom" 的行数（异常判据）。
- worker 退出次数："backend worker ... exited" 与 "backend worker is gone" 的行数（异常判据）。
- 热轮切段判据：续段检测脚本 cut_continuation_check.py（按记录的 SHA256 核对后以 python3 -I 调用）。
  严格档与宽松档中 remain ≤ 32768 的对数大于 0 即为异常。
- 请求数与状态分布：uvicorn 访问日志 "POST ... HTTP/x" 的行数，按状态码计数（参考，只记录）。
- POST 归属的热轮行数分布：只作参考，归属不可靠，不作判据。
- 422 等客户端错误：只记录，不作异常判据。
- 观察器：samples.jsonl 中不满足 observe_overnight.eligible 的采样；终态 terminal.json（--final 时读取）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

WORK = Path(__file__).resolve().parent
RUN = Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-01')
SERVE_LOG = RUN / 'serve.log'
OBSERVER_DIR = RUN / 'overnight_observation'
OBSERVE_MODULE = WORK / 'release_e3' / 'observe_overnight.py'
PREREG = Path('/data2/FreeToken/development/release_e3_accounting_20261012/PREREG_RELEASE_E3.json')
POINTER = Path('/data2/FreeToken/run/production.active.json')
HEALTH_URL = 'http://172.16.108.9:8095/health'
THRESH = 32768
# 主会话裁定（2026-10-12 12:03 之后）：热轮切段的判据是续段检测脚本，按记录的 SHA256 核对后调用。
PEER_CHECK = Path('/data2/FreeToken/development/release_e3_accounting_20261012/cut_continuation_check.py')
PEER_SHA = '31a46f4c4a80368564a2bc5745aee592734c3a74d258ccfc412e07a60082c8a1'
ANSI = re.compile(r'\x1b\[[0-9;]*m')
PREFILL = re.compile(r'Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)')
POST = re.compile(r'"POST ([^"]+) HTTP/[0-9.]+" (\d{3})')
OOM = re.compile(r'out of memory|worker_restarting_after_oom', re.IGNORECASE)
WORKER = re.compile(r'backend worker \S+ exited|backend worker is gone', re.IGNORECASE)


def analyze_lines(lines: list[str]) -> dict[str, Any]:
    """逐行统计（纯函数，便于自测）。"""
    lines = [ANSI.sub('', line) for line in lines]
    oom = [{'line': i, 'text': line[:160]} for i, line in enumerate(lines, 1) if OOM.search(line)]
    worker = [{'line': i, 'text': line[:160]} for i, line in enumerate(lines, 1) if WORKER.search(line)]
    statuses: Counter = Counter()
    rounds: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for i, line in enumerate(lines, 1):
        m = PREFILL.search(line)
        if m and m.group(1) == '1':  # 只统计单序列行
            current.append({'line': i, 'new_tokens': int(m.group(2)), 'cached': int(m.group(3))})
        pm = POST.search(line)
        if pm:
            statuses[pm.group(2)] += 1
            rounds.append({'rows': current, 'end_line': i, 'path': pm.group(1)})
            current = []
    hot = [r for r in rounds if any(row['cached'] > 0 for row in r['rows'])]
    cold = [r for r in rounds if r['rows'] and not any(row['cached'] > 0 for row in r['rows'])]
    no_prefill = [r for r in rounds if not r['rows']]
    distribution = Counter(len(r['rows']) for r in hot)
    anomalies = []
    for r in hot:
        remain = sum(row['new_tokens'] for row in r['rows'])
        if len(r['rows']) > 1 and remain <= THRESH:
            anomalies.append({'end_line': r['end_line'], 'rows': len(r['rows']), 'remain': remain,
                              'cached': max(row['cached'] for row in r['rows'])})
    return {'lines': len(lines), 'oom_count': len(oom), 'oom_first': oom[:3],
            'worker_exit_count': len(worker), 'worker_first': worker[:3],
            'post_requests': sum(statuses.values()), 'post_status': dict(statuses),
            'hot_rounds': len(hot), 'cold_rounds': len(cold), 'rounds_without_prefill': len(no_prefill),
            'hot_rows_distribution': {str(k): v for k, v in sorted(distribution.items())},
            'hot_multirow_within_thresh': anomalies, 'in_flight_rows': len(current),
            'caveat': 'POST 边界近似：并发请求的行可能交错；只统计 #new-seq: 1 的行。'}


def analyze_serve_log(path: Path) -> dict[str, Any]:
    return analyze_lines(path.read_text(encoding='utf-8', errors='replace').splitlines())


def continuation_check(path: Path) -> dict[str, Any]:
    """续段检测（主会话裁定）：按记录的 SHA256 核对脚本后，以 python3 -I 运行，解析其输出的 summary。"""
    if hashlib.sha256(PEER_CHECK.read_bytes()).hexdigest() != PEER_SHA:
        raise SystemExit('cut_continuation_check.py differs from the recorded SHA256; refusing')
    proc = subprocess.run([sys.executable, '-I', str(PEER_CHECK), str(path)], capture_output=True, text=True, timeout=120)
    if proc.returncode:
        raise RuntimeError(f'cut_continuation_check.py failed: {proc.stderr[-300:]}')
    line = proc.stdout.strip().splitlines()[-1]
    name, _, rest = line.partition(' ')
    summary = ast.literal_eval(rest)
    return {'raw': line, 'summary': summary}


def load_observe_rules() -> Any:
    """只导入 observe_overnight.py 的判定函数（该文件以 __main__ 守卫启动，导入无副作用）。"""
    spec = importlib.util.spec_from_file_location('e3_observe_rules', OBSERVE_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observer_state(final: bool) -> dict[str, Any]:
    rules = load_observe_rules()
    rows = [json.loads(line) for line in (OBSERVER_DIR / 'samples.jsonl').read_text().splitlines() if line.strip()]
    not_eligible = []
    for i, row in enumerate(rows, 1):
        if not rules.eligible(row):
            latest = (row.get('watchdog_latest') or {}).get('payload') or {}
            not_eligible.append({'sample': i, 'at': row.get('at'), 'owner': row.get('active_owner_matches'),
                                 'supervisor': row.get('supervisor_alive'), 'service': row.get('service_alive'),
                                 'monitor': row.get('monitor_alive'), 'watchdog_fresh': row.get('watchdog_fresh'),
                                 'alerts': row.get('alerts_count'), 'latest_maintenance': latest.get('maintenance')})
    state: dict[str, Any] = {'samples': len(rows), 'not_eligible': not_eligible,
                             'last_sample_eligible': bool(rows) and bool(rules.eligible(rows[-1])),
                             'start': json.loads((OBSERVER_DIR / 'start.json').read_text())}
    terminal = OBSERVER_DIR / 'terminal.json'
    if final and terminal.exists():
        state['terminal'] = json.loads(terminal.read_text())
    return state


def production_state() -> dict[str, Any]:
    out: dict[str, Any] = {}
    with httpx.Client(trust_env=False, timeout=5.0) as client:
        try:
            response = client.get(HEALTH_URL)
            body = response.json() if 'json' in response.headers.get('content-type', '') else {}
            out['health'] = {'http': response.status_code, 'status': body.get('status'),
                             'maintenance': body.get('maintenance'), 'uptime_s': body.get('uptime_s'),
                             'backend_epoch': body.get('backend_epoch'), 'restart_attempts': body.get('restart_attempts'),
                             'restart_waiters': body.get('restart_waiters')}
        except httpx.HTTPError as exc:
            out['health'] = {'error': repr(exc)}
    if POINTER.exists():
        pointer = json.loads(POINTER.read_text(encoding='utf-8'))
        prereg = json.loads(PREREG.read_text(encoding='utf-8'))
        out['pointer'] = {'approval_id': pointer.get('approval_id'), 'commit': pointer.get('commit'),
                          'argv_equals_prereg_argv_e3': pointer.get('argv') == prereg['argv']['e3'],
                          'pids': {k: pointer[k]['pid'] for k in ('supervisor', 'service', 'monitor')},
                          'alive': {k: Path(f"/proc/{pointer[k]['pid']}/stat").exists() for k in ('supervisor', 'service', 'monitor')}}
    else:
        out['pointer'] = None
    out['gpu_compute_pids'] = subprocess_lines(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'])
    out['gpu_memory_mib'] = subprocess_lines(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
    return out


def subprocess_lines(argv: list[str]) -> list[str]:
    import subprocess
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()] if proc.returncode == 0 else ['error']


def anomalies_of(report: dict[str, Any]) -> list[str]:
    found = []
    serve = report['serve_log']
    if serve['oom_count']:
        found.append(f"OOM 行 {serve['oom_count']} 条")
    if serve['worker_exit_count']:
        found.append(f"worker 退出 {serve['worker_exit_count']} 条")
    cont = serve.get('continuation', {}).get('summary', {})
    for level in ('strict', 'loose'):
        block = cont.get(level, {})
        if block.get('le_32768', 0) > 0:
            found.append(f"续段切段 remain ≤ 32768（{level}）：{block['le_32768']} 对，行号 "
                         + ', '.join(str(p['line']) for p in block.get('le_examples', [])))
    health = report['production'].get('health', {})
    if health.get('http') != 200 or health.get('maintenance') != 'serving':
        found.append(f"健康检查异常：{health}")
    pointer = report['production'].get('pointer')
    if not pointer or not pointer.get('argv_equals_prereg_argv_e3') or pointer.get('commit') != '9db0ee776c25afa8d2719ab700b2de7ccc606142':
        found.append('指针或 argv 与预登记不符')
    return found


def selftest() -> int:
    """合成日志：冷轮、热轮单行、热轮多行（remain ≤ 32768，应报告）、单序列之外的行（应忽略）、OOM 与 worker 标记。"""
    lines = [
        'INFO Prefill batch, #new-seq: 1, #new-token: 512, #cached-token: 0, token usage: 0.9',
        '"POST /v1/completions HTTP/1.1" 200 OK',
        'INFO Prefill batch, #new-seq: 1, #new-token: 1000, #cached-token: 8192, token usage: 0.9',
        '"POST /v1/completions HTTP/1.1" 200 OK',
        'INFO Prefill batch, #new-seq: 1, #new-token: 10000, #cached-token: 8192, token usage: 0.9',
        'INFO Prefill batch, #new-seq: 1, #new-token: 5000, #cached-token: 0, token usage: 0.9',
        '"POST /v1/completions HTTP/1.1" 200 OK',
        'INFO Prefill batch, #new-seq: 2, #new-token: 999, #cached-token: 0, token usage: 0.9',
        '"POST /v1/completions HTTP/1.1" 500 Internal Server Error',
        'ERROR CUDA out of memory while decoding',
        'WARNING backend worker freetoken-TP0-scheduler exited',
    ]
    result = analyze_lines(lines)
    checks = {
        'requests': result['post_requests'] == 4,
        'status': result['post_status'] == {'200': 3, '500': 1},
        'cold_rounds': result['cold_rounds'] == 1,
        'hot_rounds': result['hot_rounds'] == 2,
        'hot_distribution': result['hot_rows_distribution'] == {'1': 1, '2': 1},
        'multirow_reported': len(result['hot_multirow_within_thresh']) == 1 and result['hot_multirow_within_thresh'][0]['remain'] == 15000,
        'oom_counted': result['oom_count'] == 1,
        'worker_counted': result['worker_exit_count'] == 1,
        'two_seq_rows_ignored': result['in_flight_rows'] == 0,
    }
    print(json.dumps({'selftest': checks, 'pass': all(checks.values())}, ensure_ascii=False, indent=1))
    return 0 if all(checks.values()) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='发布 e3 观察检查（只读）')
    parser.add_argument('--label', default='')
    parser.add_argument('--final', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.label:
        raise SystemExit('--label is required')
    report: dict[str, Any] = {'schema': 'ft_e3_observe_check/v1', 'label': args.label,
                              'checked_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                              'production': production_state(),
                              'serve_log': analyze_serve_log(SERVE_LOG),
                              'observer': observer_state(args.final)}
    report['serve_log']['continuation'] = continuation_check(SERVE_LOG)
    report['anomalies'] = anomalies_of(report)
    print(json.dumps({'label': args.label, 'checked_at': report['checked_at'], 'anomalies': report['anomalies'],
                      'continuation': report['serve_log']['continuation']['summary'],
                      'post_requests': report['serve_log']['post_requests'], 'post_status': report['serve_log']['post_status'],
                      'oom_count': report['serve_log']['oom_count'], 'worker_exit_count': report['serve_log']['worker_exit_count'],
                      'hot_rounds': report['serve_log']['hot_rounds'], 'hot_rows_distribution': report['serve_log']['hot_rows_distribution'],
                      'health': report['production'].get('health'), 'observer_samples': report['observer']['samples'],
                      'observer_not_eligible': len(report['observer']['not_eligible']),
                      'observer_last_eligible': report['observer']['last_sample_eligible']}, ensure_ascii=False, indent=1))
    if args.dry_run:
        return 0
    target = WORK / f'OBS_CHECK_{args.label}.json'
    with target.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    os.chmod(target, 0o444)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
