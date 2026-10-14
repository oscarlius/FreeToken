"""Run one review-gated restore, with mandatory stop-before-rollback recovery.

发布 e3 补充 1（OPHAK_RELEASE_E3_ADDENDUM1_20261012.md，SHA256 7fee5a52…）：
- execute() 在 start 之前做 W3.5 只读预检（e3_probe.run_precheck）。不通过则不启动任何服务、不进入恢复路由，返回 PRECHECK_RC。
- 启动失败或冒烟失败后，recover_after_restore_failure 先轮询最长 60 秒（每 2 秒）：
  已接管 → 运行本包 stop_approved_restore.py；返回 0 后启动 restore14，非 0 则状态不明；
  确认不存在（连续两次）→ 跳过 stop，直接启动 restore14；
  状态不明 → 不启动 restore14，写 ROUTING_AMBIGUOUS.json，返回 AMBIGUOUS_RC。
- 本包从不启动 ROLLBACK184。restore14 与 stop_approved_restore.py 保持原样。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
AMBIGUOUS_RC = 3


def _load_probe() -> Any:
    spec = importlib.util.spec_from_file_location('e3_probe', HERE / 'e3_probe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe_module = _load_probe()
live_probe = probe_module.live_probe
run_precheck = probe_module.run_precheck
POLL_S = probe_module.POLL_S
POLL_WINDOW_S = probe_module.POLL_WINDOW_S
PRECHECK_RC = probe_module.PRECHECK_RC


def load() -> dict[str, Any]:
    return json.loads((HERE / 'DEPLOYMENT_APPROVAL.json').read_text())


def command(name: str) -> list[str]:
    return [sys.executable, str(HERE / name)]


def write_new(path: Path, value: dict[str, Any]) -> None:
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write('\n')


def require_root_final_review(approval: dict[str, Any]) -> None:
    review_path = HERE / 'ROOT_FINAL_REVIEW.json'
    if not approval['conditions_met'] or not review_path.is_file():
        raise RuntimeError('PENDING root final review: execution refused')
    review = json.loads(review_path.read_text())
    approval_bytes = (HERE / 'DEPLOYMENT_APPROVAL.json').read_bytes()
    if hashlib.sha256(approval_bytes).hexdigest() != review.get('approval_sha256') or json.loads(approval_bytes) != approval:
        raise RuntimeError('restore approval content differs from final review')
    if (review.get('verdict') != 'PASS' or review.get('reviewer_role') != 'root_independent_final_reviewer'
            or review.get('package_source_manifest_sha256') != approval['package_source_manifest_sha256']
            or review.get('approval_id') != approval['approval_id']):
        raise RuntimeError('root final review is not bound to this exact package')
    manifest_path = HERE / 'SOURCE_MANIFEST.json'
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != review['package_source_manifest_sha256']:
        raise RuntimeError('restore package source manifest changed')
    manifest = json.loads(manifest_path.read_text())
    for name, digest in manifest['files'].items():
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('restore package source changed: ' + name)


def pointer_matches(pointer: Any, approval: dict[str, Any]) -> bool:
    return (isinstance(pointer, dict) and pointer.get('approval_id') == approval['approval_id']
            and pointer.get('commit') == approval['restore_commit'])


def classify(snapshot: dict[str, Any], approval: dict[str, Any]) -> str:
    """'foreign'：指针属于其他 owner，或只对上一项（归状态不明）；'takeover'：e3 已接管；
    'absent'：确认不存在；'busy'：其它（继续轮询）。"""
    if snapshot['pointer_exists'] and not pointer_matches(snapshot['pointer'], approval):
        return 'foreign'
    if snapshot['owner_json'] or pointer_matches(snapshot['pointer'], approval):
        return 'takeover'
    quiet = not (snapshot['processes'] or snapshot['listeners'] or snapshot['compute_pids'])
    if quiet and not snapshot['lock_exists'] and not snapshot['pointer_exists']:
        return 'absent'
    return 'busy'


def start_restore14(runner: Callable[..., Any]) -> int:
    return runner([sys.executable, str((HERE.parent / 'restore14') / 'deploy_conditional.py'), '--execute']).returncode


def ambiguous(approval: dict[str, Any], snapshot: Any, reason: str) -> int:
    run_dir = Path(approval['run_dir'])
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / 'ROUTING_AMBIGUOUS.json'
    write_new(path, {'schema': 'ft_routing_ambiguous/v1', 'approval_id': approval['approval_id'], 'reason': reason,
                     'restore14_started': False, 'snapshot': snapshot, 'at': time.time()})
    print(json.dumps({'event': 'routing_ambiguous', 'reason': reason, 'file': str(path)}, ensure_ascii=False),
          file=sys.stderr, flush=True)
    return AMBIGUOUS_RC


def recover_after_restore_failure(runner: Callable[..., Any], *,
                                  probe: Callable[[dict[str, Any]], dict[str, Any]] = live_probe,
                                  clock: Callable[[], float] = time.monotonic,
                                  sleep: Callable[[float], None] = time.sleep) -> int:
    """e3 失败路由（补充 1 §1）。ROLLBACK184 从不由本包启动。"""
    approval = load()
    failed = Path(approval['run_dir'])
    smoke = failed / 'smoke_execution_result.json'
    if failed.exists() and not smoke.exists():
        write_new(smoke, {'classification': 'failed', 'exit_code': 1, 'at': time.time(),
                          'phase': 'e3_start_or_readiness', 'smoke_generation_completed': False})
    deadline = clock() + POLL_WINDOW_S
    absent_polls = 0
    while True:
        try:
            snapshot = probe(approval)
        except Exception as exc:  # noqa: BLE001 - 探测失败时不能确认不存在，按状态不明处理
            return ambiguous(approval, None, f'probe failed, absence cannot be confirmed: {exc!r}')
        verdict = classify(snapshot, approval)
        if verdict == 'foreign':
            return ambiguous(approval, snapshot, 'production pointer belongs to another owner or matches only part of e3')
        if verdict == 'takeover':
            stop = runner(command('stop_approved_restore.py'))
            if stop.returncode:
                return ambiguous(approval, snapshot, f'stop_approved_restore.py returned {stop.returncode}; restore14 not started')
            return start_restore14(runner)
        absent_polls = absent_polls + 1 if verdict == 'absent' else 0
        if absent_polls >= 2:
            return start_restore14(runner)
        if clock() >= deadline:
            return ambiguous(approval, snapshot, 'no takeover and no confirmed absence within 60 seconds')
        sleep(POLL_S)


def execute(runner: Callable[..., Any] = subprocess.run, *, probe: Callable[[dict[str, Any]], dict[str, Any]] = live_probe,
            clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> int:
    approval = load()
    require_root_final_review(approval)
    gate = run_precheck(approval, probe=probe, clock=clock, sleep=sleep)
    if gate:
        return gate

    def recover() -> int:
        return recover_after_restore_failure(runner, probe=probe, clock=clock, sleep=sleep)

    try:
        started = runner(command('start_approved_release.py'))
    except subprocess.SubprocessError:
        return recover()
    if started.returncode:
        return recover()
    smoke = runner(command('wait_release_and_smoke.py'))
    if smoke.returncode:
        return recover()
    return runner(command('post_night_observer.py')).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--plan', action='store_true')
    actions.add_argument('--precheck', action='store_true')
    actions.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps(load(), sort_keys=True))
        return 0
    approval = load()
    require_root_final_review(approval)
    if args.precheck:
        return run_precheck(approval)
    return execute()


if __name__ == '__main__':
    raise SystemExit(main())
