"""T21 worker-bound ordinary requests, with no route/D0/ACK claims."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCHEMA = 'ft_r049_t21_ordinary_binding/v4'
HERE = Path(__file__).resolve().parent

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module

def _v4():
    return _load('r049_t06_v6', HERE / 'r046e_t06_ordinary_client_v6.py')

def ordinary_request(base_url, input_path, output, timeout=1800):
    adapter = _load('r049_stream_capture', HERE / 'r049_t21_ordinary_adapter_v4.py')
    return adapter.ordinary_stream_request(base_url, input_path, output, timeout)

def bind(payload, api_path, _d0, _route, input_sidecar, token_sidecar, output):
    """Reuse validated input/token seams without invoking route/D0 readers."""
    payload, api_path = Path(payload), Path(api_path)
    input_sidecar, token_sidecar, output = map(Path, (input_sidecar, token_sidecar, output))
    client = _v4()
    api = json.loads(api_path.read_text(encoding='utf-8'))
    origin = api.get('payload_source')
    if (api.get('schema') != 'ft_r049_ordinary_sse_stream/v1'
            or api.get('pause_enabled') is not False or not isinstance(origin, dict)
            or origin.get('path') != str(payload) or origin.get('sha256') != client.sha256(payload)):
        raise ValueError('T21 payload source binding differs')
    raw = Path(api.get('sse', ''))
    if raw.is_symlink() or not raw.is_file() or api.get('sse_sha256') != client.sha256(raw):
        raise ValueError('T21 raw SSE binding differs')
    uid, usage, finish = client._v2().parse_sse(raw.read_bytes())
    if api.get('uid') != uid or api.get('usage') != usage or api.get('finish_reason') != finish:
        raise ValueError('T21 API record differs from raw SSE')
    clocks = Path(api.get('events', ''))
    if clocks.is_symlink() or not clocks.is_file() or api.get('events_sha256') != client.sha256(clocks):
        raise ValueError('T21 stream event-clock source differs')
    observed = [json.loads(line) for line in clocks.read_text(encoding='utf-8').splitlines()]
    stream = [json.loads(line[5:].strip()) for line in raw.read_text(encoding='utf-8').splitlines()
              if line.startswith('data:') and line[5:].strip() != '[DONE]']
    if not observed or [row.get('event') for row in observed] != stream:
        raise ValueError('T21 stream clocks do not bind raw events')
    previous = api.get('dispatch_monotonic_ns')
    if type(previous) is not int or previous <= 0:
        raise ValueError('T21 stream dispatch clock differs')
    first = terminal = None
    adapter = _load('r049_clock_validator', HERE / 'r049_t21_ordinary_adapter_v4.py')
    for row in observed:
        mono, wall = row.get('monotonic_ns'), row.get('time_ns')
        if type(mono) is not int or mono < previous or type(wall) is not int or wall <= 0:
            raise ValueError('T21 stream event clock order differs')
        previous = mono
        event = row['event']
        if first is None and adapter._first_real(event):
            first = {'monotonic_ns': mono, 'time_ns': wall}
        if any(choice.get('finish_reason') is not None for choice in event.get('choices') or []):
            if terminal is not None:
                raise ValueError('T21 stream has multiple terminal events')
            terminal = {'monotonic_ns': mono, 'time_ns': wall}
    if api.get('first_output_event') != first or api.get('terminal_event') != terminal:
        raise ValueError('T21 first-output/terminal clocks disagree with raw events')
    tokens, terminal_binding = client._tokens_for_uid(token_sidecar, uid, usage['completion_tokens'], finish)
    actual = client._input_for_uid(input_sidecar, uid, tokens[0]['service_birth'], tokens[0]['worker_birth'])
    client._require_input_before_tokens(actual, tokens)
    if actual['input_tokens'] != usage['prompt_tokens']:
        raise ValueError('T21 worker input length disagrees with API prompt_tokens')
    details = usage.get('prompt_tokens_details')
    cached = details.get('cached_tokens') if isinstance(details, dict) else None
    if cached is not None and (type(cached) is not int or cached < 0):
        raise ValueError('T21 reported cached_tokens is invalid')
    value = {
        'schema': SCHEMA, 'verdict': 'worker_input_uid_token_bound', 'uid': uid,
        'payload_source': origin,
        'worker_input': {'path': str(input_sidecar), 'sha256': client.sha256(input_sidecar), **actual},
        'api': {**api, 'path': str(api_path), 'sha256': client.sha256(api_path)},
        'token_sidecar': {'path': str(token_sidecar), 'sha256': client.sha256(token_sidecar), 'events': tokens},
        'event_clocks': {'path': str(clocks), 'sha256': client.sha256(clocks)},
        'route': None, 'd0': None, 'cached_tokens': cached, 'terminal_binding': terminal_binding,
        'cached_tokens_independently_verified': False, 'transport': 'ordinary_sse_no_ft_dev_ack',
    }
    client.write_new(output, value)
    return value
