"""R052's exact R011 trace replay and single owned service; no standalone launch."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import os
import shutil
import sys

TRACE = Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json')
TRACE_SHA = '097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24'
CLIENT_SHA = '332a1870378d5bffa4891180280060e70f6135b6acff21b48603a5fc98ad44d9'
TARGET_INDEX = 7
TARGET_MESSAGES_SHA = 'e3a67ebe075b0126'
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
ENV_KEYS=('PYTHONPATH','VIRTUAL_ENV','CUDA_VISIBLE_DEVICES','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED','FT_D3_TRACE','FT_DEV_D0','FT_DEV_D0_PATH','FT_DEV_D0_TIMELINE','FT_DEV_D0_TIMELINE_STEPS','FT_R052_WORKER_SHUTDOWN')


def private_port_pair():
    path = Path(__file__).with_name('ft_batch_port_pair_v1.py')
    spec = importlib.util.spec_from_file_location('r052_port_pair', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    port = module.dynamic_port()
    return port, module.port_receipt(port)

def _probe(path,purpose):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as output: json.dump({'schema':'ft_r052_cpu_file_probe/v1','kind':'CPU_FILE_PROBE','not_measurement':True,'purpose':purpose},output,sort_keys=True)
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'purpose':purpose}


def client_module(worktree):
    path = worktree / 'scripts/_agent_trace_original.py'
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != CLIENT_SHA:
        raise RuntimeError('R052 reviewed replay client differs')
    spec = importlib.util.spec_from_file_location('r052_original_agent_trace', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def bind_trace(directory, source=TRACE):
    if source.is_symlink():
        raise RuntimeError('R052 trace must not be a symlink')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != TRACE_SHA:
        raise RuntimeError('R052 trace differs from retained R011 input')
    doc = json.loads(raw)
    if len(doc.get('rounds', [])) <= TARGET_INDEX:
        raise RuntimeError('R052 trace lacks the target round')
    path = directory / 'trace_input.json'
    with path.open('xb') as output:
        output.write(raw)
    path.chmod(0o444)
    return doc


def strict_usage(usage):
    if not isinstance(usage, dict):
        raise ValueError('response lacks actual usage')
    counts = [usage.get('prompt_tokens'), usage.get('completion_tokens')]
    details = usage.get('prompt_tokens_details')
    cached = None if details is None else details.get('cached_tokens') if isinstance(details, dict) else False
    if any(type(value) is not int or value < 0 for value in counts):
        raise ValueError('response usage counts are missing or invalid')
    if cached is not None and (type(cached) is not int or cached < 0):
        raise ValueError('response cached_tokens is missing or invalid')
    if counts[0] <= 0 or (cached is not None and cached > counts[0]):
        raise ValueError('response prompt/cache counts are inconsistent')
    return *counts, cached


def stream_uid(events):
    """Bind one actual request to its OpenAI SSE id, with optional dev cross-check."""
    sse_ids = {event['id'] for event in events if isinstance(event, dict) and event.get('id') is not None}
    if not sse_ids:
        raise RuntimeError('R052 response lacks an actual SSE id')
    if any(not isinstance(value, str) or not re.fullmatch(r'chatcmpl-(\d+)', value) for value in sse_ids):
        raise RuntimeError('R052 response SSE id is invalid')
    uids = {int(value.removeprefix('chatcmpl-')) for value in sse_ids}
    if len(uids) != 1:
        raise RuntimeError('R052 response contains different SSE ids')
    dev_uids = {event['ft_dev']['uid'] for event in events
                if isinstance(event, dict) and isinstance(event.get('ft_dev'), dict)
                and type(event['ft_dev'].get('uid')) is int}
    if dev_uids and dev_uids != uids:
        raise RuntimeError('R052 SSE id and ft_dev UID differ')
    uid = next(iter(uids))
    return {'uid': uid, 'sse_id': f'chatcmpl-{uid}', 'ft_dev_uid': uid if dev_uids else None}


def target_binding(trace, client):
    """Apply the formal R011 target check without sending a request."""
    row = trace['rounds'][TARGET_INDEX]
    digest = client.messages_digest(row['messages'])
    if row.get('record', {}).get('messages_sha') not in {None, digest}:
        raise RuntimeError('R052 retained message binding differs')
    if digest != TARGET_MESSAGES_SHA:
        raise RuntimeError('R052 target message identity differs from R011')
    return {'trace_index': TARGET_INDEX, 'history_uid': 8, 'messages_sha': digest}


def request(client, port, messages, tools, thinking, max_tokens):
    payload = client.build_payload(messages, MODEL, tools, thinking, max_tokens)
    events = []
    def captured():
        for event in client.post_events(f'http://127.0.0.1:{port}/v1/chat/completions', payload, 1800):
            events.append(event)
            yield event
    result = client.consume_stream(captured(), time.perf_counter())
    if result.get('finish_reason') not in {'stop', 'length', 'tool_calls'}:
        raise RuntimeError('R052 response did not finish')
    prompt, completion, cached = strict_usage(result.get('usage'))
    identity = stream_uid(events)
    return {'payload': payload, 'stream_events': events, 'response': result,
            'prompt_tokens': prompt, 'completion_tokens': completion, 'cached_tokens': cached,
            'api_cached_tokens': cached, **identity}


def replay_to_target(port, directory, trace, client):
    tools = trace.get('tools') or client.tool_specs()
    thinking = bool(trace.get('meta', {}).get('params', {}).get('thinking', True))
    records = []
    for index, row in enumerate(trace['rounds'][:TARGET_INDEX + 1]):
        messages = copy.deepcopy(row['messages'])
        digest = client.messages_digest(messages)
        if row.get('record', {}).get('messages_sha') not in {None, digest}:
            raise RuntimeError('R052 retained message binding differs')
        if index == TARGET_INDEX:
            target_binding(trace, client)
        record = request(client, port, messages, tools, thinking, 200)
        record.update(trace_index=index, messages_sha=digest)
        records.append(record)
        with (directory / f'replay_{index:02}.json').open('x') as output:
            json.dump(record, output, ensure_ascii=False, indent=2)
    response = records[-1]['response']
    assistant = client.assistant_message(response)
    if response.get('reasoning_text'):
        assistant['reasoning_content'] = response['reasoning_text']
    if not assistant.get('content') and not assistant.get('reasoning_content') and not assistant.get('tool_calls'):
        raise RuntimeError('R052 target actual output is empty')
    return {'history_uid': 8, 'trace_index': TARGET_INDEX, 'uid': records[-1]['uid'],
            'sse_id': records[-1]['sse_id'], 'ft_dev_uid': records[-1]['ft_dev_uid'],
            'messages': records[-1]['payload']['messages'], 'messages_sha': TARGET_MESSAGES_SHA,
            'text': response['content_text'], 'assistant_message': assistant,
            'prompt_tokens': records[-1]['prompt_tokens'], 'completion_tokens': records[-1]['completion_tokens'],
            'cached_tokens': records[-1]['cached_tokens'], 'tools': tools, 'thinking': thinking,
            'replay_count': len(records), 'trace_sha256': TRACE_SHA}


def followup(client, port, messages, target):
    return request(client, port, messages, target['tools'], target['thinking'], 64)


def prepare_service_files(gate,directory,worktree,port,*,file_dry_run=False):
    env = gate.clean_environment(worktree)
    env.update(FT_D3_TRACE='1', FT_DEV_D0='1', FT_DEV_D0_PATH=str(directory / 'd0'),
               FT_DEV_D0_TIMELINE='1', FT_DEV_D0_TIMELINE_STEPS='20000',
               FT_R052_WORKER_SHUTDOWN=str(directory / 'worker_shutdown.json'))
    argv = gate.serve_argv(port)
    for key in ("--kv-reserve-tokens", "--max-seq-len-override"):
        argv[argv.index(key) + 1] = "98304"
    argv.remove('--prefill-layer-major')
    argv[argv.index('--mamba-host-slots') + 1] = '32'
    runtime = directory / 'runtime'
    runtime.mkdir(mode=0o700)
    source = Path(__file__).with_name('r052_d0_shutdown_startup_v2.py')
    if source.is_symlink() or not source.is_file():
        raise RuntimeError('R052 shutdown wrapper source is unavailable')
    wrapper = runtime / source.name
    shutil.copyfile(source, wrapper)
    wrapper.chmod(0o600)
    if wrapper.read_bytes() != source.read_bytes():
        raise RuntimeError('R052 shutdown wrapper copy differs')
    argv = ['numactl', '--cpunodebind=0,1', '--interleave=all', str(gate.VENV / 'bin/python'), str(wrapper), *argv[1:]]
    recorded={key:env[key] for key in ENV_KEYS if key in env}
    (directory/'ENV.json').write_text(json.dumps(recorded,sort_keys=True)+'\n',encoding='utf-8')
    (directory/'ENV.txt').write_text(''.join(f'{key}={recorded[key]}\n' for key in sorted(recorded)),encoding='utf-8')
    (directory/'SERVE_CMD.txt').write_text(json.dumps({'argv':argv,'port':port},sort_keys=True)+'\n',encoding='utf-8')
    gate.write_new(directory / 'serve_argv.json', {'argv': argv, 'environment': recorded})
    (directory / 'serve.log').open('x',encoding='utf-8').close()
    if file_dry_run:
        return env,argv,[_probe(directory/name,'formal R052 service output') for name in ('owned_process.json','health.json','serve_args.txt','worker_shutdown.json')]
    return env,argv,None

def start_service(gate, directory, worktree, port):
    env,argv,_=prepare_service_files(gate,directory,worktree,port)
    lifecycle = gate.load_owned_lifecycle()
    with (directory / 'serve.log').open('a') as log:
        process = subprocess.Popen(argv, cwd=worktree, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    try:
        birth = lifecycle.process_identity(process.pid)
        if birth is None or birth.get('pgid') != process.pid or birth.get('session') != process.pid:
            raise RuntimeError('R052 service lacks a private owned process group')
        gate.write_new(directory / 'owned_process.json', {'pid': process.pid, 'birth': birth, 'port': port})
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('R052 service exited before readiness')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as response:
                    health=json.load(response)
                    if health.get('status') == 'ok':
                        gate.write_new(directory/'health.json',health)
                        parsed='\n'.join(line for line in (directory/'serve.log').read_text(encoding='utf-8',errors='replace').splitlines() if 'Parsed arguments' in line or 'ServerArgs(' in line)
                        if not parsed.strip(): raise RuntimeError('R052 service log lacks Parsed arguments')
                        (directory/'serve_args.txt').write_text(parsed+'\n',encoding='utf-8')
                        return process
            except (OSError, ValueError):
                pass
            time.sleep(2)
        raise TimeoutError('R052 service readiness timeout')
    except BaseException:
        try:
            lifecycle.stop_owned_process(process)
        except BaseException as error:
            error.owned_process = process
            error.owned_cleanup_failed = True
            raise
        raise

def dry_replay_outputs(directory):
    return [_probe(directory/f'replay_{index:02}.json','formal R052 replay output') for index in range(TARGET_INDEX+1)]+[_probe(directory/'followup_raw.json','formal R052 followup raw response'),_probe(directory/'result.json','formal R052 followup result'),_probe(directory/'d0_prefill.jsonl','formal D0 output'),_probe(directory/'d0_decode_steps.jsonl','formal D0 output'),_probe(directory/'d0_decode.json','formal D0 output')]


def d0_evidence(directory):
    worker_path = directory / 'worker_shutdown.json'
    worker = json.loads(worker_path.read_text())
    if worker.get('schema') != 'ft_r052_worker_shutdown/v1' or worker.get('status') != 'complete' or worker.get('scheduler_run_started') is not True or type(worker.get('pid')) is not int:
        raise RuntimeError('R052 model worker did not complete its D0 shutdown')
    snapshot = json.loads((directory / 'd0_decode.json').read_text())
    count = snapshot.get('anchor_snapshots_taken')
    if type(count) is not int or count < 0:
        raise RuntimeError('R052 lacks an actual D0 anchor snapshot count')
    matches = re.findall(r'D0 anchor_snapshots_taken=(\d+)', (directory / 'serve.log').read_text())
    if not matches or int(matches[-1]) != count:
        raise RuntimeError('R052 final log and D0 snapshot count disagree or are missing')
    paths = ['d0_prefill.jsonl', 'd0_decode_steps.jsonl', 'd0_decode.json', 'worker_shutdown.json']
    for name in paths:
        if not (directory / name).is_file() or not (directory / name).stat().st_size:
            raise RuntimeError(f'R052 missing D0 segment evidence: {name}')
    requests = {}
    expected_chunk = 0
    for line_no, line in enumerate((directory / 'd0_prefill.jsonl').read_text(encoding='utf-8').splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(f'R052 D0 prefill row {line_no} is invalid') from error
        if not isinstance(row, dict) or type(row.get('chunk')) is not int or row['chunk'] != expected_chunk or not isinstance(row.get('reqs'), list):
            raise RuntimeError(f'R052 D0 prefill row {line_no} lacks request evidence')
        expected_chunk += 1
        for req in row['reqs']:
            if not isinstance(req, dict) or type(req.get('rid')) is not int or type(req.get('new_tokens')) is not int or req['new_tokens'] < 0 or type(req.get('cached_tokens')) is not int or req['cached_tokens'] < 0:
                raise RuntimeError(f'R052 D0 prefill row {line_no} has invalid request evidence')
            requests.setdefault(req['rid'], []).append({'chunk': row['chunk'], 'new_tokens': req['new_tokens'], 'cached_tokens': req['cached_tokens']})
    return {'anchor_snapshots_taken': count, 'final_log_count': int(matches[-1]),
            'worker_shutdown': worker,
            'files': {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in paths},
            'prefill_requests': requests}


def confirm_cache_evidence(target, follow, d0):
    """Use final D0 admissions, never a missing API field or continuation record."""
    requests = d0.get('prefill_requests')
    if not isinstance(requests, dict):
        raise RuntimeError('R052 lacks final D0 admission evidence')
    if target.get('uid') == follow.get('uid'):
        raise RuntimeError('R052 target and follow-up share an SSE UID')
    for label, record in (('target', target), ('follow-up', follow)):
        uid = record.get('uid')
        if type(uid) is not int:
            raise RuntimeError(f'R052 {label} lacks actual SSE UID')
        rows = requests.get(uid)
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f'R052 {label} D0 admission evidence is missing')
        first, *continuations = rows
        if any(type(row.get('new_tokens')) is not int or row['new_tokens'] < 0 or type(row.get('cached_tokens')) is not int or row['cached_tokens'] != 0 for row in continuations):
            raise RuntimeError(f'R052 {label} D0 continuation cache evidence is invalid')
        actual = first.get('cached_tokens')
        total = actual + sum(row['new_tokens'] for row in rows) if type(actual) is int and type(first.get('new_tokens')) is int and first['new_tokens'] >= 0 else None
        if type(actual) is not int or actual < 0 or type(record.get('prompt_tokens')) is not int or record['prompt_tokens'] <= 0 or total != record['prompt_tokens']:
            raise RuntimeError(f'R052 {label} D0 prompt accounting differs')
        api_cached = record.get('api_cached_tokens', record.get('cached_tokens'))
        if api_cached is not None and api_cached != actual:
            raise RuntimeError(f'R052 {label} API and D0 cached_tokens differ')
        record['api_cached_tokens'] = api_cached
        record['cached_tokens'] = actual
        record['d0_admission_cached_tokens'] = actual
    return {'target_cached_tokens': target['cached_tokens'], 'followup_cached_tokens': follow['cached_tokens']}
