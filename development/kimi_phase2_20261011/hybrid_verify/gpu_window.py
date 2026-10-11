"""Explicit root-admitted hybrid verification window: O1 -> H1 -> H2 -> O2.

KIMI_RUNBOOK_PHASE2_20261011 section 2.4. The window does NOT stop or restore the
production 481 service: stage 2 does that with the separately reviewed restore08
tooling. This master refuses to start unless the frozen production owner is already
gone (recorded supervisor/service/monitor PIDs dead, LAN production port bindable,
no ft serve process, overnight observer exited, GPU lock absent). Every service runs
through hybrid_service.execute with its own GPU lock and cleanup proof; a measurement
failure skips to the next service, an unproven cleanup aborts the window. After the
last service the pre-registered J1-J5 criteria are computed mechanically into
verdict.json.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path('/data2/FreeToken')
HERE = Path(__file__).resolve().parent
X_SHA = 'f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162'
CONTROLLER_FILES = ('gpu_window.py', 'hybrid_service.py', 'window_measure.py', 'warmup_client.py')
# hybrid_service.require_master_context rejects any service deadline later than the
# window deadline minus 60 s; handing over window - 120 s keeps that check strict.
SERVICE_RESERVE_SECONDS = 120


def validate_controller_pins(doc):
    required = {str(HERE / name) for name in CONTROLLER_FILES}
    pins = doc.get('controller_source_pins', {})
    if set(pins) != required:
        raise ValueError('controller source pin set incomplete or unexpected')
    for file, digest in pins.items():
        if hashlib.sha256(Path(file).read_bytes()).hexdigest() != digest:
            raise ValueError('controller source pin differs')


def append_event(output, event, **values):
    import datetime
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    record = {'at': now, 'event': event, **values}
    with (output / 'events.jsonl').open('a') as handle:
        handle.write(json.dumps(record) + '\n')
    line = '\n- ' + now + ' | HYBRID_VERIFY_WINDOW | ' + event + ' | ' + json.dumps(values, ensure_ascii=False) + '\n'
    with (ROOT / 'plan/COORDINATION_LOG.md').open('a', encoding='utf8') as handle:
        handle.write(line)
    print(json.dumps(record), flush=True)


def load_d07():
    spec = importlib.util.spec_from_file_location('window_d07', ROOT / 'development/d07_g3g4_prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _production_gone(doc, d07):
    baseline = doc['baseline_owner']
    problems = []
    active_path = ROOT / 'run/production.active.json'
    live = json.loads(active_path.read_text()) if active_path.exists() else None
    if live is not None and live != baseline:
        problems.append('production.active.json differs from the admitted baseline owner; re-review required')
    for role in ('supervisor', 'service', 'monitor'):
        recorded = baseline.get(role) or {}
        pid = recorded.get('pid')
        if not pid:
            continue
        identity = d07.process_identity(pid)
        if identity and identity.get('start_ticks') == recorded.get('start_ticks'):
            problems.append(f'production {role} pid {pid} still alive')
    try:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('172.16.108.9', 8095))
    except OSError:
        problems.append('LAN production port 8095 is not bindable (481 still serving?)')
    listing = subprocess.check_output(['ps', '-eo', 'pid,args'], text=True)
    serves = [line.strip() for line in listing.splitlines()
              if 'ft' in line and 'serve' in line and 'grep' not in line and str(os.getpid()) not in line]
    serves = [line for line in serves if '/bin/ft serve' in line or line.split(None, 1)[1].startswith('ft serve')]
    if serves:
        problems.append(f'ft serve processes remain: {serves}')
    observer_start = Path(baseline['run_dir']) / 'overnight_observation/start.json'
    if not observer_start.exists():
        problems.append(f'overnight observer start.json missing at {observer_start}')
    else:
        observer = json.loads(observer_start.read_text())
        pid = observer.get('observer_pid')
        identity = d07.process_identity(pid) if pid else None
        if identity and pid and identity.get('state') != 'Z':
            problems.append(f'overnight observer pid {pid} still running (must exit on its own)')
    if Path('/data2/_shared/gpu.lock').exists():
        problems.append('GPU owner lock file exists; stage-2 T16 tooling must have released it')
    return problems


def _verify_frozen_inputs(doc):
    old_sha = None
    pins = {}
    for group, entry in doc['inputs'].items():
        digest = hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()
        if digest != entry['sha256']:
            raise ValueError(f'{group} frozen input hash differs')
        pins[group] = digest
    if pins.get('X') != X_SHA:
        raise ValueError('X input is not the frozen D08/D10 X')
    return pins


def preconditions(doc, d07):
    problems = _production_gone(doc, d07)
    if problems:
        raise RuntimeError('stopped-production preconditions unmet: ' + json.dumps(problems, ensure_ascii=False))
    return {'production_pids_dead': True, 'lan_8095_bindable': True, 'no_ft_serve': True,
            'observer_exited': True, 'gpu_lock_absent': True}


def measurement_lanes(output, service, phase):
    lanes = []
    base = output / f'service_{service}'
    if not base.exists():
        return lanes
    for directory in sorted(base.glob(f'{phase}_*')):
        terminal = directory / 'terminal.json'
        if not terminal.exists():
            continue
        doc = json.loads(terminal.read_text())
        for row in doc.get('results', []):
            lanes.append({'service': service, 'phase': phase, 'repeat': doc.get('repeat'),
                          'status': doc.get('status'), 'directory': str(directory), **row})
    return lanes


def quality_score(output, service):
    path = output / f'service_{service}' / 'quality60_score.json'
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def compute_verdicts(output, doc):
    spec = importlib.util.spec_from_file_location('output_compare', doc['output_compare_path'])
    compare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare)

    def lane_speeds(service, phase, counted_only=True):
        rows = measurement_lanes(output, service, phase)
        return [r['decode_tps'] for r in rows if r['status'] == 'measured' and (r['counted'] or not counted_only)]

    all_lanes = [lane for service in doc['service_order'] for phase in
                 ('x_single', 'x_two', 'lc1_single', 'lc2_two')
                 for lane in measurement_lanes(output, service, phase)]
    abnormal = [r for r in all_lanes if r['status'] == 'abnormal' or r['decode_tps'] < 7.8]
    short = [r for r in all_lanes if not r['counted']]

    verdict = {'criteria': {}, 'abnormal_lanes': abnormal, 'short_lanes_excluded': short}

    o_two = lane_speeds('O1', 'x_two') + lane_speeds('O2', 'x_two')
    h1_two = lane_speeds('H1', 'x_two')
    if not o_two or not h1_two:
        verdict['criteria']['J1'] = {'status': 'no_data', 'question': '两路收益'}
    else:
        reference = _mean(o_two)
        threshold = reference * 1.15
        verdict['criteria']['J1'] = {
            'question': '两路收益', 'offload_two_lane_speeds': o_two, 'offload_mean': reference,
            'h1_two_lane_speeds': h1_two, 'threshold': threshold,
            'status': 'met' if min(h1_two) >= threshold else 'not_met'}

    o1_two, o2_two = lane_speeds('O1', 'x_two'), lane_speeds('O2', 'x_two')
    if not o1_two or not o2_two:
        verdict['criteria']['J2'] = {'status': 'no_data', 'question': '测量漂移'}
    else:
        m1, m2 = _mean(o1_two), _mean(o2_two)
        drift = abs(m1 - m2) / _mean([m1, m2])
        verdict['criteria']['J2'] = {'question': '测量漂移', 'o1_mean': m1, 'o2_mean': m2,
                                     'relative_drift': drift,
                                     'status': 'met' if drift <= 0.05 else 'drift'}

    q_o1, q_h1 = quality_score(output, 'O1'), quality_score(output, 'H1')
    if not q_o1 or not q_h1:
        verdict['criteria']['J3'] = {'status': 'no_data', 'question': '质量等价'}
    else:
        verdict['criteria']['J3'] = {'question': '质量等价', 'o1_pass': q_o1['score_pass'],
                                     'h1_pass': q_h1['score_pass'],
                                     'status': 'met' if q_h1['score_pass'] >= q_o1['score_pass'] - 3 else 'not_met'}

    def outputs_of(service, phase, repeat):
        path = output / f'service_{service}' / f'{phase}_{repeat}' / 'profile_export_raw.jsonl'
        return compare.outputs(path) if path.exists() else None

    j4_groups = {}
    reproducible = True
    for name, a, b in (('H1_x_single_repeat1_vs_repeat2', ('H1', 'x_single', 1), ('H1', 'x_single', 2)),
                       ('H1_x_two_repeat1_vs_repeat2', ('H1', 'x_two', 1), ('H1', 'x_two', 2)),
                       ('H2_x_single_vs_H1_x_single_1', ('H2', 'x_single', 1), ('H1', 'x_single', 1))):
        left, right = outputs_of(*a), outputs_of(*b)
        if left is None or right is None:
            j4_groups[name] = {'status': 'no_data'}
            reproducible = False
            continue
        diffs = {}
        for prompt in sorted(set(left) & set(right)):
            position = compare.first_diff(left[prompt], right[prompt])
            if position is not None:
                diffs[str(prompt)] = {'first_diff_char': position,
                                      'len_a': len(left[prompt]), 'len_b': len(right[prompt])}
        if diffs:
            reproducible = False
        j4_groups[name] = {'status': 'identical' if not diffs else 'differs', 'diffs': diffs}
    verdict['criteria']['J4'] = {'question': '自身复现性', 'groups': j4_groups,
                                 'status': 'reproducible' if reproducible else 'affected'}

    j5 = {'question': '长上下文（只记录）'}
    for phase in ('lc1_single', 'lc2_two'):
        if phase == 'lc2_two' and 'LC2' not in doc['inputs']:
            j5[phase] = {'status': 'not_in_admission'}
            continue
        o = lane_speeds('O1', phase) + lane_speeds('O2', phase)
        h = lane_speeds('H1', phase)
        j5[phase] = {'offload_mean': _mean(o), 'h1_mean': _mean(h),
                     'ratio': (_mean(h) / _mean(o)) if o and h else None,
                     'status': 'recorded' if o and h else 'no_data'}
    verdict['criteria']['J5'] = j5

    verdict['overall'] = 'abnormal' if abnormal else 'complete'
    return verdict


def execute(path):
    path = Path(path)
    doc = json.loads(path.read_text())
    if path.is_symlink() or path.stat().st_mode & 0o222 or not doc.get('admit'):
        raise ValueError('sealed root admission required')
    if doc.get('schema') != 'ft_hybrid_verify_20261011/v1':
        raise ValueError('admission schema differs')
    validate_controller_pins(doc)
    input_pins = _verify_frozen_inputs(doc)
    for key in ('old_runner_sha256', 'output_compare_sha256'):
        target = doc['old_runner_path'] if key == 'old_runner_sha256' else doc['output_compare_path']
        if hashlib.sha256(Path(target).read_bytes()).hexdigest() != doc[key]:
            raise ValueError(f'{key} pin differs')
    q = doc['quality60']
    for pinned, actual in ((q['script'], q['script_sha256']), (q['prompts'], q['prompts_sha256'])):
        if hashlib.sha256(Path(pinned).read_bytes()).hexdigest() != actual:
            raise ValueError('quality60 pin differs')
    for key in ('warmup_adapter_path', 'warmup_inputs_path'):
        if hashlib.sha256(Path(doc[key]).read_bytes()).hexdigest() != doc[key.replace('_path', '_sha256')]:
            raise ValueError('warmup pin differs')
    d07 = load_d07()
    output = Path(doc['output_root'])
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    deadline = started + doc['window_limit_seconds']
    error = None
    append_event(output, 'window_started', deadline_epoch=deadline,
                 window_limit_seconds=doc['window_limit_seconds'],
                 input_pins=input_pins, service_order=doc['service_order'],
                 master_identity=d07.process_identity(os.getpid()))
    try:
        checks = preconditions(doc, d07)
        append_event(output, 'preconditions_passed', **checks)
        from hybrid_service import execute as run_service
        for label in doc['service_order']:
            try:
                measured = run_service(path, label, deadline - SERVICE_RESERVE_SECONDS)
                append_event(output, 'service_terminal', service=label, measured=measured)
            except BaseException as exc:
                append_event(output, 'service_abort', service=label, error=repr(exc))
                raise
        verdict = compute_verdicts(output, doc)
        with (output / 'verdict.json').open('x', encoding='utf8') as handle:
            json.dump(verdict, handle, indent=2)
            handle.write('\n')
        append_event(output, 'verdicts_computed', overall=verdict['overall'],
                     criteria={k: v.get('status') for k, v in verdict['criteria'].items()})
    except BaseException as exc:
        error = repr(exc)
        append_event(output, 'window_error', error=error)
    with (output / 'terminal.json').open('x', encoding='utf8') as handle:
        json.dump({'error': error, 'elapsed_seconds': time.time() - started,
                   'window_limit_seconds': doc['window_limit_seconds'],
                   'deadline_exceeded': time.time() > deadline,
                   'production_stop_or_restore_attempted_by_this_tool': False,
                   'push_executed': False}, handle, indent=2)
        handle.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    if not args.execute:
        print('inert')
        return
    execute(args.admission)


if __name__ == '__main__':
    main()
