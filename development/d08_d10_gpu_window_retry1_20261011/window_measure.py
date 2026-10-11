"""Inert X-only runner for the user-approved single/hybrid measurements."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/data2/FreeToken')
OLD = ROOT / 'development/d10_reanalysis_20261010/closed_loop_20261010'
X_SHA = 'f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162'

def load_old():
    spec = importlib.util.spec_from_file_location('frozen_allxy', OLD/'allxy_runner.py')
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
        argv[argv.index(flag)+1] = str(count)
    return argv

def copy_lane0_exact(source,target):
    expected=Path(source).read_bytes().splitlines(keepends=True)[0]
    with Path(target).open('xb') as handle:handle.write(expected)
    if Path(target).read_bytes()!=expected:raise ValueError('single frozen input byte copy differs')

def summarise(old, directory, count):
    raw = old.rows(directory/'profile_export_raw.jsonl')
    records = old.rows(directory/'profile_export.jsonl')
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
        if tuple(payload.get(k) for k in ('temperature','top_p','ignore_eos','max_tokens')) != (0,1,False,256):
            raise ValueError('frozen X parameters differ')
        finishes = []
        for response in row.get('responses', []):
            for packet in response.get('packets', []):
                if packet.get('name') != 'data':
                    continue
                try:
                    chunk = json.loads(packet.get('value', ''))
                except (ValueError, TypeError):
                    continue
                finishes += [c['finish_reason'] for c in chunk.get('choices',[]) if c.get('finish_reason')]
        m = metrics[row['metadata']['x_request_id']]
        itl = m['inter_token_latency']
        if itl.get('unit') != 'ms' or not isinstance(itl.get('value'), (int,float)) or itl['value'] <= 0:
            raise ValueError('invalid AIPerf inter_token_latency')
        tokens = m['usage_completion_tokens']['value']
        if tokens != 256 or finishes != ['length']:
            raise ValueError('invalid arm: X requires exactly 256 length completion')
        result.append({'request_id':row['metadata']['x_request_id'], 'completion_tokens':tokens,
                       'prompt_tokens':m['usage_prompt_tokens']['value'], 'finish_reasons':finishes,
                       'inter_token_latency_ms':itl['value'], 'decode_tps':1000/itl['value']})
    return result

def run(admission, phase, pid, ticks, deadline):
    path=Path(admission)
    if path.is_symlink() or path.stat().st_mode & 0o222:
        raise ValueError('sealed root admission is required')
    doc = json.loads(Path(admission).read_text())
    if not doc.get('admit') or phase not in ('offload_single','hybrid_single','hybrid_two'):
        raise ValueError('root admission/scope missing')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != doc['measure_sha256']:
        raise ValueError('runner source pin differs')
    old = load_old()
    if old.sha(OLD/'inputs_X.jsonl') != X_SHA or old.sha(OLD/'allxy_runner.py') != doc['old_runner_sha256']:
        raise ValueError('frozen X/CLI source pin differs')
    old.check_inputs(OLD/'inputs_X.jsonl', 'X')
    count = 2 if phase == 'hybrid_two' else 1
    directory = Path(doc['output_root'])/phase
    directory.mkdir(exist_ok=False)
    source = OLD/'inputs_X.jsonl'
    if count == 1:
        source = directory/'input_lane0.jsonl'
        copy_lane0_exact(OLD/'inputs_X.jsonl',source)
    expected_bytes=(OLD/'inputs_X.jsonl').read_bytes()
    if count == 1:
        expected_bytes=expected_bytes.splitlines(keepends=True)[0]
    if source.read_bytes() != expected_bytes:
        raise ValueError('executed dataset differs from frozen source slice')
    binding={'source_x_sha256':X_SHA,'executed_input':str(source),
             'executed_input_sha256':old.sha(source),'frozen_line_indices':list(range(count)),
             'byte_identical_to_frozen_slice':True}
    write(directory/'input_binding.json',binding)
    before = old.proc_snapshot(pid)
    if before['service_start_ticks'] != ticks:
        raise RuntimeError('service PID birth mismatch')
    write(directory/'before.json', before)
    seconds = min(180, int(deadline-time.time()))
    if seconds <= 0:
        raise TimeoutError('window deadline expired before measurement')
    argv = measurement_command(old, 'http://172.16.108.9:8095', source, directory, count, seconds)
    write(directory/'command.json', argv)
    completed = subprocess.run(argv, capture_output=True, timeout=seconds)
    with (directory/'stdout.txt').open('xb') as handle: handle.write(completed.stdout)
    with (directory/'stderr.txt').open('xb') as handle: handle.write(completed.stderr)
    write(directory/'exit.json', {'returncode':completed.returncode})
    if completed.returncode:
        raise RuntimeError('AIPerf failed')
    after = old.proc_snapshot(pid)
    write(directory/'after.json', after)
    if after['service_start_ticks'] != ticks:
        raise RuntimeError('service PID reused')
    result = summarise(old, directory, count)
    status = 'abnormal' if any(r['decode_tps'] < 7.8 for r in result) else 'measured'
    write(directory/'terminal.json', {'status':status,'phase':phase,'calls':count,'input_binding':binding,'results':result})
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--admission');parser.add_argument('--phase');parser.add_argument('--pid',type=int);parser.add_argument('--ticks',type=int);parser.add_argument('--deadline',type=float);args=parser.parse_args()
    if not args.run:
        print('inert: explicit root-admitted measurement required');return
    run(args.admission,args.phase,args.pid,args.ticks,args.deadline)

if __name__=='__main__': main()
