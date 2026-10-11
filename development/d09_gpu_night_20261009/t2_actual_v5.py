"""Replay the frozen T2 protocol on one root-owned, freshly started D09 service."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
import urllib.request

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'd09_prediction_20261009'
FROZEN = HERE / 'agent_trace_remote_frozen.py'
RID = 'E2-D09-T2-actual-v5'
CANDIDATE = 'c17b69a46cd512fbf3d127d3879bce92caae457b'
EXPECTED = {
    'source/trace.json': '055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899',
    'source/trace_rev.json': '097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24',
    'source/C_coldfirst.json': '9ac71421f2b23629f7610d9736e9855088550c5d1bc60cd272752279ee93d62f',
    'source/C_warm.json': 'b6d01815d140c5da45b9bad1bdbf0c10c83a7c6bcce1b4dcbfa4799954b0918e',
    'source/C_edit.json': 'ca3e317837035bcf3607c571d5abc5a06e6a29bed96c025e7a15f37c341690f9',
    'PREDICTION_MANIFEST_v4.json': 'edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    with Path(path).open('x') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def prepare():
    assert sha(FROZEN) == '423feeb37bead3cacd2b066dc142a00cfb814f713ee1fcd766a456f64ce2cf17'
    for name, digest in EXPECTED.items():
        assert sha(SOURCE / name) == digest, name
    spec = importlib.util.spec_from_file_location('d09_t2_original_protocol', FROZEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.REPLAY_MAX_TOKENS == 32, 'replay token budget polluted by environment'
    normal = json.loads((SOURCE / 'source/trace.json').read_text())
    reverse = json.loads((SOURCE / 'source/trace_rev.json').read_text())
    assert [r['messages'] for r in reverse['rounds']] == [r['messages'] for r in reversed(normal['rounds'])]
    plan = []
    for mode, trace, refname in (
        ('reverse_cold', reverse, 'C_coldfirst.json'),
        ('ascending_warm', normal, 'C_warm.json'),
        ('edit', normal, 'C_edit.json'),
    ):
        reference = json.loads((SOURCE / 'source' / refname).read_text())
        params = reference['meta']['params']
        assert params['max_tokens'] == 32 and len(trace['rounds']) == len(reference['rounds']) == 12
        for index, (row, ref) in enumerate(zip(trace['rounds'], reference['rounds'])):
            messages = copy.deepcopy(row['messages'])
            applied, note = module.apply_edit(messages, params['edit_at_idx'], module.DEFAULT_EDIT_TEXT)
            assert bool(applied) == bool(ref['edit_applied']), (mode, index, 'edit state')
            assert module.messages_digest(messages) == ref['messages_sha'], (mode, index, 'messages')
            payload = module.build_payload(messages, params['model'], trace.get('tools') or module.tool_specs(), params['thinking'], 32)
            plan.append({'mode': mode, 'round': index, 'payload': payload,
                         'payload_sha256': hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                         'messages_sha': ref['messages_sha'], 'edit_applied': applied, 'edit_note': note})
    assert len(plan) == 36
    bindings = {str(SOURCE / name): digest for name, digest in EXPECTED.items()}
    bindings.update({str(FROZEN): sha(FROZEN), str(Path(__file__).resolve()): sha(__file__)})
    return module, plan, bindings


def stream(module, opener, url, payload, clock, raw):
    started = clock()
    done = False

    def events():
        nonlocal done
        request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with opener.open(request, timeout=1800) as response:
            for line in response:
                text = line.decode(errors='strict')
                raw.append({'at_s': clock() - started, 'line': text})
                if not text.startswith('data:'):
                    continue
                data = text[5:].strip()
                if data == '[DONE]':
                    done = True
                    return
                yield json.loads(data)
    result = module.consume_stream(events(), started)
    result['elapsed_s'] = clock() - started
    result['done_received'] = done
    return result


def identity_matches(expected):
    try:
        fields = Path('/proc/' + str(expected['pid']) + '/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] != 'Z' and int(fields[19]) == expected['start_ticks']
    except (FileNotFoundError, ProcessLookupError):
        return False


def check_admission(admission, bindings):
    assert admission['root_approved'] is True and admission['rid'] == RID
    assert admission['bindings'] == bindings
    assert admission['max_tokens'] == 32 and admission['generation_calls_max'] == 36
    parsed = urlsplit(admission['endpoint'])
    assert parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port
    assert parsed.path in ('', '/') and not parsed.query and not parsed.fragment and not parsed.username
    path = Path(admission['owner_file'])
    assert sha(path) == admission['owner_sha256']
    owner = json.loads(path.read_text())
    assert owner['candidate_commit'] == CANDIDATE
    assert owner['pid_identity'] == admission['service_identity'] and identity_matches(owner['pid_identity'])
    argv = owner['argv']
    assert int(argv[argv.index('--port') + 1]) == parsed.port
    assert '--enable-message-boundary-ckpt' in argv
    log = Path(admission['service_log'])
    assert log.is_file() and log.parent.resolve() == path.parent.resolve()
    return log


def execute(module, plan, opener, endpoint, log, out, clock=time.perf_counter):
    out.mkdir(parents=True, exist_ok=False)
    predictions = {row['round']: row for row in json.loads((SOURCE / 'PREDICTION_MANIFEST_v4.json').read_text())['eligible_predictions']}
    results = []
    attempted = 0
    error = None
    try:
        for item in plan:
            attempted += 1
            stem = item['mode'] + '_' + str(item['round']).zfill(2)
            put(out / (stem + '.request.json'), item)
            offset = log.stat().st_size
            raw = []
            try:
                measured = stream(module, opener, endpoint.rstrip('/') + '/v1/chat/completions', item['payload'], clock, raw)
            finally:
                put(out / (stem + '.sse.json'), raw)
                with log.open('rb') as handle:
                    handle.seek(offset)
                    (out / (stem + '.serve-window.txt')).write_bytes(handle.read())
            prompt, cached, completion = module.usage_counts(measured['usage'])
            assert measured['done_received'] and measured['ttft_any_s'] is not None
            assert prompt > 0 and 0 <= cached <= prompt and 0 < completion <= 32, 'missing or invalid usage'
            record = {'mode': item['mode'], 'round': item['round'], 'messages_sha': item['messages_sha'],
                      'edit_applied': item['edit_applied'], 'ttft_any_s': measured['ttft_any_s'],
                      'elapsed_s': measured['elapsed_s'], 'prompt_tokens': prompt, 'cached_tokens': cached,
                      'completion_tokens': completion, 'cold_geometry_observed': cached == 0 if item['mode'] == 'reverse_cold' else None,
                      'result': measured}
            if item['mode'] == 'edit' and item['round'] in predictions:
                prediction = predictions[item['round']]
                record['prediction'] = prediction
                record['residual_s'] = measured['ttft_any_s'] - prediction['predicted_ttft_any_s_target']
            put(out / (stem + '.result.json'), record)
            results.append(record)
    except BaseException as exc:
        error = repr(exc)
    put(out / 'terminal.json', {'rid': RID, 'at': time.time(), 'generation_calls_attempted': attempted,
                               'completed': len(results), 'error': error,
                               'verdict': 'failed_harness' if error else 'measured_pending_independent_review',
                               'cold_geometry_violations': [row['round'] for row in results if row['cold_geometry_observed'] is False],
                               'product_acceptance': False, 'service_owned_and_cleaned_by_parent': True})
    if error:
        raise RuntimeError(error)
    return results


def file_dry(module, plan, bindings):
    timer = SimpleNamespace(now=0.0)
    clock = lambda: timer.now
    module.time = SimpleNamespace(perf_counter=clock)
    with tempfile.TemporaryDirectory(prefix='d09_t2_v5_') as temporary:
        root = Path(temporary)
        log = root / 'serve.log'
        log.write_bytes('旧日志中文\n'.encode())
        calls = []

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def __iter__(self):
                for delay, line in ((.125, b'data: {"choices":[{"delta":{"reasoning_content":"first"}}]}\n'),
                                    (.625, b'data: {"choices":[{"delta":{},"finish_reason":"length"}],"usage":{"prompt_tokens":100,"completion_tokens":32,"prompt_tokens_details":{"cached_tokens":0}}}\n'),
                                    (.25, b'data: [DONE]\n')):
                    timer.now += delay
                    with log.open('ab') as handle:
                        handle.write('新日志中文\n'.encode())
                    yield line
        class Opener:
            def open(self, request, timeout):
                payload = json.loads(request.data)
                assert payload == plan[len(calls)]['payload']
                calls.append(payload)
                return Response()
        results = execute(module, plan, Opener(), 'http://127.0.0.1:1', log, root / 'results', clock)
        assert len(calls) == len(results) == 36
        assert all(row['ttft_any_s'] == .125 and row['elapsed_s'] == 1 for row in results)
        assert len([row for row in results if 'prediction' in row]) == 2
        assert sum(bool(row['edit_applied']) for row in results) == 7
        for path in (root / 'results').glob('*.serve-window.txt'):
            assert path.read_text() == '新日志中文\n' * 3
        return {'rid': RID, 'bindings': bindings, 'actual_mock_calls': 36, 'max_tokens': 32,
                'first_delta_s': .125, 'stream_complete_s': 1, 'edit_applied_rounds': 7,
                'only_registered_edit_predictions': 2, 'binary_log_offsets_valid': True,
                'gpu_http_service_actions': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--filedry', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--admission', type=Path)
    args = parser.parse_args()
    module, plan, bindings = prepare()
    if args.filedry and not args.run:
        print(json.dumps(file_dry(module, plan, bindings), indent=2))
    elif args.run and args.admission and not args.filedry:
        admission = json.loads(args.admission.read_text())
        log = check_admission(admission, bindings)
        execute(module, plan, urllib.request.build_opener(urllib.request.ProxyHandler({})), admission['endpoint'], log, Path(admission['output_dir']))
    else:
        parser.error('select --filedry or --run --admission')
