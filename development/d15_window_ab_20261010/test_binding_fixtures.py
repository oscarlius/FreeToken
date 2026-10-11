"""Exercise the actual ordinary binder and spawn target without a model/GPU."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.removesuffix('.py'), HERE / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request_receipts(tmp_path):
    payload = tmp_path / 'payload.json'
    payload.write_text(json.dumps({'stream': True, 'stream_options': {'include_usage': True},
                                  'messages': [{'role': 'user', 'content': 'test'}]}))
    raw = tmp_path / 'api.sse'
    events = [
        {'id': 'chatcmpl-7', 'choices': [{'delta': {'content': 'ok'}, 'finish_reason': None}]},
        {'id': 'chatcmpl-7', 'choices': [{'delta': {}, 'finish_reason': 'stop'}],
         'usage': {'prompt_tokens': 2, 'completion_tokens': 2}},
    ]
    raw.write_bytes((''.join('data: ' + json.dumps(e) + '\n\n' for e in events)
                     + 'data: [DONE]\n\n').encode())
    api = tmp_path / 'api.json'
    clocks = tmp_path / 'api.events.jsonl'
    clock_rows = [{'monotonic_ns': mono, 'time_ns': wall, 'event': event}
                  for event, mono, wall in zip(events, (110, 1_000_000_110), (1000, 2000))]
    clocks.write_text(''.join(json.dumps(row)+'\n' for row in clock_rows))
    api.write_text(json.dumps({'schema': 'ft_r049_ordinary_sse_stream/v1', 'pause_enabled': False,
                              'payload_source': {'path': str(payload), 'sha256': digest(payload)},
                              'sse': str(raw), 'sse_sha256': digest(raw), 'uid': 7,
                              'usage': events[-1]['usage'], 'finish_reason': 'stop',
                              'events': str(clocks), 'events_sha256': digest(clocks),
                              'dispatch_monotonic_ns': 100,
                              'first_output_event': {'monotonic_ns': 110, 'time_ns': 1000},
                              'terminal_event': {'monotonic_ns': 1_000_000_110, 'time_ns': 2000}}))
    service = {'pid': 1, 'start_ticks': 13, 'execution_id': '1:13', 'pgid': 1, 'session': 1}
    worker = {'pid': 2, 'start_ticks': 14, 'execution_id': '2:14', 'pgid': 1, 'session': 1}
    ids = tmp_path / 'ids.json'
    ids.write_bytes(b'[10,11]')
    inputs = tmp_path / 'inputs.jsonl'
    inputs.write_text(json.dumps({'schema': 'ft_t06_ordinary_input/v3', 'uid': 7, 'input_tokens': 2,
                                 'canonical_encoding': 'utf8-json-int-array-separators=,:',
                                 'input_ids_path': str(ids), 'input_ids_sha256': digest(ids),
                                 'input_ids_file_sha256': digest(ids),
                                 'source': 'Scheduler._process_one_msg(UserMsg)', 'time_ns': 10,
                                 'service_birth': service, 'worker_birth': worker}) + '\n')
    tokens = tmp_path / 'tokens.jsonl'
    token_rows = [{'schema': 'ft_t06_ordinary_token/v3', 'uid': 7, 'request_seq': n,
                   'completion_tokens_delta': 1, 'completion_tokens_cumulative': n,
                   'next_token': 20 + n, 'finished': n == 2,
                   'finish_reason': 'stop' if n == 2 else None, 'time_ns': 10 + n,
                   'service_birth': service, 'worker_birth': worker} for n in (1, 2)]
    tokens.write_text(''.join(json.dumps(row) + '\n' for row in token_rows))
    return payload, api, inputs, tokens, ids, raw


