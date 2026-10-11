"""Actual loopback SSE through official R065/OpenAI SDK producer-consumer path."""
import hashlib, importlib.util, json, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pytest
import sdk_adapter as sdk
HERE = Path(__file__).resolve().parent

@pytest.fixture
def loopback(monkeypatch):
    state = {'calls': [], 'mode': 'ok', 'cached': None}
    items = sdk.inputs(); marker = {'alpha': items['alpha']['marker'], 'beta': items['beta']['marker']}
    monkeypatch.setattr(sdk, 'B_BODY_SHA', hashlib.sha256(b'B body').hexdigest())
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers['Content-Length']))); assert self.path == '/v1/completions'
            with lock: index = len(state['calls']); state['calls'].append(req)
            key = next(k for k, v in items.items() if v['prompt'] == req['prompt']); text = 'B body' if key == 'long' else 'short'
            if key in marker: text = marker[key]
            if state['mode'] == 'bad_b': text = 'wrong body'
            if state['mode'] == 'c_text' and key == 'long': text = 'C differs only observationally'
            if state['mode'] == 'wrong_marker' and key == 'alpha': text = marker['beta']
            if state['mode'] == 'malformed' and key == 'alpha': text += '\ufffd'
            if state['mode'] == 'http_error': self.send_error(503); return
            usage = {'prompt_tokens': items[key]['prompt_tokens'], 'completion_tokens': req['max_tokens'], 'total_tokens': items[key]['prompt_tokens'] + req['max_tokens']}
            if state['mode'] == 'c_usage' and key == 'long': usage['completion_tokens'] -= 1; usage['total_tokens'] -= 1
            if state['cached'] is not None: usage['prompt_tokens_details'] = {'cached_tokens': state['cached']}
            chunks = [{'id': f'c{index}', 'object': 'text_completion', 'created': 0, 'model': 'fixture', 'choices': [{'index': 0, 'text': text, 'finish_reason': None}], 'usage': None}, {'id': f'c{index}', 'object': 'text_completion', 'created': 0, 'model': 'fixture', 'choices': [{'index': 0, 'text': '', 'finish_reason': 'length'}], 'usage': None}, {'id': f'c{index}', 'object': 'text_completion', 'created': 0, 'model': 'fixture', 'choices': [], 'usage': usage}]
            body = (''.join('data: ' + json.dumps(x) + '\n\n' for x in chunks) + 'data: [DONE]\n\n').encode(); time.sleep(.04)
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    lock = threading.Lock(); server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}', state
    finally: server.shutdown(); thread.join(3); server.server_close()

def run(base, out):
    (out/'B').mkdir(); sdk.run_service(base, 'fixture', 'B', out)
    (out/'C').mkdir(); sdk.run_service(base, 'fixture', 'C', out)

def test_five_call_positive_contract(loopback, tmp_path):
    base, state = loopback; run(base, tmp_path)
    result = json.loads((tmp_path/'criteria_result.json').read_text())
    assert result['handoff_ready'] and result['scope'] == {'services': 2, 'calls': 5} and len(state['calls']) == 5
    assert [x['max_tokens'] for x in state['calls']] == [128, 128, 128, 64, 64]
    for req in state['calls']: assert req['temperature'] == 0 and req['top_p'] == 1 and req['ignore_eos'] is True
    assert json.loads((tmp_path/'B/calls/cached_tokens_observation.json').read_text()) == {'status': 'missing', 'value': None, 'fallback_used': False}

@pytest.mark.parametrize('mode,calls,verdict', [('bad_b', 1, 'not_met'), ('http_error', 1, 'failed_harness')])
def test_b_early_stop_and_classification(loopback, tmp_path, mode, calls, verdict):
    base, state = loopback; state['mode'] = mode
    (tmp_path/'B').mkdir()
    with pytest.raises(Exception): sdk.run_service(base, 'fixture', 'B', tmp_path)
    result = json.loads((tmp_path/'criteria_result.json').read_text()); assert result['proposed_verdict'] == verdict and len(state['calls']) == calls

@pytest.mark.parametrize('mode', ['wrong_marker', 'malformed'])
def test_c_marker_failure_is_not_met_after_b(loopback, tmp_path, mode):
    base, state = loopback; (tmp_path/'B').mkdir(); sdk.run_service(base, 'fixture', 'B', tmp_path)
    state['mode'] = mode; (tmp_path/'C').mkdir()
    with pytest.raises(ValueError): sdk.run_service(base, 'fixture', 'C', tmp_path)
    result = json.loads((tmp_path/'criteria_result.json').read_text())
    assert result['proposed_verdict'] == 'not_met' and result['service'] == 'C' and len(state['calls']) == 5

def test_c_text_difference_is_observation_and_cached_is_not_filled(loopback, tmp_path):
    base, state = loopback; state['cached'] = 7; (tmp_path/'B').mkdir(); sdk.run_service(base, 'fixture', 'B', tmp_path)
    state['mode'] = 'c_text'; (tmp_path/'C').mkdir(); sdk.run_service(base, 'fixture', 'C', tmp_path)
    result = json.loads((tmp_path/'criteria_result.json').read_text())
    assert result['handoff_ready'] and result['c_long_body_matches_B_observation'] is False
    assert json.loads((tmp_path/'B/calls/cached_tokens_observation.json').read_text())['value'] == 7

def test_c_usage_difference_is_not_met(loopback, tmp_path):
    base, state = loopback; (tmp_path/'B').mkdir(); sdk.run_service(base, 'fixture', 'B', tmp_path)
    state['mode'] = 'c_usage'; (tmp_path/'C').mkdir()
    with pytest.raises(ValueError): sdk.run_service(base, 'fixture', 'C', tmp_path)
    assert json.loads((tmp_path/'criteria_result.json').read_text())['proposed_verdict'] == 'not_met'

def test_marker_and_unicode_checks():
    sdk.discriminate('“OWN” 正常中文\n', 'OWN', 'OTHER')
    for bad in ('OWN\ufffd', 'OWN\x00', 'OTHER', 'nothing'):
        with pytest.raises(ValueError): sdk.discriminate(bad, 'OWN', 'OTHER')

def test_constants_are_authorized():
    assert sdk.B_BODY_SHA == '9845c3860e326f437ad9fa6759c0c7e1bcca71a4ce3a37b702c5a76c9dd1cf4c'
    assert sdk.D_BODY_SHA == 'ddb0e282943654ab3d6a72d83d55276ab66c7377e7d138127df48246032bc4e9'

def test_d_hash_contract_uses_one_call(loopback, tmp_path, monkeypatch):
    base, state = loopback
    monkeypatch.setattr(sdk, 'D_BODY_SHA', hashlib.sha256(b'B body').hexdigest())
    (tmp_path/'D').mkdir(); sdk.run_service(base, 'fixture', 'D', tmp_path, d_enabled=True)
    assert len(state['calls']) == 1 and state['calls'][0]['max_tokens'] == 128

@pytest.mark.skipif(not Path('/data2/FreeToken/wt/e2oom-protocol-restart/python/freetoken/scheduler/dev_prefill_schedule.py').is_file(), reason='target candidate CPU-only geometry check')
def test_existing_d_geometry_parse_admit_and_rejection():
    source = Path('/data2/FreeToken/wt/e2oom-protocol-restart/python/freetoken/scheduler/dev_prefill_schedule.py')
    name = 'r066_cpu_schedule'; spec = importlib.util.spec_from_file_location(name, source); module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    schedule = module.parse((HERE/'d_existing_schedule.json').read_text())
    module.admit(schedule, prompt_len=8257, cached_len=0, device_len=8257, request_count=1, first_generation=True, has_multimodal=False, disk_ple=False, rewind_alignment=64, fla_chunk_size=64)
    bad = json.loads((HERE/'d_existing_schedule.json').read_text()); bad[1]['start'] = 8255
    with pytest.raises(ValueError):
        module.admit(module.parse(json.dumps(bad)), prompt_len=8257, cached_len=0, device_len=8257, request_count=1, first_generation=True, has_multimodal=False, disk_ple=False, rewind_alignment=64, fla_chunk_size=64)

@pytest.mark.skipif(not Path('/data2/FreeToken/development/r066_d16_discriminate_v2/r066_runner.py').is_file(), reason='remote child-entry check')
def test_child_argv_is_bound_to_r066_admission_consumer():
    source = Path('/data2/FreeToken/development/r066_d16_discriminate_v2/r066_runner.py')
    name = 'r066_cpu_runner'; spec = importlib.util.spec_from_file_location(name, source); module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    argv = module.child_argv(64, Path('/tmp/r066-receipt'), Path('/tmp/r066-admission'))
    assert argv[1] == str(source) and argv[2:4] == ['--run', '--owned-child'] and '--admission' in argv
