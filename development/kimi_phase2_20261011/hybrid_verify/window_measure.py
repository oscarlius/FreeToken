"""Inert measurement runner for the 2026-10-11 hybrid verification window.

Phases come from KIMI_RUNBOOK_PHASE2_20261011 section 2.4: x_single / x_two on the
frozen X inputs (SHA-pinned, unchanged from the D08/D10 scope), lc1_single on the
frozen 87,328-token real agent conversation, lc2_two on the frozen two-lane
long-context pair. Common settings: temperature=0, top_p=1, ignore_eos=false,
max_tokens=256; speed = 1000 / AIPerf inter_token_latency_ms. A lane with fewer than
128 completion tokens is recorded but not counted; any lane below 7.8 tok/s marks the
measurement abnormal. All commands reuse the frozen allxy_runner CLI shape.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/data2/FreeToken')
OLD = ROOT / 'development/d10_reanalysis_20261010/closed_loop_20261010'
X_SHA = 'f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162'

PHASES = {'x_single': ('X', 1), 'x_two': ('X', 2), 'lc1_single': ('LC1', 1), 'lc2_two': ('LC2', 2)}
PHASE_TIMEOUT_S = {'X': 180, 'LC1': 900, 'LC2': 900}
SHORT_LANE_TOKENS = 128
ABNORMAL_TPS = 7.8


def load_old():
    spec = importlib.util.spec_from_file_location('frozen_allxy', OLD / 'allxy_runner.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, value):
    with Path(path).open('x', encoding='utf8') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def measurement_command(old, endpoint, source, output, count, seconds):
    if count not in (1, 2):
        raise ValueError('only the frozen one/two-request scope is approved')
    argv = old.command(endpoint, source, output, seconds)
    for flag in ('--request-count', '--concurrency'):
        argv[argv.index(flag) + 1] = str(count)
    return argv


def copy_lane0_exact(source, target):
    expected = Path(source).read_bytes().splitlines(keepends=True)[0]
    with Path(target).open('xb') as handle:
        handle.write(expected)
    if Path(target).read_bytes() != expected:
        raise ValueError('single frozen input byte copy differs')


def summarise(old, directory, count, group):
    raw = old.rows(directory / 'profile_export_raw.jsonl')
    records = old.rows(directory / 'profile_export.jsonl')
    if len(raw) != count or len(records) != count:
        raise ValueError('raw/metrics request counts differ')
    metrics = {r['metadata']['x_request_id']: r['metrics'] for r in records}
    if len(metrics) != count:
        raise ValueError('request ids must be unique')
    result = []
    for row in raw:
        if row.get('status') != 200 or row.get('metadata', {}).get('was_cancelled') is not False:
            raise ValueError('HTTP or cancellation contract differs')
        payload = row['payload']
        if tuple(payload.get(k) for k in ('temperature', 'top_p', 'ignore_eos', 'max_tokens')) != (0, 1, False, 256):
            raise ValueError('frozen request parameters differ')
        finishes = []
        for response in row.get('responses', []):
            for packet in response.get('packets', []):
                if packet.get('name') != 'data':
                    continue
                try:
                    chunk = json.loads(packet.get('value', ''))
                except (ValueError, TypeError):
                    continue
                finishes += [c['finish_reason'] for c in chunk.get('choices', []) if c.get('finish_reason')]
        m = metrics[row['metadata']['x_request_id']]
        itl = m['inter_token_latency']
        if itl.get('unit') != 'ms' or not isinstance(itl.get('value'), (int, float)) or itl['value'] <= 0:
            raise ValueError('invalid AIPerf inter_token_latency')
        tokens = m['usage_completion_tokens']['value']
        if not isinstance(tokens, int):
            raise ValueError('raw completion token count unavailable')
        if group == 'X' and (tokens != 256 or finishes != ['length']):
            raise ValueError('invalid arm: X requires exactly 256 length completion')
        result.append({'request_id': row['metadata']['x_request_id'], 'completion_tokens': tokens,
                       'prompt_tokens': m['usage_prompt_tokens']['value'], 'finish_reasons': finishes,
                       'inter_token_latency_ms': itl['value'], 'decode_tps': 1000 / itl['value'],
                       'counted': tokens >= SHORT_LANE_TOKENS})
    return result


def run(admission, service, phase, repeat, pid, ticks, deadline):
    path = Path(admission)
    if path.is_symlink() or path.stat().st_mode & 0o222:
        raise ValueError('sealed root admission is required')
    doc = json.loads(path.read_text())
    if not doc.get('admit') or doc.get('schema') != 'ft_hybrid_verify_20261011/v1':
        raise ValueError('root admission/scope missing')
    if phase not in PHASES:
        raise ValueError('phase not admitted')
    group, count = PHASES[phase]
    if group not in doc['inputs']:
        raise ValueError(f'{group} input not frozen in this admission')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != doc['measure_sha256']:
        raise ValueError('runner source pin differs')
    old = load_old()
    if old.sha(OLD / 'allxy_runner.py') != doc['old_runner_sha256']:
        raise ValueError('frozen CLI source pin differs')
    entry = doc['inputs'][group]
    source = Path(entry['path'])
    if old.sha(source) != entry['sha256']:
        raise ValueError(f'{group} frozen input hash differs')
    if group == 'X':
        if entry['sha256'] != X_SHA:
            raise ValueError('X pin in admission differs from the frozen X SHA')
        old.check_inputs(source, 'X')
    directory = Path(doc['output_root']) / f'service_{service}' / f'{phase}_{repeat}'
    directory.mkdir(parents=True, exist_ok=False)
    executed = source
    if count == 1:
        executed = directory / 'input_lane0.jsonl'
        copy_lane0_exact(source, executed)
    binding = {'group': group, 'source_sha256': entry['sha256'], 'executed_input': str(executed),
               'executed_input_sha256': old.sha(executed),
               'frozen_line_indices': list(range(count)),
               'byte_identical_to_frozen_slice': True}
    write(directory / 'input_binding.json', binding)
    before = old.proc_snapshot(pid)
    if before['service_start_ticks'] != ticks:
        raise RuntimeError('service PID birth mismatch')
    write(directory / 'before.json', before)
    seconds = min(PHASE_TIMEOUT_S[group], int(deadline - time.time()))
    if seconds <= 0:
        raise TimeoutError('window deadline expired before measurement')
    endpoint = f"http://{doc['host']}:{doc['port']}"
    argv = measurement_command(old, endpoint, executed, directory, count, seconds)
    write(directory / 'command.json', argv)
    completed = subprocess.run(argv, capture_output=True, timeout=seconds)
    with (directory / 'stdout.txt').open('xb') as handle:
        handle.write(completed.stdout)
    with (directory / 'stderr.txt').open('xb') as handle:
        handle.write(completed.stderr)
    write(directory / 'exit.json', {'returncode': completed.returncode})
    if completed.returncode:
        raise RuntimeError('AIPerf failed')
    after = old.proc_snapshot(pid)
    write(directory / 'after.json', after)
    if after['service_start_ticks'] != ticks:
        raise RuntimeError('service PID reused')
    result = summarise(old, directory, count, group)
    status = 'abnormal' if any(r['decode_tps'] < ABNORMAL_TPS for r in result) else 'measured'
    write(directory / 'terminal.json',
          {'status': status, 'service': service, 'phase': phase, 'repeat': repeat,
           'calls': count, 'input_binding': binding, 'results': result})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--admission')
    parser.add_argument('--service')
    parser.add_argument('--phase')
    parser.add_argument('--repeat', type=int)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--ticks', type=int)
    parser.add_argument('--deadline', type=float)
    args = parser.parse_args()
    if not args.run:
        print('inert: explicit root-admitted measurement required')
        return
    run(args.admission, args.service, args.phase, args.repeat, args.pid, args.ticks, args.deadline)


if __name__ == '__main__':
    main()
