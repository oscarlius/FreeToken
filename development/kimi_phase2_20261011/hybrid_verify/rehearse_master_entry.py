"""Real-entry rehearsal of the hybrid verification master (CPU only; 481 may keep serving).

Authored by the main session on 2026-10-11 after the 09:15 window01 abort, whose cause
(the master handing its raw window deadline to a service that requires a 60 s reserve)
lived in the master->service hand-off that no CPU test had ever executed.

The rehearsal runs the actual gpu_window.execute() on a copy of the sealed root admission
that differs only in output_root.  Exactly these substitutions are made, because each one
stands for something that cannot run while production serves:
  1. gpu_window.preconditions -> recorded pass (the stopped-production checks);
  2. gpu_window.append_event  -> the real function, with its coordination-log line
     redirected into the rehearsal directory (events.jsonl itself is written unchanged);
  3. __main__.__file__        -> gpu_window.py (the service's master-entry guard);
  4. hybrid_service.idle      -> raises RehearsalStop.  idle() is the first GPU/port step;
     the GPU lock is taken right after it, so nothing past this point is executed.
hybrid_service.require_master_context is wrapped only to record the deadline it receives.

--expect reach_gpu_gate   the first service passes every check up to the GPU gate;
--expect deadline_reject  the first service is rejected by the window-reserve check
                          (negative control: the rehearsal must be able to see the 09:15 bug).
"""
import argparse
import datetime
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

CONTROLLER_FILES = ('gpu_window.py', 'hybrid_service.py', 'window_measure.py', 'warmup_client.py')


class RehearsalStop(Exception):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def make_rehearsal_admission(source, out_dir):
    doc = json.loads(Path(source).read_text())
    copy = dict(doc, output_root=str(out_dir / 'window'))
    changed = sorted(k for k in set(doc) | set(copy) if doc.get(k) != copy.get(k))
    if changed != ['output_root']:
        raise AssertionError(f'rehearsal admission must differ only in output_root, got {changed}')
    target = out_dir / 'ROOT_ADMISSION.rehearsal.json'
    with target.open('x', encoding='utf8') as handle:
        json.dump(copy, handle, indent=2)
        handle.write('\n')
    target.chmod(0o444)
    return target, doc


def rehearse(harness, admission, out_dir, expect, reserve_override):
    sys.path.insert(0, str(harness))
    gpu_window = importlib.import_module('gpu_window')
    hybrid_service = importlib.import_module('hybrid_service')
    for module in (gpu_window, hybrid_service):
        if Path(module.__file__).resolve().parent != harness:
            raise AssertionError(f'{module.__name__} imported from outside the harness directory')

    sandbox = out_dir / 'sandbox_root'
    (sandbox / 'plan').mkdir(parents=True)
    calls = {'preconditions': 0, 'idle': [], 'service_deadline': []}

    def fake_preconditions(doc, d07):
        calls['preconditions'] += 1
        return {'rehearsal_substitute': True}

    real_append = gpu_window.append_event

    def sandboxed_append(output, event, **values):
        saved = gpu_window.ROOT
        gpu_window.ROOT = sandbox
        try:
            return real_append(output, event, **values)
        finally:
            gpu_window.ROOT = saved

    real_require = hybrid_service.require_master_context

    def recording_require(doc, deadline, d07):
        calls['service_deadline'].append(deadline)
        return real_require(doc, deadline, d07)

    def stop_at_gpu_gate(d07, checks=()):
        calls['idle'].append([list(c) for c in checks])
        raise RehearsalStop('reached idle(): the next step takes the GPU lock')

    main_module = sys.modules['__main__']
    saved_main_file = getattr(main_module, '__file__', None)
    gpu_window.preconditions = fake_preconditions
    gpu_window.append_event = sandboxed_append
    hybrid_service.require_master_context = recording_require
    hybrid_service.idle = stop_at_gpu_gate
    if reserve_override is not None:
        if not hasattr(gpu_window, 'SERVICE_RESERVE_SECONDS'):
            raise AssertionError('reserve override needs gpu_window.SERVICE_RESERVE_SECONDS')
        gpu_window.SERVICE_RESERVE_SECONDS = reserve_override
    main_module.__file__ = str(harness / 'gpu_window.py')
    try:
        gpu_window.execute(admission)
    finally:
        main_module.__file__ = saved_main_file

    window = out_dir / 'window'
    events = [json.loads(line) for line in (window / 'events.jsonl').read_text().splitlines()]
    terminal = json.loads((window / 'terminal.json').read_text())
    names = [e['event'] for e in events]
    abort = next((e for e in events if e['event'] == 'service_abort'), {})
    window_deadline = events[0].get('deadline_epoch') if events else None
    reserve = getattr(gpu_window, 'SERVICE_RESERVE_SECONDS', None)
    checks = {
        'event_sequence': names == ['window_started', 'preconditions_passed', 'service_abort', 'window_error'],
        'first_service_is_O1': abort.get('service') == 'O1',
        'preconditions_substitute_called_once': calls['preconditions'] == 1,
    }
    if expect == 'reach_gpu_gate':
        checks.update({
            'abort_is_rehearsal_stop': 'RehearsalStop' in abort.get('error', ''),
            'idle_called_once_on_test_endpoint': calls['idle'] == [[['127.0.0.1', 8123]]],
            'service_deadline_is_window_minus_reserve': (
                reserve is not None and len(calls['service_deadline']) == 1
                and abs(calls['service_deadline'][0] - (window_deadline - reserve)) < 1e-6),
            'reserve_strictly_inside_service_check': reserve is not None and reserve > 60,
        })
    else:
        checks.update({
            'abort_is_window_reserve_reject': 'service deadline escapes the window reserve' in abort.get('error', ''),
            'idle_never_reached': calls['idle'] == [],
        })
    return {
        'events': names, 'service_abort_error': abort.get('error'), 'terminal_error': terminal.get('error'),
        'window_deadline_epoch': window_deadline, 'service_deadline_received': calls['service_deadline'],
        'service_reserve_seconds': reserve, 'idle_calls': calls['idle'], 'checks': checks,
        'passed': all(checks.values()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--admission', required=True, help='sealed ROOT_ADMISSION.json to copy')
    parser.add_argument('--out-dir', required=True, help='new directory for this rehearsal')
    parser.add_argument('--expect', required=True, choices=('reach_gpu_gate', 'deadline_reject'))
    parser.add_argument('--reserve-override', type=float, default=None)
    parser.add_argument('--harness-dir', default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    harness = Path(args.harness_dir).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    admission, source_doc = make_rehearsal_admission(args.admission, out_dir)
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    observed = rehearse(harness, admission, out_dir, args.expect, args.reserve_override)
    receipt = {
        'schema': 'ft_hybrid_master_entry_rehearsal/v1', 'at': now(),
        'expect': args.expect, 'reserve_override': args.reserve_override,
        'script_sha256': sha(__file__), 'harness_dir': str(harness),
        'controller_sha256': {name: sha(harness / name) for name in CONTROLLER_FILES},
        'source_admission': str(Path(args.admission).resolve()),
        'source_admission_sha256': sha(args.admission),
        'rehearsal_admission_sha256': sha(admission),
        'differs_only_in': ['output_root'],
        'substitutions': ['gpu_window.preconditions', 'gpu_window.append_event(log line only)',
                          '__main__.__file__', 'hybrid_service.idle'],
        'source_output_root_untouched': source_doc['output_root'],
        **observed,
    }
    path = out_dir / 'REHEARSAL_RECEIPT.json'
    with path.open('x', encoding='utf8') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')
    path.chmod(0o444)
    print(('REHEARSAL PASS ' if receipt['passed'] else 'REHEARSAL FAIL ') + args.expect + ' ' + sha(path))
    raise SystemExit(0 if receipt['passed'] else 1)


if __name__ == '__main__':
    main()
